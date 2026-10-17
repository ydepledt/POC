"""Train independent seeds and compare actual first versus evolved populations."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evolution_lab.__main__ import atomic_json
from evolution_lab.config import SimulationConfig
from evolution_lab.training import train


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 42, 123])
    parser.add_argument("--population", type=int, default=200)
    parser.add_argument("--generations", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("data/validation/learning.json"))
    args = parser.parse_args()
    results = []
    for seed in args.seeds:
        folder = args.output.parent / f"seed-{seed}-n{args.population}"
        config = SimulationConfig(seed=seed, population=args.population, generations=args.generations,
                                  min_generations=args.generations, budget_seconds=600)
        summary = train(config, folder, resume=(folder / "checkpoint.npz").exists())
        metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
        first, final = metrics[0], metrics[-1]
        results.append({"seed": seed, "population": args.population, "generations": len(metrics),
            "baseline_random_best_progress": first["max_progress"],
            "final_best_progress": final["max_progress"],
            "baseline_random_mean_score": first["mean_score"],
            "final_mean_score": final["mean_score"],
            "baseline_random_completed": first["completed"], "final_completed": final["completed"],
            "best_progress_improved": final["max_progress"] > first["max_progress"] + 1e-6,
            "mean_score_improved": final["mean_score"] > first["mean_score"] + 1e-6,
            "run_dir": str(folder.resolve()), "summary": summary})
        atomic_json(args.output, {"method": "Independent seeded GA runs; comparison with each run's unevolved random first generation on the same deterministic course. Evidence of fitting this course, not unseen-track generalization.", "runs": results})
        print(json.dumps(results[-1]), flush=True)


if __name__ == "__main__":
    main()
