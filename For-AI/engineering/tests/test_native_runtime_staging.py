"""The staging helper must not overwrite an existing output directory."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows staging helper")
def test_native_runtime_staging_rejects_existing_output_before_download(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell unavailable")
    script = Path(__file__).resolve().parents[1] / "build/windows/Stage_PPS_Native_Runtime.ps1"
    output = tmp_path / "existing"
    output.mkdir()
    witness = output / "keep.txt"
    witness.write_text("existing user artifact", encoding="utf-8")
    # A valid executable path is enough: refusal must happen before either
    # extraction or network access, so this executable must never be invoked.
    result = subprocess.run(
        [shell, "-NoProfile", "-File", str(script), "-OutputDirectory", str(output),
         "-SevenZipPath", sys.executable], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "Runtime output must be a fresh directory" in result.stderr
    assert witness.read_text(encoding="utf-8") == "existing user artifact"
    assert sorted(p.name for p in output.iterdir()) == ["keep.txt"]
