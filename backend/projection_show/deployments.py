"""Show-only bundles: strict validation, staged installation and one atomic activation record."""

import json
import re
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .build.compiler import key, validate_playback
from .build.profile import PI4, validate_profile
from .config.models import LogicalSize, Surface
from .config.store import atomic_write
from .config.timeline import Timeline
from .storage import (
    DEFAULT_LIMITS,
    REQUIRED_FILES,
    digest,
    extract_bundle,
    safe_root,
    sync_directory,
)
from .timeline import bind_deployment


class BundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    bundle_version: Literal[1]
    engine_schema: Literal[2]
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    compiler_version: Literal[1]
    profile: dict
    video_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    audio_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    metadata_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_hashes: dict[str, str]
    tool_version: str = Field(max_length=300)
    encoder_backend: Literal["libx264", "h264_videotoolbox"]
    built_at: float = Field(ge=0)
    source_project: dict[str, str]
    required_surfaces: list[dict]
    warnings: list[str]
    duration_seconds: float = Field(gt=0, le=86400)
    has_audio: bool
    playback_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def _read_validated(directory: Path, project):
    checks = json.loads((directory / "checksums.json").read_text())
    if set(checks) != set(p.name for p in directory.iterdir()) - {
        "checksums.json"
    } or not REQUIRED_FILES <= set(p.name for p in directory.iterdir()):
        raise ValueError("Installed deployment file list changed")
    for name, expected in checks.items():
        if "/" in name or "\\" in name or name not in REQUIRED_FILES | {"authoring-project.yaml"}:
            raise ValueError("Unsafe deployment member")
        path = directory / name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != expected["bytes"]
            or digest(path) != expected["sha256"]
        ):
            raise ValueError(f"Deployment checksum failed: {name}")
    m = BundleManifest.model_validate_json((directory / "bundle.json").read_text()).model_dump()
    if m["profile"] != asdict(PI4):
        raise ValueError("Unsupported or modified deployment profile")
    if m["id"] != key([m["video_key"], m["audio_key"], m["metadata_key"]])[:32]:
        raise ValueError("Deployment identity does not match build keys")
    if m["playback_sha256"] != checks["playback.mp4"]["sha256"]:
        raise ValueError("Playback checksum does not match manifest")
    automation = json.loads((directory / "automation.json").read_text())
    if m["metadata_key"] != key(
        {
            "automation": automation,
            "required_surfaces": m["required_surfaces"],
            "source_project": m["source_project"],
        }
    ):
        raise ValueError("Runtime metadata does not match its build key")
    atlas = json.loads((directory / "atlas.json").read_text())
    if (
        set(automation) != {"schema_version", "timeline", "surfaces"}
        or automation["schema_version"] != 1
    ):
        raise ValueError("Unsupported automation schema")
    timeline = Timeline.model_validate(automation["timeline"])
    if timeline.duration_seconds != m["duration_seconds"] or bool(timeline.audio) != m["has_audio"]:
        raise ValueError("Timeline does not match manifest duration/audio")
    local = {s.id: s for s in project.surfaces}
    projectors = {p.id: p for p in project.projectors}
    required = m["required_surfaces"]
    ids = [r["id"] for r in required]
    if len(ids) != len(set(ids)) or set(ids) != {t.surface_id for t in timeline.tracks}:
        raise ValueError("Required surface IDs do not match timeline")
    errors = []
    for req in required:
        if set(req) != {"id", "role", "logical"}:
            raise ValueError("Unknown required surface fields")
        s = local.get(req["id"])
        if not s:
            errors.append("Missing surface " + req["id"])
            continue
        if not s.enabled or not projectors[s.projector_id].enabled:
            errors.append("Disabled surface " + s.id)
        if s.role != req["role"] or s.logical != LogicalSize.model_validate(req["logical"]):
            errors.append("Incompatible role/logical dimensions: " + s.id)
    if errors:
        raise ValueError("; ".join(errors))
    if project.canvas.width != 1920 or project.canvas.height != 1080:
        raise ValueError("Destination canvas must be 1920×1080")
    enabled = [p for p in project.projectors if p.enabled]
    if len(enabled) != 1 or enabled[0].viewport.model_dump() != dict(
        x=0, y=0, width=1920, height=1080
    ):
        raise ValueError("Destination requires one full-canvas projector for pi4-1080p")
    specifications = {}
    for definition in automation["surfaces"]:
        if set(definition) != {"id", "role", "shape", "light", "logical"}:
            raise ValueError("Unsupported surface metadata")
        sid = definition["id"]
        if sid not in ids or sid in specifications:
            raise ValueError("Unexpected or duplicate surface metadata")
        specs = Surface.model_validate({**local[sid].model_dump(), **definition})
        if specs.role != local[sid].role or specs.logical != local[sid].logical:
            raise ValueError("Surface metadata incompatible with destination")
        specifications[sid] = definition
    if set(specifications) != set(ids):
        raise ValueError("Missing surface metadata")
    if sum(s["role"] == "lighting" for s in specifications.values()) > 16:
        raise ValueError("Too many lighting surfaces for profile")
    if (
        set(atlas) != {"schema_version", "width", "height", "regions"}
        or atlas["schema_version"] != 1
        or (atlas["width"], atlas["height"]) != (1920, 1080)
    ):
        raise ValueError("Unsupported atlas schema")
    clips = {c.id: (t, c) for t in timeline.tracks for c in t.clips}
    if len(atlas["regions"]) > PI4.compiled_clips:
        raise ValueError("Bundle exceeds the profile's compiled clip validation budget")
    seen = set()
    for r in atlas["regions"]:
        if set(r) != {
            "surface_id",
            "clip_id",
            "start_seconds",
            "end_seconds",
            "slot",
            "rect",
            "uv",
        }:
            raise ValueError("Unexpected atlas region fields")
        if r["clip_id"] not in clips or r["clip_id"] in seen:
            raise ValueError("Unexpected or duplicate atlas clip")
        t, c = clips[r["clip_id"]]
        seen.add(c.id)
        if (
            specifications[t.surface_id]["role"] != "media"
            or t.surface_id != r["surface_id"]
            or c.start_seconds != r["start_seconds"]
            or c.start_seconds + c.duration_seconds != r["end_seconds"]
        ):
            raise ValueError("Atlas clip timing/surface mismatch")
        if type(r["slot"]) is not int or not 0 <= r["slot"] < 4:
            raise ValueError("Invalid atlas slot")
        if len(r["rect"]) != 4 or any(type(v) is not int for v in r["rect"]):
            raise ValueError("Invalid atlas rectangle")
        x, y, w, h = r["rect"]
        if (
            min(x, y) < 0
            or min(w, h) <= 0
            or x + w > 1920
            or y + h > 1080
            or r["uv"] != [x / 1920, y / 1080, w / 1920, h / 1080]
        ):
            raise ValueError("Invalid atlas UV/rectangle")
    if seen != set(clips):
        raise ValueError("Missing atlas clips")
    expected = validate_profile(bind_deployment(project, automation), PI4)["atlas"]
    if atlas != expected:
        raise ValueError("Atlas layout does not match deterministic profile packing")
    validate_playback(directory / "playback.mp4", PI4, m["duration_seconds"], m["has_audio"])
    extras = sorted(set(local) - set(ids))
    return {
        "manifest": m,
        "atlas": atlas,
        "automation": automation,
        "directory": str(directory),
        "extra_surfaces": extras,
        "validation": "valid",
    }


