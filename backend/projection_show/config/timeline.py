"""Version-two coordinated show definitions. No renderer or I/O dependencies."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Time = Annotated[float, Field(ge=0, le=86400, allow_inf_nan=False)]
Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
ID = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")]


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Keyframe(Definition):
    time_seconds: Time
    value: Unit
    interpolation: Literal["linear", "hold"] = "linear"


class Opacity(Definition):
    default: Unit = 1
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        times = [k.time_seconds for k in self.keyframes]
        if any(a >= b for a, b in zip(times, times[1:], strict=False)):
            raise ValueError("Opacity keyframes must have strictly increasing times")
        return self


class Clip(Definition):
    id: ID
    scene_id: ID
    start_seconds: Time = 0
    source_in_seconds: Time = 0
    duration_seconds: Annotated[float, Field(gt=0, le=86400)]


class Track(Definition):
    id: ID
    surface_id: ID
    clips: list[Clip] = Field(default_factory=list, max_length=2000)
    opacity: Opacity = Field(default_factory=Opacity)

    @model_validator(mode="after")
    def no_overlap(self) -> Self:
        clips = sorted(self.clips, key=lambda c: c.start_seconds)
        if any(
            a.start_seconds + a.duration_seconds > b.start_seconds + 1e-9
            for a, b in zip(clips, clips[1:], strict=False)
        ):
            raise ValueError(f"Track {self.id}: clips may not overlap")
        return self


class Audio(Definition):
    scene_id: ID
    start_seconds: Time = 0
    source_in_seconds: Time = 0
    duration_seconds: Annotated[float, Field(gt=0, le=86400)]
    volume: Unit = 1
    muted: bool = False
    sync_offset_ms: int = Field(default=0, ge=-1000, le=1000)


class Timeline(Definition):
    duration_seconds: Annotated[float, Field(gt=0, le=86400)] = 60
    loop: bool = False
    track_order: list[ID] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list, max_length=256)
    audio: Audio | None = None

    @model_validator(mode="after")
    def bounds(self) -> Self:
        for label, ids in [
            ("track IDs", [t.id for t in self.tracks]),
            ("track surfaces", [t.surface_id for t in self.tracks]),
            ("clip IDs", [c.id for t in self.tracks for c in t.clips]),
            ("track order", self.track_order),
        ]:
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate {label}")
        if set(self.track_order) - {t.surface_id for t in self.tracks}:
            raise ValueError("Track order references an unknown surface track")
        for t in self.tracks:
            if any(k.time_seconds > self.duration_seconds for k in t.opacity.keyframes):
                raise ValueError(f"Track {t.id}: opacity keyframe outside timeline duration")
            if any(
                c.start_seconds + c.duration_seconds > self.duration_seconds + 1e-9 for c in t.clips
            ):
                raise ValueError(f"Track {t.id}: clip ends after timeline duration")
        if (
            self.audio
            and self.audio.start_seconds + self.audio.duration_seconds
            > self.duration_seconds + 1e-9
        ):
            raise ValueError("Audio ends after timeline duration")
        return self
