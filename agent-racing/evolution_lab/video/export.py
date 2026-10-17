"""H.264 export, publication drafts, provenance and full-file decode validation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import imageio_ffmpeg
import numpy as np

from evolution_lab.rendering import ReplayRenderer
from .audio import synthesize_audio
from .story import build_story, load_replay


def _atomic_json(path: Path, data: dict):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def validate_video(path: Path | str, expected_width: int | None = None, expected_height: int | None = None,
                   expected_duration: float | None = None, expected_fps: float | None = None) -> dict:
    """Read stream metadata and decode every video frame with packaged FFmpeg.

    This is the FFprobe equivalent used because the portable package supplies
    FFmpeg on Windows even when neither binary is installed system-wide.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1024:
        return {"valid": False, "errors": ["MP4 absent ou vide."], "path": str(path)}
    metadata_process = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, errors="replace", timeout=30)
    description = metadata_process.stderr
    duration_match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", description)
    video_line = next((line for line in description.splitlines() if "Video:" in line), "")
    size_match = re.search(r"(?<![\d:])(\d{2,5})x(\d{2,5})(?![\d])", video_line)
    fps_match = re.search(r"(\d+(?:\.\d+)?) fps", video_line)
    seconds = (int(duration_match[1]) * 3600 + int(duration_match[2]) * 60 + float(duration_match[3])) if duration_match else 0.
    width, height = (int(size_match[1]), int(size_match[2])) if size_match else (0, 0)
    fps = float(fps_match[1]) if fps_match else 0.
    codec = re.search(r"Video: ([^ ,]+)", video_line)
    codec = codec[1] if codec else "unknown"
    decoded = subprocess.run([_ffmpeg(), "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-progress", "pipe:1", "-f", "null", "-"],
                             capture_output=True, text=True, errors="replace", timeout=max(60, seconds * 5))
    frames = [int(frame) for frame in re.findall(r"frame=(\d+)", decoded.stdout)]
    frame_count = max(frames, default=0)
    errors = []
    if decoded.returncode or decoded.stderr.strip():
        errors.append("Erreur de décodage : " + decoded.stderr.strip()[-2000:])
    if frame_count < 1:
        errors.append("Aucune image vidéo décodée.")
    if codec != "h264":
        errors.append(f"Codec inattendu : {codec}")
    for actual, expected, label in [(width, expected_width, "largeur"), (height, expected_height, "hauteur")]:
        if expected is not None and actual != expected:
            errors.append(f"{label} : {actual}, attendu : {expected}")
    if expected_duration is not None and abs(seconds - expected_duration) > max(.15, 1 / max(fps, 1)):
        errors.append(f"Durée : {seconds}, attendu : {expected_duration}")
    if expected_fps is not None and abs(fps - expected_fps) > .01:
        errors.append(f"Fréquence : {fps}, attendu : {expected_fps}")
    if expected_duration is not None and expected_fps is not None and frame_count != round(expected_duration * expected_fps):
        errors.append(f"Nombre d'images : {frame_count}, attendu : {round(expected_duration * expected_fps)}")
    return {"valid": not errors, "errors": errors, "path": str(path), "bytes": path.stat().st_size, "codec": codec,
            "width": width, "height": height, "fps": fps, "duration": seconds, "decoded_frames": frame_count,
            "audio_codec": "aac" if "Audio: aac" in description else None, "pixel_format": "yuv420p" if "yuv420p" in video_line else None,
            "method": "FFmpeg stream inspection + full-file decode"}


def export_video(run_dir: Path, output_path: Path | None = None, duration: float = 24.0, fps: int = 30,
                 width: int = 1080, height: int = 1920) -> dict:
    try:
        return _export_video(run_dir, output_path, duration, fps, width, height)
    except Exception as exc:
        if Path(run_dir).is_dir():
            _atomic_json(Path(run_dir) / "render_status.json", {"status": "failed", "error": str(exc)})
        raise


