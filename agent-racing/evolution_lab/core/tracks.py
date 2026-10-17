"""Procedural courses validated geometrically and with a bicycle controller.

The reference driver is used ONLY for validation, never as an evolved brain.
"""
from dataclasses import dataclass, field
import numpy as np
from scipy.interpolate import CubicSpline
from shapely.geometry import LineString


@dataclass
class Track:
    name: str
    width: float
    closed: bool
    centerline: np.ndarray
    validation: dict = field(default_factory=dict)

    def __post_init__(self):
        self.centerline = np.asarray(self.centerline, dtype=np.float64)
        points = self.centerline
        self.starts = points if self.closed else points[:-1]
        self.ends = np.roll(points, -1, axis=0) if self.closed else points[1:].copy()
        if not self.closed:
            # Finish before the physical cap so the full car can cross safely.
            final_direction = points[-1] - points[-2]
            self.ends[-1] -= final_direction / max(np.linalg.norm(final_direction), 1e-9) * 2.2
        self.vectors = self.ends - self.starts
        self.segment_lengths = np.linalg.norm(self.vectors, axis=1)
        self.cumulative = np.r_[0., np.cumsum(self.segment_lengths)]
        self.length = float(self.cumulative[-1])
        self.tangents = self.vectors / np.maximum(self.segment_lengths[:, None], 1e-9)
        line = LineString(np.vstack((points, points[0])) if self.closed else points)
        self.road = line.buffer(self.width / 2, cap_style=2, join_style=1)
        walls = []
        if self.road.geom_type == "Polygon":
            for ring in [self.road.exterior, *self.road.interiors]:
                coords = np.asarray(ring.coords)
                walls.extend(np.concatenate((coords[:-1], coords[1:]), axis=1))
        self.walls = np.asarray(walls, dtype=np.float64).reshape(-1, 4)

    def to_dict(self):
        return {"name": self.name, "width": self.width, "closed": self.closed,
                "centerline": self.centerline.tolist(), "checkpoints": self.ends.tolist(),
                "length": self.length, "validation": self.validation,
                "car_length": 3.6, "car_width": 1.7, "car_radius": 2.0}

    @classmethod
    def from_dict(cls, data):
        return cls(data["name"], data["width"], data["closed"], data["centerline"], data.get("validation", {}))


