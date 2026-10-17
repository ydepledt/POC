"""Synthetic fixtures test replay provenance and encoding, never training claims."""

import json
from pathlib import Path

import numpy as np
import pytest

from evolution_lab.video import export_video, validate_video
from evolution_lab.video.story import build_story, load_replay, _events, _cluster_focus


@pytest.fixture
def replay_run(tmp_path: Path) -> Path:
    (tmp_path / "replays").mkdir()
    angles = np.linspace(0, 2 * np.pi, 100, endpoint=False)
    centerline = np.column_stack([np.cos(angles) * 70, np.sin(angles) * 100])
    track = {"name": "synthetic_test_fixture", "width": 18, "closed": True,
             "centerline": centerline.tolist(), "checkpoints": centerline[::10].tolist(), "length": 540}
    (tmp_path / "track.json").write_text(json.dumps(track), encoding="utf-8")
    metrics = []
    for generation in (1, 2, 3):
        steps, population = 25, 24
        times = np.linspace(0, 4.8, steps).astype(np.float32)
        progress = np.repeat(np.linspace(0, .1 + generation * .17, steps)[:, None], population, axis=1)
        progress *= np.linspace(.2, 1., population)[None, :]
        headings = progress * 2 * np.pi + np.pi / 2
        positions = np.stack([np.cos(progress * 2 * np.pi) * 70, np.sin(progress * 2 * np.pi) * 100], axis=-1)
        alive = np.ones((steps, population), dtype=bool)
        alive[8:, :12] = False
        alive[16:, 12:18] = False
        for car in range(population):
            dead = np.flatnonzero(~alive[:, car])
            if len(dead):
                positions[dead[0]:, car] = positions[dead[0], car]
                progress[dead[0]:, car] = progress[dead[0], car]
        np.savez_compressed(tmp_path / "replays" / f"gen_{generation:04d}.npz", positions=positions.astype("f4"), headings=headings.astype("f4"),
                            progress=progress.astype("f4"), alive=alive, times=times, scores=(progress * 100).astype("f4"), generation=np.array(generation),
                            completed=np.zeros_like(alive))
        metrics.append({"generation": generation, "population": population, "max_progress": float(progress.max()), "best_score": float(progress.max() * 100), "completed": 0})
    (tmp_path / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps({"population": 24, "generations": 3, "best_progress": .61, "completed": 0}), encoding="utf-8")
    return tmp_path


def test_story_selects_real_generations_and_collision(replay_run):
    scenes, events, _, _, _ = build_story(replay_run, 24)
    assert scenes[0]["generation"] == 1
    assert scenes[-1]["generation"] == 3
    assert scenes[-1]["output_end"] == 24
    assert any(e["type"] == "elimination" and e["count"] == 12 for e in events)
    assert not any(e["type"] == "collision" for e in events)  # fixture has no verified boundary contacts
    assert not any(e["type"] == "completion" for e in events)
    assert all(s["source_end"] >= s["source_start"] for s in scenes)
    assert all("tour validé" not in s["title"].lower() for s in scenes)


def test_export_encodes_and_counters_match_every_source_frame(replay_run):
    metadata = export_video(replay_run, duration=1.2, fps=10, width=360, height=640)
    assert metadata["validation"]["valid"], metadata["validation"]
    assert metadata["validation"]["codec"] == "h264"
    assert metadata["validation"]["audio_codec"] == "aac"
    assert metadata["validation"]["decoded_frames"] == 12
    assert metadata["resolution"] == [360, 640]
    assert len({f["generation"] for f in metadata["frame_audit"]}) == 3
    for frame in metadata["frame_audit"]:
        replay = load_replay(replay_run / "replays" / f"gen_{frame['generation']:04d}.npz")
        index = frame["replay_index"]
        assert frame["alive"] == int(replay["alive"][index].sum())
        assert frame["best_progress"] == float(replay["progress"][index].max())
        assert frame["best_score"] == float(replay["scores"][index].max())
        assert frame["replay_time"] == float(replay["times"][index])
    assert (replay_run / "thumbnail.png").stat().st_size > 1024
    publication = json.loads((replay_run / "publication.json").read_text(encoding="utf-8"))
    assert publication["status"] == "draft" and publication["publish_requires_consent"]
    assert metadata["audio"]["music"] is False


def test_corrupt_video_fails_validation(tmp_path):
    path = tmp_path / "corrupt.mp4"
    path.write_bytes(b"not a video" * 500)
    validation = validate_video(path)
    assert not validation["valid"]
    assert validation["decoded_frames"] == 0


def test_invalid_aspect_ratio_rejected(replay_run):
    with pytest.raises(ValueError, match="9:16"):
        export_video(replay_run, duration=1, width=640, height=360)


def test_replay_shape_corruption_rejected(tmp_path):
    bad = tmp_path / "gen_0001.npz"
    np.savez(bad, positions=np.zeros((3, 2, 2)), headings=np.zeros((3, 1)), alive=np.ones((3, 2)),
             progress=np.zeros((3, 2)), times=np.arange(3), scores=np.zeros((3, 2)), generation=1)
    with pytest.raises(ValueError, match="Dimensions"):
        load_replay(bad)


def test_stagnation_is_not_reported_as_collision(replay_run):
    replay = load_replay(replay_run / "replays" / "gen_0001.npz")
    replay["crash_times"] = np.full(24, -1., dtype="f4")
    replay["crash_times"][:5] = replay["times"][8]
    events = _events(replay, -1., 10)
    assert next(event for event in events if event["type"] == "elimination")["count"] == 12
    assert next(event for event in events if event["type"] == "collision")["count"] == 5


def test_dense_cluster_camera_does_not_target_empty_space():
    points = np.array([[0., 0.], [1., 0.], [2., 0.], [1000., 1000.]])
    center, count = _cluster_focus(points, 18.)
    assert center == [1., 0.]
    assert count == 3


def test_completed_baseline_uses_success_counts(replay_run):
    metrics_path = replay_run / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    for metric, count in zip(metrics, (1, 4, 7)):
        metric["max_progress"] = 1.
        metric["completed"] = count
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
    scenes, _, _, _, _ = build_story(replay_run, 24)
    assert scenes[-1]["narrative_metric"] == "completed"
    assert "1 → 7" in scenes[-1]["subtitle"]
    assert scenes[0]["type"] == "initial"
    assert not any(s["type"] == "completion" and s["generation"] > 1 for s in scenes)
