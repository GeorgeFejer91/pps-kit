//! Development-only asset regeneration; no device access or catalogue publication.
//! Usage: cargo run -p pps-designer-core --example regenerate_serino_exp3_proxy --
//! <renderer.exe> <FABIAN.sofa> <new-output-directory> [cancellation-file]
use pps_designer_core::*;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    error::Error,
    fs::{self, File, OpenOptions},
    io::{Cursor, Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::atomic::AtomicBool,
    time::{Duration, Instant},
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;
const FRAMES: usize = 176_400;
const TEMPLATE: &str = "serino_2015_peri_hand_exp3";
const POLICY: &str = "serino-exp3-continuous-pink-cartesian-proxy.v2";

fn request(receding: bool) -> GenerationRequest {
    let far = Position {
        x_m: 0.35,
        y_m: 0.93,
        z_m: 0.0,
    };
    let near = Position {
        x_m: 0.35,
        y_m: 0.05,
        z_m: 0.0,
    };
    let peak = 20.0 * 0.9_f64.log10();
    GenerationRequest {
        schema: REQUEST_SCHEMA.into(),
        source_algorithm: SOURCE_ALGORITHM.into(),
        sample_rate_hz: 44_100,
        duration_s: 4.0,
        seed: if receding { 20_153_241 } else { 20_152_232 },
        source: SourceSpec::Noise {
            color: NoiseColor::Pink,
            profile: SourceProfile::Continuous,
        },
        trajectory: TrajectorySpec::Linear {
            start: if receding { near } else { far },
            end: if receding { far } else { near },
            pre_hold_s: 0.0,
            movement_duration_s: 4.0,
        },
        tactile: vec![],
        level: LevelPolicy::PeakNormalize {
            target_peak_dbfs: peak,
            peak_ceiling_dbfs: peak,
        },
    }
}

fn read_bounded(path: &Path, maximum: u64) -> Result<Vec<u8>> {
    let mut file = File::open(path)?;
    if file.metadata()?.len() > maximum {
        return Err("file exceeds bound".into());
    }
    let mut bytes = Vec::new();
    (&mut file).take(maximum + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > maximum {
        return Err("file grew beyond bound".into());
    }
    Ok(bytes)
}

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

fn cancel_check(cancel: Option<&Path>) -> Result<()> {
    if cancel.is_some_and(Path::exists) {
        return Err("cancelled; staged outputs remain unpublished".into());
    }
    Ok(())
}

fn execute(renderer: &Path, directory: &Path, cancel: Option<&Path>) -> Result<()> {
    cancel_check(cancel)?;
    let mut command = Command::new(renderer);
    command
        .arg("--config")
        .arg(directory.join("config.json"))
        .arg("--output-dir")
        .arg(directory)
        .arg("--manifest")
        .arg(directory.join("renderer.json"))
        .arg("--qc")
        .arg(directory.join("renderer.csv"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn()?;
    let deadline = Instant::now() + Duration::from_secs(60);
    loop {
        let status = match child.try_wait() {
            Ok(status) => status,
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(error.into());
            }
        };
        if let Some(status) = status {
            if !status.success() {
                return Err(format!("renderer failed: {status}").into());
            }
            return cancel_check(cancel);
        }
        if Instant::now() >= deadline || cancel.is_some_and(Path::exists) {
            let _ = child.kill();
            let _ = child.wait();
            return Err("renderer cancelled or exceeded 60-second deadline".into());
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

fn rms(pcm: &[f32]) -> f64 {
    (pcm.iter().map(|v| f64::from(*v).powi(2)).sum::<f64>() / pcm.len() as f64).sqrt()
}

fn verify_pcm(pcm: &[f32]) -> Result<Value> {
    if pcm.len() != FRAMES * 2 || pcm.iter().any(|v| !v.is_finite()) {
        return Err("invalid stereo length or samples".into());
    }
    let peak = pcm.iter().map(|v| f64::from(v.abs())).fold(0.0, f64::max);
    if (peak - 0.9).abs() > 1e-6 || pcm.chunks(8_820).any(|window| rms(window) < 1e-6) {
        return Err("incorrect digital peak or silent 100ms window".into());
    }
    let channel_difference = pcm
        .chunks_exact(2)
        .map(|f| f64::from(f[0] - f[1]).powi(2))
        .sum::<f64>();
    if channel_difference <= 1e-6 {
        return Err("spatial output has identical channels".into());
    }
    Ok(
        json!({"frames":FRAMES,"channels":2,"sample_rate":44100,"duration_s":4.0,
        "peak":peak,"peak_dbfs":20.0*peak.log10(),"rms":rms(pcm),
        "first_500ms_rms":rms(&pcm[..44100]),"last_500ms_rms":rms(&pcm[pcm.len()-44100..]),
        "silent_100ms_windows":0,"finite":true,"clipping":false}),
    )
}

fn render_one(
    renderer: &Path,
    hrtf: &Path,
    output: &Path,
    receding: bool,
    cancel: Option<&Path>,
) -> Result<()> {
    cancel_check(cancel)?;
    let name = if receding {
        "looming_Hand_moving_sound_-_receding"
    } else {
        "looming_Hand_moving_sound"
    };
    let directory = output.join(if receding { "receding" } else { "looming" });
    fs::create_dir(&directory)?;
    let cancelled = AtomicBool::new(false);
    let request = request(receding);
    let prepared = prepare(&request, &cancelled)?;
    let options = SpatializerOptions {
        hrtf_path: hrtf.to_str().ok_or("HRTF path is not UTF-8")?.into(),
        hrtf_format: HrtfFormat::Sofa,
        head_radius_m: 0.09,
        distance_attenuation: true,
        near_field: false,
        propagation_delay: true,
    };
    let mut dry = Vec::new();
    let config = write_spatializer_input(&prepared, &mut dry, &options, &cancelled)?;
    write_new(&directory.join("dry.f32"), &dry)?;
    write_new(
        &directory.join("config.json"),
        &serde_json::to_vec_pretty(&config)?,
    )?;
    execute(renderer, &directory, cancel)?;
    let report: Value =
        serde_json::from_slice(&read_bounded(&directory.join("renderer.json"), 64 * 1024)?)?;
    let raw = read_stereo_wav(
        File::open(directory.join("stereo.wav"))?,
        44100,
        FRAMES,
        &cancelled,
    )?;
    let raw_bytes: Vec<u8> = raw.iter().flat_map(|v| v.to_le_bytes()).collect();
    if report["source_sha256"] != sha(&dry)
        || report["stereo_pcm_sha256"] != sha(&raw_bytes)
        || report["schema"] != "pps-3dti-spatialized.v2"
        || report["frames"] != FRAMES
        || report["channels"] != 2
        || report["sample_rate_hz"] != 44100
        || report["source_algorithm"] != SOURCE_ALGORITHM
        || report["spatialization"]["normalization"] != "none"
        || report["spatialization"]["distance_attenuation"] != true
        || report["spatialization"]["propagation_delay"] != true
        || report["spatialization"]["near_field"] != false
        || report["physical_spl_qualified"] != false
    {
        return Err("native renderer evidence does not match request/PCM".into());
    }
    let generated = compose_spatial_output(prepared, raw, &cancelled)?;
    let mut wav = Cursor::new(Vec::new());
    write_ingredient_wav(&mut wav, &generated, &cancelled)?;
    let bytes = wav.into_inner();
    let pcm = read_stereo_wav(Cursor::new(&bytes), 44100, FRAMES, &cancelled)?;
    let qc = verify_pcm(&pcm)?;
    cancel_check(cancel)?;
    write_new(&output.join(format!("{name}.wav")), &bytes)?;
    let source = json!({"schema":"pps-premade-native-proxy-evidence.v1","template_id":TEMPLATE,
        "proxy_policy":POLICY,"direction":if receding {"receding"} else {"looming"},
        "asset":{"path":format!("assets/preloads/{TEMPLATE}/02_looming_stimuli/{name}.wav"),
            "sha256":sha(&bytes),"bytes":bytes.len(),"frames":FRAMES,"duration_s":4.0,
            "sample_rate":44100,"channels":2,"source_profile":"continuous_noise","noise_type":"pink"},
        "request":request,"source_qc":generated.source_qc,"level_qc":generated.level_qc,"measured_pcm":qc,
        "spatializer_report":report,"renderer_executable_sha256":sha(&read_bounded(renderer,64*1024*1024)?),
        "hrtf_sha256":sha(&read_bounded(hrtf,128*1024*1024)?),
        "source_reference":"https://doi.org/10.1038/srep18603",
        "source_pointer":"Main Results Experiment3; Methods Acoustic Stimuli; SI two-speaker setup p2",
        "provenance":{"scientific_source_conformance":false,"physical_spl_qualified":false,
            "physical_timing_qualified":false,"legacy_numpy_seed_compatible":false,
            "level_policy":"Explicit digital peak 0.90 with distance attenuation; no SPL or source-envelope equivalence.",
            "source_origin":"Chosen 93 cm sound-onset anchor and right-hand 35 cm lateral offset are approximation conventions.",
            "motion":"Reported 22 cm/s applied to the chosen 88 cm path gives 4 s; exact original onset origin remains unresolved.",
            "seed_policy":"Explicit native V2 seeds 20152232/20153241; their integers do not establish legacy waveform parity.",
            "apparatus":"Binaural FABIAN/3DTI proxy for original two-speaker intensity motion; near-field correction disabled.",
            "terminal_silence":"Separate 100 ms trial-strip silence required for terminal tactile cue; absent from this 4 s auditory WAV and not source-reported.",
            "renderer_tail":"Native output truncates at the chosen 4 s duration; no sound hold or padded movement."}});
    write_new(
        &output.join(format!("{name}.native_generation.json")),
        &serde_json::to_vec_pretty(&source)?,
    )?;
    let csv = format!("status,noise_type,source_profile,duration_s,sample_rate,channels,frames,peak_dbfs,clipping,wav_sha256,source_algorithm,seed,physical_spl_qualified\nrendered_native_proxy,pink,continuous_noise,4,44100,2,{FRAMES},{:.9},false,{},{},{},false\n",
        qc["peak_dbfs"].as_f64().ok_or("peak QC absent")?,sha(&bytes),SOURCE_ALGORITHM,request.seed);
    write_new(
        &output.join(format!("{name}.render_qc.csv")),
        csv.as_bytes(),
    )?;
    println!("{name}: {}", sha(&bytes));
    Ok(())
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if !(3..=4).contains(&args.len()) {
        return Err(
            "usage: <renderer.exe> <FABIAN.sofa> <new-output-directory> [cancellation-file]".into(),
        );
    }
    let renderer = fs::canonicalize(&args[0])?;
    let hrtf = fs::canonicalize(&args[1])?;
    let cancel = args.get(3).map(PathBuf::from);
    cancel_check(cancel.as_deref())?;
    fs::create_dir(&args[2])?;
    let output = fs::canonicalize(&args[2])?;
    for receding in [false, true] {
        render_one(&renderer, &hrtf, &output, receding, cancel.as_deref())?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn proxy_keeps_explicit_motion_color_level_and_distinct_new_seeds() {
        for receding in [false, true] {
            let prepared = prepare(&request(receding), &AtomicBool::new(false)).unwrap();
            assert_eq!(prepared.dry_pcm().len(), FRAMES);
            assert_eq!(
                prepared.position_at(0.0).unwrap().y_m,
                if receding { 0.05 } else { 0.93 }
            );
            assert!(
                (prepared.position_at(4.0).unwrap().y_m - if receding { 0.93 } else { 0.05 }).abs()
                    < 1e-12
            );
            assert!(prepared.tactile_pcm().iter().all(|v| *v == 0.0));
            assert!(prepared.dry_pcm().chunks(4410).all(|v| rms(v) > 1e-6));
            assert!(prepared.source_qc().burst_onset_frames.is_empty());
        }
        assert_ne!(request(false).seed, request(true).seed);
    }
    #[test]
    fn output_checker_rejects_silence_clipping_and_short_files() {
        assert!(verify_pcm(&vec![0.0; FRAMES * 2]).is_err());
        assert!(verify_pcm(&vec![1.0; FRAMES * 2]).is_err());
        assert!(verify_pcm(&[0.9, 0.2]).is_err());
    }
}
