"""Resumable, bounded-memory experiment runner with atomic artifacts."""
from dataclasses import asdict
from pathlib import Path
from typing import Callable
import json
import os
import time
import numpy as np
import psutil
from .config import SimulationConfig
from .core.tracks import Track, generate_track
from .core.evolution import initial_population, next_generation
from .core.simulation import simulate_generation


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False, allow_nan=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)


def atomic_npz(path, **arrays):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as file:
        np.savez_compressed(file, **arrays)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)


def _retained_replays(metrics, limit, available=None):
    if not metrics:
        return set()
    record = []
    high = -float("inf")
    for item in metrics:
        if item["best_score"] > high + 1e-7:
            record.append(item["generation"])
            high = item["best_score"]
    keep = {1, metrics[-1]["generation"], max(metrics, key=lambda m: m["best_score"])["generation"]}
    successful = [m["generation"] for m in metrics if m["completed"]]
    if successful:
        keep.add(successful[0])
    available = set(m["generation"] for m in metrics) if available is None else set(available)
    keep &= available
    candidates = sorted((set(record + [metrics[-1]["generation"]]) & available) - keep)
    remaining = max(0, limit - len(keep))
    if candidates and remaining:
        indices = np.linspace(0, len(candidates) - 1, min(remaining, len(candidates))).round().astype(int)
        keep.update(candidates[i] for i in indices)
    return keep


