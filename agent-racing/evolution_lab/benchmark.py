"""Repeatable local measurements; inference timing is not a learning comparison."""
from __future__ import annotations

from dataclasses import asdict
import math
import platform
from pathlib import Path
import statistics
import time

import numpy as np
import numba
import psutil


@numba.njit(cache=True)
def dense_batch(inputs, weights1, bias1, weights2, bias2):
    n, features = inputs.shape
    hidden = bias1.shape[1]
    output = np.empty((n, 2), dtype=np.float64)
    for i in range(n):
        activation = np.empty(hidden)
        for j in range(hidden):
            value = bias1[i, j]
            for k in range(features):
                value += inputs[i, k] * weights1[i, k, j]
            activation[j] = math.tanh(value)
        for j in range(2):
            value = bias2[i, j]
            for k in range(hidden):
                value += activation[k] * weights2[i, k, j]
            output[i, j] = math.tanh(value)
    return output


def numpy_batch(inputs, weights1, bias1, weights2, bias2):
    hidden = np.tanh(np.einsum("ni,nij->nj", inputs, weights1) + bias1)
    return np.tanh(np.einsum("ni,nij->nj", hidden, weights2) + bias2)


def _timed(function, repetitions=9):
    timings = []
    for _ in range(repetitions):
        start = time.perf_counter()
        function()
        timings.append(time.perf_counter() - start)
    return {"median_seconds": statistics.median(timings), "min_seconds": min(timings), "repetitions": repetitions}


def inference_benchmark(population=1500):
    rng = np.random.default_rng(20261011)
    shape = (8, 8, 2)
    inputs = rng.uniform(-1, 1, (population, shape[0]))
    w1 = rng.normal(0, .3, (population, shape[0], shape[1]))
    b1 = rng.normal(0, .3, (population, shape[1]))
    w2 = rng.normal(0, .3, (population, shape[1], shape[2]))
    b2 = rng.normal(0, .3, (population, shape[2]))
    args = inputs, w1, b1, w2, b2
    expected = numpy_batch(*args)
    start = time.perf_counter()
    actual = dense_batch(*args)
    compile_time = time.perf_counter() - start
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    result = {"population": population, "topology": list(shape),
              "method": "Identical dense weights, biases and tanh activation; one forward pass per car. Warm median; excludes evolution and topology search.",
              "numba_initial_call_seconds": compile_time,
              "numpy": _timed(lambda: numpy_batch(*args), 50),
              "numba": _timed(lambda: dense_batch(*args), 50),
              "python_same_loop": _timed(lambda: dense_batch.py_func(*args), 3)}
    try:
        from neat.nn import FeedForwardNetwork
        inputs_ids, hidden_ids, output_ids = list(range(-8, 0)), list(range(8)), [8, 9]
        networks = []
        for i in range(population):
            evaluations = [(j, math.tanh, sum, float(b1[i, j]), 1., [(k, float(w1[i, t, j])) for t, k in enumerate(inputs_ids)]) for j in hidden_ids]
            evaluations += [(node, math.tanh, sum, float(b2[i, j]), 1., [(k, float(w2[i, k, j])) for k in hidden_ids]) for j, node in enumerate(output_ids)]
            networks.append(FeedForwardNetwork(inputs_ids, output_ids, evaluations))
        samples = [row.tolist() for row in inputs]
        def neat_pass():
            return [network.activate(sample) for network, sample in zip(networks, samples)]
        np.testing.assert_allclose(np.asarray(neat_pass()), expected, atol=1e-12)
        result["neat_python"] = _timed(neat_pass)
    except ImportError:
        result["neat_python"] = {"status": "not installed; pip install -r requirements-benchmark.txt"}
    result["python_to_numba_speedup"] = result["python_same_loop"]["median_seconds"] / result["numba"]["median_seconds"]
    return result


def benchmark(output: Path):
    from evolution_lab.__main__ import atomic_json
    from evolution_lab.config import SimulationConfig
    from evolution_lab.training import train
    import json
    import tempfile
    process = psutil.Process()
    results = {"platform": platform.platform(), "python": platform.python_version(),
               "cpu": platform.processor(), "logical_cpus": psutil.cpu_count(),
               "numpy": np.__version__, "numba": numba.__version__,
               "inference": inference_benchmark(), "raycast": raycast_benchmark(), "simulation": []}
    with tempfile.TemporaryDirectory(prefix="evolution-benchmark-") as tmp:
        for population in (150, 1500):
            config = SimulationConfig(population=population, generations=3, min_generations=3, seed=83, budget_seconds=600)
            run_dir = Path(tmp) / str(population)
            cpu_before = process.cpu_times()
            start = time.perf_counter()
            train(config, run_dir)
            wall = time.perf_counter() - start
            cpu_after = process.cpu_times()
            cpu_seconds = (cpu_after.user + cpu_after.system) - (cpu_before.user + cpu_before.system)
            metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
            results["simulation"].append({"population": population, "config": asdict(config), "wall_seconds": wall,
                "cpu_seconds": cpu_seconds, "cpu_percent_one_core": 100 * cpu_seconds / wall,
                "rss_bytes_after": process.memory_info().rss, "peak_rss_bytes": getattr(process.memory_info(), "peak_wset", None),
                "metrics": metrics})
    atomic_json(output, results)
    return results


def raycast_benchmark():
    from evolution_lab.core.tracks import generate_track
    from evolution_lab.core.simulation import raycast
    track = generate_track()
    cases = [(float(p[0]), float(p[1]), float(a)) for p, a in zip(track.centerline, np.linspace(0, 2 * np.pi, len(track.centerline)))]
    def run(function):
        return [function(x, y, a, track.walls, 65.) for x, y, a in cases]
    np.testing.assert_allclose(run(raycast), run(raycast.py_func), atol=1e-10)
    compiled = _timed(lambda: run(raycast), 10)
    python = _timed(lambda: run(raycast.py_func), 3)
    return {"rays": len(cases), "wall_segments": len(track.walls), "numba": compiled,
            "python": python, "speedup": python["median_seconds"] / compiled["median_seconds"],
            "method": "Identical actual simulation raycast dispatcher versus its uncompiled Python function; warmed calls including Python invocation overhead."}
