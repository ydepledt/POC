"""Small original procedural sound effects; no music or external assets."""

from __future__ import annotations

from pathlib import Path
import wave

import numpy as np


def synthesize_audio(path: Path, duration: float, scenes: list[dict], audit: list[dict], rate: int = 48000) -> dict:
    samples = np.zeros(round(duration * rate), dtype=np.float32)
    rng = np.random.default_rng(7301)
    effects = []

    def effect(start: float, length: float, kind: str, strength: float = 1.):
        offset = round(start * rate)
        length = min(round(length * rate), len(samples) - offset)
        if length <= 0:
            return
        t = np.arange(length, dtype=np.float32) / rate
        if kind == "collision":
            signal = rng.uniform(-1, 1, length) * np.exp(-t * 45) * .075
            signal += np.sin(2 * np.pi * 91 * t) * np.exp(-t * 30) * .07
        elif kind == "elimination":
            signal = np.sin(2 * np.pi * 170 * t) * np.exp(-t * 50) * .035
        elif kind == "record":
            frequency = np.where(t < .13, 523.25, np.where(t < .26, 659.25, 783.99))
            phase = 2 * np.pi * np.cumsum(frequency) / rate
            signal = np.sin(phase) * np.minimum(t * 50, 1) * np.exp(-t * 4) * .12
        else:
            signal = np.sin(2 * np.pi * (130 * t + 350 * t * t)) * np.sin(np.pi * np.clip(t / .16, 0, 1)) ** 2 * .075
        samples[offset:offset + length] += signal.astype(np.float32) * strength
        effects.append({"time": round(start, 3), "type": kind})

    for scene in scenes:
        effect(scene["output_start"], .17, "transition")
        for impact_time in scene.get("collision_cues", []):
            if scene["source_start"] <= impact_time <= scene["source_end"]:
                phase = (impact_time - scene["source_start"]) / max(.001, scene["source_end"] - scene["source_start"])
                effect(scene["output_start"] + phase * (scene["output_end"] - scene["output_start"]), .18, "collision")
        cue = scene.get("record_cue_time")
        if cue is not None and scene["type"] != "collision":
            phase = (cue - scene["source_start"]) / max(.001, scene["source_end"] - scene["source_start"])
            cue_time = scene["output_start"] + float(np.clip(phase, 0, 1)) * (scene["output_end"] - scene["output_start"])
            effect(cue_time, .52, "record")
    prior = None
    last_collision = -1.
    for frame in audit:
        if prior and frame["generation"] == prior["generation"]:
            lost = prior["alive"] - frame["alive"] - max(0, frame["completed"] - prior["completed"])
            if lost >= max(2, frame["population"] * .025) and frame["video_time"] - last_collision > .22:
                # Deactivation may mean stagnation, so this is a neutral UI tick.
                effect(frame["video_time"], .18, "elimination", min(1., .3 + lost / frame["population"]))
                last_collision = frame["video_time"]
        prior = frame
    # Clean fade avoids a click at the exported file's boundaries.
    fade = min(len(samples) // 2, rate // 20)
    samples[:fade] *= np.linspace(0, 1, fade)
    samples[-fade:] *= np.linspace(1, 0, fade)
    pcm = (np.clip(samples, -.9, .9) * 32767).astype("<i2")
    stereo = np.column_stack([pcm, pcm]).ravel()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(stereo.tobytes())
    return {"type": "original_procedural_effects", "music": False, "sample_rate": rate, "effects": effects}