def train(config: SimulationConfig, run_dir: Path, resume: bool = False,
          stop_requested: Callable[[], bool] | None = None) -> dict:
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    replay_dir = run_dir / "replays"
    replay_dir.mkdir(exist_ok=True)
    checkpoint_path = run_dir / "checkpoint.npz"
    started = time.perf_counter()
    process = psutil.Process()
    cpu_started = sum(process.cpu_times()[:2])
    rng = np.random.default_rng(config.seed)
    metrics, completed_generations, elapsed_before = [], 0, 0.
    best_score, best_progress, best_generation = -1e30, 0., 0
    best_genome, stagnation, record_events = None, 0, []
    effective_config = asdict(config)
    if resume:
        if not checkpoint_path.exists():
            raise FileNotFoundError("No training checkpoint exists in this run")
        with np.load(checkpoint_path, allow_pickle=False) as checkpoint:
            saved_config = json.loads(str(checkpoint["config_json"]))
            editable = {"generations", "budget_seconds", "video_duration", "visual_style", "replay_limit"}
            if any(saved_config[k] != effective_config.get(k) for k in saved_config if k not in editable):
                raise ValueError("Resume requires identical simulation/GA settings and seed")
            population = checkpoint["next_population"].copy()
            rng.bit_generator.state = json.loads(str(checkpoint["rng_state_json"]))
            state = json.loads(str(checkpoint["state_json"]))
            metrics = json.loads(str(checkpoint["metrics_json"]))
            track = Track.from_dict(json.loads(str(checkpoint["track_json"])))
            best_genome = checkpoint["best_genome"].copy()
        completed_generations = state["generation"]
        elapsed_before = state["elapsed_seconds"]
        best_score, best_progress = state["best_score"], state["best_progress"]
        best_generation, stagnation = state["best_generation"], state["stagnation"]
        record_events = state.get("record_events", [])
        atomic_npz(run_dir / "best_brain.npz", genome=best_genome,
                   sensors=np.array(config.sensors), hidden_size=np.array(config.hidden_size),
                   generation=np.array(best_generation), score=np.array(best_score), progress=np.array(best_progress))
        for path in replay_dir.glob("gen_*.npz"):
            if path.stem[4:].isdigit() and int(path.stem[4:]) > completed_generations:
                path.unlink()
        atomic_json(run_dir / "metrics.json", metrics)
    else:
        if checkpoint_path.exists() or (run_dir / "metrics.json").exists():
            raise FileExistsError("This run already contains training data; choose resume or a new directory")
        track = generate_track(config.track, config.seed, config.difficulty, width=config.track_width,
                               length=config.track_length, corners=config.corners, hairpins=config.hairpins,
                               max_curvature=config.max_curvature, closed=config.closed)
        population = initial_population(config, rng)
    atomic_json(run_dir / "config.json", effective_config)
    atomic_json(run_dir / "track.json", track.to_dict())
    atomic_json(run_dir / "metrics.json", metrics)

    def status(kind, generation, message):
        atomic_json(run_dir / "status.json", {"status": kind, "generation": generation,
                    "best_score": best_score if best_generation else 0., "best_progress": best_progress,
                    "elapsed_seconds": elapsed_before + time.perf_counter() - started, "message": message})

    status("training", completed_generations, "Préparation du moteur de simulation")
    reason, error = "generations", None
    try:
        for generation in range(completed_generations + 1, config.generations + 1):
            if stop_requested and stop_requested():
                reason = "stopped"
                break
            if elapsed_before + time.perf_counter() - started >= config.budget_seconds:
                reason = "budget"
                break
            status("training", generation, f"Simulation réelle de la génération {generation}")
            evaluation = simulate_generation(track, population, config, generation)
            candidate = int(np.argmax(evaluation.scores))
            score = float(evaluation.scores[candidate])
            new_record = score > best_score + 1e-7
            if new_record:
                best_score, best_genome, best_generation = score, population[candidate].copy(), generation
                best_progress = float(evaluation.progress[candidate])
                stagnation = 0
                record_events.append({"generation": generation, "score": score, "progress": best_progress})
            else:
                stagnation += 1
            population, genetic = next_generation(population, evaluation.scores, config, rng, stagnation)
            item = {**evaluation.metrics, "elapsed_seconds": elapsed_before + time.perf_counter() - started,
                    "new_record": new_record, "stagnation": stagnation, "genetics": genetic,
                    "rss_mb": process.memory_info().rss / 1024**2,
                    "process_cpu_seconds": sum(process.cpu_times()[:2]) - cpu_started}
            metrics.append(item)
            completed_generations = generation
            # Only the current generation occupies trajectory RAM. Persist first,
            # records and current final; prune redundant saved generations below.
            atomic_npz(replay_dir / f"gen_{generation:04d}.npz", **evaluation.replay)
            atomic_npz(run_dir / "best_brain.npz", genome=best_genome,
                       sensors=np.array(config.sensors), hidden_size=np.array(config.hidden_size),
                       generation=np.array(best_generation), score=np.array(best_score), progress=np.array(best_progress))
            state = {"generation": generation, "elapsed_seconds": elapsed_before + time.perf_counter() - started,
                     "best_score": best_score, "best_progress": best_progress, "best_generation": best_generation,
                     "stagnation": stagnation, "record_events": record_events}
            # Checkpoint is canonical: metrics and JSON views are repaired from it
            # on resume if interrupted between these atomic replacements.
            atomic_npz(checkpoint_path, next_population=population, best_genome=best_genome,
                       rng_state_json=np.array(json.dumps(rng.bit_generator.state)),
                       state_json=np.array(json.dumps(state)), metrics_json=np.array(json.dumps(metrics)),
                       config_json=np.array(json.dumps(effective_config)), track_json=np.array(json.dumps(track.to_dict())))
            atomic_json(run_dir / "metrics.json", metrics)
            available = [int(p.stem[4:]) for p in replay_dir.glob("gen_*.npz") if p.stem[4:].isdigit()]
            keep = _retained_replays(metrics, config.replay_limit, available)
            for path in replay_dir.glob("gen_*.npz"):
                try:
                    number = int(path.stem[4:])
                except ValueError:
                    continue
                if number not in keep and path.parent.resolve() == replay_dir.resolve():
                    path.unlink()
            status("training", generation, f"Génération {generation} sauvegardée")
            del evaluation
            if generation >= config.min_generations and item["completed"] / config.population >= config.target_completion_fraction:
                reason = "objective"
                break
    except Exception as exception:
        reason, error = "failed", f"{type(exception).__name__}: {exception}"
        status("failed", completed_generations, error)
        raise
    finally:
        total_elapsed = elapsed_before + time.perf_counter() - started
        baseline = metrics[0] if metrics else {"max_progress": 0., "best_score": 0., "mean_score": 0., "completed": 0}
        final = metrics[-1] if metrics else baseline
        improvement = (best_score - baseline["best_score"]) if metrics else 0.
        summary = {"status": "failed" if error else ("stopped" if reason == "stopped" else "completed"),
                   "stop_reason": reason, "population": config.population, "generations": completed_generations,
                   "best_progress": best_progress, "best_score": best_score if metrics else 0.,
                   "best_generation": best_generation, "completed": max((m["completed"] for m in metrics), default=0),
                   "elapsed_seconds": total_elapsed, "seed": config.seed,
                   "baseline_best_progress": baseline["max_progress"], "baseline_best_score": baseline["best_score"],
                   "baseline_mean_score": baseline["mean_score"], "baseline_completed": baseline["completed"],
                   "final_mean_score": final["mean_score"], "final_completed": final["completed"],
                   "improvement_progress": best_progress - baseline["max_progress"], "improvement_score": improvement,
                   "learning_improved": bool(improvement > 1e-6 or final["mean_score"] > baseline["mean_score"] + 1e-6),
                   "replay_generations": sorted(int(p.stem[4:]) for p in replay_dir.glob("gen_*.npz")),
                   "peak_observed_rss_mb": max((m["rss_mb"] for m in metrics), default=process.memory_info().rss / 1024**2),
                   "error": error, "neural_inputs": ["wall_distance"] * config.sensors + ["speed"],
                   "model": f"{config.sensors + 1}-{config.hidden_size}-2 tanh MLP",
                   "agent_collisions": False}
        atomic_json(run_dir / "summary.json", summary)
        status(summary["status"], completed_generations, error or f"Entraînement terminé : {reason}")
    return summary
