"""Verify every exported frame's metadata against the unchanged source arrays."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def verify(folder: Path):
    metadata = json.loads((folder / "video_metadata.json").read_text(encoding="utf-8"))
    for name, expected in metadata["source_sha256"].items():
        path = folder / name.replace("\\", "/")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    generation = None
    replay = None
    for frame in metadata["frame_audit"]:
        if frame["generation"] != generation:
            generation = frame["generation"]
            with np.load(folder / "replays" / f"gen_{generation:04d}.npz", allow_pickle=False) as archive:
                replay = {key: archive[key] for key in ("alive", "completed", "progress", "scores", "times")}
        i = frame["replay_index"]
        assert frame["alive"] == int(replay["alive"][i].sum())
        assert frame["best_progress"] == float(replay["progress"][i].max())
        assert frame["best_score"] == float(replay["scores"][i].max())
        assert frame["replay_time"] == float(replay["times"][i])
        if "completed" in frame:
            assert frame["completed"] == int(replay["completed"][i].sum())
    result = {"valid": True, "frames_verified": len(metadata["frame_audit"]),
              "generations_shown": sorted({f["generation"] for f in metadata["frame_audit"]}),
              "source_hashes_verified": len(metadata["source_sha256"]), "video": metadata["validation"]}
    (folder / "video_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    print(json.dumps(verify(parser.parse_args().run_dir), indent=2))
