"""Compiled headless bicycle simulation. Neural inputs are wall rays and speed.

Agents intentionally do not collide with each other: evolution compares all
brains in identical track conditions, without crowd-induced randomness.
"""
from dataclasses import dataclass
import math
import time
import numpy as np
from numba import njit


CAR_RADIUS = 2.0  # Encloses the rendered 3.6 x 1.7 vehicle, including corners.


@njit(cache=True)
def raycast(x, y, angle, walls, maximum):
    dx, dy = math.cos(angle), math.sin(angle)
    result = maximum
    for k in range(len(walls)):
        ax, ay, bx, by = walls[k]
        ex, ey = bx - ax, by - ay
        denominator = dx * ey - dy * ex
        if abs(denominator) < 1e-10:
            continue
        qx, qy = ax - x, ay - y
        distance = (qx * ey - qy * ex) / denominator
        if distance < 0 or distance >= result:
            continue
        along = (qx * dy - qy * dx) / denominator
        if 0 <= along <= 1:
            result = distance
    return result


@njit(cache=True)
def neural_action_compiled(genome, inputs, hidden_size):
    hidden = np.zeros(hidden_size, dtype=np.float64)
    cut = len(inputs) * hidden_size
    for h in range(hidden_size):
        value = float(genome[cut + h])
        for j in range(len(inputs)):
            value += inputs[j] * genome[j * hidden_size + h]
        hidden[h] = math.tanh(value)
    outputs = np.zeros(2, dtype=np.float64)
    for o in range(2):
        value = float(genome[-2 + o])
        for h in range(hidden_size):
            value += hidden[h] * genome[cut + hidden_size + h * 2 + o]
        outputs[o] = math.tanh(value)
    return outputs


@njit(cache=True)
def bicycle_step(x, y, heading, speed, steering, direction, throttle, dt, max_speed):
    desired = direction * .6
    steering += max(-1.5 * dt, min(1.5 * dt, desired - steering))
    acceleration = 8 * max(throttle, 0.) - 12 * max(-throttle, 0.) - .025 * speed * speed
    speed = max(0., min(max_speed, speed + acceleration * dt))
    heading += speed / 2.5 * math.tan(steering) * dt
    heading = math.atan2(math.sin(heading), math.cos(heading))
    x += speed * math.cos(heading) * dt
    y += speed * math.sin(heading) * dt
    return x, y, heading, speed, steering


@njit(cache=True)
def distance_to_road(x, y, starts, vectors, lengths):
    closest = 1e30
    for k in range(len(starts)):
        px, py = x - starts[k, 0], y - starts[k, 1]
        fraction = max(0., min(1., (px * vectors[k, 0] + py * vectors[k, 1]) / (lengths[k] * lengths[k])))
        dx, dy = px - fraction * vectors[k, 0], py - fraction * vectors[k, 1]
        closest = min(closest, dx * dx + dy * dy)
    return math.sqrt(closest)


@njit(cache=True)
def swept_disc_collision(old_x, old_y, x, y, walls, radius=CAR_RADIUS):
    """Exact distance between the motion segment and each wall segment.

    Sweeping an enclosing disc prevents corner grazing and tunneling even when
    both timestep endpoints are valid. Cheap bounding boxes reject distant walls.
    """
    mx, my = x - old_x, y - old_y
    move_squared = mx * mx + my * my
    radius_squared = radius * radius
    for k in range(len(walls)):
        ax, ay, bx, by = walls[k]
        if max(ax, bx) < min(old_x, x) - radius or min(ax, bx) > max(old_x, x) + radius:
            continue
        if max(ay, by) < min(old_y, y) - radius or min(ay, by) > max(old_y, y) + radius:
            continue
        ex, ey = bx - ax, by - ay
        edge_squared = ex * ex + ey * ey
        denominator = mx * ey - my * ex
        if abs(denominator) > 1e-12:
            qx, qy = ax - old_x, ay - old_y
            t = (qx * ey - qy * ex) / denominator
            u = (qx * my - qy * mx) / denominator
            if 0 <= t <= 1 and 0 <= u <= 1:
                return True
        # The minimum distance between two disjoint segments occurs at an end.
        for endpoint in range(2):
            px, py = (old_x, old_y) if endpoint == 0 else (x, y)
            t = max(0., min(1., ((px - ax) * ex + (py - ay) * ey) / max(edge_squared, 1e-20)))
            if (px - ax - t * ex)**2 + (py - ay - t * ey)**2 <= radius_squared:
                return True
            px, py = (ax, ay) if endpoint == 0 else (bx, by)
            t = max(0., min(1., ((px - old_x) * mx + (py - old_y) * my) / max(move_squared, 1e-20)))
            if (px - old_x - t * mx)**2 + (py - old_y - t * my)**2 <= radius_squared:
                return True
    return False


