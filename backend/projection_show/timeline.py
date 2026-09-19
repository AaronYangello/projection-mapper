"""Pure show evaluation; half-open clips, surface automation and an explicit clock."""

import math
from dataclasses import asdict, dataclass
from typing import Protocol

from .config.models import Project
from .config.timeline import Opacity


@dataclass(frozen=True)
class ActiveLayer:
    id: str
    surface_id: str
    source_id: str | None
    source_seconds: float
    opacity: float
    role: str = "media"
    shape: str = "rectangle"
    color: str | None = None
    clip_id: str | None = None


class ShowController(Protocol):
    def tick(self, delta: float) -> None: ...
    def layers(self) -> list[ActiveLayer]: ...
    def snapshot(self) -> dict: ...


def bind_deployment(project, metadata):
    """Validate a virtual show against local calibration without applying an authoring project."""
    data = project.model_dump(mode="json")
    definitions = {s["id"]: s for s in metadata["surfaces"]}
    data["surfaces"] = [{**s, **definitions.get(s["id"], {})} for s in data["surfaces"]]
    data["show"]["mode"] = "timeline"
    data["show"]["timeline"] = metadata["timeline"]
    ids = {c["scene_id"] for t in metadata["timeline"]["tracks"] for c in t["clips"]}
    data["scenes"] = [dict(id=sid, name=sid, type="color", color="#000000") for sid in sorted(ids)]
    if audio := metadata["timeline"].get("audio"):
        data["scenes"].append(
            dict(
                id=audio["scene_id"],
                name="Master audio",
                type="audio",
                path="media/compiled-audio.wav",
            )
        )
    return Project.model_validate(data)


def opacity_at(automation: Opacity, seconds: float) -> float:
    """Default before the first point; outgoing interpolation; hold the final value."""
    keys = automation.keyframes
    if not keys or seconds < keys[0].time_seconds:
        return automation.default
    for a, b in zip(keys, keys[1:], strict=False):
        if seconds < b.time_seconds:
            if a.interpolation == "hold":
                return a.value
            f = (seconds - a.time_seconds) / (b.time_seconds - a.time_seconds)
            return a.value + (b.value - a.value) * f
    return keys[-1].value


def evaluate(project: Project, seconds: float) -> list[ActiveLayer]:
    surfaces = {s.id: s for s in project.surfaces}
    result = []
    for track in project.show.timeline.tracks:
        surface = surfaces[track.surface_id]
        clip = next(
            (
                c
                for c in track.clips
                if c.start_seconds <= seconds < c.start_seconds + c.duration_seconds
            ),
            None,
        )
        result.append(
            ActiveLayer(
                track.id,
                surface.id,
                clip.scene_id if clip else None,
                seconds - clip.start_seconds + clip.source_in_seconds if clip else 0,
                opacity_at(track.opacity, seconds),
                surface.role,
                surface.shape,
                surface.light.color if surface.role == "lighting" else None,
                clip.id if clip else None,
            )
        )
    return result


def source_bounds(project: Project, entries: list[dict]) -> list[str]:
    """Inspect-backed bounds, separate from pure schema validation and usable before a build."""
    scenes = {s.id: s for s in project.scenes}
    indexed = {e["path"]: e for e in entries}
    errors = []
    clips = [
        (c.id, c.scene_id, c.source_in_seconds, c.duration_seconds)
        for t in project.show.timeline.tracks
        for c in t.clips
    ]
    a = project.show.timeline.audio
    if a:
        clips.append(("Master audio", a.scene_id, a.source_in_seconds, a.duration_seconds))
    for label, sid, start, duration in clips:
        s = scenes[sid]
        if s.type == "color":
            continue
        e = indexed.get(s.path)
        if not e or e.get("error"):
            errors.append(f"{label} / {s.name}: {e.get('error') if e else 'source not indexed'}")
        elif e.get("type") != s.type:
            errors.append(f"{label} / {s.name}: expected {s.type}, found {e.get('type')}")
        elif s.type in ("video", "audio") and start + duration > e["duration_seconds"] + 0.001:
            errors.append(
                f"{label} / {s.name}: range ends at {start + duration:g}s; "
                f"source is {e['duration_seconds']:g}s"
            )
    return errors


class TimelineController:
    def __init__(self, project: Project):
        self.project = project
        self.position = 0.0
        self.cycle = 0
        self.ended = False

    def seek(self, seconds: float):
        if (
            not math.isfinite(seconds)
            or not 0 <= seconds <= self.project.show.timeline.duration_seconds
        ):
            raise ValueError("Seek must be inside the timeline")
        self.position = seconds
        self.ended = seconds == self.project.show.timeline.duration_seconds

    def tick(self, delta: float):
        if not math.isfinite(delta) or delta < 0:
            raise ValueError("Clock delta must be finite and non-negative")
        duration = self.project.show.timeline.duration_seconds
        position = self.position + delta
        if self.project.show.timeline.loop and position >= duration:
            self.cycle += int(position // duration)
            self.position = position % duration
            self.ended = False
        else:
            self.position = min(position, duration)
            self.ended = self.position >= duration

    def layers(self):
        return evaluate(self.project, self.position)

    def snapshot(self):
        t = self.project.show.timeline
        events = []
        for track in t.tracks:
            for c in track.clips:
                events += [
                    {
                        "time": c.start_seconds,
                        "surface_id": track.surface_id,
                        "kind": "Clip starts",
                        "id": c.id,
                    },
                    {
                        "time": c.start_seconds + c.duration_seconds,
                        "surface_id": track.surface_id,
                        "kind": "Clip ends",
                        "id": c.id,
                    },
                ]
            events += [
                {
                    "time": k.time_seconds,
                    "surface_id": track.surface_id,
                    "kind": "Opacity",
                    "value": k.value,
                }
                for k in track.opacity.keyframes
            ]
        return {
            "mode": "timeline",
            "position": self.position,
            "duration": t.duration_seconds,
            "loop": t.loop,
            "cycle": self.cycle,
            "ended": self.ended,
            "layers": [asdict(layer) for layer in self.layers()],
            "upcoming": sorted(
                [e for e in events if e["time"] > self.position], key=lambda e: e["time"]
            )[:8],
        }


class ShuffleController:
    """Adapter leaves the existing tested scheduler and manual behavior intact."""

    def __init__(self, scheduler):
        self.scheduler = scheduler

    def tick(self, delta):
        self.scheduler.tick(delta)

    def snapshot(self):
        return {"mode": "shuffle_bag", **self.scheduler.snapshot()}

    def layers(self):
        s = self.scheduler.snapshot()
        c = s["current"]
        return (
            [ActiveLayer(str(c["id"]), c["surface_id"], c["scene_id"], s["elapsed"], s["opacity"])]
            if c
            else []
        )
