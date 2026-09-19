"""Inspect regular files inside a project's media directory, without opening network URLs."""

import hashlib
import math
import re
from pathlib import Path

import av
from PIL import Image, ImageOps

VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def resolve_media(root: Path, relative: str) -> Path:
    from ..config.models import FileScene

    relative = FileScene.local_media_path(relative)
    root = root.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root / "media"):
        raise ValueError("Media symlink escapes the project's media directory")
    if not target.is_file():
        raise ValueError("Media file is missing or is not a regular file")
    if target.suffix.lower() not in VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS:
        raise ValueError("Unsupported media extension")
    return target


def open_video(path: Path):
    return av.open(
        str(path), options={"protocol_whitelist": "file", "enable_drefs": "0"}, timeout=(5, 5)
    )


def probe(root: Path, relative: str) -> dict:
    asset_id = "asset-" + hashlib.sha256(relative.encode()).hexdigest()[:16]
    result = {
        "id": asset_id,
        "path": relative,
        "name": re.sub(r"^upload-[a-f0-9]{16}-", "", Path(relative).stem),
        "type": "image"
        if Path(relative).suffix.lower() in IMAGE_EXTENSIONS
        else "audio"
        if Path(relative).suffix.lower() in AUDIO_EXTENSIONS
        else "video",
        "error": None,
        "thumbnail": False,
    }
    try:
        path = resolve_media(root, relative)
        result["bytes"] = path.stat().st_size
        if result["type"] == "audio":
            with open_video(path) as container:
                stream = next(iter(container.streams.audio), None)
                if not stream:
                    raise ValueError("No audio stream")
                duration = (
                    float(stream.duration * stream.time_base)
                    if stream.duration
                    else float((container.duration or 0) / av.time_base)
                )
                if not math.isfinite(duration) or duration <= 0:
                    raise ValueError("A finite positive audio duration is required")
                next(container.decode(audio=0))
                result.update(
                    duration_seconds=duration,
                    codec=stream.codec_context.name,
                    channels=stream.codec_context.channels,
                    sample_rate=stream.codec_context.sample_rate,
                )
            return result
        if result["type"] == "image":
            with Image.open(path) as image:
                if image.width * image.height > 33_554_432:
                    raise ValueError("Image exceeds the 32 megapixel decode limit")
                image = ImageOps.exif_transpose(image)
                result.update(
                    width=image.width,
                    height=image.height,
                    duration_seconds=None,
                    fps=None,
                    codec=image.format or path.suffix.lstrip("."),
                )
                thumbnail = image.convert("RGB")
        else:
            with open_video(path) as container:
                stream = next(iter(container.streams.video), None)
                if stream is None:
                    raise ValueError("No video stream")
                duration = (
                    float(stream.duration * stream.time_base)
                    if stream.duration
                    else (float(container.duration / av.time_base) if container.duration else 0)
                )
                if not math.isfinite(duration) or duration <= 0.05:
                    raise ValueError(
                        "A finite video duration greater than 0.05 seconds is required"
                    )
                if stream.width * stream.height > 33_554_432:
                    raise ValueError("Video exceeds the 32 megapixel decode limit")
                # Avoid an unhelpful black opening frame. Bound thumbnail work independently
                # of clip duration, and never decode audio streams.
                sample_at = min(3.0, duration / 4)
                container.seek(int(sample_at * av.time_base))
                for index, first in enumerate(container.decode(video=0)):
                    thumbnail = first.to_image()
                    pts = float((first.pts or 0) * first.time_base)
                    if pts >= sample_at or index >= 240:
                        break
                else:
                    raise ValueError("No decodable video frames")
                result.update(
                    width=stream.width,
                    height=stream.height,
                    duration_seconds=duration,
                    fps=float(stream.average_rate) if stream.average_rate else None,
                    codec=stream.codec_context.name,
                )
        if result["width"] * result["height"] > 33_554_432:
            raise ValueError("Media exceeds the 32 megapixel decode limit")
        thumbnail.thumbnail((400, 240))
        cache = root / "cache" / "thumbnails"
        cache.mkdir(parents=True, exist_ok=True)
        thumbnail.save(cache / f"{asset_id}.jpg", "JPEG", quality=85)
        result["thumbnail"] = True
    except (
        OSError,
        ValueError,
        av.FFmpegError,
        StopIteration,
        Image.DecompressionBombError,
    ) as exc:
        result["error"] = str(exc)[:300] or "Could not decode media"
    return result


def scan(root: Path, configured_paths: list[str] = ()) -> list[dict]:
    folder = root / "media"
    paths = set(configured_paths)
    if folder.is_dir() and folder.resolve().is_relative_to(root.resolve()):
        paths.update(
            str(p.relative_to(root))
            for p in folder.rglob("*")
            if not any(part.startswith(".") for part in p.relative_to(folder).parts)
            and p.suffix.lower() in VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS
        )
    if len(paths) > 500:
        raise ValueError("This milestone supports scanning up to 500 media files per project")
    return [probe(root, path) for path in sorted(paths)]


def playback_plan(project, entries: list[dict]) -> tuple[dict[str, float], set[str], list[str]]:
    indexed = {entry["path"]: entry for entry in entries}
    durations, unavailable, warnings = {}, set(), []
    for scene in project.scenes:
        if scene.type == "color":
            continue
        entry = indexed.get(scene.path)
        error = "File has not been indexed" if not entry else entry.get("error")
        if entry and entry["type"] != scene.type:
            error = "Scene type does not match media file"
        if not error and scene.type == "video":
            duration = min(
                scene.end_seconds or entry["duration_seconds"], entry["duration_seconds"]
            )
            duration -= scene.start_seconds
            if duration <= 0.05:
                error = "Clip starts after the video ends or has no playable duration"
            else:
                durations[scene.id] = duration
        if error:
            unavailable.add(scene.id)
            if scene.enabled:
                warnings.append(f"{scene.name}: {error}")
    return durations, unavailable, warnings
