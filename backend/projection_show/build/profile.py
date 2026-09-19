"""Named installation limits; the generic project model has no Pi-specific counts."""

from dataclasses import asdict, dataclass

from ..config.models import Project


@dataclass(frozen=True)
class Profile:
    name: str = "pi4-1080p"
    version: int = 1
    width: int = 1920
    height: int = 1080
    fps: int = 30
    media_slots: int = 4
    lighting_surfaces: int = 16
    compiled_clips: int = 1024

    @property
    def canvas_size(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def max_projectors(self) -> int:
        return 1


@dataclass(frozen=True)
class Pi5Profile(Profile):
    """4K installation canvas with a separately bounded 1080p decode atlas."""

    name: str = "pi5-4k30"
    canvas_width: int = 3840
    canvas_height: int = 2160

    @property
    def canvas_size(self) -> tuple[int, int]:
        return self.canvas_width, self.canvas_height

    @property
    def max_projectors(self) -> int:
        return 4


PI4 = Profile()
PI5_4K = Pi5Profile()
PROFILES = {profile.name: profile for profile in (PI4, PI5_4K)}


def get_profile(name):
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError("Unknown build profile; available: " + ", ".join(PROFILES)) from exc


def layout(project: Project, profile=PI4):
    """Interval coloring permits many tracks, at most four simultaneously occupied slots."""
    clips = sorted(
        [(c.start_seconds, t.surface_id, c) for t in project.show.timeline.tracks for c in t.clips],
        key=lambda v: (v[0], v[1], v[2].id),
    )
    ends = []
    regions = []
    if len(clips) > profile.compiled_clips:
        raise ValueError(f"{profile.name} supports at most {profile.compiled_clips} compiled clips")
    for start, sid, c in clips:
        slot = next((i for i, end in enumerate(ends) if end <= start + 1e-9), len(ends))
        if slot == len(ends):
            ends.append(0)
        ends[slot] = start + c.duration_seconds
        regions.append(
            {
                "surface_id": sid,
                "clip_id": c.id,
                "start_seconds": start,
                "end_seconds": start + c.duration_seconds,
                "slot": slot,
            }
        )
    count = len(ends)
    if count > profile.media_slots:
        raise ValueError(
            f"{profile.name} allows at most {profile.media_slots} simultaneous media clips; "
            f"found {count}"
        )
    columns = 1 if count <= 1 else 2
    rows = 1 if count <= 2 else 2
    width = profile.width // columns
    height = profile.height // rows
    for r in regions:
        x = (r["slot"] % columns) * width
        y = (r["slot"] // columns) * height
        r.update(
            rect=[x, y, width, height],
            uv=[
                x / profile.width,
                y / profile.height,
                width / profile.width,
                height / profile.height,
            ],
        )
    return {
        "schema_version": 1,
        "width": profile.width,
        "height": profile.height,
        "regions": regions,
    }


def validate_destination(project: Project, profile=PI4):
    canvas_width, canvas_height = profile.canvas_size
    if project.canvas.width != canvas_width or project.canvas.height != canvas_height:
        raise ValueError(f"{profile.name} requires a {canvas_width}×{canvas_height} output canvas")
    enabled = [p for p in project.projectors if p.enabled]
    if profile.max_projectors == 1:
        if len(enabled) != 1 or enabled[0].viewport.model_dump() != dict(
            x=0, y=0, width=canvas_width, height=canvas_height
        ):
            raise ValueError(f"{profile.name} requires one full-canvas enabled projector")
    elif not 1 <= len(enabled) <= profile.max_projectors:
        raise ValueError(
            f"{profile.name} requires between one and {profile.max_projectors} enabled projectors"
        )


def validate_profile(project: Project, profile=PI4):
    if project.show.mode != "timeline":
        raise ValueError("Build requires the saved Timeline mode; stop and choose Use this mode")
    validate_destination(project, profile)
    surfaces = {s.id: s for s in project.surfaces}
    lights = [t for t in project.show.timeline.tracks if surfaces[t.surface_id].role == "lighting"]
    if len(lights) > profile.lighting_surfaces:
        raise ValueError(
            f"{profile.name} permits at most {profile.lighting_surfaces} lighting tracks"
        )
    atlas = layout(project, profile)
    warnings = (
        ["Pi 5 compiled decode, HDMI audio and sustained thermal qualification remain open."]
        if profile.name == PI5_4K.name
        else ["Pi 4 graphics, decode, HDMI audio and thermal qualification remain unverified."]
    )
    if project.canvas.refresh_rate != profile.fps:
        warnings.append(
            "Bundle playback targets 30 fps; the destination display refresh is configured locally."
        )
    if len({r["slot"] for r in atlas["regions"]}) > 1:
        warnings.append(
            "Atlas pixels are shared between concurrent surfaces; four slots receive 960×540 each."
        )
    return {"profile": asdict(profile), "atlas": atlas, "warnings": warnings}
