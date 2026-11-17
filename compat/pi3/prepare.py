"""Convert a verified compiled timeline into VideoCore IV textures for offline playback."""

import argparse
import hashlib
import io
import json
import struct
import subprocess
import zlib
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from projection_show.config.store import ProjectStore

SIZE = 512
FPS = 30


def copy_verified(bundle, target, record):
    digest = hashlib.sha256()
    size = 0
    while True:
        block = bundle.read(1024 * 1024)
        if not block:
            break
        digest.update(block)
        size += len(block)
        target.write(block)
    if size != record["bytes"] or digest.hexdigest() != record["sha256"]:
        raise ValueError("Bundle member checksum mismatch")


def read_metadata(bundle):
    checks = json.loads(bundle.read("checksums.json"))
    result = []
    for name in ("bundle.json", "atlas.json", "automation.json"):
        output = io.BytesIO()
        with bundle.open(name) as source:
            copy_verified(source, output, checks[name])
        result.append(json.loads(output.getvalue()))
    return (*result, checks["playback.mp4"])


def show_data(project, atlas, automation, manifest):
    timeline = automation["timeline"]
    duration = timeline["duration_seconds"]
    if not 0 < duration <= 3600:
        raise ValueError("Pi 3 supports timelines up to one hour")
    if (project.canvas.width, project.canvas.height) != (1920, 1080):
        raise ValueError("Pi 3 requires the single 1080p projector profile")
    outputs = [p for p in project.projectors if p.enabled]
    if len(outputs) != 1 or outputs[0].viewport.model_dump() != {
        "x": 0,
        "y": 0,
        "width": 1920,
        "height": 1080,
    }:
        raise ValueError("Pi 3 requires one fullscreen output")
    tracks = {track["surface_id"]: track for track in timeline["tracks"]}
    metadata = {surface["id"]: surface for surface in automation["surfaces"]}
    regions = {region["clip_id"]: region["uv"] for region in atlas["regions"]}
    surfaces = []
    for s in project.surfaces:
        if s.id not in tracks:
            continue
        data = metadata[s.id]
        if (
            not s.enabled
            or s.projector_id != outputs[0].id
            or data["role"] != s.role
            or data["logical"] != s.logical.model_dump()
        ):
            raise ValueError("Project and bundle surface definitions differ: " + s.name)
        track = tracks[s.id]
        clips = track["clips"]
        if s.role == "media" and (
            len(clips) != 1
            or clips[0]["start_seconds"] != 0
            or clips[0]["duration_seconds"] != duration
        ):
            raise ValueError("Pi 3 supports one continuous compiled clip per media surface")
        surfaces.append(
            dict(
                id=s.id,
                name=s.name,
                role=s.role,
                shape=data["shape"],
                blend_mode=data.get("blend_mode", "normal"),
                logical=data["logical"],
                color=data["light"]["color"],
                opacity=track["opacity"],
                points=s.mapping.points(),
                uv=regions[clips[0]["id"]] if clips else [0, 0, 1, 1],
            )
        )
    if {s["id"] for s in surfaces} != set(tracks) or not 1 <= len(surfaces) <= 20:
        raise ValueError("Pi 3 requires all compiled surfaces and can load up to twenty")
    audio = timeline.get("audio")
    if audio and (
        audio["start_seconds"]
        or audio["source_in_seconds"]
        or audio["duration_seconds"] != duration
        or audio["volume"] != 1
        or audio["muted"]
        or audio["sync_offset_ms"]
    ):
        raise ValueError("Pi 3 requires an aligned, full-length stereo master WAV")
    audio_path = next((s.path for s in project.scenes if audio and s.id == audio["scene_id"]), None)
    if audio and not audio_path:
        raise ValueError("Original master WAV is required for this bundle")
    return dict(
        project_name=project.name,
        width=1920,
        height=1080,
        duration=duration,
        loop=timeline["loop"],
        audio_path=audio_path,
        surfaces=surfaces,
        bundle_id=manifest["id"],
    )


def textures(video, output, total):
    size_bytes = SIZE * SIZE * 3
    offsets = []
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-vf",
            f"scale={SIZE}:{SIZE}:flags=area",
            "-an",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        stdout=subprocess.PIPE,
    )
    try:
        with output.open("xb") as file:
            file.write(struct.pack("<4sIII", b"PSP1", SIZE, SIZE, total))
            file.write(bytes((total + 1) * 4))
            previous = np.zeros(SIZE * SIZE, dtype=np.uint16)
            for i in range(total):
                data = process.stdout.read(size_bytes)
                if len(data) != size_bytes:
                    raise ValueError(f"Atlas ended early at frame {i}")
                rgb = np.frombuffer(data, dtype=np.uint8).reshape((-1, 3))
                r = rgb[:, 0].astype(np.uint16)
                g = rgb[:, 1].astype(np.uint16)
                b = rgb[:, 2].astype(np.uint16)
                pixels = ((r * 31 + 127) // 255 << 11) | ((g * 63 + 127) // 255 << 5)
                pixels |= (b * 31 + 127) // 255
                offsets.append(file.tell())
                key = i % FPS == 0
                delta = pixels if key else pixels ^ previous
                if key or np.any(delta):
                    file.write(zlib.compress(delta.astype("<u2", copy=False).tobytes(), 3))
                previous = pixels
            if process.stdout.read(1) or process.wait():
                raise ValueError("Atlas frame count differs from the compiled timeline")
            offsets.append(file.tell())
            if offsets[-1] >= 2**31:
                raise ValueError("Pi 3 texture file exceeds the size limit")
            file.seek(16)
            file.write(struct.pack(f"<{len(offsets)}I", *offsets))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("project", type=Path)
    p.add_argument("bundle", type=Path)
    p.add_argument("video", type=Path, help="already extracted playback.mp4")
    p.add_argument("output", type=Path)
    args = p.parse_args()
    project = ProjectStore(args.project).load()
    with ZipFile(args.bundle) as bundle:
        manifest, atlas, automation, video = read_metadata(bundle)
    if manifest["profile"]["name"] != "pi4-1080p":
        raise ValueError("Build the project using the single 1080p output profile")
    with args.video.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    if digest != video["sha256"] or args.video.stat().st_size != video["bytes"]:
        raise ValueError("Playback video does not match the verified show bundle")
    show = show_data(project, atlas, automation, manifest)
    args.output.mkdir()
    textures(args.video, args.output / "atlas.psp", round(show["duration"] * FPS))
    (args.output / "show.json").write_text(json.dumps(show, indent=2) + "\n")
    print("Generated", args.output, "from bundle", show["bundle_id"])


if __name__ == "__main__":
    main()
