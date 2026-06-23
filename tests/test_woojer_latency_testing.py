from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "Woojer-latency-testing" / "scripts" / "run_woojer_audio_loopback_stress.py"


def _load_woojer_script():
    spec = importlib.util.spec_from_file_location("run_woojer_audio_loopback_stress", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _delayed_capture(stimulus: np.ndarray, *, delay_samples: int, input_channels: int = 3, return_channel: int = 3) -> np.ndarray:
    capture = np.zeros((stimulus.shape[0] + delay_samples + 64, input_channels), dtype=np.float32)
    capture[delay_samples : delay_samples + stimulus.shape[0], return_channel - 1] = stimulus[:, 2]
    return capture


def test_known_baseline_delay_recovery():
    woojer = _load_woojer_script()
    stimulus, planned, _manifest = woojer.build_pulse_stimulus(
        sample_rate=1000,
        output_channels=4,
        drive_output_channel_1based=3,
        pulse_count=5,
        pulse_interval_ms=300,
        amplitude=0.05,
    )
    capture = _delayed_capture(stimulus, delay_samples=17)

    _events, analysis = woojer.analyze_return_capture(capture, planned, sample_rate=1000, min_peak=0.01)

    assert analysis["passed"]
    assert analysis["detected_count"] == 5
    assert analysis["latency_ms"]["median_ms"] == pytest.approx(17.0)
    assert analysis["residual_jitter_ms"]["p95_ms"] == pytest.approx(0.0)


def test_woojer_loop_added_delay_after_baseline_subtraction(tmp_path: Path):
    woojer = _load_woojer_script()
    stimulus, planned, _manifest = woojer.build_pulse_stimulus(
        sample_rate=1000,
        output_channels=4,
        drive_output_channel_1based=3,
        pulse_count=5,
        pulse_interval_ms=300,
        amplitude=0.05,
    )
    _baseline_events, baseline_analysis = woojer.analyze_return_capture(
        _delayed_capture(stimulus, delay_samples=10),
        planned,
        sample_rate=1000,
        min_peak=0.01,
    )
    baseline_report = woojer.build_report(
        mode="direct-baseline",
        run_dir=tmp_path / "baseline",
        settings={},
        analysis=baseline_analysis,
    )
    _events, loop_analysis = woojer.analyze_return_capture(
        _delayed_capture(stimulus, delay_samples=31),
        planned,
        sample_rate=1000,
        min_peak=0.01,
    )
    report = woojer.build_report(
        mode="woojer-loop",
        run_dir=tmp_path / "loop",
        settings={},
        analysis=loop_analysis,
        baseline_report=baseline_report,
    )

    assert report["passed"]
    assert report["baseline_comparison"]["status"] == "compared"
    assert report["baseline_comparison"]["added_latency_ms"]["median_ms"] == pytest.approx(21.0)


def test_low_signal_fails_reliability_gate():
    woojer = _load_woojer_script()
    _stimulus, planned, _manifest = woojer.build_pulse_stimulus(sample_rate=1000, pulse_count=3, amplitude=0.05)
    capture = np.zeros((3000, 3), dtype=np.float32)

    _events, analysis = woojer.analyze_return_capture(capture, planned, sample_rate=1000, min_peak=0.01)

    assert not analysis["passed"]
    assert analysis["signal_qc"]["low_signal"]
    assert analysis["detected_count"] == 0


def test_clipping_fails_reliability_gate():
    woojer = _load_woojer_script()
    stimulus, planned, _manifest = woojer.build_pulse_stimulus(sample_rate=1000, pulse_count=3, amplitude=0.05)
    capture = _delayed_capture(stimulus, delay_samples=10)
    capture *= 25.0

    _events, analysis = woojer.analyze_return_capture(capture, planned, sample_rate=1000, min_peak=0.01)

    assert not analysis["passed"]
    assert analysis["signal_qc"]["clipped"]


def test_missed_pulse_fails_detection_rate():
    woojer = _load_woojer_script()
    stimulus, planned, _manifest = woojer.build_pulse_stimulus(
        sample_rate=1000,
        output_channels=4,
        drive_output_channel_1based=3,
        pulse_count=10,
        pulse_interval_ms=300,
        amplitude=0.05,
    )
    capture = _delayed_capture(stimulus, delay_samples=10)
    final_expected = int(planned[-1]["expected_sample_index"])
    capture[final_expected - 20 :, 2] = 0.0

    _events, analysis = woojer.analyze_return_capture(capture, planned, sample_rate=1000, min_peak=0.01)

    assert not analysis["passed"]
    assert analysis["detected_count"] == 9
    assert analysis["detection_rate"] == pytest.approx(0.9)


def test_wrong_input_channel_fails_low_signal():
    woojer = _load_woojer_script()
    stimulus, planned, _manifest = woojer.build_pulse_stimulus(sample_rate=1000, pulse_count=3, amplitude=0.05)
    capture = _delayed_capture(stimulus, delay_samples=10, input_channels=3, return_channel=2)

    _events, analysis = woojer.analyze_return_capture(
        capture,
        planned,
        sample_rate=1000,
        return_input_channel_1based=3,
        min_peak=0.01,
    )

    assert not analysis["passed"]
    assert analysis["signal_qc"]["low_signal"]


def test_missing_baseline_is_reported_without_added_latency(tmp_path: Path):
    woojer = _load_woojer_script()
    stimulus, planned, _manifest = woojer.build_pulse_stimulus(sample_rate=1000, pulse_count=3, amplitude=0.05)
    _events, analysis = woojer.analyze_return_capture(
        _delayed_capture(stimulus, delay_samples=12),
        planned,
        sample_rate=1000,
        min_peak=0.01,
    )

    report = woojer.build_report(mode="woojer-loop", run_dir=tmp_path / "loop", settings={}, analysis=analysis)

    assert report["passed"]
    assert report["baseline_comparison"]["status"] == "missing_baseline"
    assert "added_latency_ms" not in report["baseline_comparison"]


def test_load_baseline_report_requires_report_file(tmp_path: Path):
    woojer = _load_woojer_script()

    with pytest.raises(FileNotFoundError):
        woojer.load_baseline_report(tmp_path / "missing_baseline")


def test_cli_help_does_not_touch_hardware():
    result = subprocess.run([sys.executable, str(SCRIPT_PATH), "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "--mode" in result.stdout
    assert "woojer-loop" in result.stdout
