from pathlib import Path
import subprocess
import sys


def test_help_and_dependency_check():
    help_result = subprocess.run([sys.executable, "-m", "evolution_lab", "--help"], capture_output=True, text=True)
    assert help_result.returncode == 0
    assert "serve" in help_result.stdout
    result = subprocess.run([sys.executable, "-m", "evolution_lab", "doctor"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '"status": "ok"' in result.stdout


def test_missing_explicit_config_fails_without_starting(tmp_path: Path):
    run = tmp_path / "run"
    result = subprocess.run([sys.executable, "-m", "evolution_lab", "train", "--config", str(tmp_path / "absent.json"), "--run-dir", str(run)], capture_output=True)
    assert result.returncode == 1
    assert not (run / "checkpoint.npz").exists()
    assert (run / "status.json").exists()
