import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from evolution_lab.automation.worker import write_json
from evolution_lab.ui.server import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path)
    app.state.worker.enabled = False
    with TestClient(app) as client:
        yield client


def new_run(client, **values):
    response = client.post("/api/runs", json={"config": {"population": 20, "generations": 3, "seed": 14, **values}})
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


def test_app_starts_with_honest_empty_dashboard(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "Le mouvement s’apprend" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    dashboard = client.get("/api/overview").json()
    assert dashboard["counts"] == {"simulations": 0, "generations": 0, "videos": 0, "active": 0, "best_progress": 0}
    assert not dashboard["schedule"]["enabled"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/defaults").json()["config"]["population"] == 1500


def test_default_form_numbers_pass_browser_step_validation(client):
    """Regression: hidden advanced mutation field once blocked every launch."""
    from decimal import Decimal
    from html.parser import HTMLParser

    class Inputs(HTMLParser):
        def __init__(self):
            super().__init__()
            self.numbers = []

        def handle_starttag(self, tag, attributes):
            values = dict(attributes)
            if tag == "input" and values.get("type") == "number" and "value" in values:
                self.numbers.append(values)

    parser = Inputs()
    parser.feed(client.get("/").text)
    for field in parser.numbers:
        value = Decimal(field["value"])
        minimum = Decimal(field.get("min", "0"))
        maximum = Decimal(field.get("max", "Infinity"))
        assert minimum <= value <= maximum, field["name"]
        if field.get("step") != "any":
            step = Decimal(field.get("step", "1"))
            assert (value - minimum) % step == 0, field["name"]


def test_job_submission_validation_and_idempotency(client):
    assert client.post("/api/runs", json=[]).status_code == 422
    assert client.post("/api/runs", content="bad-json", headers={"Content-Type": "application/json"}).status_code == 422
    invalid = client.post("/api/runs", json={"population": -1})
    assert invalid.status_code == 422
    payload = {"config": {"population": 20, "generations": 3}}
    first = client.post("/api/runs", json=payload, headers={"Idempotency-Key": "same-click"})
    repeated = client.post("/api/runs", json=payload, headers={"Idempotency-Key": "same-click"})
    assert first.status_code == 201
    assert repeated.json()["run_id"] == first.json()["run_id"]
    dashboard = client.get("/api/overview").json()
    assert dashboard["counts"]["simulations"] == 1
    assert dashboard["counts"]["active"] == 1


def test_stop_resume_and_existing_artifact_discovery(client):
    run_id = new_run(client)
    assert client.post(f"/api/runs/{run_id}/stop", json={}).status_code == 200
    path = client.app.state.worker.runs_dir / run_id
    assert (path / "STOP").exists()
    assert client.get(f"/api/runs/{run_id}").json()["state"] == "cancelled"
    assert client.post(f"/api/runs/{run_id}/resume", json={}).status_code == 409
    np.savez(path / "checkpoint.npz", weights=np.zeros((20, 10)))
    assert client.post(f"/api/runs/{run_id}/resume", json={}).status_code == 200
    assert client.post(f"/api/runs/{run_id}/resume", json={}).status_code == 409
    external = client.app.state.worker.runs_dir / "demo-existing"
    external.mkdir()
    write_json(external / "config.json", {"population": 20, "generations": 2})
    write_json(external / "metrics.json", [{"generation": 1, "max_progress": .4, "best_score": 10}])
    write_json(external / "status.json", {"status": "completed", "generation": 1})
    counts = client.get("/api/overview").json()["counts"]
    assert counts["simulations"] == 2
    assert counts["best_progress"] == .4


def test_metrics_and_saved_generation_replay_are_actual(client):
    run_id = new_run(client)
    path = client.app.state.worker.runs_dir / run_id
    (path / "replays").mkdir()
    positions = np.array([[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=np.float32)
    np.savez(path / "replays" / "gen_0001.npz", positions=positions, headings=np.zeros((2, 2)),
             alive=np.array([[True, True], [False, True]]), times=np.array([0., 1.]),
             completed=np.array([[False, False], [True, False]]))
    write_json(path / "track.json", {"centerline": [[0, 0], [10, 0], [10, 10]], "width": 12})
    result = client.get(f"/api/runs/{run_id}/replay/1").json()
    assert result["positions"] == positions.tolist()
    assert result["alive_counts"] == [2, 1]
    assert result["completed_counts"] == [0, 1]
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["replays"] == [1]
    assert detail["track"]["width"] == 12
    assert client.get(f"/api/runs/{run_id}/replay/99").status_code == 404
    assert client.get(f"/api/runs/{run_id}/replay/-1").status_code == 422


def test_local_only_writes_and_download_allowlist(client):
    assert client.post("/api/runs", json={}, headers={"Origin": "https://external.example"}).status_code == 403
    assert client.post("/api/runs", data="population=10").status_code == 415
    assert client.get("/", headers={"Host": "external.example"}).status_code == 400
    run_id = new_run(client)
    assert client.get(f"/api/runs/{run_id}/files/job.log").status_code == 404
    assert client.get(f"/api/runs/{run_id}/files/config.json").status_code == 200
    assert client.get("/api/runs/not_here").status_code == 404


def test_schedule_and_limits_are_saved_without_publishing(client):
    assert not client.get("/api/schedule").json()["schedule"]["enabled"]
    assert client.put("/api/schedule", json={"enabled": "yes"}).status_code == 422
    assert client.put("/api/schedule", json={"mode": "publish"}).status_code == 422
    assert client.put("/api/schedule", json={"tracks": []}).status_code == 422
    response = client.put("/api/schedule", json={"enabled": True, "count": 2, "interval_minutes": 60, "tracks": ["oval", "procedural"]})
    assert response.status_code == 200
    assert response.json()["next_run"] > 0
    assert response.json()["produced"] == 0
    assert client.put("/api/limits", json={"memory_mb": 100}).status_code == 422
    assert client.put("/api/limits", json={"memory_mb": 2048}).json()["memory_mb"] == 2048
    publications = client.get("/api/publications").json()
    assert publications["automatic_publishing"] is False
    assert {c["state"] for c in publications["connectors"]} == {"unconfigured"}


def test_manual_publication_requires_video_and_deduplicates(client):
    run_id = new_run(client)
    assert client.post(f"/api/publications/{run_id}", json={"platform": "youtube"}).status_code == 409
    path = client.app.state.worker.runs_dir / run_id
    (path / "video.mp4").write_bytes(b"test-fixture")
    first = client.post(f"/api/publications/{run_id}", json={"platform": "youtube"}).json()
    second = client.post(f"/api/publications/{run_id}", json={"platform": "youtube"}).json()
    assert first["id"] == second["id"]
    assert first["state"] == "manual"
    assert "Aucune connexion" in first["message"]
