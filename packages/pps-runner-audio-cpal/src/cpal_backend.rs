use std::{
    sync::Arc,
    time::{Duration, Instant},
};

use pps_runner_audio::{OutputFence, PreparedPlaybackPlan, RenderControl};

use cpal::{
    traits::{DeviceTrait, HostTrait, StreamTrait},
    BufferSize, SampleFormat, StreamConfig, SupportedBufferSize,
};

use crate::{
    contract::{OutputBufferSelection, OutputBufferSupport, OutputFaultKind},
    playback::PlaybackOwner,
    service::{
        BackendConfig, BackendDevice, BackendEnumeration, BackendFailure, CallbackSignals,
        OutputBackend, SelectionKey,
    },
    NativePlaybackRecord, OutputServiceErrorCode, PlaybackCancellation, PlaybackControlReceipt,
    PlaybackStatus, MAXIMUM_F32_CONFIGS_PER_DEVICE, MAXIMUM_OUTPUT_CHANNELS,
    MAXIMUM_OUTPUT_DEVICES,
};

const MAXIMUM_SCANNED_OUTPUT_DEVICES: usize = 128;
const MAXIMUM_SCANNED_CONFIG_RANGES_PER_DEVICE: usize = 256;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct CpalSelectionKey {
    device_index: usize,
    config_index: usize,
}

impl SelectionKey for CpalSelectionKey {}

struct RetainedCpalDevice {
    device: cpal::Device,
    configs: Vec<cpal::SupportedStreamConfigRange>,
}

pub(crate) struct CpalBackend {
    host: cpal::Host,
    devices: Vec<RetainedCpalDevice>,
    stream: Option<cpal::Stream>,
    selection: Option<(CpalSelectionKey, crate::ExactOutputSelection)>,
    playback: Option<PlaybackOwner>,
}

impl CpalBackend {
    pub(crate) fn open() -> Result<Self, BackendFailure> {
        Ok(Self {
            host: cpal::default_host(),
            devices: Vec::new(),
            stream: None,
            selection: None,
            playback: None,
        })
    }
}

impl OutputBackend for CpalBackend {
    type Key = CpalSelectionKey;

    fn enumerate(&mut self) -> Result<BackendEnumeration<Self::Key>, BackendFailure> {
        self.devices.clear();
        let devices = self.host.output_devices().map_err(|_| {
            BackendFailure::new(
                OutputFaultKind::EnumerationFailed,
                OutputServiceErrorCode::EnumerationFailed,
                "Native output-device enumeration failed.",
            )
        })?;

        let mut public_devices = Vec::new();
        let mut devices_truncated = false;
        for (scanned_device_index, device) in devices.enumerate() {
            if scanned_device_index >= MAXIMUM_SCANNED_OUTPUT_DEVICES {
                devices_truncated = true;
                break;
            }
            let display_name = device.to_string();
            let supported = match device.supported_output_configs() {
                Ok(configs) => configs,
                Err(_) => continue,
            };
            let mut retained_configs = Vec::new();
            let mut public_configs = Vec::new();
            let mut configs_truncated = false;
            for (scanned_config_index, range) in supported.enumerate() {
                if scanned_config_index >= MAXIMUM_SCANNED_CONFIG_RANGES_PER_DEVICE {
                    configs_truncated = true;
                    break;
                }
                if range.sample_format() != SampleFormat::F32 {
                    continue;
                }
                if range.channels() == 0 || range.channels() > MAXIMUM_OUTPUT_CHANNELS {
                    continue;
                }
                if retained_configs.len() >= MAXIMUM_F32_CONFIGS_PER_DEVICE {
                    configs_truncated = true;
                    break;
                }
                let config_index = retained_configs.len();
                public_configs.push(BackendConfig {
                    key: CpalSelectionKey {
                        device_index: self.devices.len(),
                        config_index,
                    },
                    channels: range.channels(),
                    minimum_sample_rate_hz: range.min_sample_rate(),
                    maximum_sample_rate_hz: range.max_sample_rate(),
                    buffer_support: supported_buffer(*range.buffer_size()),
                });
                retained_configs.push(range);
            }
            if public_configs.is_empty() {
                continue;
            }
            if self.devices.len() >= MAXIMUM_OUTPUT_DEVICES {
                devices_truncated = true;
                break;
            }
            public_devices.push(BackendDevice {
                display_name,
                configs: public_configs,
                configs_truncated,
            });
            self.devices.push(RetainedCpalDevice {
                device,
                configs: retained_configs,
            });
        }
        Ok(BackendEnumeration {
            devices: public_devices,
            devices_truncated,
        })
    }

