"""Profile one warmed 1,500-car training job, including persistence."""
import cProfile
import json
from pathlib import Path
import pstats
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evolution_lab.config import SimulationConfig
from evolution_lab.training import train

output = Path("data/benchmarks")
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="evolution-profile-") as directory:
    train(SimulationConfig(population=10, generations=1, max_seconds=2), Path(directory) / "warm")
    profiler = cProfile.Profile()
    profiler.runcall(train, SimulationConfig(population=1500, generations=3, seed=83), Path(directory) / "measured")
    profiler.dump_stats(str(output / "training.prof"))
    stats = pstats.Stats(profiler)
    rows = []
    for (file, line, name), (primitive, calls, self_time, cumulative_time, callers) in sorted(stats.stats.items(), key=lambda item: -item[1][3])[:30]:
        rows.append({"file": file, "line": line, "name": name, "calls": calls, "self_seconds": self_time, "cumulative_seconds": cumulative_time})
    result = {"total_seconds": stats.total_tt, "top_cumulative": rows}
    (output / "profile.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"total_seconds": stats.total_tt, "top": rows[:6]}, indent=2))