def _resample(points, length, closed):
    points = np.asarray(points)
    if closed:
        points = np.vstack((points, points[0]))
    cumulative = np.r_[0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    points = points * (length / cumulative[-1])
    cumulative *= length / cumulative[-1]
    distances = np.linspace(0, length, max(40, int(length / 5)) + (0 if closed else 1), endpoint=not closed)
    return np.column_stack([np.interp(distances, cumulative, points[:, k]) for k in range(2)])


def generate_track(name="oval", seed=42, difficulty="easy", *, width=None,
                   length=650., corners=8, hairpins=0, max_curvature=.16, closed=True):
    if name not in {"oval", "kidney", "technical", "chicane", "procedural"}:
        raise ValueError(f"Unknown track: {name}")
    if difficulty not in {"easy", "medium", "hard", "extreme"}:
        raise ValueError(f"Unknown difficulty: {difficulty}")
    rng = np.random.default_rng(seed)
    level = {"easy": 0, "medium": 1, "hard": 2, "extreme": 3}[difficulty]
    road_width = float(width if width is not None else [18, 15, 13, 11][level])
    # Smooth radial curves guarantee connected candidate paths. Validation rejects
    # offset overlap and excessive curvature; random courses retry deterministically.
    for attempt in range(40):
        theta = np.linspace(0, 2 * np.pi, 1200, endpoint=False)
        if name == "oval":
            radial = np.ones_like(theta)
        elif name == "kidney":
            radial = 1 + .20 * np.cos(2 * theta) + .10 * np.sin(3 * theta)
        elif name == "technical":
            radial = 1 + (.10 + .025 * level) * np.cos(3 * theta) + .06 * np.sin(4 * theta)
        elif name == "chicane":
            # Six alternating bends are distinct from the broad technical lobes.
            radial = 1 + .08 * np.cos(2 * theta) + (.05 + .01 * level) * np.sin(6 * theta)
        else:
            count = max(6, corners)
            angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
            noise = rng.uniform(-1, 1, count) * (.12 + .025 * level)
            if hairpins:
                noise[np.arange(hairpins) * max(1, count // hairpins)] -= .12
            spline = CubicSpline(np.r_[angles, 2 * np.pi], np.r_[noise, noise[0]], bc_type="periodic")
            radial = 1 + spline(theta)
        if attempt:
            radial = 1 + (radial - 1) * .95**attempt
        points = np.column_stack((85 * radial * np.cos(theta), 115 * radial * np.sin(theta)))
        if not closed:
            # An open route has real start/end caps and no wraparound checkpoints.
            points = points[:1000]
        points = _resample(points, length, closed)
        track = Track(name, road_width, closed, points)
        validation = validate_track(track, max_curvature=max_curvature, reference=True)
        if validation["valid"]:
            track.validation = {**validation, "seed": seed, "difficulty": difficulty,
                                "attempts": attempt + 1, "requested_corners": corners,
                                "requested_hairpins": hairpins,
                                "shape_parameters_are_hints": True}
            return track
    raise ValueError("Could not produce a traversable track for these width/length/curvature settings")


def validate_track(track, *, max_curvature=.16, reference=True):
    errors = []
    p = track.centerline
    if len(p) < 4 or not np.isfinite(p).all() or track.width < 5:
        errors.append("insufficient or invalid geometry")
    if np.any(track.segment_lengths < .1):
        errors.append("duplicate checkpoints")
    line = LineString(np.vstack((p, p[0])) if track.closed else p)
    if not line.is_simple:
        errors.append("centerline self-intersects")
    if not track.road.is_valid or track.road.geom_type != "Polygon":
        errors.append("road is not a continuous polygon")
    if track.closed and len(track.road.interiors) != 1:
        errors.append("road offsets overlap or erase the interior")
    angles = np.arctan2(track.vectors[:, 1], track.vectors[:, 0])
    turn = np.angle(np.exp(1j * (np.roll(angles, -1) - angles)))
    if not track.closed:
        turn = turn[:-1]
    curvature = np.abs(turn) / track.segment_lengths[:len(turn)]
    max_k = float(np.max(curvature)) if len(curvature) else float("inf")
    if max_k > min(max_curvature, 1.7 / track.width):
        errors.append("curvature exceeds road/vehicle envelope")
    # Detect nonlocal arms whose road corridors overlap. Adjacent segments need
    # enough arc-length separation before a Euclidean proximity is suspicious.
    delta = np.abs(track.cumulative[:-1, None] - track.cumulative[None, :-1])
    if track.closed:
        delta = np.minimum(delta, track.length - delta)
    distances = np.linalg.norm(track.starts[:, None] - track.starts[None, :], axis=2)
    if np.any((delta > track.width * 2.5) & (distances < track.width * 1.02)):
        errors.append("nonlocal road corridors overlap")
    reference_result = {"completed": False}
    if reference and not errors:
        reference_result = reference_traversal(track)
        if not reference_result["completed"]:
            errors.append("reference bicycle controller did not finish")
    return {"valid": not errors, "errors": errors, "max_curvature": max_k,
            "reference": reference_result}


def reference_traversal(track):
    """Pure pursuit with the same dt, steering and bicycle model as agents."""
    from .simulation import bicycle_step, swept_disc_collision
    position = track.centerline[0].copy()
    if not track.closed:
        position += track.tangents[0] * 2.1
    heading = float(np.arctan2(track.vectors[0, 1], track.vectors[0, 0]))
    speed, steering, passed = 4., 0., 0
    dt, radius, max_error = .05, 2.0, 0.
    for step in range(int(track.length / 3 / dt)):
        seg = min(passed, len(track.starts) - 1)
        target_index = min(seg + 2, len(track.ends) - 1)
        if track.closed:
            target_index = (seg + 2) % len(track.ends)
        target = track.ends[target_index]
        difference = target - position
        angle = np.arctan2(np.sin(np.arctan2(difference[1], difference[0]) - heading),
                           np.cos(np.arctan2(difference[1], difference[0]) - heading))
        desired = np.clip(np.arctan2(5. * np.sin(angle), np.linalg.norm(difference)), -.6, .6)
        target_speed = 10. / (1 + 2 * abs(angle))
        throttle = np.clip((target_speed - speed) / 3, -1., 1.)
        previous = position.copy()
        px, py, heading, speed, steering = bicycle_step(position[0], position[1], heading, speed, steering, desired / .6, throttle, dt, 22.)
        position[:] = px, py
        if not track.closed and passed == len(track.ends) - 1:
            before = np.dot(previous - track.ends[-1], track.tangents[-1])
            after = np.dot(position - track.ends[-1], track.tangents[-1])
            if before <= 0 <= after and after > before:
                position[:] = previous + (-before / (after - before)) * (position - previous) + track.tangents[-1] * 1e-8
        projection = np.clip(np.einsum("ij,ij->i", position - track.starts, track.vectors) /
                             np.maximum(track.segment_lengths**2, 1e-9), 0, 1)
        distance = float(np.min(np.linalg.norm(position - track.starts - projection[:, None] * track.vectors, axis=1)))
        max_error = max(max_error, distance)
        collision = swept_disc_collision(previous[0], previous[1], position[0], position[1], track.walls)
        if distance + radius >= track.width / 2 or collision:
            return {"completed": False, "max_lateral_error": max_error, "steps": step}
        for _ in range(3):
            seg = min(passed, len(track.starts) - 1)
            if np.dot(position - track.ends[seg], track.tangents[seg]) >= 0:
                passed += 1
                if passed == len(track.ends):
                    return {"completed": True, "seconds": (step + 1) * dt,
                            "max_lateral_error": max_error, "checkpoints": passed}
            else:
                break
    return {"completed": False, "max_lateral_error": max_error, "checkpoints": passed}