    fn create_silence(
        &mut self,
        key: &Self::Key,
        selection: &crate::ExactOutputSelection,
        signals: Arc<CallbackSignals>,
        backend_timeout: Duration,
    ) -> Result<(), BackendFailure> {
        let retained = self
            .devices
            .get(key.device_index)
            .ok_or_else(BackendFailure::contract)?;
        let range = retained
            .configs
            .get(key.config_index)
            .ok_or_else(BackendFailure::contract)?;
        if range.sample_format() != SampleFormat::F32
            || range.channels() != selection.channels()
            || !range.contains_rate(selection.sample_rate_hz())
        {
            return Err(BackendFailure::contract());
        }
        let buffer_size = match selection.buffer() {
            OutputBufferSelection::Default => BufferSize::Default,
            OutputBufferSelection::Fixed(frames) => BufferSize::Fixed(frames),
        };
        let config = StreamConfig {
            channels: selection.channels(),
            sample_rate: selection.sample_rate_hz(),
            buffer_size,
        };
        let callback_signals = Arc::clone(&signals);
        let error_signals = signals;
        let callback_channels = selection.channels();
        if self.stream.is_some() {
            return Err(BackendFailure::contract());
        }
        let stream = retained
            .device
            .build_output_stream_raw(
                config,
                SampleFormat::F32,
                move |data, _| {
                    let exact_f32 = data.sample_format() == SampleFormat::F32;
                    let sample_count = data.len();
                    if !crate::service::raw_callback_shape_is_bounded(
                        exact_f32,
                        callback_channels,
                        sample_count,
                    ) {
                        callback_signals.record_callback_fault();
                        return;
                    }
                    callback_signals.write_raw_silence(
                        exact_f32,
                        callback_channels,
                        sample_count,
                        data.bytes_mut(),
                    );
                },
                move |_| error_signals.record_callback_fault(),
                Some(backend_timeout),
            )
            .map_err(|_| {
                BackendFailure::new(
                    OutputFaultKind::StreamBuildFailed,
                    OutputServiceErrorCode::StreamBuildFailed,
                    "The native silence stream could not be created.",
                )
            })?;
        self.stream = Some(stream);
        self.selection = Some((*key, selection.clone()));
        Ok(())
    }

    fn play_silence(&mut self) -> Result<(), BackendFailure> {
        self.stream
            .as_ref()
            .ok_or_else(BackendFailure::contract)?
            .play()
            .map_err(|_| {
                BackendFailure::new(
                    OutputFaultKind::StreamPlayFailed,
                    OutputServiceErrorCode::StreamPlayFailed,
                    "The native silence stream could not be started.",
                )
            })
    }

    fn release(&mut self) -> Result<(), BackendFailure> {
        self.stream = None;
        if self
            .playback
            .as_ref()
            .is_some_and(|playback| !playback.status().callback_retired)
        {
            return Err(BackendFailure::new(
                OutputFaultKind::StreamReleaseFailed,
                OutputServiceErrorCode::StreamReleaseFailed,
                "The native playback callback has not retired.",
            ));
        }
        self.playback = None;
        self.selection = None;
        Ok(())
    }

