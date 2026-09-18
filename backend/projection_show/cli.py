"""Desktop launcher: native graphics on main thread, one API/runtime owner thread."""

import argparse
import logging
import threading
import time
from pathlib import Path

import uvicorn

from . import __version__
from .api import create_app
from .config.store import ProjectStore
from .runtime import RenderBridge, Runtime


def main():
    parser = argparse.ArgumentParser(prog="projection-show")
    parser.add_argument("command", choices=["run", "validate", "version"], nargs="?", default="run")
    parser.add_argument("--project", type=Path, default=Path("projects/demo/project.yaml"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--api-only", action="store_true", help="No renderer; status reports OFFLINE"
    )
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument(
        "--hidden", action="store_true", help="Hidden native window for GPU verification"
    )
    parser.add_argument(
        "--duration", type=float, help="Exit after this many seconds (native smoke tests)"
    )
    parser.add_argument("--frontend", type=Path, default=Path("frontend/dist"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "version":
        print(__version__)
        return
    store = ProjectStore(args.project)
    try:
        project = store.load()
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Invalid project: {exc}\n")
    if args.command == "validate":
        print(
            f"Valid: {project.name} · {len(project.projectors)} projectors "
            f"· {len(project.surfaces)} surfaces"
        )
        return
    bridge = RenderBridge()
    runtime = Runtime(store, bridge)
    app = create_app(runtime, args.frontend)
    server = uvicorn.Server(
        uvicorn.Config(app, host=args.host, port=args.port, log_level="info", access_log=False)
    )
    if args.api_only:
        server.run()
        return
    stop = threading.Event()

    def serve():
        try:
            server.run()
        finally:
            stop.set()

    thread = threading.Thread(target=serve, name="api-runtime", daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started or not thread.is_alive():
                break
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("API did not start; check the address and port")
        from .render.engine import run_renderer

        run_renderer(
            bridge,
            stop,
            visible=not args.hidden,
            fullscreen=(args.fullscreen or project.canvas.fullscreen) and not args.windowed,
            monitor=project.canvas.monitor,
            duration=args.duration,
        )
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.exception("Native output failed")
        raise SystemExit(1) from None
    finally:
        stop.set()
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