@njit(cache=True)
def advance_checkpoints(old_x, old_y, x, y, passed, starts, ends, tangents, lengths, cumulative, width):
    """Validate forward gate crossings in strict order, with lateral bounds.

    Projecting onto arbitrary nearest segments would permit shortcuts. Instead
    every checkpoint is a road-width gate; the next gate cannot be skipped.
    """
    count = len(starts)
    for _ in range(4):
        if passed >= count:
            return passed, 1.
        tx, ty = tangents[passed]
        ex, ey = ends[passed]
        before = (old_x - ex) * tx + (old_y - ey) * ty
        after = (x - ex) * tx + (y - ey) * ty
        if before <= 1e-7 and after >= 0 and after > before:
            fraction = -before / (after - before)
            crossing_x = old_x + fraction * (x - old_x) - ex
            crossing_y = old_y + fraction * (y - old_y) - ey
            if abs(-ty * crossing_x + tx * crossing_y) <= width / 2 - CAR_RADIUS:
                passed += 1
                continue
        break
    if passed >= count:
        return passed, 1.
    px, py = x - starts[passed, 0], y - starts[passed, 1]
    along = max(0., min(lengths[passed] * .999999, px * tangents[passed, 0] + py * tangents[passed, 1]))
    return passed, (cumulative[passed] + along) / cumulative[-1]


@njit(cache=True)
def _simulate(genomes, starts, ends, vectors, tangents, lengths, cumulative, walls,
              width, closed, sensors, hidden_size, dt, steps, stride, max_speed, sensor_range):
    count = len(genomes)
    frames = (steps + stride - 1) // stride + 1
    positions = np.zeros((frames, count, 2), np.float32)
    headings = np.zeros((frames, count), np.float32)
    alive_frames = np.zeros((frames, count), np.bool_)
    completed_frames = np.zeros((frames, count), np.bool_)
    progress_frames = np.zeros((frames, count), np.float32)
    score_frames = np.zeros((frames, count), np.float32)
    times = np.zeros(frames, np.float32)
    x = np.full(count, starts[0, 0])
    y = np.full(count, starts[0, 1])
    if not closed:
        x += tangents[0, 0] * (CAR_RADIUS + .1)
        y += tangents[0, 1] * (CAR_RADIUS + .1)
    heading = np.full(count, math.atan2(vectors[0, 1], vectors[0, 0]))
    speed = np.full(count, 4.)
    steering = np.zeros(count)
    alive = np.ones(count, np.bool_)
    completed = np.zeros(count, np.bool_)
    passed = np.zeros(count, np.int32)
    progress = np.zeros(count)
    scores = np.zeros(count)
    distance = np.zeros(count)
    last_improved = np.zeros(count)
    last_mark = np.zeros(count)
    crash_times = np.full(count, -1.)
    completion_times = np.full(count, -1.)
    inputs = np.zeros(sensors + 1)
    frame, active_steps = 0, 0
    for step in range(steps + 1):
        current_time = step * dt
        active_count = 0
        if step > 0:
            for a in range(count):
                if not alive[a]:
                    continue
                active_steps += 1
                for s in range(sensors):
                    angle = heading[a] - math.pi / 2 + math.pi * s / (sensors - 1)
                    inputs[s] = raycast(x[a], y[a], angle, walls, sensor_range) / sensor_range
                inputs[sensors] = speed[a] / max_speed
                action = neural_action_compiled(genomes[a], inputs, hidden_size)
                old_x, old_y = x[a], y[a]
                x[a], y[a], heading[a], speed[a], steering[a] = bicycle_step(
                    x[a], y[a], heading[a], speed[a], steering[a], action[0], action[1], dt, max_speed)
                new_passed, new_progress = advance_checkpoints(old_x, old_y, x[a], y[a], passed[a], starts, ends, tangents, lengths, cumulative, width)
                if not closed and new_passed == len(starts):
                    before = (old_x - ends[-1, 0]) * tangents[-1, 0] + (old_y - ends[-1, 1]) * tangents[-1, 1]
                    after = (x[a] - ends[-1, 0]) * tangents[-1, 0] + (y[a] - ends[-1, 1]) * tangents[-1, 1]
                    fraction = max(0., min(1., -before / max(after - before, 1e-12)))
                    x[a] = old_x + fraction * (x[a] - old_x)
                    y[a] = old_y + fraction * (y[a] - old_y)
                moved = math.sqrt((x[a] - old_x)**2 + (y[a] - old_y)**2)
                distance[a] += moved
                lateral = distance_to_road(x[a], y[a], starts, vectors, lengths)
                crossing = swept_disc_collision(old_x, old_y, x[a], y[a], walls)
                # An open route's last finish gate is inset before the physical cap.
                finished = new_passed == len(starts) and lateral + CAR_RADIUS < width / 2
                if lateral + CAR_RADIUS >= width / 2 or crossing:
                    alive[a] = False
                    crash_times[a] = current_time
                else:
                    passed[a] = new_passed
                    progress[a] = max(progress[a], new_progress)
                    if progress[a] > last_mark[a] + .004:
                        last_mark[a] = progress[a]
                        last_improved[a] = current_time
                    if finished:
                        completed[a] = True
                        alive[a] = False
                        completion_times[a] = current_time
                    elif current_time - last_improved[a] > 4.:
                        alive[a] = False
                scores[a] = progress[a] * 1000 + passed[a] * .2
                if completed[a]:
                    scores[a] += 300 + (steps * dt - completion_times[a]) * 2
                elif not alive[a]:
                    scores[a] -= 2
                if alive[a]:
                    active_count += 1
        else:
            active_count = count
        if step % stride == 0 or step == steps or active_count == 0:
            for a in range(count):
                positions[frame, a, 0], positions[frame, a, 1] = x[a], y[a]
                headings[frame, a] = heading[a]
                alive_frames[frame, a] = alive[a]
                completed_frames[frame, a] = completed[a]
                progress_frames[frame, a] = progress[a]
                score_frames[frame, a] = scores[a]
            times[frame] = current_time
            frame += 1
        if active_count == 0:
            break
    return (positions[:frame], headings[:frame], alive_frames[:frame], completed_frames[:frame],
            progress_frames[:frame], score_frames[:frame], times[:frame], scores, progress,
            passed, completed, distance, crash_times, completion_times, active_steps, step)


