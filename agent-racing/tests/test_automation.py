from pathlib import Path
import time

from evolution_lab.automation.store import Store
from evolution_lab.automation.worker import Orchestrator, write_json
from evolution_lab.publishing.manual import export_bundle


def test_queue_claim_is_transactional_and_duplicate_safe(tmp_path):
    store = Store(tmp_path / "queue.sqlite")
    store.add_run("example", {"population": 20})
    first = store.enqueue("example", dedupe_key="request-1")
    duplicate = store.enqueue("example", dedupe_key="request-1")
    overlapping = store.enqueue("example", "render")
    assert first["id"] == duplicate["id"] == overlapping["id"]
    job = store.claim()
    assert job["attempts"] == 1
    assert Store(tmp_path / "queue.sqlite").claim() is None
    store.finish(job["id"], "completed")
    assert store.enqueue("example", "render")["id"] != first["id"]


def test_failure_backoff_and_max_attempts(tmp_path):
    store = Store(tmp_path / "queue.sqlite")
    first = store.enqueue("example")
    job = store.claim()
    before = time.time()
    assert store.fail(job["id"], "Encoder unavailable") == "retrying"
    assert store.jobs()[0]["next_attempt"] >= before + 15
    assert store.claim() is None
    second = store.claim(now=before + 20)
    assert second["attempts"] == 2
    assert store.fail(second["id"], "Encoder unavailable") == "retrying"
    third = store.claim(now=time.time() + 100)
    assert store.fail(third["id"], "Encoder unavailable") == "failed"
    assert store.claim(now=time.time() + 1000) is None
    assert first["id"] == third["id"]


def test_recovery_preserves_queue_and_marks_interrupted(tmp_path):
    path = tmp_path / "queue.sqlite"
    store = Store(path)
    store.enqueue("active")
    store.enqueue("waiting")
    store.claim()
    restarted = Store(path)
    assert restarted.recover() == 1
    states = {j["run_id"]: j["state"] for j in restarted.jobs()}
    assert states == {"active": "interrupted", "waiting": "queued"}
    assert restarted.claim()["run_id"] == "waiting"


def test_schedule_is_opt_in_finite_and_deduplicated(tmp_path):
    store = Store(tmp_path / "queue.sqlite")
    worker = Orchestrator(tmp_path, store)
    worker.schedule_tick(now=1000)
    assert store.jobs() == []
    schedule = store.get_setting("schedule")
    schedule.update(enabled=True, count=2, population=20, generations=2, next_run=1000, interval_minutes=1, batch_id="test")
    store.set_setting("schedule", schedule)
    worker.schedule_tick(now=1000)
    worker.schedule_tick(now=1001)
    assert len(store.jobs()) == 1
    worker.schedule_tick(now=1060)
    assert len(store.jobs()) == 2
    assert not store.get_setting("schedule")["enabled"]
    assert store.get_setting("schedule")["produced"] == 2
    assert len(list(worker.runs_dir.iterdir())) == 2


def test_cancellation_does_not_claim_queued_job(tmp_path):
    store = Store(tmp_path / "queue.sqlite")
    store.enqueue("waiting")
    store.stop("waiting")
    assert store.claim() is None
    assert store.jobs()[0]["state"] == "cancelled"


def test_second_application_cannot_recover_live_worker(tmp_path):
    store = Store(tmp_path / "queue.sqlite")
    first = Orchestrator(tmp_path, store)
    second = Orchestrator(tmp_path, Store(tmp_path / "queue.sqlite"))
    try:
        first.start()
        second.start()
        assert first.thread and first.thread.is_alive()
        assert second.thread is None
        assert "autre instance" in second.last_error
    finally:
        second.close()
        first.close()


def test_export_is_local_versioned_and_preserves_existing_files(tmp_path):
    import pytest
    run = tmp_path / "run"
    run.mkdir()
    (run / "video.mp4").write_bytes(b"first-version")
    write_json(run / "publication.json", {"title": "Real results"})
    with pytest.raises(ValueError):
        export_bundle(run, "relative-path")
    with pytest.raises(ValueError):
        export_bundle(run, str(run / "nested"))
    result = export_bundle(run, str(tmp_path / "exports"))
    target = Path(result["destination"])
    (target / "publication.json").write_text("User edited title")
    repeated = export_bundle(run, str(tmp_path / "exports"))
    assert repeated["copied"] == []
    assert "publication.json" in repeated["skipped"]
    assert (target / "publication.json").read_text() == "User edited title"
    (run / "video.mp4").write_bytes(b"second-version")
    revised = export_bundle(run, str(tmp_path / "exports"))
    assert revised["destination"] != result["destination"]
    assert not result["published"]


