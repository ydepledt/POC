"""Deterministic editorial decisions grounded in recorded generation data."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _cluster_focus(points: np.ndarray, cell_size: float) -> tuple[list[float], int]:
    """Aim at the densest local group, never the empty mean between groups."""
    cells = np.floor(points / max(cell_size, .001)).astype(np.int32)
    _, membership, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    chosen = int(np.argmax(counts))
    local = points[membership == chosen]
    return local.mean(axis=0).astype(float).tolist(), len(local)


def load_replay(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as archive:
        replay = {name: archive[name] for name in archive.files}
    required = {"positions", "headings", "alive", "progress", "times", "scores", "generation"}
    if not required.issubset(replay):
        raise ValueError(f"Replay incomplet : {path.name}")
    shape = replay["positions"].shape
    if len(shape) != 3 or shape[-1] != 2 or min(shape[:2]) < 1:
        raise ValueError(f"Positions invalides : {path.name}")
    for key in ("headings", "alive", "progress", "scores"):
        if replay[key].shape != shape[:2]:
            raise ValueError(f"Dimensions incompatibles pour {key} : {path.name}")
    if replay["times"].shape != (shape[0],) or np.any(np.diff(replay["times"]) <= 0):
        raise ValueError(f"Horodatage invalide : {path.name}")
    if any(not np.isfinite(replay[key]).all() for key in ("positions", "headings", "progress", "scores", "times")):
        raise ValueError(f"Valeurs non finies dans {path.name}")
    if np.any(replay["progress"] < -.0001) or np.any(replay["progress"] > 1.0001):
        raise ValueError(f"Progression hors limites dans {path.name}")
    if "completed" in replay and replay["completed"].shape != shape[:2]:
        raise ValueError(f"Dimensions incompatibles pour completed : {path.name}")
    for key in ("crash_times", "completion_times"):
        if key in replay and (replay[key].shape != (shape[1],) or not np.isfinite(replay[key]).all()):
            raise ValueError(f"Dimensions ou valeurs incompatibles pour {key} : {path.name}")
    replay["generation"] = int(replay["generation"].item())
    return replay


def _events(replay: dict, previous_record: float, checkpoint_count: int, previous_completed: int = 0, track: dict | None = None) -> list[dict]:
    events = []
    generation = replay["generation"]
    times, alive = replay["times"], replay["alive"].astype(bool)
    completed = replay.get("completed", np.zeros_like(alive)).astype(bool)
    deactivations = alive[:-1] & ~alive[1:] & ~completed[1:]
    deaths = deactivations.sum(axis=1)
    if len(deaths) and deaths.max() > 0:
        index = int(np.argmax(deaths)) + 1
        newly_dead = alive[index - 1] & ~alive[index] & ~completed[index]
        focus, cluster_count = _cluster_focus(replay["positions"][index, newly_dead], float(track.get("width", 18)) if track else 18.)
        events.append({"type": "elimination", "generation": generation, "replay_index": index, "time": float(times[index]),
                       "count": int(deaths[index - 1]), "focus": focus, "focus_cluster_count": cluster_count})
    # alive=False also includes stagnation. Use explicit crash times when present,
    # otherwise conservatively verify road-edge contact from the true geometry.
    rows, cars = np.where(deactivations)
    collision_mask = np.zeros(len(rows), dtype=bool)
    method = "explicit_crash_times"
    if "crash_times" in replay:
        crash_times = replay["crash_times"][cars]
        collision_mask = (crash_times >= times[rows] - .001) & (crash_times <= times[rows + 1] + .001) & (crash_times >= 0)
    elif len(rows) and track and "car_radius" in track:
        line = np.asarray(track["centerline"], dtype=float)
        if track.get("closed", True) and not np.allclose(line[0], line[-1]):
            line = np.vstack([line, line[0]])
        starts, vectors = line[:-1], np.diff(line, axis=0)
        terminal = replay["positions"][rows + 1, cars]
        delta = terminal[:, None, :] - starts[None, :, :]
        fraction = np.clip(np.sum(delta * vectors[None, :, :], axis=-1) / np.maximum(np.sum(vectors * vectors, axis=-1), 1e-9), 0, 1)
        nearest = starts[None, :, :] + fraction[:, :, None] * vectors[None, :, :]
        distance = np.sqrt(np.min(np.sum((terminal[:, None, :] - nearest) ** 2, axis=-1), axis=1))
        collision_mask = distance + float(track["car_radius"]) >= float(track["width"]) / 2 - .001
        method = "recorded_terminal_road_edge_contact"
    if collision_mask.any():
        counts = np.bincount(rows[collision_mask] + 1, minlength=len(times))
        index = int(np.argmax(counts))
        impacted = cars[collision_mask & (rows + 1 == index)]
        focus, cluster_count = _cluster_focus(replay["positions"][index, impacted], float(track.get("width", 18)) if track else 18.)
        events.append({"type": "collision", "generation": generation, "replay_index": index, "time": float(times[index]),
                       "interval_seconds": float(times[index] - times[index - 1]), "count": int(counts[index]), "detection": method,
                       "focus": focus, "focus_cluster_count": cluster_count})
    maxima = replay["progress"].max(axis=1)
    crossings = np.flatnonzero(maxima > previous_record + .005)
    if previous_record >= 0 and len(crossings):
        index = int(crossings[0])
        events.append({"type": "record", "generation": generation, "replay_index": index, "time": float(times[index]), "previous_record": previous_record,
                       "progress": float(maxima[-1])})
    if checkpoint_count > 1:
        for fraction in (.25, .5, .75):
            crossings = np.flatnonzero(maxima >= fraction)
            if len(crossings):
                index = int(crossings[0])
                events.append({"type": "milestone", "generation": generation, "time": float(times[index]), "replay_index": index, "progress": fraction})
    finish = np.flatnonzero(completed.any(axis=1))
    if len(finish):
        index = int(finish[0])
        events.append({"type": "completion", "generation": generation, "time": float(times[index]), "replay_index": index, "count": int(completed[-1].sum())})
    completion_records = np.flatnonzero(completed.sum(axis=1) > previous_completed)
    if previous_completed > 0 and len(completion_records):
        index = int(completion_records[0])
        events.append({"type": "completion_record", "generation": generation, "time": float(times[index]), "replay_index": index,
                       "previous_completed": previous_completed, "count": int(completed[-1].sum())})
    return events


def build_story(run_dir: Path, duration: float) -> tuple[list[dict], list[dict], dict, list[dict], dict]:
    """Choose early, collision, strongest-record and final sequences.

    Unretained generations remain in the chart, but never receive invented replay
    imagery. All returned scene source times belong to their one stated replay.
    """
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    track = json.loads((run_dir / "track.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    if not metrics:
        raise ValueError("Aucune génération enregistrée : entraînez la simulation avant l'export.")
    by_generation = {int(m["generation"]): m for m in metrics}
    paths = {}
    for path in sorted((run_dir / "replays").glob("gen_*.npz")):
        try:
            generation = int(path.stem.split("_")[-1])
        except ValueError:
            continue
        if generation in by_generation:
            paths[generation] = path
    if not paths:
        raise ValueError("Aucun replay enregistré : entraînez la simulation avant l'export.")
    available = sorted(paths)
    first, final = available[0], available[-1]
    completion_mode = float(by_generation[first]["max_progress"]) >= .95 and max(int(m.get("completed", 0)) for m in metrics) > 0
    previous_record = -1.
    previous_completed = 0
    improvements = []
    prior_records = {}
    prior_completions = {}
    for generation in sorted(by_generation):
        progress = float(by_generation[generation]["max_progress"])
        completed = int(by_generation[generation].get("completed", 0))
        prior_records[generation] = previous_record
        prior_completions[generation] = previous_completed
        gain = completed - previous_completed if completion_mode else progress - previous_record
        threshold = 0 if completion_mode else .005
        if generation in paths and gain > threshold and generation != first:
            improvements.append((gain, generation))
        previous_record = max(previous_record, progress)
        previous_completed = max(previous_completed, completed)
    selected = {first, final}
    # Maximum five source generations keeps a short edit legible.
    selected.update(g for _, g in sorted(improvements, reverse=True)[:3])
    completions = [g for g in available if by_generation[g].get("completed", 0) > 0]
    if completions:
        selected.add(completions[0])
    if len(selected) > 5:
        keep = {first, final, completions[0]} if completions else {first, final}
        keep.update(g for _, g in sorted(improvements, reverse=True) if len(keep) < 5)
        selected = keep
    if len(selected) < min(4, len(available)):
        for offset in np.linspace(0, len(available) - 1, 4).round().astype(int):
            selected.add(available[offset])
    scenes, events = [], []
    first_collision = None
    for generation in sorted(selected):
        replay = load_replay(paths[generation])
        event_list = _events(replay, prior_records[generation], len(track.get("checkpoints", [])), prior_completions[generation], track)
        events.extend(event_list)
        times = replay["times"]
        progress = float(by_generation[generation]["max_progress"])
        completed = int(by_generation[generation].get("completed", 0))
        if generation == first:
            eyebrow, title = "01 / LA PREMIÈRE TENTATIVE", "Aucun pilote. Juste des neurones."
            subtitle = "Chaque couleur représente une voiture simulée."
            if completion_mode:
                subtitle = f"Déjà {completed} tour{'s' if completed > 1 else ''} validé{'s' if completed > 1 else ''} sur {int(by_generation[generation]['population'])} voitures."
            kind = "initial"
            first_collision = next((e for e in event_list if e["type"] == "collision"), None) or next((e for e in event_list if e["type"] == "elimination"), None)
        elif completed > 0 and completions and generation == completions[0]:
            eyebrow, title = "UN TOUR VALIDÉ", "Une première ligne franchie."
            subtitle = f"Génération {generation} : {completed} voiture{'s' if completed > 1 else ''} termine{'nt' if completed > 1 else ''} le circuit."
            kind = "completion"
        elif completion_mode and completed > prior_completions[generation]:
            eyebrow, title = "NOUVEAU RECORD DE RÉUSSITE", "Davantage de voitures terminent."
            subtitle = f"Tours validés : {prior_completions[generation]} → {completed} sur {int(by_generation[generation]['population'])}."
            kind = "completion_record"
        elif progress > prior_records[generation] + .005:
            eyebrow, title = "NOUVEAU RECORD MESURÉ", "La sélection change la trajectoire."
            subtitle = f"Record de distance : {prior_records[generation] * 100:.1f}% → {progress * 100:.1f}%."
            kind = "record"
        else:
            eyebrow, title = "UNE AUTRE GÉNÉRATION", "Chaque tentative est mesurée."
            subtitle = f"Génération {generation} : {progress * 100:.1f}% du circuit atteints."
            kind = "evolution"
        if generation == final and generation != first:
            eyebrow, title = "LE RÉSULTAT DE L'EXPÉRIENCE", "Des résultats. Pas de promesse."
            best = float(summary.get("best_progress", max(float(m["max_progress"]) for m in metrics)))
            subtitle = f"{len(metrics)} générations • distance record : {best * 100:.1f}%."
            if summary.get("baseline_best_progress") is not None:
                baseline = float(summary["baseline_best_progress"])
                subtitle = f"Référence : {baseline * 100:.1f}% → record : {best * 100:.1f}%."
            if completion_mode:
                baseline = int(summary.get("baseline_completed", by_generation[first].get("completed", 0)))
                best_completed = max(int(m.get("completed", 0)) for m in metrics)
                title = "L'évolution gagne en régularité." if best_completed > baseline else "Chaque résultat est mesuré."
                subtitle = f"Tours validés : {baseline} → {best_completed} sur {int(by_generation[generation]['population'])} voitures."
            kind = "final"
        cue_type = "completion" if generation in completions[:1] else "completion_record" if completion_mode else "record"
        cue = next((e for e in event_list if e["type"] == cue_type), None)
        scenes.append({"generation": generation, "replay_path": str(paths[generation].relative_to(run_dir)),
                       "source_start": float(times[0]), "source_end": float(times[-1]), "type": kind,
                       "narrative_metric": "completed" if completion_mode else "max_progress",
                       "record_cue_time": cue["time"] if cue else None,
                       "collision_cues": [e["time"] for e in event_list if e["type"] == "collision"],
                       "camera": "overview" if generation == first else "leader", "eyebrow": eyebrow, "title": title, "subtitle": subtitle})
    if first_collision is not None and first_collision["count"] >= 2:
        initial = scenes[0]
        collision = first_collision
        real_collision = collision["type"] == "collision"
        scenes.insert(1, {**initial, "source_start": max(initial["source_start"], collision["time"] - 1.2),
                         "source_end": min(initial["source_end"], collision["time"] + 1.4), "type": collision["type"], "camera": "collision", "focus": collision["focus"],
                         "eyebrow": "LA BORDURE NE PARDONNE PAS" if real_collision else "LA SÉLECTION COMMENCE",
                         "title": "Un mauvais angle suffit." if real_collision else "Rouler ne suffit pas.",
                         "subtitle": f"{collision['count']} sorties de piste en {collision.get('interval_seconds', .1):.1f} s." if real_collision else f"{collision['count']} éliminations en un intervalle du replay.",
                         "record_cue_time": None})
    weights = [1.1 if scene["type"] in ("initial", "final") else .8 if scene["type"] in ("collision", "elimination") else 1 for scene in scenes]
    cursor, total_weight = 0., sum(weights)
    for scene, weight in zip(scenes, weights):
        scene["output_start"] = cursor
        scene["output_end"] = cursor + duration * weight / total_weight
        scene["source_speed"] = (scene["source_end"] - scene["source_start"]) / (scene["output_end"] - cursor)
        cursor = scene["output_end"]
    scenes[-1]["output_end"] = duration
    return scenes, events, track, metrics, summary

