"""Command-line entry points shared by the desktop launchers and local job queue."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys

# Keep background work bounded on machines with many logical cores.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("NUMBA_NUM_THREADS", "2")


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="Evolution Lab")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("train", "run"):
        command = sub.add_parser(name)
        command.add_argument("--config", type=Path)
        command.add_argument("--run-dir", type=Path, required=True)
        command.add_argument("--resume", action="store_true")
    render = sub.add_parser("render")
    render.add_argument("--run-dir", type=Path, required=True)
    render.add_argument("--duration", type=float)
    render.add_argument("--fps", type=int, default=30)
    render.add_argument("--width", type=int, default=1080)
    render.add_argument("--height", type=int, default=1920)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--data-dir", type=Path)
    serve.add_argument("--open-browser", action="store_true")
    validate = sub.add_parser("validate")
    validate.add_argument("path", type=Path)
    sub.add_parser("doctor")
    bench = sub.add_parser("benchmark")
    bench.add_argument("--output", type=Path, default=Path("data/benchmarks/benchmark.json"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    try:
        if args.command == "doctor":
            import numpy, numba, imageio_ffmpeg
            import subprocess
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run([ffmpeg, "-version"], check=True, capture_output=True)
            print(json.dumps({"python": sys.version, "numpy": numpy.__version__, "numba": numba.__version__, "ffmpeg": ffmpeg, "status": "ok"}, indent=2))
            return 0
        if args.command == "serve":
            import threading
            import webbrowser
            import uvicorn
            from evolution_lab.ui.server import create_app
            if args.open_browser:
                threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
            uvicorn.run(create_app(args.data_dir), host="127.0.0.1", port=args.port, log_level="info")
            return 0
        if args.command == "validate":
            from evolution_lab.video import validate_video
            result = validate_video(args.path)
            print(json.dumps(result, indent=2))
            return 0 if result.get("valid") else 1
        if args.command == "benchmark":
            from evolution_lab.benchmark import benchmark
            result = benchmark(args.output)
            print(json.dumps({"report": str(args.output.resolve()), "inference": result["inference"],
                              "raycast": result["raycast"], "populations": [row["population"] for row in result["simulation"]]}, indent=2))
            return 0
        run_dir = args.run_dir.resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(run_dir / "execution.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(file_handler)
        explicit_config = getattr(args, "config", None)
        if explicit_config is not None and not explicit_config.is_file():
            raise FileNotFoundError(f"Fichier de configuration introuvable : {explicit_config}")
        config_path = explicit_config or run_dir / "config.json"
        config_data = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
        if args.command in ("train", "run"):
            from evolution_lab.config import SimulationConfig
            from evolution_lab.training import train
            config = SimulationConfig(**config_data)
            result = train(config, run_dir, resume=args.resume, stop_requested=lambda: (run_dir / "STOP").exists())
            print(json.dumps(result, indent=2), flush=True)
            if args.command == "train" or (run_dir / "STOP").exists():
                return 0
        if args.command in ("render", "run"):
            from evolution_lab.video import export_video
            status_path = run_dir / "status.json"
            prior = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
            atomic_json(status_path, {**prior, "status": "rendering", "message": "Création du montage MP4"})
            duration = getattr(args, "duration", None) or config_data.get("video_duration", 24.0)
            result = export_video(run_dir, duration=duration, fps=getattr(args, "fps", 30), width=getattr(args, "width", 1080), height=getattr(args, "height", 1920))
            atomic_json(status_path, {**prior, "status": "completed", "message": "Vidéo validée et prête"})
            print(json.dumps({key: result[key] for key in ("video_path", "thumbnail_path", "validation", "rendering_seconds", "encoding_seconds", "total_export_seconds") if key in result}, indent=2, default=str), flush=True)
        return 0
    except KeyboardInterrupt:
        logging.warning("Interruption demandée. Les générations sauvegardées peuvent être reprises.")
        return 130
    except Exception as exc:
        logging.exception("Échec de l'opération")
        if hasattr(args, "run_dir"):
            status_path = args.run_dir / "status.json"
            try:
                prior = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
                atomic_json(status_path, {**prior, "status": "failed", "message": str(exc)})
            except OSError:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
