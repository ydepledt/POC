import json
from dataclasses import replace
import numpy as np
import pytest
from evolution_lab.config import SimulationConfig
from evolution_lab.training import train, _retained_replays


def test_resume_matches_uninterrupted_genetic_run(tmp_path):
    config = SimulationConfig(population=30, generations=4, max_seconds=5., replay_limit=4)
    uninterrupted = tmp_path / "whole"
    split = tmp_path / "split"
    train(config, uninterrupted)
    train(replace(config, generations=2), split)
    # Simulate a crash between updating a presentation artifact and checkpoint.
    (split / "metrics.json").write_text("[]")
    np.savez(split / "best_brain.npz", genome=np.zeros(3))
    np.savez(split / "replays" / "gen_0099.npz", generation=np.array(99))
    summary = train(config, split, resume=True)
    assert summary["generations"] == 4
    assert not (split / "replays" / "gen_0099.npz").exists()
    for name in ["checkpoint.npz", "best_brain.npz"]:
        with np.load(uninterrupted / name) as a, np.load(split / name) as b:
            key = "next_population" if name == "checkpoint.npz" else "genome"
            np.testing.assert_array_equal(a[key], b[key])
            if name == "checkpoint.npz":
                assert str(a["rng_state_json"]) == str(b["rng_state_json"])
    whole_metrics = json.loads((uninterrupted / "metrics.json").read_text())
    split_metrics = json.loads((split / "metrics.json").read_text())
    assert [m["best_score"] for m in whole_metrics] == [m["best_score"] for m in split_metrics]
    assert [m["mean_score"] for m in whole_metrics] == [m["mean_score"] for m in split_metrics]


def test_stop_at_boundary_and_resume(tmp_path):
    config = SimulationConfig(population=20, generations=3, max_seconds=2.)
    calls = []
    def stop():
        calls.append(1)
        return len(calls) > 1
    result = train(config, tmp_path / "run", stop_requested=stop)
    assert result["status"] == "stopped" and result["generations"] == 1
    resumed = train(config, tmp_path / "run", resume=True)
    assert resumed["generations"] == 3
    metrics = json.loads((tmp_path / "run" / "metrics.json").read_text())
    assert [m["generation"] for m in metrics] == [1, 2, 3]
    for path in (tmp_path / "run" / "replays").glob("*.npz"):
        with np.load(path) as replay:
            assert replay["positions"].shape[1] == 20
            assert int(replay["generation"]) == int(path.stem[4:])


def test_existing_run_and_incompatible_resume_are_rejected(tmp_path):
    config = SimulationConfig(population=12, generations=1, max_seconds=1.)
    train(config, tmp_path)
    with pytest.raises(FileExistsError):
        train(config, tmp_path)
    with pytest.raises(ValueError, match="identical"):
        train(replace(config, seed=7), tmp_path, resume=True)


def test_selective_replays_keep_first_final_and_existing_only():
    metrics = [{"generation": i, "best_score": i, "completed": int(i > 5)} for i in range(1, 21)]
    available = {1, 6, 12, 18, 19, 20}
    selected = _retained_replays(metrics, 4, available)
    assert {1, 6, 20} <= selected <= available
    assert len(selected) <= 4


def test_stop_before_first_generation_leaves_readable_artifacts(tmp_path):
    result = train(SimulationConfig(population=4, generations=1), tmp_path, stop_requested=lambda: True)
    assert result["status"] == "stopped" and result["generations"] == 0
    assert json.loads((tmp_path / "metrics.json").read_text()) == []
    assert not (tmp_path / "checkpoint.npz").exists()


def test_actual_evolution_improves_against_random_baseline(tmp_path):
    config = SimulationConfig(population=150, generations=8, track="kidney", difficulty="medium", max_seconds=48., seed=42)
    result = train(config, tmp_path)
    assert result["baseline_completed"] == 0
    assert result["improvement_progress"] > .25
    assert result["final_mean_score"] > result["baseline_mean_score"] * 2
    assert result["completed"] > 0
    assert result["learning_improved"]
    assert result["generations"] >= config.min_generations