def read_validated(directory, project):
    try:
        return _read_validated(directory, project)
    except (KeyError, TypeError, IndexError, OverflowError) as exc:
        raise ValueError(
            "Malformed deployment metadata; check bundle schema and field types"
        ) from exc


class Deployments:
    def __init__(self, root, limits=DEFAULT_LIMITS):
        self.root = safe_root(root)
        self.folder = safe_root(root / "deployments")
        self.staging = safe_root(root / ".deployment-staging")
        self.limits = limits
        self.state_path = root / "deployment-state.json"
        for p in self.staging.iterdir():
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()

    def state(self):
        state = (
            json.loads(self.state_path.read_text())
            if self.state_path.exists()
            else {"active": None, "previous": None}
        )
        if set(state) != {"active", "previous"}:
            raise ValueError("Invalid deployment state fields")
        for ident in state.values():
            if ident is not None and not re.fullmatch("[a-f0-9]{32}", ident):
                raise ValueError("Invalid deployment state; restore a known-good record")
        return state

    def directory(self, ident):
        if not re.fullmatch("[a-f0-9]{32}", ident):
            raise ValueError("Invalid deployment ID")
        directory = self.folder / ident
        if directory.is_symlink():
            raise ValueError("Deployment cannot be a symlink")
        return directory

    def stage(self, archive, project, cancel=None, progress=lambda *args: None):
        progress(0.1, "Validating bundle")
        with tempfile.TemporaryDirectory(prefix="validation-", dir=self.staging) as tmp:
            path = Path(tmp)
            extract_bundle(archive, path, self.limits, cancel)
            validated = read_validated(path, project)
            ident = validated["manifest"]["id"]
            if cancel and cancel.is_set():
                raise ValueError("Deployment validation cancelled")
            dest = self.directory(ident)
            if dest.exists():
                existing = read_validated(dest, project)
                if any(
                    existing["manifest"][k] != validated["manifest"][k]
                    for k in ["video_key", "audio_key", "metadata_key", "playback_sha256"]
                ):
                    raise ValueError("Deployment ID collision")
            else:
                path.rename(dest)
                sync_directory(self.folder)
            validated["directory"] = str(dest)
            progress(1, "Validated; activation requires confirmation")
            return validated

    def prepare_activation(self, ident, project):
        return read_validated(self.directory(ident), project)

    def activate(self, validated, expected_active):
        state = self.state()
        if state["active"] != expected_active:
            raise ValueError("Active deployment changed; review and confirm again")
        ident = validated["manifest"]["id"]
        if ident != state["active"]:
            atomic_write(
                self.state_path, json.dumps({"active": ident, "previous": state["active"]})
            )
        return self.state()

    def unload(self, expected_active):
        state = self.state()
        if state["active"] != expected_active:
            raise ValueError("Active deployment changed; review again")
        atomic_write(
            self.state_path,
            json.dumps({"active": None, "previous": state["active"] or state["previous"]}),
        )
        return self.state()

    def status(self):
        state = self.state()
        result = {**state, "deployments": []}
        for d in sorted(self.folder.iterdir()):
            if d.is_dir() and not d.is_symlink():
                try:
                    result["deployments"].append(
                        BundleManifest.model_validate_json(
                            (d / "bundle.json").read_text()
                        ).model_dump()
                    )
                except (ValueError, OSError):
                    continue
        return result
