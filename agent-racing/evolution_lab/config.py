"""Validated, serializable experiment configuration."""
from dataclasses import asdict, dataclass
import math


@dataclass
class SimulationConfig:
    population: int = 1500
    generations: int = 30
    seed: int = 42
    track: str = "oval"
    difficulty: str = "easy"
    max_seconds: float = 40.0
    budget_seconds: float = 600.0
    mutation_rate: float = 0.15
    mutation_strength: float = 0.25
    elite_fraction: float = 0.05
    sensors: int = 7
    video_duration: float = 24.0
    hidden_size: int = 8
    dt: float = 0.1
    replay_fps: int = 10
    max_speed: float = 22.0
    sensor_range: float = 65.0
    track_width: float | None = None
    track_length: float = 650.0
    corners: int = 8
    hairpins: int = 0
    max_curvature: float = 0.16
    closed: bool = True
    min_generations: int = 6
    target_completion_fraction: float = 0.1
    stagnation_generations: int = 6
    replay_limit: int = 9
    max_replay_memory_mb: float = 256.0
    visual_style: str = "midnight"

    def __post_init__(self):
        for name, lo, hi in (("population", 2, 10000), ("generations", 1, 10000),
                             ("sensors", 5, 9), ("hidden_size", 2, 32),
                             ("replay_fps", 1, 30), ("corners", 4, 24),
                             ("hairpins", 0, 4), ("replay_limit", 4, 30)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
                raise ValueError(f"{name} must be an integer between {lo} and {hi}")
        for name, lo, hi in (("max_seconds", 1, 600), ("budget_seconds", 1, 86400),
                             ("mutation_rate", 0, 1), ("mutation_strength", 0, 3),
                             ("elite_fraction", 0.001, 0.5), ("dt", 0.025, 0.1),
                             ("max_speed", 5, 35), ("sensor_range", 10, 150),
                             ("track_length", 200, 1600), ("max_curvature", 0.015, 0.3),
                             ("video_duration", 2, 60), ("target_completion_fraction", 0.001, 1),
                             ("max_replay_memory_mb", 32, 1024)):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"{name} must be finite and between {lo} and {hi}")
        if self.track_width is not None and not 8 <= self.track_width <= 35:
            raise ValueError("track_width must be between 8 and 35")
        if self.track not in {"oval", "kidney", "technical", "chicane", "procedural"}:
            raise ValueError("unknown track")
        if self.difficulty not in {"easy", "medium", "hard", "extreme"}:
            raise ValueError("unknown difficulty")
        if not isinstance(self.seed, int) or not 0 <= self.seed < 2**32:
            raise ValueError("seed must be between 0 and 2**32-1")
        if not isinstance(self.min_generations, int) or self.min_generations < 1:
            raise ValueError("min_generations must be a positive integer")
        if not isinstance(self.stagnation_generations, int) or self.stagnation_generations < 1:
            raise ValueError("stagnation_generations must be a positive integer")
        if not isinstance(self.closed, bool):
            raise ValueError("closed must be boolean")
        stride = max(1, round(1 / (self.replay_fps * self.dt)))
        frames = math.ceil(round(self.max_seconds / self.dt) / stride) + 1
        if frames * self.population * 22 > self.max_replay_memory_mb * 1024**2:
            raise ValueError("Replay memory budget exceeded: reduce population, duration, or replay_fps")

    def to_dict(self):
        return asdict(self)
