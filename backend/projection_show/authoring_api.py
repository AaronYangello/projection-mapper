"""Authoring/storage API; long-running I/O never runs on the runtime event loop."""

import asyncio
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .audio_settings import AudioSettings
from .config.models import Project
from .config.store import atomic_write
from .config.timeline import Timeline


class TimelineUpdate(BaseModel):
    revision: int
    timeline: Timeline


class ModeUpdate(BaseModel):
    revision: int
    mode: Literal["shuffle_bag", "timeline"]


class Seek(BaseModel):
    seconds: float = Field(ge=0, allow_inf_nan=False)


class UploadStart(BaseModel):
    name: str
    size: int = Field(gt=0)


def routes(runtime, services):
    api = APIRouter(prefix="/api")

    def checked(operation):
        try:
            return operation()
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        except OSError as e:
            raise HTTPException(500, "Storage operation failed; existing data retained") from e

    def editable(revision):
        if services.role != "authoring":
            raise HTTPException(403, "Timeline authoring is available on the Mac authoring system")
        if revision != runtime.revision:
            raise HTTPException(409, "Project changed; reload before saving")

    @api.get("/capabilities")
    async def capabilities():
        return services.capabilities()

    @api.get("/runtime/audio")
    async def get_audio():
        return AudioSettings(**runtime.playback_options, **runtime.audio_overrides).model_dump()

    @api.put("/runtime/audio")
    async def set_audio(body: AudioSettings):
        options = body.model_dump(include={"audio_sink", "audio_device"})
        if options != runtime.playback_options and runtime.state != "READY":
            raise HTTPException(409, "Stop playback before changing the audio output device")
        if body.audio_device and body.audio_sink != "alsa":
            raise HTTPException(409, "An explicit HDMI device requires the ALSA audio sink")
        # Small atomic settings commit stays on the single runtime owner, so a start
        # cannot race the stopped-state routing check.
        checked(lambda: atomic_write(services.audio_path, body.model_dump_json()))
        body.apply(runtime)
        runtime.publish()
        return body.model_dump()

    @api.get("/show/timeline")
    async def timeline():
        return {
            "revision": runtime.revision,
            "timeline": runtime.project.show.timeline.model_dump(mode="json"),
        }

    @api.put("/show/timeline")
    async def save_timeline(body: TimelineUpdate):
        editable(body.revision)
        data = runtime.project.model_dump(mode="json")
        data["show"]["timeline"] = body.timeline.model_dump(mode="json")
        checked(lambda: runtime.apply(Project.model_validate(data)))
        return {"revision": runtime.revision, "project": runtime.project.model_dump(mode="json")}

    @api.post("/show/mode")
    async def mode(body: ModeUpdate):
        editable(body.revision)
        data = runtime.project.model_dump(mode="json")
        data["show"]["mode"] = body.mode
        checked(lambda: runtime.apply(Project.model_validate(data)))
        return {"revision": runtime.revision, "project": runtime.project.model_dump(mode="json")}

    @api.post("/runtime/seek")
    async def seek(body: Seek):
        checked(lambda: runtime.seek(body.seconds))
        return runtime.status()

    @api.post("/media/uploads")
    async def begin_upload(body: UploadStart):
        if runtime.state != "READY":
            raise HTTPException(409, "Stop the show before uploading media")
        return checked(lambda: services.uploads.begin(body.name, body.size))

    @api.get("/media/uploads/{ident}")
    async def get_upload(ident: str):
        return checked(lambda: services.uploads.get(ident))

    @api.delete("/media/uploads/{ident}")
    async def cancel_upload(ident: str):
        return checked(lambda: services.uploads.cancel(ident))

    @api.post("/media/upload")
    async def upload(request: Request, upload_id: str):
        uploads = services.uploads
        generation = runtime.revision
        handle = checked(lambda: uploads.start(upload_id))
        try:
            async for chunk in request.stream():
                await asyncio.to_thread(uploads.append, upload_id, handle, chunk)
            await asyncio.to_thread(handle.flush)
            await asyncio.to_thread(os.fsync, handle.fileno())
            handle.close()
            result = await asyncio.to_thread(uploads.validate, upload_id)
            if runtime.state != "READY" or runtime.revision != generation:
                raise ValueError("Show changed during upload. Stop playback and retry installation")
            return uploads.install(upload_id, result)
        except BaseException as e:
            uploads.fail(
                upload_id, "Upload interrupted" if isinstance(e, asyncio.CancelledError) else str(e)
            )
            if isinstance(e, asyncio.CancelledError):
                raise
            raise HTTPException(409, str(e)) from e
        finally:
            handle.close()

    return api
