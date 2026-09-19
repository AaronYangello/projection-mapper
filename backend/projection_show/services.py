"""Machine-local capabilities, storage limits, and bounded serializable jobs."""

import copy
import importlib.util
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .audio_settings import AudioSettings
from .deployments import Deployments
from .storage import DEFAULT_LIMITS, Uploads, safe_root
from .target import TargetSettings


class Jobs:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="show-job")
        self.lock = threading.Lock()
        self.records = {}
        self.cancellations = {}

    def submit(self, kind, operation):
        with self.lock:
            completed = [
                i for i, j in self.records.items() if j["state"] not in ("queued", "running")
            ]
            for ident in completed[:-100]:
                self.records.pop(ident)
                self.cancellations.pop(ident)
            if any(
                j["kind"] == kind and j["state"] in ("queued", "running")
                for j in self.records.values()
            ):
                raise ValueError(f"A {kind} job is already active")
            ident = uuid.uuid4().hex
            cancel = threading.Event()
            self.cancellations[ident] = cancel
            self.records[ident] = {
                "id": ident,
                "kind": kind,
                "state": "queued",
                "progress": 0,
                "message": "Queued",
                "created_at": time.time(),
                "error": None,
            }

        def progress(value, message, **extra):
            with self.lock:
                self.records[ident].update(progress=max(0, min(1, value)), message=message, **extra)

        def run():
            with self.lock:
                self.records[ident]["state"] = "running"
            try:
                result = operation(cancel, progress)
                with self.lock:
                    self.records[ident].update(
                        state="cancelled"
                        if cancel.is_set() and not result.get("activation_confirmed")
                        else "complete",
                        progress=1,
                        result=result,
                    )
            except Exception as exc:
                with self.lock:
                    self.records[ident].update(
                        state="cancelled" if cancel.is_set() else "error", error=str(exc)[:1000]
                    )

        self.pool.submit(run)
        return self.get(ident)

    def get(self, ident):
        with self.lock:
            if ident not in self.records:
                raise ValueError("Job not found")
            return copy.deepcopy(self.records[ident])

    def cancel(self, ident):
        self.get(ident)
        self.cancellations[ident].set()
        return self.get(ident)

    def close(self):
        for event in self.cancellations.values():
            event.set()
        self.pool.shutdown(wait=True, cancel_futures=True)


class Services:
    def __init__(
        self, runtime, *, role="authoring", data_root: Path | None = None, limits=DEFAULT_LIMITS
    ):
        if role not in ("authoring", "appliance"):
            raise ValueError("Unknown operational role")
        self.role = role
        self.runtime = runtime
        self.limits = limits
        self.data_root = safe_root(data_root or runtime.store.path.parent / "runtime-data")
        self.uploads = Uploads(runtime.store.path.parent, limits)
        self.jobs = Jobs()
        self.deployments = Deployments(self.data_root, limits)
        self.target = TargetSettings(self.data_root)
        self.audio_path = self.data_root / "audio-settings.json"
        if self.audio_path.exists():
            AudioSettings.model_validate_json(self.audio_path.read_text()).apply(runtime)
        active = self.deployments.state()["active"]
        if active:
            try:
                validated = self.deployments.prepare_activation(active, runtime.project)
                runtime.install_deployment(validated, resume=runtime.project.show.auto_start)
            except (ValueError, OSError) as exc:
                runtime.command("stop")
                runtime.deployment_warning = f"Active deployment validation failed: {exc}"
                previous = self.deployments.state()["previous"]
                if previous:
                    try:
                        validated = self.deployments.prepare_activation(previous, runtime.project)
                        self.deployments.activate(validated, active)
                        runtime.install_deployment(validated)
                        runtime.deployment_warning += (
                            "; recovered previous bundle, stopped for inspection"
                        )
                    except (ValueError, OSError):
                        runtime.deployment_warning += "; previous bundle also unavailable"

    def capabilities(self):
        ffmpeg = bool(shutil.which("ffmpeg") or importlib.util.find_spec("imageio_ffmpeg"))
        return {
            "role": self.role,
            "timeline_edit": self.role == "authoring",
            "compiler": self.role == "authoring" and ffmpeg,
            "compiler_reason": None
            if ffmpeg
            else "Install the compiler extra to build on this machine",
            "media_upload": True,
            "deploy": True,
            "deployment_write": bool(os.environ.get("PROJECTION_SHOW_TOKEN")),
            "deployment_reason": None
            if os.environ.get("PROJECTION_SHOW_TOKEN")
            else (
                "Configure PROJECTION_SHOW_TOKEN on this server "
                "before accepting bundle uploads or activation."
            ),
            "physical_pi_verified": False,
            "upload_limit_bytes": self.limits.media_bytes,
            "bundle_limit_bytes": self.limits.bundle_bytes,
        }