def test_actual_worker_subprocess_generates_artifacts(tmp_path):
    """Exercise the same CLI subprocess used by the user interface."""
    store = Store(tmp_path / "queue.sqlite")
    worker = Orchestrator(tmp_path, store)
    queued = worker.new_run({"population": 12, "generations": 2, "max_seconds": 2,
                             "budget_seconds": 20, "video_duration": 2, "seed": 71})
    job = store.claim()
    worker.execute(job)
    assert store.jobs()[0]["state"] == "completed", (worker.runs_dir / queued["run_id"] / "job.log").read_text(encoding="utf-8")
    run = worker.runs_dir / queued["run_id"]
    assert (run / "video.mp4").stat().st_size > 1000
    assert (run / "checkpoint.npz").exists()
    assert (run / "metrics.json").exists()
    assert store.publications()[0]["platform"] == "local"


def test_restart_validates_real_checkpoint_then_resumes_same_job(tmp_path):
    from evolution_lab.config import SimulationConfig
    from evolution_lab.training import train
    store = Store(tmp_path / "queue.sqlite")
    worker = Orchestrator(tmp_path, store)
    config = SimulationConfig(population=12, generations=2, max_seconds=2, budget_seconds=20, video_duration=2)
    run = worker.runs_dir / "interrupted-training"
    train(config, run)
    job = store.enqueue(run.name)
    store.claim()
    # Graceful application shutdown is different from the user's Stop action.
    (run / ".shutdown-stop").touch()
    (run / "STOP").touch()
    restarted = Orchestrator(tmp_path, Store(tmp_path / "queue.sqlite"))
    before = time.time()
    restarted.recover_jobs()
    recovered = restarted.store.jobs()[0]
    assert recovered["id"] == job["id"]
    assert recovered["state"] == "retrying"
    assert recovered["kind"] == "resume"
    assert recovered["attempts"] == 1
    assert recovered["next_attempt"] >= before + 15
    assert restarted.store.claim() is None
    resumed = restarted.store.claim(now=time.time() + 20)
    restarted.execute(resumed)
    assert restarted.store.jobs()[0]["state"] == "completed", (run / "job.log").read_text(encoding="utf-8")
    assert restarted.store.jobs()[0]["attempts"] == 2
    assert (run / "video.mp4").stat().st_size > 1000
    assert not (run / "STOP").exists()


def test_restart_never_retries_user_stop_invalid_data_or_exhausted_job(tmp_path):
    store = Store(tmp_path / "queue.sqlite")
    worker = Orchestrator(tmp_path, store)
    for name in ["user-stopped", "broken", "exhausted", "still-running"]:
        path = worker.runs_dir / name
        path.mkdir()
        write_json(path / "config.json", {"population": 12, "generations": 2})
        (path / "checkpoint.npz").write_bytes(b"invalid-checkpoint")
        job = store.enqueue(name)
        with store.connect() as db:
            db.execute("UPDATE jobs SET state='running', attempts=? WHERE id=?", (3 if name == "exhausted" else 1, job["id"]))
    (worker.runs_dir / "user-stopped" / "STOP").touch()
    worker.stop_orphan = lambda path: path.name != "still-running"
    worker.recover_jobs()
    jobs = {j["run_id"]: j for j in store.jobs()}
    assert jobs["user-stopped"]["state"] == "stopped"
    assert jobs["broken"]["state"] == "interrupted"
    assert "invalide" in jobs["broken"]["error"]
    assert jobs["exhausted"]["state"] == "failed"
    assert jobs["still-running"]["state"] == "interrupted"
    assert worker.recovery_blocked
    assert store.claim(now=time.time() + 1000) is None


def test_restart_render_recovers_from_real_saved_replays(tmp_path):
    from evolution_lab.config import SimulationConfig
    from evolution_lab.training import train
    store = Store(tmp_path / "queue.sqlite")
    worker = Orchestrator(tmp_path, store)
    run = worker.runs_dir / "render-interrupted"
    train(SimulationConfig(population=12, generations=2, max_seconds=2, budget_seconds=20, video_duration=2), run)
    job = store.enqueue(run.name, "render")
    store.claim()
    worker.recover_jobs()
    recovered = store.jobs()[0]
    assert recovered["id"] == job["id"]
    assert recovered["kind"] == "render"
    assert recovered["state"] == "retrying"
