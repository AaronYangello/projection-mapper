"""Deterministic, time-based scheduler. No I/O or renderer dependencies."""

import random
from dataclasses import asdict, dataclass

from .config.models import Project


class ShuffleBag:
    def __init__(self, items: list[str], rng: random.Random):
        self.items, self.rng = list(items), rng
        self.bag: list[str] = []
        self.last: str | None = None

    def pop(self) -> str:
        if not self.items:
            raise ValueError("No eligible items")
        if not self.bag:
            self.bag = self.items.copy()
            self.rng.shuffle(self.bag)
            if len(self.bag) > 1 and self.bag[-1] == self.last:
                self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
        self.last = self.bag.pop()
        return self.last


@dataclass(frozen=True)
class Cue:
    id: int
    surface_id: str
    scene_id: str
    fade_in: float
    hold: float
    fade_out: float
    gap: float
    manual: bool = False

    @property
    def duration(self) -> float:
        return self.fade_in + self.hold + self.fade_out


class Scheduler:
    def __init__(
        self,
        project: Project,
        media_durations: dict[str, float] | None = None,
        unavailable: set[str] | None = None,
    ):
        self.settings = project.show
        self.sources = {s.id: s for s in project.scenes}
        self.media_durations = media_durations or {}
        rng = random.Random(self.settings.seed)
        projectors = {p.id for p in project.projectors if p.enabled}
        self.surfaces = ShuffleBag(
            [
                s.id
                for s in project.surfaces
                if s.enabled
                and s.foreground_enabled
                and s.role == "media"
                and s.projector_id in projectors
                and self.settings.surfaces.accepts(s.tags)
            ],
            rng,
        )
        self.scenes = ShuffleBag(
            [
                s.id
                for s in project.scenes
                if s.enabled
                and s.type != "audio"
                and self.settings.scenes.accepts(s.tags)
                and s.id not in (unavailable or set())
                and (s.type != "video" or s.id in self.media_durations)
            ],
            rng,
        )
        self.rng = rng
        self.queue: list[Cue] = []
        self.current: Cue | None = None
        self.elapsed = 0.0
        self.time = 0.0
        self.sequence = 0
        self.forced_fade: tuple[float, float] | None = None
        self._fill()

    def _fill(self) -> None:
        if not self.surfaces.items or not self.scenes.items:
            return
        while len(self.queue) < self.settings.queue_length:
            self.queue.append(self.make_cue(self.surfaces.pop(), self.scenes.pop()))

    def make_cue(self, surface_id: str, scene_id: str, manual=False) -> Cue:
        self.sequence += 1
        fade_in, fade_out = self.settings.fade_in_seconds, self.settings.fade_out_seconds
        hold = self.rng.uniform(self.settings.hold_seconds.min, self.settings.hold_seconds.max)
        scene = self.sources[scene_id]
        if scene.type == "video" and scene.playback == "full_clip":
            total = self.media_durations[scene_id]
            if fade_in + fade_out > total:
                ratio = total / (fade_in + fade_out)
                fade_in, fade_out = fade_in * ratio, fade_out * ratio
            hold = max(0, total - fade_in - fade_out)
        return Cue(
            self.sequence,
            surface_id,
            scene_id,
            fade_in,
            hold,
            fade_out,
            self.rng.uniform(self.settings.gap_seconds.min, self.settings.gap_seconds.max),
            manual,
        )

    def play(self, surface_id: str, scene_id: str) -> None:
        self.current = self.make_cue(surface_id, scene_id, manual=True)
        self.elapsed, self.forced_fade = 0.0, None

    def exclude(self, scene_id: str) -> None:
        self.scenes.items = [s for s in self.scenes.items if s != scene_id]
        self.scenes.bag = [s for s in self.scenes.bag if s != scene_id]
        self.queue = [cue for cue in self.queue if cue.scene_id != scene_id]
        self._fill()

    def next(self) -> None:
        self.current = self.queue.pop(0) if self.queue else None
        self.elapsed, self.forced_fade = 0.0, None
        self._fill()

    def tick(self, delta: float) -> None:
        delta = max(0, delta)
        self.time += delta
        if self.current is None:
            self.next()
        if self.current is None:
            return
        self.elapsed += delta
        while self.current:
            total = self.current.duration + self.current.gap
            if self.forced_fade:
                total = self.forced_fade[0] + self.current.fade_out + self.current.gap
            if self.elapsed < total:
                break
            remainder = self.elapsed - total
            self.next()
            self.elapsed = remainder

    def fade_out(self) -> None:
        if self.current and self.phase()[0] not in ("GAP", "FADING_OUT"):
            self.forced_fade = (self.elapsed, self.phase()[1])

    def phase(self) -> tuple[str, float, float]:
        c, t = self.current, self.elapsed
        if c is None:
            return "IDLE", 0.0, 0.0
        if self.forced_fade:
            start, opacity = self.forced_fade
            left = c.fade_out - (t - start)
            if left <= 0:
                return "GAP", 0.0, max(0, left + c.gap)
            return "FADING_OUT", opacity * left / c.fade_out, left
        if t < c.fade_in:
            return "FADING_IN", t / c.fade_in, c.duration - t
        if t < c.fade_in + c.hold:
            return "FOREGROUND", 1.0, c.duration - t
        if t < c.duration:
            return "FADING_OUT", (c.duration - t) / c.fade_out, c.duration - t
        return "GAP", 0.0, max(0, c.duration + c.gap - t)

    def snapshot(self) -> dict:
        phase, opacity, remaining = self.phase()
        return {
            "current": asdict(self.current) if self.current else None,
            "phase": phase,
            "opacity": opacity,
            "remaining": remaining,
            "elapsed": self.elapsed,
            "show_time": self.time,
            "queue": [asdict(c) for c in self.queue],
            "eligible_surfaces": len(self.surfaces.items),
            "eligible_scenes": len(self.scenes.items),
        }