def _export_video(run_dir: Path, output_path: Path | None, duration: float, fps: int, width: int, height: int) -> dict:
    run_dir = Path(run_dir).resolve()
    output_path = Path(output_path).resolve() if output_path is not None else run_dir / "video.mp4"
    if not math.isfinite(duration) or not 1 <= duration <= 60:
        raise ValueError("La durée doit être comprise entre 1 et 60 secondes (20–60 conseillées).")
    if fps not in (10, 15, 24, 25, 30, 60):
        raise ValueError("Choisissez 30 ou 60 images/s ; 10, 15, 24 et 25 sont également disponibles.")
    if width < 180 or height < 320 or width % 2 or height % 2:
        raise ValueError("Dimensions paires minimales : 180 × 320.")
    if abs(width / height - 9 / 16) > .001:
        raise ValueError("Le film vertical doit conserver le format 9:16.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    scenes, events, track, metrics, summary = build_story(run_dir, duration)
    renderer = ReplayRenderer(track, metrics, width, height)
    total_frames = round(duration * fps)
    duration = total_frames / fps
    audit, hashes = [], {}
    rendering_seconds = 0.
    source_generation = None
    scene_index = 0
    replay = None
    thumbnail = None
    thumbnail_frame = max(0, total_frames - max(1, int(fps * .7)))
    render_status = run_dir / "render_status.json"
    _atomic_json(render_status, {"status": "rendering", "frames": 0, "total_frames": total_frames, "progress": 0})
    with tempfile.TemporaryDirectory(prefix="evolution_video_", dir=output_path.parent) as temporary:
        temp_dir = Path(temporary)
        silent = temp_dir / "silent.mp4"
        final = temp_dir / "final.mp4"
        ffmpeg_log_path = temp_dir / "encode.log"
        with ffmpeg_log_path.open("wb") as error_log:
            encoder = subprocess.Popen([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
                                        "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "veryfast",
                                        "-crf", "19", "-threads", "4", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE, stderr=error_log)
            try:
                for frame in range(total_frames):
                    video_time = frame / fps
                    while scene_index < len(scenes) - 1 and video_time >= scenes[scene_index]["output_end"]:
                        scene_index += 1
                    scene = scenes[scene_index]
                    if source_generation != scene["generation"]:
                        source_path = run_dir / scene["replay_path"]
                        replay = load_replay(source_path)
                        if replay["generation"] != scene["generation"]:
                            raise ValueError("L'identité de génération du replay ne correspond pas au montage.")
                        source_generation = replay["generation"]
                        digest = hashlib.sha256()
                        with source_path.open("rb") as source:
                            for block in iter(lambda: source.read(1024 * 1024), b""):
                                digest.update(block)
                        hashes[scene["replay_path"]] = digest.hexdigest()
                    phase = float(np.clip((video_time - scene["output_start"]) / max(scene["output_end"] - scene["output_start"] - 1 / fps, 1 / fps), 0, 1))
                    source_time = scene["source_start"] + phase * (scene["source_end"] - scene["source_start"])
                    # Nearest *recorded* state: counters and geometry have one origin.
                    right = min(int(np.searchsorted(replay["times"], source_time)), len(replay["times"]) - 1)
                    left = max(0, right - 1)
                    index = left if abs(float(replay["times"][left]) - source_time) < abs(float(replay["times"][right]) - source_time) else right
                    frame_start = time.perf_counter()
                    image, counters = renderer.render(replay, index, scene, phase, video_time, duration)
                    rendering_seconds += time.perf_counter() - frame_start
                    audit.append({"video_frame": frame, "video_time": round(video_time, 6), "scene_index": scene_index, **counters})
                    if frame == thumbnail_frame:
                        thumbnail = image.copy()
                    encoder.stdin.write(image.tobytes())
                    if frame % max(1, fps) == 0:
                        _atomic_json(render_status, {"status": "rendering", "frames": frame, "total_frames": total_frames,
                                                    "progress": round(frame / total_frames, 4), "generation": source_generation})
                encoder.stdin.close()
                code = encoder.wait(timeout=max(90, duration * 5))
                if code:
                    raise RuntimeError("FFmpeg n'a pas pu encoder la vidéo : " + ffmpeg_log_path.read_text(errors="replace")[-2000:])
            except BaseException:
                encoder.kill()
                encoder.wait()
                raise
        audio_path = temp_dir / "effects.wav"
        audio_metadata = synthesize_audio(audio_path, duration, scenes, audit)
        mux = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(audio_path), "-map", "0:v:0", "-map", "1:a:0",
                              "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-t", str(duration), "-movflags", "+faststart", str(final)], capture_output=True, text=True, timeout=90)
        if mux.returncode:
            raise RuntimeError("FFmpeg n'a pas pu ajouter les effets sonores : " + mux.stderr[-2000:])
        _atomic_json(render_status, {"status": "validating", "frames": total_frames, "total_frames": total_frames, "progress": 1.})
        validation = validate_video(final, width, height, duration, fps)
        if not validation["valid"]:
            raise RuntimeError("Vidéo non valide : " + "; ".join(validation["errors"]))
        os.replace(final, output_path)
        validation["path"] = str(output_path)
    if thumbnail is not None:
        thumbnail.save(run_dir / "thumbnail.png")
    elapsed = time.perf_counter() - start
    best_progress = float(summary.get("best_progress", max(float(m["max_progress"]) for m in metrics)))
    population = int(summary.get("population", audit[0]["population"]))
    title = f"{population:,} IA apprennent à conduire : {best_progress * 100:.1f}% du circuit".replace(",", " ")
    completion_note = ""
    if scenes[0].get("narrative_metric") == "completed":
        baseline_completed = int(summary.get("baseline_completed", metrics[0].get("completed", 0)))
        best_completed = max(int(m.get("completed", 0)) for m in metrics)
        title = f"{population:,} IA au volant : de {baseline_completed} à {best_completed} tours validés".replace(",", " ")
        completion_note = f"Nombre de voitures terminant le circuit : référence {baseline_completed}, meilleure génération {best_completed} sur {population}. "
    publication = {"status": "draft", "title": title,
                   "description": f"Simulation réelle de {population} voitures contrôlées par des réseaux neuronaux. "
                                  f"{len(metrics)} générations par sélection, reproduction et mutations. "
                                  f"Progression maximale mesurée : {best_progress * 100:.1f}%. "
                                  + completion_note +
                                  "Montage de replays enregistrés, compteurs issus des états simulés. Effets sonores originaux, sans musique.",
                   "hashtags": ["#EvolutionLab", "#IntelligenceArtificielle", "#Neuroevolution", "#Simulation", "#Apprentissage"],
                   "video_path": str(output_path), "thumbnail_path": str(run_dir / "thumbnail.png"), "publish_requires_consent": True,
                   "generated_at": datetime.now(timezone.utc).isoformat()}
    metadata = {"video_path": str(output_path), "thumbnail_path": str(run_dir / "thumbnail.png"), "resolution": [width, height], "width": width, "height": height,
                "fps": fps, "duration": duration, "frame_count": total_frames, "segments": scenes, "events": events, "frame_audit": audit,
                "source_sha256": hashes, "training_summary": summary, "validation": validation, "audio": audio_metadata,
                "rendering_seconds": round(rendering_seconds, 3), "encoding_seconds": round(max(0, elapsed - rendering_seconds), 3),
                "total_export_seconds": round(elapsed, 3), "encoding_timing_note": "Wall time outside Pillow rendering; includes pipe waits, mux and validation.",
                "provenance": "Every frame references one stored generation, source index and true counters. No synthetic agents or invented outcomes.",
                "generated_at": datetime.now(timezone.utc).isoformat(), "title": title}
    _atomic_json(run_dir / "publication.json", publication)
    _atomic_json(run_dir / "video_metadata.json", metadata)
    _atomic_json(render_status, {"status": "complete", "frames": total_frames, "total_frames": total_frames, "progress": 1., "video_path": str(output_path), "elapsed_seconds": round(elapsed, 3)})
    return metadata