@dataclass
class Evaluation:
    scores: np.ndarray
    progress: np.ndarray
    checkpoints: np.ndarray
    completed: np.ndarray
    distance: np.ndarray
    replay: dict
    metrics: dict


def simulate_generation(track, genomes, config, generation=1):
    from .evolution import genome_size
    genomes = np.ascontiguousarray(genomes, dtype=np.float32)
    if genomes.shape != (config.population, genome_size(config.sensors, config.hidden_size)) or not np.isfinite(genomes).all():
        raise ValueError("Population shape or genome values are invalid")
    started = time.perf_counter()
    result = _simulate(genomes, track.starts, track.ends, track.vectors, track.tangents,
                       track.segment_lengths, track.cumulative, track.walls, track.width, track.closed,
                       config.sensors, config.hidden_size, config.dt,
                       int(round(config.max_seconds / config.dt)),
                       max(1, int(round(1 / (config.replay_fps * config.dt)))),
                       config.max_speed, config.sensor_range)
    (positions, headings, alive, completed_frames, progress_frames, score_frames, times,
     scores, progress, passed, completed, distance, crash_times, completion_times, active_steps, step) = result
    elapsed = time.perf_counter() - started
    replay = {"positions": positions, "headings": headings, "alive": alive,
              "completed": completed_frames, "progress": progress_frames, "scores": score_frames,
              "times": times, "generation": np.asarray(generation, dtype=np.int32),
              "crash_times": crash_times.astype(np.float32),
              "completion_times": completion_times.astype(np.float32)}
    metrics = {"generation": generation, "population": len(genomes), "alive": int(alive[-1].sum()),
               "mean_score": float(np.mean(scores)), "best_score": float(np.max(scores)),
               "max_progress": float(np.max(progress)), "max_distance": float(np.max(distance)),
               "checkpoint_counts": [int(np.sum(passed >= k)) for k in range(1, len(track.ends) + 1)],
               "completed": int(completed.sum()), "generation_seconds": elapsed,
               "steps_per_second": float(active_steps / max(elapsed, 1e-9)),
               "simulation_steps": int(step), "agent_steps": int(active_steps),
               "simulated_seconds": float(times[-1]),
               "first_completion_seconds": float(completion_times[completed].min()) if completed.any() else None,
               "crashed": int((crash_times >= 0).sum()),
               "mean_progress": float(np.mean(progress))}
    return Evaluation(scores, progress, passed, completed, distance, replay, metrics)
