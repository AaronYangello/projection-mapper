"""REST commands/configuration and live state. No OpenGL calls in this module."""

import asyncio
import contextlib
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from . import __version__
from .authoring_api import routes
from .build_api import routes as build_routes
from .calibration import Preview
from .config.models import Project
from .diagnostics import HostStats
from .media.catalog import scan
from .runtime import Runtime
from .services import Services


class ProjectUpdate(BaseModel):
    revision: int
    project: Project


class PatternUpdate(BaseModel):
    pattern: Literal["show", "grid", "white", "color", "border"]


class MappingStart(BaseModel):
    surface_id: str
    revision: int


class MediaPlay(BaseModel):
    surface_id: str
    scene_id: str


def create_app(
    runtime: Runtime, frontend: Path | None = None, *, services: Services | None = None
) -> FastAPI:
    services = services or Services(runtime)

    @asynccontextmanager
    async def lifespan(app):
        stats = HostStats(runtime.store.path.parent)

        async def sample_host():
            while True:
                runtime.machine_stats = await asyncio.to_thread(stats.sample)
                await asyncio.sleep(2)

        async def ticker():
            import time

            while True:
                runtime.tick(time.monotonic())
                await asyncio.sleep(1 / runtime.project.canvas.refresh_rate)

        task = asyncio.create_task(ticker())
        monitor = asyncio.create_task(sample_host())
        yield
        task.cancel()
        monitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        with contextlib.suppress(asyncio.CancelledError):
            await monitor
        await asyncio.to_thread(services.jobs.close)

    app = FastAPI(title="Projection Show Engine", version=__version__, lifespan=lifespan)
    app.include_router(routes(runtime, services))
    app.include_router(build_routes(runtime, services))
    app.state.services = services
    token = os.environ.get("PROJECTION_SHOW_TOKEN", "")

    def authorized(headers) -> bool:
        if not token:
            return True
        return hmac.compare_digest(headers.get("authorization", ""), f"Bearer {token}")

    def same_origin(headers) -> bool:
        origin = headers.get("origin")
        return not origin or urlparse(origin).netloc == headers.get("host")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            # This one streaming download authenticates a short-lived HttpOnly cookie
            # issued by an authenticated POST. Bearer tokens never enter download URLs.
            download = request.method == "GET" and request.url.path == "/api/builds/download"
            if not download and not authorized(request.headers):
                return Response("Authentication required", status_code=401)
            if request.method not in ("GET", "HEAD", "OPTIONS") and not same_origin(
                request.headers
            ):
                return Response("Cross-origin commands are not allowed", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/status")
    async def status():
        return runtime.status()

    @app.get("/api/project")
    async def project():
        return {"revision": runtime.revision, "project": runtime.project.model_dump(mode="json")}

    @app.post("/api/project/validate")
    async def validate_project(project: Project):
        return project.model_dump(mode="json")

    @app.put("/api/project")
    async def update_project(update: ProjectUpdate):
        if update.revision != runtime.revision:
            raise HTTPException(409, "Project changed; reload before saving")
        try:
            runtime.apply(update.project)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                500, "Could not save project; current configuration retained"
            ) from exc
        return {"revision": runtime.revision, "project": runtime.project.model_dump(mode="json")}

    @app.post("/api/runtime/{action}")
    async def command(action: str):
        try:
            runtime.command(action)
        except (ValueError, ValidationError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return runtime.status()

    def mapping_call(action):
        try:
            return action()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, "Mapping could not be saved; preview retained") from exc

    @app.post("/api/mapping")
    async def begin_mapping(body: MappingStart):
        return mapping_call(lambda: runtime.begin_mapping(body.surface_id, body.revision))

    @app.put("/api/mapping/{session_id}")
    async def preview_mapping(session_id: str, body: Preview):
        return mapping_call(lambda: runtime.preview_mapping(session_id, body))

    @app.post("/api/mapping/{session_id}/heartbeat")
    async def mapping_heartbeat(session_id: str):
        return mapping_call(lambda: runtime.calibration.owned(session_id).response())

    @app.post("/api/mapping/{session_id}/save")
    async def save_mapping(session_id: str):
        return mapping_call(lambda: runtime.save_mapping(session_id))

    @app.delete("/api/mapping/{session_id}")
    async def end_mapping(session_id: str):
        mapping_call(lambda: runtime.end_mapping(session_id))
        return {"ended": True}

    @app.put("/api/pattern")
    async def pattern(update: PatternUpdate):
        runtime.set_pattern(update.pattern)
        return runtime.status()

    @app.get("/api/media")
    async def media():
        return {
            "assets": runtime.media,
            "folder": str((runtime.store.path.parent / "media").resolve()),
        }

    @app.post("/api/media/scan")
    async def scan_media():
        if runtime.state != "READY":
            raise HTTPException(409, "Stop the show before rescanning media")
        generation = runtime.revision
        paths = [s.path for s in runtime.project.scenes if s.type != "color"]
        entries = await asyncio.to_thread(scan, runtime.store.path.parent, paths)
        if runtime.revision != generation:
            raise HTTPException(409, "Project changed during scan; rescan again")
        mapping_call(lambda: runtime.install_media_index(entries))
        return {
            "assets": runtime.media,
            "folder": str((runtime.store.path.parent / "media").resolve()),
        }

    @app.post("/api/media/{asset_id}/add")
    async def add_media(asset_id: str):
        return mapping_call(lambda: runtime.add_media(asset_id))

    @app.get("/api/media/{asset_id}/thumbnail")
    async def media_thumbnail(asset_id: str):
        entry = next((e for e in runtime.media if e["id"] == asset_id and e["thumbnail"]), None)
        if not entry:
            raise HTTPException(404, "No thumbnail available")
        return FileResponse(
            runtime.store.path.parent / "cache" / "thumbnails" / f"{entry['id']}.jpg"
        )

    @app.post("/api/manual/play")
    async def play_media(body: MediaPlay):
        mapping_call(lambda: runtime.play_media(body.surface_id, body.scene_id))
        return runtime.status()

    @app.get("/api/preview.jpg")
    async def preview():
        data = runtime.bridge.preview()
        if data is None or runtime.bridge.telemetry()["status"] != "LIVE":
            raise HTTPException(503, "Native GPU preview is unavailable")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.websocket("/api/live")
    async def live(socket: WebSocket):
        if not same_origin(socket.headers):
            await socket.close(code=1008)
            return
        await socket.accept()
        # Browser WebSockets cannot set Authorization; a first message avoids URL token leakage.
        if token:
            try:
                auth = await asyncio.wait_for(socket.receive_json(), timeout=5)
                if not isinstance(auth, dict) or not hmac.compare_digest(
                    str(auth.get("token", "")), token
                ):
                    await socket.close(code=1008)
                    return
            except (TimeoutError, ValueError, WebSocketDisconnect):
                await socket.close(code=1008)
                return
        runtime.clients += 1
        try:
            while True:
                await socket.send_json(runtime.status())
                await asyncio.sleep(0.1)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
        finally:
            runtime.clients -= 1

    if frontend and (frontend / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/")
        async def index():
            # Rebuilds change the hashed asset names; never reuse a stale app shell.
            return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-store"})
    else:

        @app.get("/")
        async def setup_hint():
            return {
                "message": "Build frontend with npm ci && npm run build in frontend/",
                "api_docs": "/docs",
            }

    return app
