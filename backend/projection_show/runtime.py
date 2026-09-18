"""Single-owner runtime with a snapshot bridge to the main-thread GPU renderer."""

import copy
import logging
import threading
import time
from collections import deque

from .calibration import Calibration, Preview
from .config.models import Project
from .config.store import ProjectStore
from .media.catalog import playback_plan, scan
from .scheduler import Scheduler

logger = logging.getLogger(__name__)


class RenderBridge:
    """Only plain copied data crosses threads; all GL objects stay on the main thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self._frame: dict | None = None
        self._telemetry: dict = {"status": "OFFLINE", "fps": 0, "late_frames": 0}
        self._jpeg: bytes | None = None

    def publish(self, snapshot: dict) -> None:
        with self.lock:
            self._frame = snapshot  # Owner never mutates a published snapshot.

    def read(self) -> dict | None:
        with self.lock:
            return self._frame

    def report(self, **data) -> None:
        with self.lock:
            self._telemetry.update(data)
            self._telemetry["updated_at"] = time.monotonic()

    def telemetry(self) -> dict:
        with self.lock:
            result = dict(self._telemetry)
        if result.get("status") == "LIVE" and time.monotonic() - result["updated_at"] > 3:
            result["status"] = "UNRESPONSIVE"
        return result

    def preview(self, jpeg: bytes | None = None) -> bytes | None:
        with self.lock:
            if jpeg is not None:
                self._jpeg = jpeg
            return self._jpeg


class Runtime:
    """Mutated only by the API event loop (or a deterministic test clock)."""

    def __init__(self, store: ProjectStore, bridge: RenderBridge):
        self.store, self.bridge = store, bridge
        self.project = store.load()
        self.media = scan(
            store.path.parent, [s.path for s in self.project.scenes if s.type != "color"]
        )
        self.media_durations, self.unavailable_media, self.media_warnings = playback_plan(
            self.project, self.media
        )
        self.failed_media: set[str] = set()
        self.playback_generation = 1
        self.scheduler = self.new_scheduler()
        self.state = "RUNNING" if self.project.show.auto_start else "READY"
        self.blackout = False
        self.pattern = "show"
        self.revision = 1
        self.render_revision = 1
        self.calibration = Calibration()
        self.clients = 0
        self.events: deque[dict] = deque(maxlen=30)
        self.started = self.last_tick = time.monotonic()
        self.ambient_time = 0.0
        self.event("Project loaded", self.project.name)
        self.tick(self.last_tick)

    def event(self, title: str, detail: str = "") -> None:
        self.events.appendleft({"time": time.time(), "title": title, "detail": detail})
        logger.info("%s %s", title, detail)

    def tick(self, now: float) -> None:
        if self.calibration.expire():
            self.event("Calibration expired", "Unsaved geometry reverted")
        delta, self.last_tick = max(0, now - self.last_tick), now
        if self.state != "PAUSED" and not self.blackout:
            self.ambient_time += delta
        if self.state == "RUNNING" and not self.blackout:
            decoder = self.bridge.telemetry().get("decoder", {})
            current = self.scheduler.current
            if (
                decoder.get("state") == "ERROR"
                and current
                and decoder.get("cue_id") == current.id
                and decoder.get("generation") == self.playback_generation
                and current.scene_id not in self.failed_media
            ):
                self.failed_media.add(current.scene_id)
                self.scheduler.exclude(current.scene_id)
                self.event("Media skipped", decoder.get("error", "Decode failed"))
                self.scheduler.next()
            before = self.scheduler.current
            self.scheduler.tick(delta)
            if self.scheduler.current != before and self.scheduler.current:
                c = self.scheduler.current
                self.event("Cue started", f"{c.surface_id} · {c.scene_id}")
        self.publish()

    def command(self, action: str) -> None:
        self.tick(time.monotonic())
        if action == "start":
            self.state = "RUNNING"
        elif action == "pause":
            if self.state == "RUNNING":
                self.state = "PAUSED"
        elif action == "resume":
            self.state = "RUNNING"
        elif action in ("stop", "restart"):
            self.scheduler = self.new_scheduler()
            self.playback_generation += 1
            self.state = "READY" if action == "stop" else "RUNNING"
        elif action == "skip":
            self.scheduler.next()
        elif action == "fade-out":
            self.scheduler.fade_out()
        elif action == "blackout":
            self.blackout = True
        elif action == "restore":
            self.blackout = False
        elif action == "reload":
            self.apply(self.store.load(), persist=False)
        else:
            raise ValueError(f"Unknown runtime action: {action}")
        self.event("Runtime command", action)
        self.publish()

    def apply(self, project: Project, *, persist: bool = True) -> None:
        if self.calibration.session:
            raise ValueError("Finish calibration before applying project configuration")
        if self.state != "READY":
            raise ValueError("Stop the show before applying project configuration")
        if persist:
            self.store.save(project)
        self.project = project
        self.media_durations, self.unavailable_media, self.media_warnings = playback_plan(
            project, self.media
        )
        self.failed_media.clear()
        self.scheduler = self.new_scheduler()
        self.playback_generation += 1
        self.revision += 1
        self.render_revision += 1
        self.event("Project applied", project.name)
        self.publish()

    def begin_mapping(self, surface_id: str, revision: int) -> dict:
        if revision != self.revision:
            raise ValueError("Project changed; reload before calibrating")
        result = self.calibration.begin(self.project, self.revision, surface_id)
        self.event("Calibration started", surface_id)
        self.publish()
        return result

    def new_scheduler(self) -> Scheduler:
        return Scheduler(
            self.project, self.media_durations, self.unavailable_media | self.failed_media
        )

    def install_media_index(self, entries: list[dict]) -> None:
        if self.state != "READY":
            raise ValueError("Stop the show before rescanning media")
        self.media = entries
        self.media_durations, self.unavailable_media, self.media_warnings = playback_plan(
            self.project, entries
        )
        self.failed_media.clear()
        self.scheduler = self.new_scheduler()
        self.playback_generation += 1
        self.event("Media indexed", f"{len(entries)} files")
        self.publish()

    def add_media(self, asset_id: str) -> dict:
        entry = next((e for e in self.media if e["id"] == asset_id), None)
        if not entry or entry["error"]:
            raise ValueError("Select a successfully indexed media file")
        if any(s.type != "color" and s.path == entry["path"] for s in self.project.scenes):
            raise ValueError("This file is already in the show")
        data = self.project.model_dump(mode="json")
        data["scenes"].append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "type": entry["type"],
                "path": entry["path"],
                "fit": "cover",
            }
        )
        self.apply(Project.model_validate(data))
        return {"project": self.project.model_dump(mode="json"), "revision": self.revision}

    def play_media(self, surface_id: str, scene_id: str) -> None:
        surface = next((s for s in self.project.surfaces if s.id == surface_id), None)
        scene = next((s for s in self.project.scenes if s.id == scene_id), None)
        if (
            not surface
            or not surface.enabled
            or not surface.foreground_enabled
            or not any(p.id == surface.projector_id and p.enabled for p in self.project.projectors)
        ):
            raise ValueError("Select an enabled foreground surface on an enabled projector")
        if not scene or not scene.enabled or scene_id in self.unavailable_media | self.failed_media:
            raise ValueError("Scene is unavailable; rescan media after fixing the file")
        self.scheduler.play(surface_id, scene_id)
        self.state = "RUNNING"
        self.event("Manual cue", f"{surface.name} · {scene.name}")
        self.publish()

    def preview_mapping(self, session_id: str, update: Preview) -> dict:
        result = self.calibration.preview(session_id, update)
        self.publish()
        return result

    def save_mapping(self, session_id: str) -> dict:
        project = self.calibration.project_to_save(self.project, self.revision, session_id)
        self.store.save(project)
        self.project = project
        self.revision += 1
        result = self.calibration.saved(self.revision)
        self.event("Mapping saved", self.calibration.session.surface_id)
        self.publish()
        return result

    def end_mapping(self, session_id: str) -> None:
        self.calibration.end(session_id)
        self.event("Calibration finished", "Saved geometry restored")
        self.publish()

    def set_pattern(self, pattern: str) -> None:
        self.pattern = pattern
        self.event("Output pattern", pattern)
        self.publish()

    def status(self) -> dict:
        result = self.scheduler.snapshot()
        renderer = self.bridge.telemetry()
        warnings = []
        warnings.extend(self.media_warnings)
        if self.failed_media:
            warnings.append(
                "Decode failures excluded from scheduling. Fix files and rescan: "
                + ", ".join(sorted(self.failed_media))
            )
        if renderer["status"] != "LIVE":
            warnings.append("Native renderer is " + renderer["status"].lower())
        if renderer.get("warning"):
            warnings.append(renderer["warning"])
        if not self.scheduler.surfaces.items or not self.scheduler.scenes.items:
            warnings.append(
                "No eligible surface/scene pair. Check enabled flags and tag selectors."
            )
        if self.pattern != "show":
            warnings.append(f"Test pattern active: {self.pattern}. Return to Show to see cues.")
        result.update(
            {
                "state": "BLACKOUT" if self.blackout else self.state,
                "transport": self.state,
                "blackout": self.blackout,
                "pattern": self.pattern,
                "renderer": renderer,
                "revision": self.revision,
                "calibration": None
                if not self.calibration.session
                else {
                    "surface_id": self.calibration.session.surface_id,
                    "dirty": self.calibration.session.dirty,
                },
                "clients": self.clients,
                "uptime": max(0, time.monotonic() - self.started),
                "warnings": warnings,
                "events": list(self.events),
                "canvas": self.project.canvas.model_dump(),
                "media_count": len(self.media),
            }
        )
        return result

    def publish(self) -> None:
        self.bridge.publish(
            {
                "project": self.project.model_dump(mode="json"),
                "revision": self.render_revision,
                "geometry_revision": self.calibration.generation,
                "calibration": self.calibration.render_state(),
                "blackout": self.blackout,
                "pattern": self.pattern,
                "ambient_time": self.ambient_time,
                "scheduler": copy.deepcopy(self.scheduler.snapshot()),
                "transport": self.state,
                "project_root": str(self.store.path.parent),
                "media_durations": self.media_durations.copy(),
                "playback_generation": self.playback_generation,
            }
        )
