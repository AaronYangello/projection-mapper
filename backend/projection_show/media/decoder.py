"""A bounded latest-request worker; native FFmpeg owns decoding, GL never waits on it."""

import threading
from dataclasses import dataclass
from pathlib import Path

import av
from PIL import Image, ImageOps

from .catalog import open_video, resolve_media


@dataclass(frozen=True)
class DecodedFrame:
    serial: int
    seconds: float
    size: tuple[int, int]
    rgb: bytes


class VideoReader:
    """Used only by its decoder worker. Presents the frame at/before the requested PTS."""

    def __init__(self, path: Path):
        self.container = open_video(path)
        self.stream = self.container.streams.video[0]
        self.stream.thread_type = "AUTO"
        self.stream.codec_context.thread_count = 2
        self.start = float((self.stream.start_time or 0) * self.stream.time_base)
        self.frames = iter(self.container.decode(video=0))
        self.before = self.after = None
        self.last_request = -1.0
        self.eof = False
        self.decoded = 0

    def timestamp(self, frame) -> float:
        if frame.pts is None:
            raise ValueError("Video frames require presentation timestamps")
        return float(frame.pts * frame.time_base) - self.start

    def at(self, seconds: float, stopped=lambda: False):
        if seconds < self.last_request - 0.001 or seconds - max(0, self.last_request) > 2:
            self.container.seek(
                int((seconds + self.start) / self.stream.time_base),
                stream=self.stream,
                backward=True,
            )
            self.frames = iter(self.container.decode(video=0))
            self.before = self.after = None
            self.eof = False
        self.last_request = seconds
        while not stopped():
            if self.after is None and not self.eof:
                try:
                    self.after = next(self.frames)
                    self.decoded += 1
                except StopIteration:
                    self.eof = True
            if self.after is None:
                return self.before
            if self.timestamp(self.after) > seconds + 0.00001 and self.before is not None:
                return self.before
            self.before, self.after = self.after, None
            if self.timestamp(self.before) >= seconds - 0.00001:
                return self.before
        return None

    def close(self):
        self.container.close()


class Decoder:
    """One requested timestamp and one published RGB frame; no unbounded frame queues."""

    def __init__(self, root: Path, scene: dict):
        self.condition = threading.Condition()
        self.scene = scene
        self.root = root
        self.wanted: float | None = None
        self.stopped = False
        self.frame: DecodedFrame | None = None
        self.health: dict = {
            "state": "LOADING",
            "backend": "FFmpeg / PyAV",
            "decoded_frames": 0,
            "error": None,
            "pts": None,
        }
        self.thread = threading.Thread(target=self._run, name="native-media-decoder", daemon=True)
        self.thread.start()

    def request(self, seconds: float):
        with self.condition:
            self.wanted = seconds
            self.condition.notify()

    def snapshot(self):
        with self.condition:
            return self.frame, dict(self.health)

    def _run(self):
        reader = None
        try:
            path = resolve_media(self.root, self.scene["path"])
            if self.scene["type"] == "image":
                with Image.open(path) as image:
                    if image.width * image.height > 33_554_432:
                        raise ValueError("Image exceeds decode size limit")
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    with self.condition:
                        self.frame = DecodedFrame(1, 0, image.size, image.tobytes())
                        self.health.update(state="READY", decoded_frames=1, pts=0)
                return
            reader = VideoReader(path)
            last_pts, serial = None, 0
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.stopped or self.wanted is not None)
                    if self.stopped:
                        break
                    wanted, self.wanted = self.wanted, None
                frame = reader.at(wanted, lambda: self.stopped)
                if frame is None:
                    if reader.eof and not self.stopped:
                        raise ValueError("No decodable video frames")
                    continue
                pts = reader.timestamp(frame)
                if pts != last_pts:
                    if frame.width * frame.height > 33_554_432:
                        raise ValueError("Frame exceeds decode size limit")
                    rgb = frame.to_ndarray(format="rgb24").tobytes()
                    serial += 1
                    result = DecodedFrame(serial, pts, (frame.width, frame.height), rgb)
                    with self.condition:
                        self.frame = result
                    last_pts = pts
                with self.condition:
                    self.health.update(
                        state="EOF" if reader.eof else "READY",
                        pts=pts,
                        decoded_frames=reader.decoded,
                    )
        except (
            OSError,
            ValueError,
            IndexError,
            av.FFmpegError,
            Image.DecompressionBombError,
        ) as exc:
            with self.condition:
                self.health.update(state="ERROR", error=str(exc)[:300])
        finally:
            if reader:
                reader.close()

    def close(self, *, wait=True):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()
        if wait:
            self.thread.join(timeout=2)


def fit_transform(
    source: tuple[int, int], target: tuple[int, int], mode: str, focal=(0.5, 0.5)
) -> tuple[tuple, tuple]:
    sw, sh = source
    tw, th = target
    if mode == "stretch":
        return (1.0, 1.0), (0.0, 0.0)
    scale = (
        max(tw / sw, th / sh)
        if mode == "cover"
        else min(tw / sw, th / sh)
        if mode == "contain"
        else 1
    )
    uv_scale = (tw / (sw * scale), th / (sh * scale))
    offset = tuple(
        max(0, min(1 - span, center - span / 2)) if span < 1 else (1 - span) / 2
        for span, center in zip(uv_scale, focal, strict=True)
    )
    return uv_scale, offset
