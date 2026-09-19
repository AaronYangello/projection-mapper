"""Compiler/deployment endpoints. Readiness and confirmation are rechecked at activation."""

import asyncio
import json
import os
import secrets
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .build.compiler import change_kind, compile_show, plan
from .config.store import atomic_write
from .storage import free_space
from .target import deploy, test_connection


class BuildRequest(BaseModel):
    revision: int
    profile: Literal["pi4-1080p"] = "pi4-1080p"
    encoder: Literal["auto", "libx264", "h264_videotoolbox"] = "auto"


class Confirmation(BaseModel):
    bundle_id: str | None = None
    target_url: str | None = None
    confirmed: Literal[True]
    expected_active: str | None


class TargetUpdate(BaseModel):
    url: str = Field(max_length=500)
    token: str | None = Field(default=None, max_length=4096)


def routes(runtime, services):
    router = APIRouter(prefix="/api")
    last_path = services.data_root / "last-build.json"
    uploads_active = 0
    downloads = {}

    def guarded(operation):
        try:
            return operation()
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        except OSError as e:
            raise HTTPException(
                500, "Storage operation failed; existing deployment retained"
            ) from e

    def authoring():
        if services.role != "authoring":
            raise HTTPException(403, "Build and target settings belong to the authoring machine")

    def deploy_authorized():
        if not os.environ.get("PROJECTION_SHOW_TOKEN"):
            raise HTTPException(
                403,
                "Configure application bearer authentication before accepting deployment changes",
            )

    def stopped():
        if runtime.state != "READY" or runtime.calibration.session:
            raise HTTPException(409, "Stop playback and finish mapping before activation")

    def latest():
        return json.loads(last_path.read_text()) if last_path.exists() else None

    @router.get("/builds/latest")
    async def last_build():
        return latest()

    @router.post("/builds/inspect")
    async def inspect(body: BuildRequest):
        authoring()
        if body.revision != runtime.revision:
            raise HTTPException(409, "Project changed; reload first")
        project = runtime.project.model_copy(deep=True)
        previous = latest()

        def operation(cancel, progress):
            current = plan(project, runtime.store.path.parent, body.profile, body.encoder, cancel)
            return {
                "change": change_kind(current, previous["manifest"] if previous else None),
                "plan": current,
                "revision": body.revision,
            }

        return guarded(lambda: services.jobs.submit("inspect", operation))

    @router.post("/builds")
    async def build(body: BuildRequest):
        authoring()
        if not services.capabilities()["compiler"]:
            raise HTTPException(409, "Install the compiler extra on this authoring machine")
        if body.revision != runtime.revision:
            raise HTTPException(409, "Project changed; reload before building")
        project = runtime.project.model_copy(deep=True)
        output = runtime.store.path.parent / "builds" / (uuid.uuid4().hex + ".pshow")

        def operation(cancel, progress):
            result = compile_show(
                project,
                runtime.store.path.parent,
                output,
                profile_name=body.profile,
                encoder=body.encoder,
                cancel=cancel,
                progress=progress,
            )
            result["revision"] = body.revision
            atomic_write(last_path, json.dumps(result))
            return result

        return guarded(lambda: services.jobs.submit("build", operation))

    @router.get("/builds/latest/bundle")
    async def export_latest():
        result = latest()
        if not result:
            raise HTTPException(404, "Build a bundle first")
        path = Path(result["bundle_path"])
        if not path.resolve().is_relative_to((runtime.store.path.parent / "builds").resolve()):
            raise HTTPException(409, "Build path is outside the project builds directory")
        return FileResponse(
            path, filename=runtime.project.id + ".pshow", media_type="application/zip"
        )

    @router.post("/builds/latest/download")
    async def prepare_download(request: Request, response: Response):
        result = latest()
        if not result:
            raise HTTPException(404, "Build a bundle first")
        for ticket, entry in list(downloads.items()):
            if entry[0] < time.monotonic():
                downloads.pop(ticket)
        if len(downloads) >= 20:
            raise HTTPException(429, "Too many pending downloads; try again in a minute")
        ticket = secrets.token_urlsafe(32)
        downloads[ticket] = (time.monotonic() + 60, result["bundle_path"])
        response.set_cookie(
            "show-download",
            ticket,
            max_age=60,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path="/api/builds/download",
        )
        return {"url": "/api/builds/download"}

    @router.get("/builds/download")
    async def download(request: Request):
        entry = downloads.pop(request.cookies.get("show-download", ""), None)
        if not entry or entry[0] < time.monotonic():
            raise HTTPException(401, "Download expired; choose Export bundle again")
        path = Path(entry[1])
        if not path.resolve().is_relative_to((runtime.store.path.parent / "builds").resolve()):
            raise HTTPException(409, "Invalid build path")
        result = FileResponse(
            path, filename=runtime.project.id + ".pshow", media_type="application/zip"
        )
        result.delete_cookie("show-download", path="/api/builds/download")
        return result

    @router.post("/builds/latest/preview")
    async def preview():
        authoring()
        stopped()
        result = latest()
        if not result:
            raise HTTPException(409, "Build a bundle first")
        revision = runtime.revision
        try:
            validated = await asyncio.to_thread(
                services.deployments.stage,
                Path(result["bundle_path"]),
                runtime.project.model_copy(deep=True),
            )
        except (ValueError, OSError) as e:
            raise HTTPException(409, str(e)) from e
        stopped()
        if revision != runtime.revision:
            raise HTTPException(409, "Project changed during validation")
        validated["preview"] = True
        runtime.install_deployment(validated)
        return {"preview": True, "manifest": validated["manifest"]}

    @router.post("/builds/preview/unload")
    async def unload_preview():
        authoring()
        stopped()
        if not runtime.deployment or not runtime.deployment.get("preview"):
            raise HTTPException(409, "No authoring preview is loaded")
        runtime.unload_deployment()
        return runtime.status()

    @router.get("/builds/{ident}")
    async def job(ident: str):
        return guarded(lambda: services.jobs.get(ident))

    @router.delete("/builds/{ident}")
    async def cancel_job(ident: str):
        return guarded(lambda: services.jobs.cancel(ident))

    @router.get("/builds/{ident}/bundle")
    async def export(ident: str):
        job = guarded(lambda: services.jobs.get(ident))
        if job["kind"] != "build" or job["state"] != "complete":
            raise HTTPException(409, "Build is not complete")
        return FileResponse(
            job["result"]["bundle_path"],
            filename=runtime.project.id + ".pshow",
            media_type="application/zip",
        )

    @router.get("/deployments")
    async def deployments():
        return await asyncio.to_thread(services.deployments.status)

    @router.post("/deployments/upload")
    async def upload_bundle(request: Request):
        nonlocal uploads_active
        deploy_authorized()
        if uploads_active >= services.limits.concurrent:
            raise HTTPException(429, "Bundle upload slots are busy")
        try:
            size = int(request.headers.get("content-length", "0"))
        except ValueError:
            raise HTTPException(400, "Invalid upload size") from None
        if not 0 < size <= services.limits.bundle_bytes:
            raise HTTPException(413, "Declare a positive bounded bundle Content-Length")
        uploads_active += 1
        path = None
        try:
            await asyncio.to_thread(free_space, services.deployments.staging, size, services.limits)
            fd, name = tempfile.mkstemp(
                prefix="upload-", suffix=".pshow", dir=services.deployments.staging
            )
            path = Path(name)
            received = 0
            with os.fdopen(fd, "wb") as f:
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > size:
                        raise ValueError("Bundle exceeds declared upload size")
                    await asyncio.to_thread(free_space, path.parent, len(chunk), services.limits)
                    await asyncio.to_thread(f.write, chunk)
                if received != size:
                    raise ValueError("Incomplete bundle upload")
                await asyncio.to_thread(f.flush)
                await asyncio.to_thread(os.fsync, f.fileno())
            project = runtime.project.model_copy(deep=True)

            def operation(cancel, progress):
                try:
                    return services.deployments.stage(path, project, cancel, progress)
                finally:
                    path.unlink(missing_ok=True)

            return guarded(lambda: services.jobs.submit("install", operation))
        except BaseException as e:
            if path is not None:
                path.unlink(missing_ok=True)
            if isinstance(e, (asyncio.CancelledError, HTTPException)):
                raise
            raise HTTPException(409, "Bundle upload failed: " + str(e)[:300]) from e
        finally:
            uploads_active -= 1

    async def activate_id(ident, body):
        deploy_authorized()
        stopped()
        revision = runtime.revision
        try:
            validated = await asyncio.to_thread(
                services.deployments.prepare_activation,
                ident,
                runtime.project.model_copy(deep=True),
            )
        except (ValueError, OSError) as e:
            raise HTTPException(409, str(e)) from e
        stopped()
        if revision != runtime.revision:
            raise HTTPException(409, "Installation changed during validation; review again")
        guarded(
            lambda: runtime.deployment_project(validated)
        )  # all fallible construction before commit
        state = guarded(lambda: services.deployments.activate(validated, body.expected_active))
        runtime.install_deployment(validated)
        return {
            **state,
            "manifest": validated["manifest"],
            "validation": "valid",
            "activation_confirmed": True,
        }

    @router.post("/deployments/rollback")
    async def rollback(body: Confirmation):
        previous = services.deployments.state()["previous"]
        if not previous:
            raise HTTPException(409, "No previous deployment to restore")
        return await activate_id(previous, body)

    @router.post("/deployments/unload")
    async def unload(body: Confirmation):
        deploy_authorized()
        stopped()
        result = guarded(lambda: services.deployments.unload(body.expected_active))
        runtime.unload_deployment()
        return result

    @router.post("/deployments/{ident}/activate")
    async def activate(ident: str, body: Confirmation):
        return await activate_id(ident, body)

    @router.get("/target")
    async def target():
        authoring()
        return services.target.public()

    @router.put("/target")
    async def target_save(body: TargetUpdate):
        authoring()
        try:
            return await asyncio.to_thread(services.target.save, body.url, body.token)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e

    @router.post("/target/test")
    async def target_test():
        authoring()
        return guarded(
            lambda: services.jobs.submit(
                "connection", lambda cancel, progress: test_connection(services.target)
            )
        )

    @router.post("/target/deploy")
    async def target_deploy(body: Confirmation):
        authoring()
        saved_target = services.target.read()
        if body.target_url != saved_target["url"]:
            raise HTTPException(409, "Target changed; review and confirm the destination again")
        result = latest()
        if not result:
            raise HTTPException(409, "Build a bundle first")
        if body.bundle_id != result["manifest"]["id"]:
            raise HTTPException(
                409, "Built artifact changed; review and confirm the current bundle"
            )
        # The confirmation applies to this exact built artifact, even if the project has changed.
        return guarded(
            lambda: services.jobs.submit(
                "deploy",
                lambda cancel, progress: deploy(
                    services.target,
                    Path(result["bundle_path"]),
                    body.expected_active,
                    cancel,
                    progress,
                    saved=saved_target,
                    expected_bundle=body.bundle_id,
                ),
            )
        )

    return router
