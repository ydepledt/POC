"""Audit that every video-frame counter comes from the referenced replay."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    folder = args.run_dir
    metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    indexed = {int(row["generation"]): row for row in metrics}
    result = []
    for path in sorted((folder / "replays").glob("gen_*.npz")):
        with np.load(path, allow_pickle=False) as replay:
            generation = int(replay["generation"])
            assert generation in indexed
            positions, alive, progress = replay["positions"], replay["alive"], replay["progress"]
            assert positions.shape[:2] == alive.shape == progress.shape
            assert positions.shape[1] == indexed[generation]["population"]
            assert np.isfinite(positions).all()
            assert ((progress >= 0) & (progress <= 1.00001)).all()
            assert np.all(np.diff(replay["times"]) > 0)
            assert not np.any(np.diff(alive.astype(int), axis=0) > 0), "A terminated agent became alive"
            assert np.isclose(np.max(progress), indexed[generation]["max_progress"], atol=1e-4)
            result.append({"generation": generation, "frames": len(positions), "agents": positions.shape[1], "max_progress": float(progress.max())})
    assert len(result) >= 2, "A multi-generation video needs multiple recorded generations"
    report = {"valid": True, "replays": result}
    (folder / "replay_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