    fn prepare_playback(
        &mut self,
        plan: Arc<PreparedPlaybackPlan>,
        signals: Arc<CallbackSignals>,
    ) -> Result<PlaybackStatus, BackendFailure> {
        let (key, selection) = self
            .selection
            .clone()
            .ok_or_else(BackendFailure::contract)?;
        if self.playback.is_some() {
            return Err(BackendFailure::new(
                OutputFaultKind::BackendContractViolation,
                OutputServiceErrorCode::AlreadyReserved,
                "Release prepared playback before binding a different plan.",
            ));
        }
        if plan.route().output_channels() != selection.channels()
            || plan.media().sample_rate_hz() != selection.sample_rate_hz()
        {
            return Err(BackendFailure::new(
                OutputFaultKind::BackendContractViolation,
                OutputServiceErrorCode::ExactConfigMismatch,
                "Prepared media must match the exact reserved output rate and channel route.",
            ));
        }
        self.release()?;
        let device = &self
            .devices
            .get(key.device_index)
            .ok_or_else(BackendFailure::contract)?
            .device;
        let config = StreamConfig {
            channels: selection.channels(),
            sample_rate: selection.sample_rate_hz(),
            buffer_size: match selection.buffer() {
                OutputBufferSelection::Default => BufferSize::Default,
                OutputBufferSelection::Fixed(frames) => BufferSize::Fixed(frames),
            },
        };
        let (owner, mut callback) = PlaybackOwner::new(plan);
        let callback_signals = Arc::clone(&signals);
        let stream = device.build_output_stream(
            config,
            move |samples: &mut [f32], info: &cpal::OutputCallbackInfo| {
                let observed_at = Instant::now();
                if callback.render(samples, observed_at, Some(info.timestamp())) {
                    callback_signals.record_callback_fault();
                }
                callback_signals.record_callback();
            },
            move |_| signals.record_callback_fault(),
            Some(Duration::from_secs(2)),
        );
        // Retain the plan and queue storage even if a driver returns an error.
        // Stream retirement is checked before the owner releases these values.
        self.playback = Some(owner);
        self.selection = Some((key, selection));
        self.stream = Some(stream.map_err(|_| {
            BackendFailure::new(
                OutputFaultKind::StreamBuildFailed,
                OutputServiceErrorCode::StreamBuildFailed,
                "The native prepared-media stream could not be created.",
            )
        })?);
        self.play_silence()?;
        self.playback_status().ok_or_else(BackendFailure::contract)
    }

    fn playback_status(&self) -> Option<PlaybackStatus> {
        self.playback.as_ref().map(PlaybackOwner::status)
    }

    fn playback_control(
        &mut self,
        fence: &OutputFence,
        control: RenderControl,
    ) -> Result<PlaybackControlReceipt, BackendFailure> {
        self.playback
            .as_mut()
            .ok_or_else(BackendFailure::contract)?
            .control(fence, control)
            .map_err(|error| {
                BackendFailure::new(
                    OutputFaultKind::BackendContractViolation,
                    match error {
                        crate::PlaybackControlError::Busy => OutputServiceErrorCode::QueueFull,
                        crate::PlaybackControlError::SequenceExhausted => {
                            OutputServiceErrorCode::GenerationExhausted
                        }
                        _ => OutputServiceErrorCode::StaleReservation,
                    },
                    "The native playback control was not admitted.",
                )
            })
    }

    fn playback_cancellation(
        &self,
        fence: &OutputFence,
    ) -> Result<PlaybackCancellation, BackendFailure> {
        let playback = self
            .playback
            .as_ref()
            .ok_or_else(BackendFailure::contract)?;
        if playback.fence() != fence {
            return Err(BackendFailure::contract());
        }
        Ok(playback.cancellation())
    }

    fn drain_playback(
        &mut self,
        maximum: usize,
    ) -> Result<Vec<NativePlaybackRecord>, BackendFailure> {
        Ok(self
            .playback
            .as_mut()
            .ok_or_else(BackendFailure::contract)?
            .drain(maximum))
    }
}

impl Drop for CpalBackend {
    fn drop(&mut self) {
        if self.release().is_err() {
            // One bounded retained plan/ring per quarantined output service.
            // A nonconforming driver must not free its callback storage on RT.
            if let Some(playback) = self.playback.take() {
                std::mem::forget(playback);
            }
        }
    }
}

const fn supported_buffer(value: SupportedBufferSize) -> OutputBufferSupport {
    match value {
        SupportedBufferSize::Range { min, max } => OutputBufferSupport::Range {
            minimum_frames: min,
            maximum_frames: max,
        },
        SupportedBufferSize::Unknown => OutputBufferSupport::Unknown,
    }
}
