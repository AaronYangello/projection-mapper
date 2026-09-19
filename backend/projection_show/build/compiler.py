"""Content-addressed FFmpeg atlas compilation with independent video/audio/metadata keys."""

import fcntl
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import av

from ..config.models import Project
from ..config.store import atomic_write
from ..media.catalog import probe, resolve_media
from ..storage import DEFAULT_LIMITS, digest, free_space, sync_directory
from ..timeline import source_bounds
from .profile import get_profile, validate_profile

COMPILER_VERSION = 1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def key(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def executable():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise ValueError(
            "FFmpeg unavailable. Install projection-show[compiler] on the authoring Mac"
        ) from e


def version():
    return subprocess.run(
        [executable(), "-version"], capture_output=True, text=True, timeout=10, check=True
    ).stdout.splitlines()[0]


def check_cancel(cancel):
    if cancel.is_set():
        raise ValueError("Build cancelled")


def run_ffmpeg(args, work, cancel, progress, duration):
    """No shell. Bounded diagnostic tail on disk; cancellable child process."""
    check_cancel(cancel)
    log = work / "ffmpeg.log"
    progressfile = work / "progress.txt"
    progressfile.unlink(missing_ok=True)
    with log.open("wb") as stderr:
        process = subprocess.Popen(
            [
                executable(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-progress",
                str(progressfile),
                *args,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
        )
        try:
            while process.poll() is None:
                if cancel.wait(0.1):
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise ValueError("Build cancelled")
                if progressfile.exists():
                    with progressfile.open("rb") as p:
                        p.seek(max(0, progressfile.stat().st_size - 4096))
                        lines = p.read().decode(errors="replace").splitlines()
                    values = [
                        int(line.split("=")[1])
                        for line in lines
                        if line.startswith("out_time_us=") and line.split("=")[1].isdigit()
                    ]
                    if values:
                        progress(min(0.99, values[-1] / 1e6 / duration), "Encoding")
            if process.returncode:
                with log.open("rb") as f:
                    f.seek(max(0, log.stat().st_size - 3000))
                    error = f.read().decode(errors="replace")
                raise ValueError("FFmpeg failed: " + error.strip())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    check_cancel(cancel)


def media_info(path):
    with av.open(str(path), options={"protocol_whitelist": "file", "enable_drefs": "0"}) as c:
        videos = list(c.streams.video)
        audio = list(c.streams.audio)
        if len(videos) != 1 or len(audio) > 1:
            raise ValueError("Playback must have exactly one video and at most one audio stream")
        v = videos[0]
        info = {
            "width": v.width,
            "height": v.height,
            "fps": float(v.average_rate or 0),
            "video_codec": v.codec_context.name,
            "pixel_format": v.codec_context.format.name,
            "duration": float((c.duration or 0) / av.time_base),
            "audio_codec": audio[0].codec_context.name if audio else None,
            "audio_channels": audio[0].codec_context.channels if audio else 0,
            "stream_count": len(c.streams),
        }
        next(c.decode(video=0))
        return info


def validate_playback(path, profile, duration, has_audio):
    info = media_info(path)
    expected = (profile.width, profile.height, profile.fps, "h264", "yuv420p")
    actual = tuple(info[k] for k in ["width", "height", "fps", "video_codec", "pixel_format"])
    if actual != expected or abs(info["duration"] - duration) > 0.15:
        raise ValueError(f"Playback media does not match profile/duration: {info}")
    if (
        bool(info["audio_codec"]) != has_audio
        or (has_audio and (info["audio_codec"] != "aac" or info["audio_channels"] != 2))
        or info["stream_count"] != 1 + int(has_audio)
    ):
        raise ValueError("Playback audio or stream count does not match manifest")
    return info


def plan(project: Project, root: Path, profile_name="pi4-1080p", encoder="auto", cancel=None):
    project = Project.model_validate(project.model_dump(mode="json"))
    if encoder not in ("auto", "libx264", "h264_videotoolbox"):
        raise ValueError("Unknown encoder backend")
    cancel = cancel or threading.Event()
    profile = get_profile(profile_name)
    validation = validate_profile(project, profile)
    sources = {s.id: s for s in project.scenes}
    ids = {c.scene_id for t in project.show.timeline.tracks for c in t.clips}
    audio = project.show.timeline.audio
    if audio:
        ids.add(audio.scene_id)
    entries = []
    hashes = {}
    for sid in sorted(ids):
        check_cancel(cancel)
        s = sources[sid]
        if s.type != "color":
            e = probe(root, s.path)
            entries.append(e)
            if e["error"]:
                raise ValueError(f"{s.name} ({s.path}): {e['error']}")
            hashes[sid] = digest(resolve_media(root, s.path), cancel)
    errors = source_bounds(project, entries)
    if errors:
        raise ValueError("; ".join(errors))
    surfaces = {s.id: s for s in project.surfaces}
    video_sources = {
        sid: sources[sid].model_dump(mode="json")
        for sid in sorted(ids)
        if sources[sid].type != "audio"
    }
    for data in video_sources.values():
        for ignored in [
            "name",
            "enabled",
            "tags",
            "path",
            "playback",
            "end_behavior",
            "start_seconds",
            "end_seconds",
        ]:
            data.pop(ignored, None)
    video_inputs = {
        "compiler": COMPILER_VERSION,
        "profile": validation["profile"],
        "tool": version(),
        "encoder": encoder,
        "duration": project.show.timeline.duration_seconds,
        "atlas": validation["atlas"],
        "tracks": [
            {
                "surface_id": t.surface_id,
                "logical": surfaces[t.surface_id].logical.model_dump(),
                "clips": [c.model_dump() for c in t.clips],
            }
            for t in sorted(project.show.timeline.tracks, key=lambda t: t.surface_id)
            if t.clips
        ],
        "sources": video_sources,
        "hashes": {sid: h for sid, h in hashes.items() if sources[sid].type != "audio"},
    }
    video_key = key(video_inputs)
    audio_inputs = {
        "video_key": video_key,
        "audio": {
            k: v
            for k, v in audio.model_dump().items()
            if k not in ("volume", "muted", "sync_offset_ms")
        }
        if audio
        else None,
        "hash": hashes.get(audio.scene_id) if audio else None,
    }
    required = [
        {
            "id": t.surface_id,
            "role": surfaces[t.surface_id].role,
            "logical": surfaces[t.surface_id].logical.model_dump(),
        }
        for t in project.show.timeline.tracks
    ]
    automation = {
        "schema_version": 1,
        "timeline": project.show.timeline.model_dump(mode="json"),
        "surfaces": [
            {
                "id": t.surface_id,
                "role": surfaces[t.surface_id].role,
                "shape": surfaces[t.surface_id].shape,
                "light": surfaces[t.surface_id].light.model_dump(),
                "logical": surfaces[t.surface_id].logical.model_dump(),
            }
            for t in project.show.timeline.tracks
        ],
    }
    metadata = {
        "automation": automation,
        "required_surfaces": required,
        "source_project": {"id": project.id, "name": project.name},
    }
    return {
        **validation,
        "video_key": video_key,
        "audio_key": key(audio_inputs),
        "metadata_key": key(metadata),
        "input_hashes": hashes,
        "tool_version": video_inputs["tool"],
        "automation": automation,
        "required_surfaces": required,
        "source_project": metadata["source_project"],
        "encoder_request": encoder,
    }


def change_kind(current, previous):
    if not previous or current["video_key"] != previous.get("video_key"):
        return "video_recompile"
    if current["audio_key"] != previous.get("audio_key"):
        return "audio_remux"
    if current["metadata_key"] != previous.get("metadata_key"):
        return "manifest_only"
    return "current"  # Mapping, projector viewport and calibration do not enter build keys.


def encoding_args(backend):
    if backend == "h264_videotoolbox":
        return [
            "-c:v",
            backend,
            "-allow_sw",
            "0",
            "-b:v",
            "10M",
            "-profile:v",
            "high",
            "-level:v",
            "4.1",
            "-g",
            "30",
            "-bf",
            "0",
        ]
    return [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "19",
        "-profile:v",
        "high",
        "-level:v",
        "4.1",
        "-g",
        "30",
        "-bf",
        "0",
    ]


def video_args(project, root, atlas, backend, out):
    duration = project.show.timeline.duration_seconds
    args = ["-f", "lavfi", "-i", f"color=c=black:s=1920x1080:r=30:d={duration}"]
    graph = ["[0:v]setpts=PTS-STARTPTS[base0]"]
    sources = {s.id: s for s in project.scenes}
    surfaces = {s.id: s for s in project.surfaces}
    clips = {c.id: c for t in project.show.timeline.tracks for c in t.clips}
    for i, r in enumerate(atlas["regions"], 1):
        c = clips[r["clip_id"]]
        s = sources[c.scene_id]
        surface = surfaces[r["surface_id"]]
        x, y, w, h = r["rect"]
        aspect = surface.logical.width / surface.logical.height
        logical_w = max(2, round(min(w, h * aspect) / 2) * 2)
        logical_h = max(2, round(logical_w / aspect / 2) * 2)
        if s.type == "color":
            args += [
                "-f",
                "lavfi",
                "-i",
                f"color=c={s.color}:s={logical_w}x{logical_h}:r=30:d={c.duration_seconds}",
            ]
        else:
            args += ["-protocol_whitelist", "file,pipe", "-enable_drefs", "0"]
            if s.type == "image":
                args += ["-loop", "1", "-framerate", "30"]
            args += ["-i", str(resolve_media(root, s.path))]
        fit = []
        if s.type != "color":
            if s.fit == "cover":
                fit = [
                    f"scale={logical_w}:{logical_h}:force_original_aspect_ratio=increase",
                    f"crop={logical_w}:{logical_h}:x='min(max(iw*{s.focal_point[0]}-ow/2,0),iw-ow)':y='min(max(ih*{s.focal_point[1]}-oh/2,0),ih-oh)'",
                ]
            elif s.fit == "contain":
                fit = [
                    f"scale={logical_w}:{logical_h}:force_original_aspect_ratio=decrease",
                    f"pad={logical_w}:{logical_h}:(ow-iw)/2:(oh-ih)/2:black",
                ]
            elif s.fit == "native":
                fit = [
                    f"scale=iw*{logical_w / surface.logical.width}:"
                    f"ih*{logical_h / surface.logical.height}",
                    f"pad=w='max(iw,{logical_w})':h='max(ih,{logical_h})':x=(ow-iw)/2:y=(oh-ih)/2:black",
                    f"crop={logical_w}:{logical_h}",
                ]
        filters = [
            f"trim=start={c.source_in_seconds}:duration={c.duration_seconds}",
            f"setpts=PTS-STARTPTS+{c.start_seconds}/TB",
            "fps=30",
            *fit,
            f"scale={w}:{h}",
            "setsar=1",
            "format=yuv420p",
        ]
        graph.append(f"[{i}:v]" + ",".join(filters) + f"[clip{i}]")
        graph.append(
            f"[base{i - 1}][clip{i}]overlay={x}:{y}:eof_action=pass:repeatlast=0:"
            f"enable='gte(t,{c.start_seconds})*"
            f"lt(t,{c.start_seconds + c.duration_seconds})'[base{i}]"
        )
    n = len(atlas["regions"])
    args += [
        "-filter_complex_threads",
        "2",
        "-filter_complex",
        ";".join(graph),
        "-map",
        f"[base{n}]",
        "-an",
        *encoding_args(backend),
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-t",
        str(duration),
        "-movflags",
        "+faststart",
        str(out),
    ]
    return args


def _compile_show(
    project: Project,
    root: Path,
    output: Path,
    *,
    profile_name="pi4-1080p",
    encoder="auto",
    cancel=None,
    progress=None,
):
    cancel = cancel or threading.Event()
    progress = progress or (lambda *a, **kw: None)
    started = time.monotonic()
    progress(0, "Validating sources")
    p = plan(project, root, profile_name, encoder, cancel)
    profile = get_profile(profile_name)
    cache = root / "cache" / "compiler"
    cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Two video cache copies, mux, and bundle at a conservative 24 Mbit/s.
    free_space(cache, int(project.show.timeline.duration_seconds * 12_000_000), DEFAULT_LIMITS)
    with tempfile.TemporaryDirectory(prefix=".build-", dir=cache) as temporary:
        work = Path(temporary)
        video = cache / (p["video_key"] + ".mp4")
        record = cache / (p["video_key"] + ".json")
        reused_video = False
        backend = None
        if video.is_file() and record.is_file():
            saved = cache_record(record)
            if saved.get("sha256") == digest(video) and saved.get("encoder") in (
                "libx264",
                "h264_videotoolbox",
            ):
                backend = saved["encoder"]
                reused_video = True
        if not reused_video:
            backends = (
                [encoder]
                if encoder != "auto"
                else ["h264_videotoolbox", "libx264"]
                if platform.system() == "Darwin"
                else ["libx264"]
            )
            for backend in backends:
                try:
                    run_ffmpeg(
                        video_args(project, root, p["atlas"], backend, work / "video.mp4"),
                        work,
                        cancel,
                        lambda v, m, backend=backend: progress(v * 0.75, m, encoder=backend),
                        project.show.timeline.duration_seconds,
                    )
                    break
                except ValueError as exc:
                    check_cancel(cancel)
                    if backend == backends[-1]:
                        raise
                    p["warnings"].append(
                        "VideoToolbox failed; used software libx264 fallback. " + str(exc)[-250:]
                    )
            validate_playback(
                work / "video.mp4", profile, project.show.timeline.duration_seconds, False
            )
            check_cancel(cancel)
            os.replace(work / "video.mp4", video)
            atomic_write(record, canonical({"sha256": digest(video), "encoder": backend}))
        mux = cache / (p["audio_key"] + ".mux.mp4")
        muxrecord = cache / (p["audio_key"] + ".mux.json")
        reused_audio = (
            mux.is_file()
            and muxrecord.is_file()
            and cache_record(muxrecord).get("sha256") == digest(mux)
        )
        if not reused_audio:
            audio = project.show.timeline.audio
            if audio:
                source = next(s for s in project.scenes if s.id == audio.scene_id)
                filters = (
                    f"atrim=start={audio.source_in_seconds}:duration={audio.duration_seconds},"
                    f"asetpts=PTS-STARTPTS,adelay={round(audio.start_seconds * 1000)}:all=1,apad"
                )
                args = [
                    "-i",
                    str(video),
                    "-protocol_whitelist",
                    "file,pipe",
                    "-i",
                    str(resolve_media(root, source.path)),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-af",
                    filters,
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-ac",
                    "2",
                    "-ar",
                    "48000",
                    "-t",
                    str(project.show.timeline.duration_seconds),
                    "-movflags",
                    "+faststart",
                    str(work / "mux.mp4"),
                ]
                run_ffmpeg(
                    args,
                    work,
                    cancel,
                    lambda v, m: progress(0.75 + v * 0.15, "Muxing master audio"),
                    project.show.timeline.duration_seconds,
                )
            else:
                shutil.copyfile(video, work / "mux.mp4")
            validate_playback(
                work / "mux.mp4", profile, project.show.timeline.duration_seconds, bool(audio)
            )
            check_cancel(cancel)
            os.replace(work / "mux.mp4", mux)
            atomic_write(muxrecord, canonical({"sha256": digest(mux)}))
        for sid, checksum in p["input_hashes"].items():
            check_cancel(cancel)
            source = next(s for s in project.scenes if s.id == sid)
            if digest(resolve_media(root, source.path), cancel) != checksum:
                raise ValueError(f"{source.name}: source changed during build; retry")
        progress(0.92, "Packaging validated bundle")
        manifest = {
            k: p[k]
            for k in (
                "profile",
                "video_key",
                "audio_key",
                "metadata_key",
                "input_hashes",
                "tool_version",
                "required_surfaces",
                "source_project",
                "warnings",
            )
        }
        manifest.update(
            bundle_version=1,
            engine_schema=2,
            id=key([p["video_key"], p["audio_key"], p["metadata_key"]])[:32],
            built_at=time.time(),
            encoder_backend=backend,
            duration_seconds=project.show.timeline.duration_seconds,
            has_audio=bool(project.show.timeline.audio),
            playback_sha256=digest(mux),
            compiler_version=COMPILER_VERSION,
        )
        files = {
            "bundle.json": canonical(manifest).encode(),
            "atlas.json": canonical(p["atlas"]).encode(),
            "automation.json": canonical(p["automation"]).encode(),
        }
        checks = {
            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in files.items()
        }
        checks["playback.mp4"] = {
            "bytes": mux.stat().st_size,
            "sha256": manifest["playback_sha256"],
        }
        files["checksums.json"] = canonical(checks).encode()
        fd, partial = tempfile.mkstemp(prefix=".bundle-", suffix=".tmp", dir=output.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED) as z:
                for name, data in files.items():
                    check_cancel(cancel)
                    z.writestr(name, data)
                with (
                    z.open("playback.mp4", "w", force_zip64=True) as target,
                    mux.open("rb") as source,
                ):
                    while chunk := source.read(1024 * 1024):
                        check_cancel(cancel)
                        target.write(chunk)
            with open(partial, "rb") as f:
                os.fsync(f.fileno())
            check_cancel(cancel)
            os.replace(partial, output)
            sync_directory(output.parent)
        finally:
            Path(partial).unlink(missing_ok=True)
    result = {
        "manifest": manifest,
        "bundle_path": str(output),
        "bundle_sha256": digest(output),
        "reused_video": reused_video,
        "reused_audio": reused_audio,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    progress(1, "Bundle ready", encoder=backend)
    return result


def cache_record(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (ValueError, OSError):
        return {}  # Cache is expendable, including after interrupted writes.


def compile_show(project, root, output, **options):
    """CLI and API share a cancellable per-project compiler lock."""
    from ..storage import safe_root

    cancel = options.setdefault("cancel", threading.Event())
    cache = safe_root(safe_root(root / "cache") / "compiler")
    with (cache / ".compiler.lock").open("a") as lock:
        while True:
            check_cancel(cancel)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                cancel.wait(0.1)
        try:
            return _compile_show(project, root, output, **options)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
