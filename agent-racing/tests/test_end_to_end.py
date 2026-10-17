"""A real subprocess training/save/resume/render flow, not mocked inference."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def command(*args):
    result = subprocess.run([sys.executable, "-m", "evolution_lab", *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_real_training_restart_replay_and_video(tmp_path: Path):
    config = tmp_path / "experiment.json"
    settings = {"population": 24, "generations": 2, "min_generations": 20, "max_seconds": 6., "seed": 951, "track": "kidney", "video_duration": 2.}
    config.write_text(json.dumps(settings), encoding="utf-8")
    run_dir = tmp_path / "run"
    command("train", "--config", config, "--run-dir", run_dir)
    assert (run_dir / "best_brain.npz").is_file()
    initial_metrics = json.loads((run_dir / "metrics.json").read_text())
    assert len(initial_metrics) == 2
    settings["generations"] = 3
    config.write_text(json.dumps(settings), encoding="utf-8")
    command("train", "--resume", "--config", config, "--run-dir", run_dir)
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics[:2] == initial_metrics
    assert [m["generation"] for m in metrics] == [1, 2, 3]
    uninterrupted = tmp_path / "uninterrupted"
    command("train", "--config", config, "--run-dir", uninterrupted)
    expected = json.loads((uninterrupted / "metrics.json").read_text())
    for a, b in zip(metrics, expected):
        for field in ("best_score", "mean_score", "max_progress", "checkpoint_counts", "completed"):
            assert a[field] == b[field], field
    with np.load(run_dir / "checkpoint.npz") as resumed, np.load(uninterrupted / "checkpoint.npz") as continuous:
        np.testing.assert_array_equal(resumed["next_population"], continuous["next_population"])
    command("render", "--run-dir", run_dir, "--duration", 2, "--fps", 10, "--width", 270, "--height", 480)
    validation = json.loads(command("validate", run_dir / "video.mp4").stdout)
    assert validation["valid"]
    metadata = json.loads((run_dir / "video_metadata.json").read_text(encoding="utf-8"))
    assert len({f["generation"] for f in metadata["frame_audit"]}) >= 2
    assert metadata["resolution"] == [270, 480]
