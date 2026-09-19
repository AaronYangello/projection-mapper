"""Prototype Zero's public config contract; unsupported fields fail visibly."""

from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .migrations import migrate
from .timeline import Timeline

Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Seconds = Annotated[float, Field(ge=0, le=3600, allow_inf_nan=False)]
Dimension = Annotated[int, Field(ge=16, le=8192)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
Point = tuple[Unit, Unit]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Named(Model):
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True


class Canvas(Model):
    width: Dimension = 1920
    height: Dimension = 1080
    refresh_rate: int = Field(default=60, ge=1, le=240)
    fullscreen: bool = False
    monitor: int = Field(default=0, ge=0)
    preview_fps: float = Field(default=1, ge=0, le=10, allow_inf_nan=False)
    preview_width: int = Field(default=480, ge=160, le=1920)


class Viewport(Model):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: Dimension
    height: Dimension


class Projector(Named):
    viewport: Viewport


class Mapping(Model):
    top_left: Point = (0.1, 0.1)
    top_right: Point = (0.9, 0.1)
    bottom_right: Point = (0.9, 0.9)
    bottom_left: Point = (0.1, 0.9)

    def points(self) -> list[Point]:
        return [self.top_left, self.top_right, self.bottom_right, self.bottom_left]

    @model_validator(mode="after")
    def convex_clockwise(self) -> Self:
        points = self.points()
        for i in range(4):
            a, b, c = points[i], points[(i + 1) % 4], points[(i + 2) % 4]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if cross <= 1e-6:
                raise ValueError(
                    "Corners must form a non-degenerate convex clockwise quadrilateral"
                )
        return self


class LogicalSize(Model):
    width: Dimension = 1080
    height: Dimension = 1080


class Light(Model):
    color: Color = "#ffffff"
    # Fixed-color today. A later version can add color automation here.


class Surface(Named):
    projector_id: Identifier
    logical: LogicalSize = Field(default_factory=LogicalSize)
    mapping: Mapping = Field(default_factory=Mapping)
    tags: list[str] = Field(default_factory=list)
    ambient_profile: Identifier | None = None
    foreground_enabled: bool = True
    role: Literal["media", "lighting"] = "media"
    shape: Literal["rectangle", "circle"] = "rectangle"
    light: Light = Field(default_factory=Light)


class Ambient(Named):
    type: Literal["none", "solid", "particles"] = "particles"
    color: Color = "#a2c9de"
    opacity: Unit = 0.3
    count: int = Field(default=80, ge=0, le=2000)
    speed: float = Field(default=0.035, ge=0, le=2)
    size: float = Field(default=3, ge=0.5, le=100)
    drift: float = Field(default=0.02, ge=-2, le=2)
    seed: int = 42
    foreground_opacity: Unit = 0.1


class ColorScene(Named):
    type: Literal["color"] = "color"
    color: Color
    tags: list[str] = Field(default_factory=list)


class FileScene(Named):
    path: str
    tags: list[str] = Field(default_factory=list)
    fit: Literal["cover", "contain", "stretch", "native"] = "cover"
    focal_point: Point = (0.5, 0.5)

    @field_validator("path")
    @classmethod
    def local_media_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or "\x00" in value
            or len(path.parts) < 2
            or path.parts[0] != "media"
        ):
            raise ValueError(
                "Media paths must be relative files under the project's media/ directory"
            )
        return str(path)


class ImageScene(FileScene):
    type: Literal["image"]


class VideoScene(FileScene):
    type: Literal["video"]
    playback: Literal["full_clip", "timed"] = "full_clip"
    end_behavior: Literal["hold", "loop"] = "hold"
    start_seconds: Seconds = 0
    end_seconds: Seconds | None = None

    @model_validator(mode="after")
    def valid_clip(self) -> Self:
        if self.end_seconds is not None and self.end_seconds <= self.start_seconds:
            raise ValueError("Clip end must be after clip start")
        return self


class AudioScene(FileScene):
    type: Literal["audio"]


Scene = Annotated[ColorScene | ImageScene | VideoScene | AudioScene, Field(discriminator="type")]


class Range(Model):
    min: Seconds
    max: Seconds

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.max < self.min:
            raise ValueError("Range maximum must be greater than or equal to minimum")
        return self


