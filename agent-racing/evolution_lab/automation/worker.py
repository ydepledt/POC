from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

import psutil
import numpy as np

from .store import Store
from evolution_lab.publishing import export_bundle

LOGGER = logging.getLogger(__name__)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default if default is not None else {}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class Orchestrator:
    """One local CPU job at a time; opt-in schedule runs only while app is open."""
    def __init__(self, data_dir: Path, store: Store):
        self.data_dir = data_dir
        self.runs_dir = data_dir / "simulations"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.shutdown = threading.Event()
        self.thread: threading.Thread | None = None
        self.process: subprocess.Popen | None = None
        self.current_run: Path | None = None
        self.enabled = True
        self.last_error = ""
        self.schedule_lock = threading.RLock()
        self.lock_handle = None
        self.recovery_blocked = False

    def start(self) -> None:
        if not self.enabled:
            return
        # Cross-process lock: opening two UI instances must not recover or race an active job.
        handle = (self.data_dir / "worker.lock").open("a+b")
        try:
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            self.last_error = "Une autre instance de l’application traite déjà cette file. Les tâches sont partagées."
            return
        self.lock_handle = handle
        # A hard parent-process crash can leave a child behind. Only terminate a PID
        # whose recorded creation time and exact run argument prove ownership.
        self.recover_jobs()
        if self.recovery_blocked:
            self.last_error = "Un ancien traitement reste actif ou inaccessible. La file attend un redémarrage après sa fin."
            return
        self.thread = threading.Thread(target=self.loop, name="evolution-lab-worker", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.shutdown.set()
        if self.current_run is not None:
            if not (self.current_run / "STOP").exists():
                (self.current_run / ".shutdown-stop").touch()
            (self.current_run / "STOP").touch()
        if self.thread:
            self.thread.join(timeout=8)
        if self.process and self.process.poll() is None:
            self.terminate_child()
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)
        if self.lock_handle:
            self.lock_handle.close()
            self.lock_handle = None

    def stop_orphan(self, run_dir: Path) -> bool:
        record = read_json(run_dir / ".worker-process.json")
        if record:
            try:
                process = psutil.Process(record["pid"])
                command = process.cmdline()
                if abs(process.create_time() - record["created"]) <= .01 and str(run_dir) in command and "evolution_lab" in command:
                    children = process.children(recursive=True)
                    for child in children:
                        child.terminate()
                    process.terminate()
                    _, alive = psutil.wait_procs([*children, process], timeout=3)
                    for remaining in alive:
                        remaining.kill()
                    _, alive = psutil.wait_procs(alive, timeout=2)
                    if alive:
                        return False
            except psutil.NoSuchProcess:
                pass
            except (psutil.AccessDenied, KeyError, TypeError, ValueError):
                return False
        # Covers the rare crash between Popen and writing its ownership record.
        # An unrecorded matching process is never killed or duplicated automatically.
        for process in psutil.process_iter(["cmdline"]):
            try:
                command = process.info.get("cmdline") or []
                if "evolution_lab" in command and str(run_dir) in command:
                    return False
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return True

    def validate_recovery(self, run_dir: Path, kind: str) -> None:
        """Check the saved data needed by the actual resume/render implementation."""
        from evolution_lab.config import SimulationConfig
        from evolution_lab.core.evolution import genome_size
        from evolution_lab.core.tracks import Track

        config = SimulationConfig(**read_json(run_dir / "config.json"))
        if kind == "render":
            sources = sorted((run_dir / "replays").glob("gen_*.npz"))
            if not sources or not read_json(run_dir / "metrics.json", []):
                raise ValueError("Aucune génération sauvegardée exploitable pour le montage.")
            Track.from_dict(read_json(run_dir / "track.json"))
            for source in sources:
                with np.load(source, allow_pickle=False) as data:
                    positions = data["positions"]
                    shape = positions.shape[:2]
                    if positions.ndim != 3 or positions.shape[2] != 2 or not shape[0] or not shape[1] or not np.isfinite(positions).all():
                        raise ValueError("Trajectoires invalides.")
                    for key in ["headings", "alive", "progress", "scores"]:
                        if data[key].shape != shape or not np.isfinite(data[key]).all():
                            raise ValueError("Données de relecture incomplètes.")
                    if data["times"].shape != (shape[0],) or not np.isfinite(data["times"]).all():
                        raise ValueError("Chronologie de relecture invalide.")
            return
        with np.load(run_dir / "checkpoint.npz", allow_pickle=False) as data:
            saved = json.loads(str(data["config_json"]))
            SimulationConfig(**saved)
            editable = {"generations", "budget_seconds", "video_duration", "visual_style", "replay_limit"}
            if any(saved[k] != asdict(config).get(k) for k in saved if k not in editable):
                raise ValueError("La configuration ne correspond plus à la sauvegarde.")
            population, best = data["next_population"], data["best_genome"]
            size = genome_size(config.sensors, config.hidden_size)
            if population.shape != (config.population, size) or best.shape != (size,) or not np.isfinite(population).all() or not np.isfinite(best).all():
                raise ValueError("Population sauvegardée invalide.")
            rng = np.random.default_rng()
            rng.bit_generator.state = json.loads(str(data["rng_state_json"]))
            state = json.loads(str(data["state_json"]))
            metrics = json.loads(str(data["metrics_json"]))
            Track.from_dict(json.loads(str(data["track_json"])))
            if not isinstance(state["generation"], int) or state["generation"] < 1 or not metrics or metrics[-1]["generation"] != state["generation"]:
                raise ValueError("Générations de la sauvegarde incohérentes.")
            for key in ["elapsed_seconds", "best_score", "best_progress", "best_generation", "stagnation"]:
                if not np.isfinite(state[key]):
                    raise ValueError("Statistiques de sauvegarde invalides.")

    def recover_jobs(self) -> None:
        self.recovery_blocked = False
        previous = [job for job in self.store.jobs() if job["state"] in {"running", "stopping", "interrupted"}]
        safe = {job["id"]: self.stop_orphan(self.runs_dir / job["run_id"]) for job in previous}
        self.store.recover()
        for job in previous:
            run_dir = self.runs_dir / job["run_id"]
            shutdown_stop = (run_dir / ".shutdown-stop").exists()
            user_stopped = job["state"] == "stopping" or (run_dir / ".user-stop").exists() or ((run_dir / "STOP").exists() and not shutdown_stop)
            if user_stopped:
                self.store.finish(job["id"], "stopped", "Arrêt volontaire conservé. Reprise manuelle disponible.")
                continue
            if not safe[job["id"]]:
                self.recovery_blocked = True
                self.store.finish(job["id"], "interrupted", "Un processus peut encore utiliser cette expérience. Reprise automatique suspendue.")
                continue
            if job["attempts"] >= job["max_attempts"]:
                self.store.retry_interrupted(job["id"], job["kind"])
                continue
            try:
                self.validate_recovery(run_dir, job["kind"])
            except Exception as exc:
                self.store.finish(job["id"], "interrupted", f"Reprise automatique impossible : sauvegarde absente ou invalide ({exc}).")
                continue
            kind = "render" if job["kind"] == "render" else "resume"
            self.store.retry_interrupted(job["id"], kind)

    def terminate_child(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        try:
            process = psutil.Process(self.process.pid)
            for child in process.children(recursive=True):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            process.terminate()
        except psutil.NoSuchProcess:
            pass

    def check_resources(self) -> None:
        limits = self.store.get_setting("limits")
        if shutil.disk_usage(self.data_dir).free < limits["min_free_gb"] * 1024 ** 3:
            raise ValueError("Espace disque libre insuffisant. Libérez de l’espace ou ajustez la limite.")
        total = sum(p.stat().st_size for p in self.runs_dir.rglob("*") if p.is_file() and not p.is_symlink())
        if total > limits["disk_gb"] * 1024 ** 3:
            raise ValueError("Budget de stockage atteint. Les expériences sont conservées : aucun nettoyage automatique.")

    def new_run(self, config: dict, destination: str = "", dedupe_key: str | None = None) -> dict:
        from evolution_lab.config import SimulationConfig
        import uuid
        config = asdict(SimulationConfig(**config))
        self.check_resources()
        if len([j for j in self.store.jobs() if j["state"] in {"queued", "retrying"}]) >= 50:
            raise ValueError("La file contient déjà 50 tâches. Attendez leur traitement.")
        if dedupe_key:
            with self.store.connect() as db:
                row = db.execute("SELECT * FROM jobs WHERE dedupe_key=?", (dedupe_key,)).fetchone()
                if row:
                    return dict(row)
        run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True)
        write_json(run_dir / "config.json", config)
        self.store.add_run(run_id, config)
        return self.store.enqueue(run_id, destination=destination, dedupe_key=dedupe_key)

    def schedule_tick(self, now: float | None = None) -> None:
        now = now or time.time()
        with self.schedule_lock:
            schedule = self.store.get_setting("schedule")
            if not schedule["enabled"] or schedule["produced"] >= schedule["count"]:
                return
            if schedule.get("next_run") and now < schedule["next_run"]:
                return
            index = schedule["produced"]
            config = {"population": schedule["population"], "generations": schedule["generations"],
                      "seed": int(now) % 2**31 + index,
                      "track": schedule["tracks"][index % len(schedule["tracks"])],
                      "difficulty": schedule["difficulty"], "budget_seconds": schedule["budget_seconds"],
                      "video_duration": schedule["video_duration"]}
            self.new_run(config, destination=schedule["destination"],
                         dedupe_key=f"schedule-{schedule.get('batch_id', 'first')}-{index}")
            schedule["produced"] += 1
            schedule["next_run"] = now + schedule["interval_minutes"] * 60
            if schedule["produced"] >= schedule["count"]:
                schedule["enabled"] = False
            self.store.set_setting("schedule", schedule)

    def loop(self) -> None:
        while not self.shutdown.is_set():
            try:
                self.schedule_tick()
                job = self.store.claim()
                if job:
                    self.execute(job)
            except Exception as exc:
                LOGGER.exception("Erreur de la file locale")
                self.last_error = str(exc)
            self.shutdown.wait(1)

    def command(self, job: dict, run_dir: Path) -> list[str]:
        command = [sys.executable, "-m", "evolution_lab"]
        if job["kind"] == "render":
            return command + ["render", "--run-dir", str(run_dir)]
        command += ["run", "--config", str(run_dir / "config.json"), "--run-dir", str(run_dir)]
        if job["kind"] == "resume" or (run_dir / "checkpoint.npz").is_file():
            command += ["--resume"]
        return command

    def execute(self, job: dict) -> None:
        run_dir = self.runs_dir / job["run_id"]
        self.current_run = run_dir
        try:
            self.check_resources()
            stop = run_dir / "STOP"
            # Queued cancellations can race a claim. Honor their durable state.
            if self.store.jobs(job["run_id"])[0]["state"] in {"cancelled", "stopping"}:
                self.store.finish(job["id"], "cancelled")
                return
            if stop.exists():
                stop.unlink()
            (run_dir / ".shutdown-stop").unlink(missing_ok=True)
            (run_dir / ".user-stop").unlink(missing_ok=True)
            limits = self.store.get_setting("limits")
            config = read_json(run_dir / "config.json")
            timeout = float(config.get("budget_seconds", 600)) + 1800
            env = os.environ.copy()
            env.update({key: str(limits["threads"]) for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"]})
            env["PYTHONUNBUFFERED"] = "1"
            root = Path(__file__).resolve().parents[2]
            started = time.monotonic()
            violation = None
            stopping_since = None
            with (run_dir / "job.log").open("ab") as log:
                log.write(f"\n--- {job['kind']} · tentative {job['attempts']} ---\n".encode())
                kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
                self.process = subprocess.Popen(self.command(job, run_dir), cwd=root, env=env, stdout=log,
                                                stderr=subprocess.STDOUT, **kwargs)
                write_json(run_dir / ".worker-process.json", {"pid": self.process.pid, "created": psutil.Process(self.process.pid).create_time()})
                while self.process.poll() is None:
                    elapsed = time.monotonic() - started
                    if self.shutdown.is_set() or stop.exists():
                        stop.touch()
                        stopping_since = stopping_since or time.monotonic()
                        if time.monotonic() - stopping_since > 20:
                            self.terminate_child()
                    try:
                        proc = psutil.Process(self.process.pid)
                        rss = proc.memory_info().rss + sum(child.memory_info().rss for child in proc.children(recursive=True) if child.is_running())
                        if rss > limits["memory_mb"] * 1024**2:
                            violation = "Budget mémoire dépassé. La dernière sauvegarde est conservée."
                        if elapsed > timeout:
                            violation = "Limite de durée dépassée. La dernière sauvegarde est conservée."
                        if violation:
                            self.terminate_child()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    self.shutdown.wait(.5) if not self.shutdown.is_set() else time.sleep(.1)
                code = self.process.returncode
            if self.shutdown.is_set():
                self.store.finish(job["id"], "interrupted", "Application fermée. La reprise automatique vérifiera la sauvegarde au redémarrage.")
            elif stop.exists():
                self.store.finish(job["id"], "stopped")
            elif violation:
                self.store.finish(job["id"], "failed", violation)
            elif code:
                self.store.fail(job["id"], f"Le processus s’est arrêté (code {code}). Consultez le journal.")
            else:
                self.store.finish(job["id"], "completed")
                if job["destination"]:
                    try:
                        export_bundle(run_dir, job["destination"])
                    except Exception as exc:
                        self.store.finish(job["id"], "completed", f"Vidéo créée, export à réessayer : {exc}")
                if (run_dir / "video.mp4").is_file():
                    self.store.publication(job["run_id"], "local", "Vidéo disponible localement. Aucune publication réalisée.")
            self.last_error = ""
        except Exception as exc:
            LOGGER.exception("Échec du job %s", job["id"])
            self.store.fail(job["id"], str(exc))
        finally:
            self.process = None
            self.current_run = None
