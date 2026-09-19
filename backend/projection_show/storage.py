"""Bounded streams and untrusted ZIP validation. Never extract with extractall()."""

import hashlib
import json
import os
import re
import shutil
import stat
import threading
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .media.catalog import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, probe


@dataclass(frozen=True)
class StorageLimits:
    media_bytes: int = 2 * 1024**3
    bundle_bytes: int = 4 * 1024**3
    expanded_bytes: int = 8 * 1024**3
    free_bytes: int = 512 * 1024**2
    files: int = 500
    concurrent: int = 2
    zip_members: int = 8
    compression_ratio: int = 100

    def __post_init__(self):
        for name, value in self.__dict__.items():
            if type(value) is not int or value < (0 if name == "free_bytes" else 1):
                raise ValueError(
                    f"Storage limit {name} must be a positive integer (free_bytes may be zero)"
                )


DEFAULT_LIMITS = StorageLimits()


def digest(path: Path, cancel=None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            if cancel and cancel.is_set():
                raise ValueError("Hashing cancelled")
            h.update(block)
    return h.hexdigest()


def safe_root(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError("Storage root must not be a symlink")
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def sync_directory(path: Path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def free_space(path: Path, required: int, limits: StorageLimits):
    if shutil.disk_usage(path).free < required + limits.free_bytes:
        raise ValueError("Insufficient free disk space; free space or choose another data root")


def upload_name(name: str) -> str:
    if (
        not name
        or len(name) > 240
        or any(c in name for c in ("/", "\\", "\x00"))
        or name in (".", "..")
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("Use a filename without paths or control characters")
    suffix = Path(name).suffix.lower()
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(name).stem).strip("-")[:100] or "media"
    return stem + suffix


class Uploads:
    """Streaming is driven by the API; probing/hashing run off its event loop."""

    def __init__(self, root: Path, limits=DEFAULT_LIMITS):
        self.root = root.resolve()
        self.limits = limits
        self.media = safe_root(self.root / "media")
        self.partial = safe_root(self.media / ".uploads")
        self.lock = threading.Lock()
        self.jobs = {}
        # This application owns this namespace; after restart no job can resume it.
        for p in self.partial.iterdir():
            if p.is_file() or p.is_symlink():
                p.unlink()

    def begin(self, name: str, size: int) -> dict:
        name = upload_name(name)
        if Path(name).suffix not in VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS:
            raise ValueError("Unsupported media extension")
        if not 0 < size <= self.limits.media_bytes:
            raise ValueError("Upload exceeds the media size limit")
        with self.lock:
            if (
                sum(
                    j["state"] in ("waiting", "uploading", "validating") for j in self.jobs.values()
                )
                >= self.limits.concurrent
            ):
                raise ValueError("Upload slots are busy; finish or cancel another upload")
            if (
                len([p for p in self.media.rglob("*") if p.is_file() and ".uploads" not in p.parts])
                >= self.limits.files
            ):
                raise ValueError("Media file count limit reached")
            free_space(self.media, size, self.limits)
            job = {
                "id": uuid.uuid4().hex,
                "name": name,
                "size": size,
                "received": 0,
                "state": "waiting",
                "error": None,
            }
            self.jobs[job["id"]] = job
            return dict(job)

    def get(self, ident):
        if ident not in self.jobs:
            raise ValueError("Upload not found")
        return dict(self.jobs[ident])

    def path(self, ident):
        job = self.get(ident)
        return self.partial / (ident + Path(job["name"]).suffix)

    def cancel(self, ident):
        with self.lock:
            job = self.jobs.get(ident)
            if not job:
                raise ValueError("Upload not found")
            if job["state"] in ("complete", "duplicate"):
                raise ValueError("Upload already installed")
            job["state"] = "cancelled"
        self.path(ident).unlink(missing_ok=True)
        return self.get(ident)

    def start(self, ident):
        with self.lock:
            job = self.jobs[ident]
            if job["state"] != "waiting":
                raise ValueError("Upload has already started or was cancelled")
            free_space(self.media, job["size"], self.limits)
            job["state"] = "uploading"
        return self.path(ident).open("xb")

    def append(self, ident, handle, chunk):
        with self.lock:
            job = self.jobs[ident]
            if job["state"] != "uploading":
                raise ValueError("Upload cancelled")
            if job["received"] + len(chunk) > job["size"]:
                raise ValueError("Upload exceeds declared size")
            free_space(self.media, len(chunk), self.limits)
            handle.write(chunk)
            job["received"] += len(chunk)

    def validate(self, ident):
        with self.lock:
            job = self.get(ident)
            if job["state"] != "uploading" or job["received"] != job["size"]:
                raise ValueError("Incomplete or cancelled upload")
            self.jobs[ident]["state"] = "validating"
        path = self.path(ident)
        info = probe(self.root, str(path.relative_to(self.root)))
        if info["error"]:
            raise ValueError(f"Cannot install {job['name']}: {info['error']}")
        checksum = digest(path)
        for existing in self.media.rglob("*"):
            if not existing.is_file() or existing.is_symlink() or ".uploads" in existing.parts:
                continue
            if existing.stat().st_size == job["size"] and digest(existing) == checksum:
                return {
                    "duplicate": True,
                    "path": str(existing.relative_to(self.root)),
                    "hash": checksum,
                }
        name = Path(job["name"])
        if any(
            p.name == job["name"]
            or re.fullmatch(r"upload-[a-f0-9]{16}-" + re.escape(job["name"]), p.name)
            for p in self.media.iterdir()
            if p.is_file()
        ):
            raise ValueError(
                "A different file with this name exists. Rename your upload and try again"
            )
        target = self.media / f"upload-{checksum[:16]}-{name.name}"
        return {"duplicate": False, "path": str(target.relative_to(self.root)), "hash": checksum}

    def install(self, ident, result):
        with self.lock:
            job = self.jobs[ident]
            if job["state"] != "validating":
                raise ValueError("Upload cancelled")
            path = self.path(ident)
            if result["duplicate"]:
                path.unlink(missing_ok=True)
            else:
                target = self.root / result["path"]
                if target.exists():
                    raise ValueError("Upload destination already exists")
                if any(
                    p.name == job["name"]
                    or re.fullmatch(r"upload-[a-f0-9]{16}-" + re.escape(job["name"]), p.name)
                    for p in self.media.iterdir()
                    if p.is_file()
                ):
                    raise ValueError("A different file with this name was installed during upload")
                if (
                    sum(p.is_file() and ".uploads" not in p.parts for p in self.media.rglob("*"))
                    >= self.limits.files
                ):
                    raise ValueError("Media file count limit reached")
                os.replace(path, target)
                sync_directory(self.media)
            job.update(state="duplicate" if result["duplicate"] else "complete", **result)
            return dict(job)

    def fail(self, ident, error):
        if ident in self.jobs:
            if self.jobs[ident]["state"] != "cancelled":
                self.jobs[ident].update(state="error", error=str(error)[:300])
            self.path(ident).unlink(missing_ok=True)


BUNDLE_FILES = {
    "bundle.json",
    "playback.mp4",
    "atlas.json",
    "automation.json",
    "checksums.json",
    "authoring-project.yaml",
}
REQUIRED_FILES = BUNDLE_FILES - {"authoring-project.yaml"}


def extract_bundle(archive: Path, destination: Path, limits=DEFAULT_LIMITS, cancel=None) -> dict:
    """Validate the central directory before writing; verify each file while streaming."""
    if archive.stat().st_size > limits.bundle_bytes:
        raise ValueError("Bundle exceeds upload limit")
    safe_root(destination)
    try:
        with zipfile.ZipFile(archive) as z:
            members = z.infolist()
            names = [i.filename for i in members]
            if len(members) > limits.zip_members or len(names) != len(set(names)):
                raise ValueError("Excessive or duplicate ZIP members")
            if not REQUIRED_FILES <= set(names) or set(names) - BUNDLE_FILES:
                raise ValueError("Bundle contains missing or unexpected files")
            total = 0
            for i in members:
                p = PurePosixPath(i.filename)
                mode = i.external_attr >> 16
                if (
                    p.is_absolute()
                    or ".." in p.parts
                    or "\\" in i.filename
                    or len(p.parts) != 1
                    or stat.S_ISLNK(mode)
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                    or i.flag_bits & 1
                ):
                    raise ValueError("Unsafe ZIP path, link, file type, or encryption")
                total += i.file_size
                if (
                    total > limits.expanded_bytes
                    or i.file_size > max(1, i.compress_size) * limits.compression_ratio
                ):
                    raise ValueError("Archive expansion limit exceeded")
                if i.filename != "playback.mp4" and i.file_size > 8 * 1024 * 1024:
                    raise ValueError("Metadata member is too large")
            free_space(destination, total, limits)
            hashes = {}
            for i in members:
                target = destination / i.filename
                if target.exists() or target.is_symlink():
                    raise ValueError("Extraction target is not empty")
                count = 0
                h = hashlib.sha256()
                with z.open(i) as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        if cancel and cancel.is_set():
                            raise ValueError("Validation cancelled")
                        count += len(chunk)
                        if count > i.file_size:
                            raise ValueError("ZIP expanded size mismatch")
                        output.write(chunk)
                        h.update(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if count != i.file_size:
                    raise ValueError("ZIP member size mismatch")
                hashes[i.filename] = {"bytes": count, "sha256": h.hexdigest()}
            checks = json.loads((destination / "checksums.json").read_text())
            if set(checks) != set(names) - {"checksums.json"}:
                raise ValueError("Checksum file list mismatch")
            if any(checks[name] != hashes[name] for name in checks):
                raise ValueError("Bundle checksum mismatch")
            sync_directory(destination)
            return json.loads((destination / "bundle.json").read_text())
    except Exception:
        # Destination is an application-chosen staging directory, never the active deployment.
        for name in BUNDLE_FILES:
            (destination / name).unlink(missing_ok=True)
        raise