class Selector(Model):
    include_tags: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)

    def accepts(self, tags: list[str]) -> bool:
        return (not self.include_tags or bool(set(tags) & set(self.include_tags))) and not bool(
            set(tags) & set(self.exclude_tags)
        )


class Show(Model):
    mode: Literal["shuffle_bag", "timeline"] = "shuffle_bag"
    timeline: Timeline = Field(default_factory=Timeline)
    max_simultaneous: Literal[1] = 1
    auto_start: bool = True
    fade_in_seconds: Seconds = 2.5
    hold_seconds: Range = Field(default_factory=lambda: Range(min=5, max=8))
    fade_out_seconds: Seconds = 3
    gap_seconds: Range = Field(default_factory=lambda: Range(min=0.5, max=2))
    queue_length: int = Field(default=6, ge=1, le=20)
    seed: int | None = None
    surfaces: Selector = Field(default_factory=Selector)
    scenes: Selector = Field(default_factory=Selector)

    @model_validator(mode="after")
    def positive_cycle(self) -> Self:
        if self.hold_seconds.min <= 0:
            raise ValueError("Minimum hold duration must be positive")
        return self


class Project(Model):
    schema_version: Literal[2] = 2
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    canvas: Canvas = Field(default_factory=Canvas)
    projectors: list[Projector] = Field(default_factory=list)
    surfaces: list[Surface] = Field(default_factory=list)
    ambient_profiles: list[Ambient] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    show: Show = Field(default_factory=Show)

    @model_validator(mode="before")
    @classmethod
    def migrate_version(cls, data):
        if isinstance(data, dict) and "schema_version" in data:
            return migrate(data)
        return data

    @field_validator("scenes", mode="before")
    @classmethod
    def legacy_colors(cls, scenes):
        # Schema 1 color scenes originally permitted omitting their type.
        return [{"type": "color", **s} if isinstance(s, dict) else s for s in scenes]

    @model_validator(mode="after")
    def references(self) -> Self:
        for label in ("projectors", "surfaces", "ambient_profiles", "scenes"):
            ids = [item.id for item in getattr(self, label)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate IDs in {label}")
        projectors = {p.id: p for p in self.projectors}
        ambient = {a.id for a in self.ambient_profiles}
        for p in self.projectors:
            v = p.viewport
            if v.x + v.width > self.canvas.width or v.y + v.height > self.canvas.height:
                raise ValueError(f"Projector {p.id} extends outside the output canvas")
        for s in self.surfaces:
            if s.projector_id not in projectors:
                raise ValueError(f"Surface {s.id} references missing projector {s.projector_id}")
            if s.ambient_profile and s.ambient_profile not in ambient:
                raise ValueError(f"Surface {s.id} references missing ambient {s.ambient_profile}")
        surfaces = {s.id: s for s in self.surfaces}
        scenes = {s.id: s for s in self.scenes}
        for track in self.show.timeline.tracks:
            surface = surfaces.get(track.surface_id)
            if not surface or not surface.enabled or not projectors[surface.projector_id].enabled:
                raise ValueError(f"Track {track.id}: destination surface must exist and be enabled")
            if surface.role == "lighting" and track.clips:
                raise ValueError(f"Track {track.id}: lighting surfaces cannot contain media clips")
            for clip in track.clips:
                scene = scenes.get(clip.scene_id)
                if not scene or not scene.enabled or scene.type == "audio":
                    raise ValueError(
                        f"Clip {clip.id}: select an enabled video, image, or color scene"
                    )
                if scene.type != "video" and clip.source_in_seconds:
                    raise ValueError(f"Clip {clip.id}: source trim applies only to video")
        audio = self.show.timeline.audio
        if audio:
            source = scenes.get(audio.scene_id)
            if not source or not source.enabled or source.type != "audio":
                raise ValueError("Master audio must reference an enabled audio scene")
        # Bound GPU allocation, not installation topology. All counts remain configuration driven.
        pixels = self.canvas.width * self.canvas.height + sum(
            s.logical.width * s.logical.height
            for s in self.surfaces
            if s.enabled and s.role == "media"
        )
        if pixels > 100_000_000:
            raise ValueError("Project exceeds the 100 megapixel render-target budget")
        return self
