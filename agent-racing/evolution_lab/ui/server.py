from __future__ import annotations

import math
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from evolution_lab.automation.store import Store
from evolution_lab.automation.worker import Orchestrator, read_json, write_json
from evolution_lab.publishing import CONNECTORS, export_bundle

TRACKS = ["oval", "kidney", "technical", "chicane", "procedural"]
DIFFICULTIES = ["easy", "medium", "hard", "extreme"]
ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}$")
ACTIVE = {"running", "queued", "retrying", "stopping"}


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or os.environ.get("EVOLUTION_LAB_DATA", Path(__file__).resolve().parents[2] / "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(data_dir / "evolution-lab.sqlite3")
    worker = Orchestrator(data_dir, store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        discover()
        worker.start()
        yield
        worker.close()

    app = FastAPI(title="Evolution Lab", lifespan=lifespan)
    app.state.store = store
    app.state.worker = worker
    app.state.data_dir = data_dir
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Origine externe refusée."}, status_code=403)
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"detail": "Une requête JSON est requise."}, status_code=415)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; media-src 'self'; frame-ancestors 'none'"
        return response

    def run_path(run_id: str) -> Path:
        if not ID_PATTERN.fullmatch(run_id):
            raise HTTPException(400, "Identifiant de simulation invalide.")
        candidate = worker.runs_dir / run_id
        if candidate.is_symlink():
            raise HTTPException(404, "Les liens symboliques ne sont pas exposés.")
        path = candidate.resolve()
        if path.parent != worker.runs_dir.resolve() or not path.is_dir() or path.is_symlink():
            raise HTTPException(404, "Simulation introuvable.")
        return path

    def discover() -> None:
        for path in worker.runs_dir.iterdir():
            if path.is_dir() and not path.is_symlink() and ID_PATTERN.fullmatch(path.name) and (path / "config.json").is_file():
                store.add_run(path.name, read_json(path / "config.json"), path.stat().st_ctime)

    def run_info(row: dict) -> dict:
        path = worker.runs_dir / row["id"]
        metrics = read_json(path / "metrics.json", [])
        summary = read_json(path / "summary.json")
        status = read_json(path / "status.json")
        jobs = store.jobs(row["id"])
        state = jobs[0]["state"] if jobs else status.get("status", summary.get("status", "saved"))
        if state == "completed" and summary.get("status") in {"stopped", "interrupted"}:
            state = summary["status"]
        latest = metrics[-1] if metrics else {}
        return {"id": row["id"], "created": row["created"], "config": row["config"], "state": state,
                "generation": status.get("generation", latest.get("generation", 0)),
                "best_progress": summary.get("best_progress", max((m.get("max_progress", 0) for m in metrics), default=0)),
                "best_score": summary.get("best_score", max((m.get("best_score", 0) for m in metrics), default=0)),
                "elapsed_seconds": status.get("elapsed_seconds", summary.get("elapsed_seconds", 0)),
                "video": (path / "video.mp4").is_file(), "thumbnail": (path / "thumbnail.png").is_file(),
                "checkpoint": (path / "checkpoint.npz").is_file(), "generations": len(metrics),
                "error": (jobs[0].get("error") if jobs else None), "archived": bool(row["archived"])}

    def info(run_id: str) -> dict:
        run_path(run_id)
        discover()
        row = next((r for r in store.runs() if r["id"] == run_id), None)
        if not row:
            raise HTTPException(404, "Simulation sans configuration.")
        return run_info(row)

    def assert_idle(run_id: str) -> None:
        if any(j["state"] in ACTIVE for j in store.jobs(run_id)):
            raise HTTPException(409, "Cette simulation a déjà une tâche en cours.")

    async def json_object(request: Request) -> dict:
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(422, "Corps JSON invalide.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(422, "Un objet JSON est requis.")
        return payload

    @app.get("/api/overview")
    def overview():
        discover()
        runs = [run_info(row) for row in store.runs()]
        return {"runs": runs, "jobs": store.jobs(), "counts": {
            "simulations": len(runs), "generations": sum(r["generations"] for r in runs),
            "videos": sum(r["video"] for r in runs), "active": sum(r["state"] in ACTIVE for r in runs),
            "best_progress": max((r["best_progress"] for r in runs), default=0)},
            "schedule": store.get_setting("schedule"), "worker_error": worker.last_error,
            "data_dir": str(data_dir)}

    @app.get("/api/defaults")
    def defaults():
        from evolution_lab.config import SimulationConfig
        return {"config": asdict(SimulationConfig()), "tracks": TRACKS, "difficulties": DIFFICULTIES}

    @app.post("/api/runs", status_code=201)
    async def create_run(request: Request):
        payload = await json_object(request)
        try:
            config = payload.get("config", payload)
            job = worker.new_run(config, dedupe_key=request.headers.get("idempotency-key"))
            return {"run_id": job["run_id"], "job": job}
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/runs/{run_id}")
    def details(run_id: str):
        result = info(run_id)
        path = run_path(run_id)
        log = path / "job.log"
        if log.exists():
            with log.open("rb") as handle:
                handle.seek(max(0, log.stat().st_size - 18000))
                log_text = handle.read().decode("utf-8", errors="replace")
        else:
            log_text = "La file attend le prochain lancement." if result["state"] == "queued" else "Aucun journal de processus pour cette expérience."
        return {**result, "metrics": read_json(path / "metrics.json", []), "status": read_json(path / "status.json"),
                "summary": read_json(path / "summary.json"), "track": read_json(path / "track.json"), "publication": read_json(path / "publication.json"),
                "video_metadata": read_json(path / "video_metadata.json"), "render_status": read_json(path / "render_status.json"), "export_receipt": read_json(path / "export_receipt.json"),
                "replays": [int(p.stem.split("_")[-1]) for p in sorted((path / "replays").glob("gen_*.npz")) if p.stem.split("_")[-1].isdigit()],
                "log": log_text, "jobs": store.jobs(run_id)}

    @app.post("/api/runs/{run_id}/stop")
    def stop(run_id: str):
        path = run_path(run_id)
        store.stop(run_id)
        (path / ".shutdown-stop").unlink(missing_ok=True)
        (path / ".user-stop").touch()
        (path / "STOP").touch()
        return {"state": "stopping", "message": "Arrêt demandé. La dernière génération sauvegardée est conservée."}

    @app.post("/api/runs/{run_id}/resume")
    def resume(run_id: str):
        path = run_path(run_id)
        assert_idle(run_id)
        if not (path / "checkpoint.npz").exists():
            raise HTTPException(409, "Aucune sauvegarde disponible. Relancez une nouvelle expérience.")
        return store.enqueue(run_id, "resume")

    @app.post("/api/runs/{run_id}/render")
    async def render(run_id: str, request: Request):
        path = run_path(run_id)
        assert_idle(run_id)
        if not list((path / "replays").glob("gen_*.npz")):
            raise HTTPException(409, "Aucune génération enregistrée pour le montage.")
        payload = await json_object(request)
        if "duration" in payload:
            try:
                duration = float(payload["duration"])
            except (TypeError, ValueError) as exc:
                raise HTTPException(422, "Durée invalide.") from exc
            if not math.isfinite(duration) or not 2 <= duration <= 60:
                raise HTTPException(422, "La durée doit être comprise entre 2 et 60 secondes.")
            config = read_json(path / "config.json")
            config["video_duration"] = duration
            write_json(path / "config.json", config)
        return store.enqueue(run_id, "render")

    @app.get("/api/runs/{run_id}/replay/{generation}")
    def replay(run_id: str, generation: int):
        path = run_path(run_id)
        if generation < 1 or generation > 100000:
            raise HTTPException(422, "Génération invalide.")
        source = path / "replays" / f"gen_{generation:04d}.npz"
        if not source.is_file() or source.is_symlink():
            raise HTTPException(404, "Cette génération n’a pas été conservée.")
        with np.load(source, allow_pickle=False) as recording:
            positions = recording["positions"]
            frames = np.unique(np.linspace(0, len(positions) - 1, min(220, len(positions))).astype(int))
            agents = np.arange(positions.shape[1])
            if len(agents) > 1500:
                agents = np.linspace(0, len(agents) - 1, 1500).astype(int)
            completed = recording["completed"][frames] if "completed" in recording else np.zeros_like(recording["alive"][frames], dtype=bool)
            return {"track": read_json(path / "track.json"), "generation": generation,
                    "population": int(positions.shape[1]), "shown": len(agents),
                    "positions": np.round(positions[frames][:, agents], 2).tolist(),
                    "headings": np.round(recording["headings"][frames][:, agents], 3).tolist(),
                    "alive": recording["alive"][frames][:, agents].astype(int).tolist(),
                    "completed": completed[:, agents].astype(int).tolist(),
                    "completed_counts": completed.sum(axis=1).tolist(),
                    "alive_counts": recording["alive"][frames].sum(axis=1).tolist(),
                    "times": np.round(recording["times"][frames], 2).tolist()}

    @app.get("/api/runs/{run_id}/files/{filename}")
    def file(run_id: str, filename: str, download: bool = False):
        allowed = {"video.mp4", "thumbnail.png", "config.json", "summary.json", "metrics.json", "publication.json", "video_metadata.json", "best_brain.npz", "checkpoint.npz"}
        if filename not in allowed:
            raise HTTPException(404, "Fichier non exposé.")
        path = run_path(run_id) / filename
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, "Fichier indisponible.")
        return FileResponse(path, filename=filename if download else None,
                            media_type="video/mp4" if filename.endswith(".mp4") else None)

    @app.post("/api/runs/{run_id}/export")
    async def export(run_id: str, request: Request):
        path = run_path(run_id)
        assert_idle(run_id)
        payload = await json_object(request)
        try:
            return export_bundle(path, payload.get("destination", ""))
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/schedule")
    def schedule():
        return {"schedule": store.get_setting("schedule"), "limits": store.get_setting("limits")}

    @app.put("/api/schedule")
    async def save_schedule(request: Request):
        payload = await json_object(request)
        with worker.schedule_lock:
            current = store.get_setting("schedule")
            candidate = {**current, **{k: v for k, v in payload.items() if k in current and k not in {"produced", "next_run", "batch_id"}}}
            try:
                for key, low, high in [("interval_minutes", 1, 10080), ("count", 1, 100), ("population", 10, 5000), ("generations", 1, 1000), ("budget_seconds", 10, 36000), ("video_duration", 2, 60)]:
                    candidate[key] = float(candidate[key]) if key == "video_duration" else int(candidate[key])
                    if not low <= candidate[key] <= high:
                        raise ValueError(f"Valeur invalide : {key} ({low}–{high}).")
                if candidate["difficulty"] not in DIFFICULTIES or not isinstance(candidate["tracks"], list) or not candidate["tracks"] or any(t not in TRACKS for t in candidate["tracks"]):
                    raise ValueError("Circuit ou difficulté invalide.")
                if type(candidate["enabled"]) is not bool:
                    raise ValueError("L’activation doit être explicite.")
                if candidate["mode"] != "draft":
                    raise ValueError("Seul le mode brouillon local est disponible.")
                if not isinstance(candidate["destination"], str):
                    raise ValueError("Le dossier d’export doit être un chemin texte.")
                if candidate["destination"] and (not Path(candidate["destination"]).expanduser().is_absolute() or candidate["destination"].startswith("\\\\")):
                    raise ValueError("Le dossier d’export doit être un chemin absolu.")
                from evolution_lab.config import SimulationConfig
                SimulationConfig(population=candidate["population"], generations=candidate["generations"],
                                 video_duration=candidate["video_duration"], budget_seconds=candidate["budget_seconds"])
            except (TypeError, ValueError) as exc:
                raise HTTPException(422, str(exc)) from exc
            candidate["produced"] = 0
            candidate["batch_id"] = uuid.uuid4().hex
            candidate["next_run"] = time.time() + candidate["interval_minutes"] * 60 if candidate["enabled"] else None
            store.set_setting("schedule", candidate)
        return candidate

    @app.put("/api/limits")
    async def save_limits(request: Request):
        payload = await json_object(request)
        limits = store.get_setting("limits")
        try:
            for key, low, high in [("memory_mb", 512, 65536), ("threads", 1, 32), ("disk_gb", 1, 1000), ("min_free_gb", .1, 100)]:
                value = float(payload.get(key, limits[key]))
                if not math.isfinite(value) or not low <= value <= high:
                    raise ValueError(f"Limite invalide : {key}.")
                limits[key] = int(value) if key in {"memory_mb", "threads"} else value
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        store.set_setting("limits", limits)
        return limits

    @app.get("/api/publications")
    def publications():
        return {"connectors": CONNECTORS, "items": store.publications(), "automatic_publishing": False}

    @app.post("/api/publications/{run_id}")
    async def prepare_publication(run_id: str, request: Request):
        path = run_path(run_id)
        if not (path / "video.mp4").exists():
            raise HTTPException(409, "Créez une vidéo avant de préparer sa publication.")
        payload = await json_object(request)
        platform = payload.get("platform", "local")
        if platform not in {"local", "youtube", "tiktok", "instagram"}:
            raise HTTPException(422, "Plateforme inconnue.")
        return store.publication(run_id, platform, "Brouillon pour export manuel. Aucune connexion ni publication réalisée.")

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    return app
