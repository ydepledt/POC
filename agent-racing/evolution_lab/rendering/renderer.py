"""Original Pillow art direction for vertical Evolution Lab replay films."""

from __future__ import annotations

import colorsys
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


INK = "#182622"
PAPER = "#F1F2EB"
GREEN = "#BCF347"
MUTED = "#78827C"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, max(size, 8))
    return ImageFont.load_default(size=max(size, 8))


def _smooth(value: float) -> float:
    value = float(np.clip(value, 0, 1))
    return value * value * (3 - 2 * value)


class ReplayRenderer:
    """Render a single true replay state plus its measured counters.

    Layout coordinates use a 1080 × 1920 design grid. All source cars are drawn;
    positions are never offset or cloned to exaggerate the visible population.
    """

    def __init__(self, track: dict, metrics: list[dict], width: int = 1080, height: int = 1920):
        self.width, self.height = width, height
        self.s = width / 1080
        self.sy = height / 1920
        self.track = track
        self.points = np.asarray(track["centerline"], dtype=float)
        if track.get("closed", True) and not np.allclose(self.points[0], self.points[-1]):
            self.points = np.vstack([self.points, self.points[0]])
        self.road_width = float(track["width"])
        self.low = self.points.min(axis=0) - self.road_width * .75
        self.high = self.points.max(axis=0) + self.road_width * .75
        self.middle = (self.high + self.low) / 2
        self.view_box = tuple(self._xy(x, y) for x, y in [(56, 490), (1024, 1410)])
        self.vw = self.view_box[1][0] - self.view_box[0][0]
        self.vh = self.view_box[1][1] - self.view_box[0][1]
        self.base_scale = min(self.vw / (self.high[0] - self.low[0]), self.vh / (self.high[1] - self.low[1])) * .9
        self.fonts = {str(size) + str(bold): _font(round(size * self.s), bold) for size in [19, 22, 24, 25, 27, 30, 32, 36, 40, 46, 54, 58, 66, 96, 110] for bold in [False, True]}
        self.metrics = metrics
        self.completion_mode = bool(metrics) and float(metrics[0].get("max_progress", 0)) >= .95 and max(int(m.get("completed", 0)) for m in metrics) > 0
        self.colors = [tuple(round(v * 255) for v in colorsys.hsv_to_rgb(.11 + i % 17 / 24, .72, .98)) for i in range(10000)]
        self.previous_center = None
        self.previous_generation = None
        self.mask = Image.new("L", (self.vw, self.vh))
        ImageDraw.Draw(self.mask).rounded_rectangle((0, 0, self.vw - 1, self.vh - 1), radius=max(2, round(28 * self.s)), fill=255)

    def _xy(self, x: float, y: float) -> tuple[int, int]:
        return round(x * self.s), round(y * self.sy)

    def _text(self, draw: ImageDraw.ImageDraw, xy, text: str, size=30, fill=INK, bold=False):
        font = self.fonts.get(str(size) + str(bold)) or _font(round(size * self.s), bold)
        draw.text(self._xy(*xy), text, font=font, fill=fill)

    def _line(self, draw, box, fill, width=1):
        draw.line([self._xy(box[0], box[1]), self._xy(box[2], box[3])], fill=fill, width=max(1, round(width * self.s)))

    def _rect(self, draw, box, fill, radius=0, outline=None):
        draw.rounded_rectangle([self._xy(box[0], box[1]), self._xy(box[2], box[3])], radius=round(radius * self.s), fill=fill, outline=outline)

    def render(self, replay: dict, index: int, scene: dict, phase: float, output_time: float, duration: float) -> tuple[Image.Image, dict]:
        generation = int(replay["generation"])
        positions = replay["positions"][index]
        headings = replay["headings"][index]
        alive = replay["alive"][index].astype(bool)
        progress = replay["progress"][index]
        scores = replay["scores"][index]
        finished = replay.get("completed")
        finished = np.zeros(len(alive), dtype=bool) if finished is None else finished[index].astype(bool)
        active = int(alive.sum())
        best_progress = float(np.max(progress))
        best_score = float(np.max(scores))
        leader = int(np.argmax(np.where(alive, progress, -1))) if active else int(np.argmax(progress))
        image = Image.new("RGB", (self.width, self.height), PAPER)
        draw = ImageDraw.Draw(image)
        self._rect(draw, (56, 72, 98, 114), INK, 11)
        self._line(draw, (66, 94, 76, 103), GREEN, 3)
        self._line(draw, (76, 103, 89, 84), GREEN, 3)
        self._text(draw, (114, 76), "EVOLUTION LAB", 27, bold=True)
        self._text(draw, (835, 80), "NEURO / AUTO", 19, MUTED)
        self._line(draw, (56, 142, 1024, 142), "#D2D8CF")
        population = len(alive)
        self._text(draw, (56, 172), f"{population:,}".replace(",", " ") + " IA AU DÉPART.", 66, bold=True)
        self._text(draw, (59, 253), "Peuvent-elles apprendre à boucler ce circuit ?", 32, MUTED)

        self._text(draw, (59, 331), "GÉNÉRATION", 22, MUTED, True)
        self._text(draw, (53, 356), f"{generation:02d}", 96, bold=True)
        self._line(draw, (310, 335, 310, 452), "#D2D8CF")
        self._text(draw, (344, 332), "EN PISTE", 22, MUTED, True)
        self._text(draw, (339, 370), f"{active:,}".replace(",", " "), 58, bold=True)
        self._text(draw, (346, 438), f"sur {population:,}".replace(",", " "), 22, MUTED)
        self._text(draw, (754, 332), "PROGRESSION", 22, MUTED, True)
        self._text(draw, (750, 372), f"{best_progress * 100:.1f}%", 58, bold=True)
        self._text(draw, (755, 438), f"score {best_score:,.0f}".replace(",", " "), 22, MUTED)

        viewport = self._render_track(replay, index, positions, headings, alive, finished, leader, scene, phase)
        image.paste(viewport, self.view_box[0], self.mask)
        draw = ImageDraw.Draw(image)
        self._rect(draw, (80, 514, 352, 559), INK, 20)
        mode = "VUE D'ENSEMBLE" if scene["camera"] == "overview" else "SUIVI DU LEADER" if scene["camera"] == "leader" else "ZONE DE COLLISION" if scene["type"] == "collision" else "ZONE D'ÉLIMINATION"
        self._text(draw, (99, 523), mode, 19, "#FFFFFF", True)
        replay_time = float(replay["times"][index])
        self._rect(draw, (820, 514, 997, 559), "#FFFFFF", 20)
        self._text(draw, (841, 523), f"t = {replay_time:05.1f} s", 19, INK, True)
        self._rect(draw, (80, 1350, 468, 1385), "#E7EAE1", 14)
        self._text(draw, (95, 1356), "REPLAY • ÉTATS RÉELS ENREGISTRÉS", 19, MUTED)
        if np.any(finished):
            self._rect(draw, (724, 1343, 997, 1389), GREEN, 20)
            self._text(draw, (744, 1355), f"{int(finished.sum())} TOUR(S) VALIDÉ(S)", 19, INK, True)

        self._text(draw, (59, 1450), scene["eyebrow"], 22, "#58782F", True)
        self._text(draw, (56, 1490), scene["title"], 46, bold=True)
        self._text(draw, (59, 1552), scene["subtitle"], 27, MUTED)
        self._rect(draw, (58, 1618, 1022, 1632), "#D4DACF", 7)
        if best_progress > 0:
            self._rect(draw, (58, 1618, 58 + 964 * min(best_progress, 1), 1632), "#74A23A", 7)
        self._text(draw, (59, 1668), "TOURS VALIDÉS PAR GÉNÉRATION" if self.completion_mode else "DISTANCE MAX. PAR GÉNÉRATION", 19, MUTED, True)
        if self.completion_mode:
            self._text(draw, (870, 1668), f"MAX. {max(int(m.get('completed', 0)) for m in self.metrics)}", 19, MUTED, True)
        self._chart(draw, generation)
        self._line(draw, (56, 1810, 1024, 1810), "#D2D8CF")
        self._text(draw, (58, 1840), "SÉLECTION  /  MUTATION  /  RECOMMENCER", 19, MUTED)
        self._text(draw, (893, 1840), f"{int(output_time):02d} / {int(duration):02d}s", 19, MUTED)
        # The very thin edge line communicates edit progress without obscuring data.
        self._rect(draw, (0, 1909, 1080 * min(output_time / duration, 1), 1920), INK)
        return image, {"generation": generation, "replay_index": index, "replay_time": replay_time, "population": population,
                       "alive": active, "completed": int(finished.sum()), "best_progress": best_progress, "best_score": best_score}

    def _render_track(self, replay, index, positions, headings, alive, completed, leader, scene, phase):
        focus = .8 * _smooth((phase - .1) / .55)
        if scene["camera"] == "overview":
            zoom, center = 1., self.middle.copy()
        elif scene["camera"] == "collision":
            collision_center = np.asarray(scene.get("focus", self.middle), dtype=float)
            zoom, center = 1 + focus * .62, self.middle * (1 - focus) + collision_center * focus
        else:
            zoom, center = 1 + focus * .78, self.middle * (1 - focus) + positions[leader] * focus
        if self.previous_generation != int(replay["generation"]):
            self.previous_center = center
        if self.previous_center is not None:
            center = self.previous_center * .9 + center * .1
        self.previous_center, self.previous_generation = center, int(replay["generation"])
        scale = self.base_scale * zoom
        def project(points):
            return (np.asarray(points) - center) * scale + np.array([self.vw / 2, self.vh / 2])
        track_image = Image.new("RGB", (self.vw, self.vh), "#E4E8DC")
        draw = ImageDraw.Draw(track_image)
        # Quiet graph-paper field gives perspective and remains readable when panning.
        for axis in (0, 1):
            start = math.floor((center[axis] - (self.vw if axis == 0 else self.vh) / scale) / 20) * 20
            for world in np.arange(start, start + (self.vw + self.vh) / scale + 60, 20):
                pixel = (world - center[axis]) * scale + (self.vw if axis == 0 else self.vh) / 2
                if axis == 0:
                    draw.line((pixel, 0, pixel, self.vh), fill="#DAE1D2")
                else:
                    draw.line((0, pixel, self.vw, pixel), fill="#DAE1D2")
        road = [tuple(p) for p in project(self.points)]
        rw = max(6, round(self.road_width * scale))
        draw.line(road, fill="#CCD5C4", width=rw + max(4, round(13 * self.s)), joint="curve")
        draw.line(road, fill="#F8FAF2", width=rw + max(2, round(5 * self.s)), joint="curve")
        draw.line(road, fill="#35403E", width=rw, joint="curve")
        # Intermittent center markings follow actual track geometry.
        for j in range(0, len(road) - 1, 5):
            draw.line(road[j:min(j + 2, len(road))], fill="#52615B", width=max(1, round(self.s)))
        checkpoints = np.asarray(self.track.get("checkpoints", []))
        # A track can have hundreds of fitness gates: show a legible subset only.
        for j in range(0, len(checkpoints), max(1, math.ceil(len(checkpoints) / 12))):
            point = checkpoints[j]
            near = int(np.argmin(np.sum((self.points - point) ** 2, axis=1)))
            tangent = self.points[(near + 1) % len(self.points)] - self.points[max(0, near - 1)]
            norm = np.array([-tangent[1], tangent[0]]) / max(np.linalg.norm(tangent), .001)
            ends = project([point - norm * self.road_width * .45, point + norm * self.road_width * .45])
            draw.line([tuple(p) for p in ends], fill="#70806D" if j else "#DFE7C5", width=max(1, round(2 * self.s)))
        # True leader trajectory only, never a suggested path or future information.
        trail = project(replay["positions"][max(0, index - 16):index + 1, leader])
        if len(trail) > 1:
            draw.line([tuple(p) for p in trail], fill="#B9D16F", width=max(1, round(2 * self.s)))
        car_pixels = project(positions)
        length = max(4.5 * self.s, 3.6 * scale)
        width = max(2.5 * self.s, 1.7 * scale)
        cos, sin = np.cos(headings), np.sin(headings)
        forward = np.stack([cos, sin], axis=-1) * length / 2
        side = np.stack([-sin, cos], axis=-1) * width / 2
        polygons = np.stack([car_pixels + forward + side, car_pixels + forward - side, car_pixels - forward - side, car_pixels - forward + side], axis=1)
        visible = (car_pixels[:, 0] > -length) & (car_pixels[:, 0] < self.vw + length) & (car_pixels[:, 1] > -length) & (car_pixels[:, 1] < self.vh + length)
        # Crashed cars stay visible, with live agents drawn last for honest visibility.
        for state in (0, 1):
            ids = np.flatnonzero(visible & ((alive | completed) if state else ~(alive | completed)))
            for car in ids:
                color = "#90A08D" if not state else "#BCF347" if completed[car] else self.colors[car % len(self.colors)]
                poly = [tuple(p) for p in polygons[car]]
                draw.polygon(poly, fill=color)
                if state and length > 9:
                    window = car_pixels[car] + forward[car] * .2
                    draw.line([tuple(window - side[car] * .65), tuple(window + side[car] * .65)], fill="#203530", width=max(1, round(self.s)))
        if visible[leader]:
            x, y = car_pixels[leader]
            radius = max(length, 9 * self.s)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline="#D9FF82", width=max(1, round(2 * self.s)))
        return track_image

    def _chart(self, draw, generation):
        count = max(1, len(self.metrics))
        gap = 4 if count < 40 else 2
        bar_width = max(1, (964 - gap * (count - 1)) / count)
        for i, metric in enumerate(self.metrics):
            if self.completion_mode:
                scale = max(1, max(int(m.get("completed", 0)) for m in self.metrics))
                level = int(metric.get("completed", 0)) / scale
            else:
                level = max(0, min(1, float(metric.get("max_progress", 0))))
            bar_height = max(3, level * 77)
            x = 58 + i * (bar_width + gap)
            color = INK if int(metric["generation"]) == generation else "#9CBA70" if int(metric["generation"]) < generation else "#D1D9C8"
            self._rect(draw, (x, 1782 - bar_height, x + bar_width, 1782), color, 2)

