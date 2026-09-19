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
    parser.add_argument(
        "command",
        choices=["run", "validate", "version", "build", "graphics-report"],
        nargs="?",
        default="run",
    )
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
    parser.add_argument("--profile", default="pi4-1080p")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--encoder", choices=["auto", "libx264", "h264_videotoolbox"], default="auto"
    )
    parser.add_argument("--role", choices=["authoring", "appliance"], default="authoring")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument(
        "--storage-limits", type=Path, help="Machine-local JSON StorageLimits overrides"
    )
    parser.add_argument("--audio-sink", choices=["auto", "alsa", "fake"], default="auto")
    parser.add_argument("--audio-device", default="")
    parser.add_argument("--graphics-backend", choices=["desktop", "gles"], default="desktop")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "version":
        print(__version__)
        return
    if args.command == "graphics-report":
        import json

        import glfw

        from .render.context import create_context, graphics_report

        window, ctx = create_context(
            backend=args.graphics_backend,
            visible=not args.hidden,
            fullscreen=args.fullscreen,
            monitor=args.monitor if hasattr(args, "monitor") else 0,
        )
        print(
            json.dumps(
                graphics_report(ctx, glfw.get_framebuffer_size(window), args.graphics_backend),
                indent=2,
            )
        )
        ctx.release()
        glfw.destroy_window(window)
        glfw.terminate()
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
    if args.command == "build":
        import json

        from .build.compiler import compile_show

        try:
            result = compile_show(
                project,
                store.path.parent,
                args.output or store.path.parent / "builds" / f"{project.id}.pshow",
                profile_name=args.profile,
                encoder=args.encoder,
                progress=lambda value, message, **extra: print(
                    json.dumps(dict(progress=value, message=message, **extra)), flush=True
                ),
            )
            print(json.dumps(result, indent=2))
        except (ValueError, OSError) as exc:
            parser.exit(1, f"Build failed: {exc}\n")
        return
    bridge = RenderBridge()
    runtime = Runtime(store, bridge)
    runtime.playback_options = {"audio_sink": args.audio_sink, "audio_device": args.audio_device}
    import json

    from .services import Services
    from .storage import StorageLimits

    try:
        limits = StorageLimits(
            **(json.loads(args.storage_limits.read_text()) if args.storage_limits else {})
        )
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Invalid storage limits: {exc}\n")

    app = create_app(
        runtime,
        args.frontend,
        services=Services(runtime, role=args.role, data_root=args.data_root, limits=limits),
    )
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
            graphics_backend=args.graphics_backend,
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
