"""Bounded asynchronous JPEG encoding for the renderer's downscaled preview."""

import io
import threading
import time
from collections.abc import Callable

from PIL import Image


def encode_preview(size: tuple[int, int], pixels: bytes) -> bytes:
    """Encode bottom-up RGB framebuffer bytes as a browser-ready JPEG."""
    image = Image.frombytes("RGB", size, pixels).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    stream = io.BytesIO()
    image.save(stream, "JPEG", quality=80)
    return stream.getvalue()


class PreviewEncoder:
    """Encode off the render thread with at most one queued frame."""

    def __init__(self, publish: Callable[[bytes], object]):
        self.publish = publish
        self.condition = threading.Condition()
        self.pending: tuple[tuple[int, int], bytes, float] | None = None
        self.encoding = False
        self.closing = False
        self.submitted_total = 0
        self.encoded_total = 0
        self.dropped_total = 0
        self.last_encode_ms = 0.0
        self.last_age_ms = 0.0
        self.thread = threading.Thread(target=self._run, name="preview-jpeg-encoder", daemon=True)
        self.thread.start()

    def can_accept(self) -> bool:
        with self.condition:
            return not self.closing and self.pending is None

    def submit(self, size: tuple[int, int], pixels: bytes) -> bool:
        with self.condition:
            if self.closing or self.pending is not None:
                self.dropped_total += 1
                return False
            self.pending = (size, pixels, time.monotonic())
            self.submitted_total += 1
            self.condition.notify()
            return True

    def snapshot(self) -> dict:
        with self.condition:
            return {
                "submitted_total": self.submitted_total,
                "encoded_total": self.encoded_total,
                "dropped_total": self.dropped_total,
                "pending": self.pending is not None,
                "encoding": self.encoding,
                "last_encode_ms": round(self.last_encode_ms, 2),
                "last_age_ms": round(self.last_age_ms, 2),
            }

    def close(self) -> None:
        with self.condition:
            self.closing = True
            self.condition.notify()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        while True:
            with self.condition:
                while self.pending is None and not self.closing:
                    self.condition.wait()
                if self.pending is None and self.closing:
                    return
                size, pixels, submitted = self.pending
                self.pending = None
                self.encoding = True
            started = time.monotonic()
            jpeg = encode_preview(size, pixels)
            finished = time.monotonic()
            self.publish(jpeg)
            with self.condition:
                self.encoding = False
                self.encoded_total += 1
                self.last_encode_ms = (finished - started) * 1000
                self.last_age_ms = (finished - submitted) * 1000
                if self.closing and self.pending is None:
                    self.condition.notify()
