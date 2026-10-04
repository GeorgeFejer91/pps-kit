use std::{
    sync::Arc,
    time::{Duration, Instant},
};

use pps_runner_audio::{OutputFence, PreparedPlaybackPlan};

use cpal::{
    traits::{DeviceTrait, HostTrait, StreamTrait},
    BufferSize, SampleFormat, StreamConfig, SupportedBufferSize,
};

use crate::{
    contract::{OutputBufferSelection, OutputBufferSupport, OutputFaultKind, OutputSampleFormat},
    playback::PlaybackOwner,
    service::{
        BackendConfig, BackendDevice, BackendEnumeration, BackendFailure, CallbackSignals,
        OutputBackend, SelectionKey,
    },
    OutputServiceErrorCode, PlaybackPort, PlaybackStatus, MAXIMUM_CALLBACK_FRAMES,
    MAXIMUM_OUTPUT_CHANNELS, MAXIMUM_OUTPUT_CONFIGS_PER_DEVICE, MAXIMUM_OUTPUT_DEVICES,
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
    hosts: Vec<(&'static str, cpal::Host)>,
    devices: Vec<RetainedCpalDevice>,
    stream: Option<cpal::Stream>,
    selection: Option<(CpalSelectionKey, crate::ExactOutputSelection)>,
    playback: Option<PlaybackOwner>,
}

impl CpalBackend {
    pub(crate) fn open() -> Result<Self, BackendFailure> {
        let mut hosts = Vec::new();
        #[cfg(windows)]
        if let Ok(asio) = cpal::host_from_id(cpal::HostId::Asio) {
            hosts.push(("ASIO", asio));
        }
        #[cfg(windows)]
        let system_host = "WASAPI";
        #[cfg(not(windows))]
        let system_host = "System";
        hosts.push((system_host, cpal::default_host()));
        Ok(Self {
            hosts,
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
        let mut public_devices = Vec::new();
        let mut devices_truncated = false;
        let mut enumerated_host = false;
        'hosts: for (host_name, host) in &self.hosts {
            let Ok(devices) = host.output_devices() else {
                continue;
            };
            enumerated_host = true;
            for (scanned_device_index, device) in devices.enumerate() {
                if scanned_device_index >= MAXIMUM_SCANNED_OUTPUT_DEVICES {
                    devices_truncated = true;
                    break;
                }
                if self.devices.len() >= MAXIMUM_OUTPUT_DEVICES {
                    devices_truncated = true;
                    break 'hosts;
                }
                let display_name = format!("{host_name} · {device}");
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
                    let Some(sample_format) = supported_format(range.sample_format()) else {
                        continue;
                    };
                    if range.channels() == 0 || range.channels() > MAXIMUM_OUTPUT_CHANNELS {
                        continue;
                    }
                    if retained_configs.len() >= MAXIMUM_OUTPUT_CONFIGS_PER_DEVICE {
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
                        sample_format,
                        buffer_support: supported_buffer(*range.buffer_size()),
                    });
                    retained_configs.push(range);
                }
                if public_configs.is_empty() {
                    continue;
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
        }
        if !enumerated_host {
            return Err(BackendFailure::new(
                OutputFaultKind::EnumerationFailed,
                OutputServiceErrorCode::EnumerationFailed,
                "Native output-device enumeration failed.",
            ));
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
        if supported_format(range.sample_format()).is_none()
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
        let sample_format = range.sample_format();
        if self.stream.is_some() {
            return Err(BackendFailure::contract());
        }
        let stream = retained
            .device
            .build_output_stream_raw(
                config,
                sample_format,
                move |data, _| {
                    let exact_format = data.sample_format() == sample_format;
                    let sample_count = data.len();
                    if !crate::service::raw_callback_shape_is_bounded(
                        exact_format,
                        callback_channels,
                        sample_count,
                    ) {
                        callback_signals.record_callback_fault();
                        return;
                    }
                    callback_signals.write_raw_silence(
                        exact_format,
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
        let retained = self
            .devices
            .get(key.device_index)
            .ok_or_else(BackendFailure::contract)?;
        let device = &retained.device;
        let sample_format = retained
            .configs
            .get(key.config_index)
            .ok_or_else(BackendFailure::contract)?
            .sample_format();
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
        let stream = match sample_format {
            SampleFormat::F32 => device.build_output_stream(
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
            ),
            SampleFormat::I32 => {
                let mut scratch =
                    vec![0.0_f32; MAXIMUM_CALLBACK_FRAMES * usize::from(MAXIMUM_OUTPUT_CHANNELS)];
                device.build_output_stream(
                    config,
                    move |samples: &mut [i32], info: &cpal::OutputCallbackInfo| {
                        if samples.len() > scratch.len() {
                            samples.fill(0);
                            callback_signals.record_callback_fault();
                            return;
                        }
                        let rendered = &mut scratch[..samples.len()];
                        if callback.render(rendered, Instant::now(), Some(info.timestamp())) {
                            callback_signals.record_callback_fault();
                        }
                        for (destination, source) in samples.iter_mut().zip(rendered) {
                            *destination = f32_to_i32(*source);
                        }
                        callback_signals.record_callback();
                    },
                    move |_| signals.record_callback_fault(),
                    Some(Duration::from_secs(2)),
                )
            }
            _ => return Err(BackendFailure::contract()),
        };
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

    fn take_playback_port(&mut self, fence: &OutputFence) -> Result<PlaybackPort, BackendFailure> {
        self.playback
            .as_mut()
            .ok_or_else(BackendFailure::contract)?
            .take_port(fence)
            .map_err(|_| BackendFailure::contract())
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

const fn supported_format(value: SampleFormat) -> Option<OutputSampleFormat> {
    match value {
        SampleFormat::F32 => Some(OutputSampleFormat::F32),
        SampleFormat::I32 => Some(OutputSampleFormat::I32),
        _ => None,
    }
}

fn f32_to_i32(sample: f32) -> i32 {
    (sample.clamp(-1.0, 1.0) * 2_147_483_648.0) as i32
}

#[cfg(test)]
mod tests {
    use super::f32_to_i32;

    #[test]
    fn converts_float_pcm_to_signed_32_bit_endpoints() {
        assert_eq!(f32_to_i32(-1.0), i32::MIN);
        assert_eq!(f32_to_i32(0.0), 0);
        assert_eq!(f32_to_i32(1.0), i32::MAX);
        assert_eq!(f32_to_i32(f32::NAN), 0);
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
