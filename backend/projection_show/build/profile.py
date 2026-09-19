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


PI4 = Profile()


def get_profile(name):
    if name != PI4.name:
        raise ValueError("Unknown build profile; available: pi4-1080p")
    return PI4


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


def validate_profile(project: Project, profile=PI4):
    if project.show.mode != "timeline":
        raise ValueError("Build requires the saved Timeline mode; stop and choose Use this mode")
    if project.canvas.width != profile.width or project.canvas.height != profile.height:
        raise ValueError(
            f"{profile.name} requires a {profile.width}×{profile.height} output canvas"
        )
    enabled = [p for p in project.projectors if p.enabled]
    if len(enabled) != 1 or enabled[0].viewport.model_dump() != dict(
        x=0, y=0, width=profile.width, height=profile.height
    ):
        raise ValueError(f"{profile.name} requires one full-canvas enabled projector")
    surfaces = {s.id: s for s in project.surfaces}
    lights = [t for t in project.show.timeline.tracks if surfaces[t.surface_id].role == "lighting"]
    if len(lights) > profile.lighting_surfaces:
        raise ValueError(
            f"{profile.name} permits at most {profile.lighting_surfaces} lighting tracks"
        )
    atlas = layout(project, profile)
    warnings = ["Pi 4 graphics, decode, HDMI audio and thermal qualification remain unverified."]
    if project.canvas.refresh_rate != profile.fps:
        warnings.append(
            "Bundle playback targets 30 fps; the destination display refresh is configured locally."
        )
    if len({r["slot"] for r in atlas["regions"]}) > 1:
        warnings.append(
            "Atlas pixels are shared between concurrent surfaces; four slots receive 960×540 each."
        )
    return {"profile": asdict(profile), "atlas": atlas, "warnings": warnings}
