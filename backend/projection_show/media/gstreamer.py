"""One native playback pipeline, bounded RGB appsink and pipeline-authoritative clock.

This module owns no GL objects. Imports are optional; missing GStreamer is an explicit fault.
Positive sync offset delays audio (the inverse of playbin's av-offset convention).
"""

import threading
import time
from pathlib import Path

from .decoder import DecodedFrame


class _Pipeline:
    def __init__(self, path: Path, *, audio_sink="auto", audio_device="", duration=0):
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstApp", "1.0")
        from gi.repository import Gst

        Gst.init(None)
        self.Gst = Gst
        self.duration = duration
        self.pipeline = Gst.ElementFactory.make("playbin")
        self.sink = Gst.ElementFactory.make("appsink")
        if not self.pipeline or not self.sink:
            raise ValueError("GStreamer playbin/appsink plugins are missing")
        self.sink.set_property("caps", Gst.Caps.from_string("video/x-raw,format=RGB"))
        self.sink.set_property("max-buffers", 2)
        self.sink.set_property("drop", True)
        self.sink.set_property("sync", True)
        self.sink.set_property("wait-on-eos", False)
        self.pipeline.set_property("video-sink", self.sink)
        factory = {"auto": "autoaudiosink", "alsa": "alsasink", "fake": "fakesink"}.get(audio_sink)
        if not factory:
            raise ValueError("Audio sink must be auto, alsa, or fake")
        sink = Gst.ElementFactory.make(factory)
        if not sink:
            raise ValueError(f"GStreamer {factory} plugin is unavailable")
        if audio_sink == "fake":
            sink.set_property("sync", True)
        if audio_device:
            if not sink.find_property("device"):
                raise ValueError("Select the ALSA audio sink to specify an HDMI device")
            sink.set_property("device", audio_device)
        self.pipeline.set_property("audio-sink", sink)
        self.pipeline.set_property("uri", path.resolve().as_uri())
        # Video + audio + software volume. Omitting soft-volume leaves playbin's
        # volume/mute properties disconnected when the selected sink has no mixer.
        self.pipeline.set_property("flags", 0x01 | 0x02 | 0x10)
        self.bus = self.pipeline.get_bus()
        self.generation = -1
        self.requested_generation = -1
        self.serial = 0
        self.frame = None
        self.last_pts = None
        self.state = "LOADING"
        self.error = None
        self.last_frame = time.monotonic()
        self.loop_count = 0
        self.factories = set()
        self.audio_factories = set()
        self.metadata_lock = threading.Lock()
        self.warning = None
        self.audio_factory = factory
        self.audio_device = audio_device
        self.expected_state = None
        # No Python callbacks from native streaming threads: playbin property setters
        # can hold the GIL while waiting on a lock held by those threads.
        self.settings = None
        if self.pipeline.set_state(Gst.State.PAUSED) == Gst.StateChangeReturn.FAILURE:
            self.pipeline.set_state(Gst.State.NULL)
            raise ValueError("GStreamer failed to preroll the playback stream")

    def _element(self, element):
        factory = element.get_factory()
        if factory:
            kind = factory.get_metadata("klass") or ""
            name = factory.get_name()
            with self.metadata_lock:
                if "Decoder" in kind and "Bin" not in kind:
                    self.factories.add(name)
                if "Sink" in kind and "Audio" in kind:
                    self.audio_factories.add(name)
            if name in ("fakesink", "fakeaudiosink") and self.audio_factory != "fakesink":
                self.error = (
                    "Audio output fell back to a silent sink; select a working audio device"
                )
                self.state = "ERROR"

    def inspect_elements(self):
        iterator = self.pipeline.iterate_recurse()
        for _ in range(256):
            result, element = iterator.next()
            if result == self.Gst.IteratorResult.RESYNC:
                iterator.resync()
            elif result == self.Gst.IteratorResult.OK:
                self._element(element)
            else:
                break

    def seek(self, seconds, loop, *, flush=True):
        G = self.Gst
        flags = G.SeekFlags.ACCURATE
        if flush:
            flags |= G.SeekFlags.FLUSH
        if loop:
            flags |= G.SeekFlags.SEGMENT
        return self.pipeline.seek(
            1.0,
            G.Format.TIME,
            flags,
            G.SeekType.SET,
            int(seconds * G.SECOND),
            G.SeekType.SET,
            int(self.duration * G.SECOND),
        )

    def update(self, *, seconds, generation, playing, loop, audio):
        G = self.Gst
        self.requested_generation = generation
        if self.state == "LOADING" and time.monotonic() - self.last_frame > 15:
            self.error = "Playback preroll timed out after fifteen seconds"
            self.state = "ERROR"
        for _ in range(256):
            message = self.bus.pop()
            if message is None:
                break
            if message.type == G.MessageType.ERROR:
                error, _ = message.parse_error()
                self.error = str(error)
                self.state = "ERROR"
                self.pipeline.set_state(G.State.PAUSED)
            elif message.type == G.MessageType.WARNING:
                warning, _ = message.parse_warning()
                self.warning = str(warning)[:300]
            elif message.type in (G.MessageType.SEGMENT_DONE, G.MessageType.EOS):
                if loop and playing:
                    if not self.seek(0, True, flush=message.type == G.MessageType.EOS):
                        self.error = "Loop seek failed"
                        self.state = "ERROR"
                    else:
                        self.loop_count += 1
                else:
                    self.state = "ENDED"
                    self.pipeline.set_state(G.State.PAUSED)
        if self.error:
            self.pipeline.set_state(G.State.PAUSED)
            return self.frame, self.health()
        _, state, pending = self.pipeline.get_state(0)
        if state >= G.State.PAUSED and self.settings != audio:
            self.pipeline.set_property("volume", (audio or {}).get("volume", 1))
            self.pipeline.set_property("mute", (audio or {}).get("muted", False))
            self.pipeline.set_property(
                "av-offset", -int((audio or {}).get("sync_offset_ms", 0) * 1_000_000)
            )
            self.settings = dict(audio or {})
            self.inspect_elements()
        if state >= G.State.PAUSED and self.generation != generation:
            if not self.seek(min(seconds, max(0, self.duration - 1 / 1000)), loop):
                self.state = "ERROR"
                self.error = "Playback stream is not seekable"
                return self.frame, self.health()
            self.generation = generation
            self.last_frame = time.monotonic()
            self.state = "READY"
        desired = (
            G.State.PLAYING
            if playing and self.generation == generation and self.state != "ENDED"
            else G.State.PAUSED
        )
        if desired != self.expected_state:
            self.pipeline.set_state(desired)
            self.expected_state = desired
            if desired == G.State.PLAYING:
                self.last_frame = time.monotonic()  # Resuming a long pause is not a stall.
        sample = self.sink.emit("try-pull-sample", 0)
        if sample is None and not playing:
            sample = self.sink.emit("try-pull-preroll", 0)
        if sample:
            buffer = sample.get_buffer()
            caps = sample.get_caps().get_structure(0)
            w = caps.get_value("width")
            h = caps.get_value("height")
            if w * h > 33_554_432:
                raise ValueError("GStreamer frame exceeds decode budget")
            pts = buffer.pts / G.SECOND
            if pts != self.last_pts:
                ok, info = buffer.map(G.MapFlags.READ)
                if ok:
                    try:
                        stride = ((w * 3 + 3) // 4) * 4
                        raw = bytes(info.data)
                        if len(raw) != w * h * 3:
                            raw = b"".join(raw[y * stride : y * stride + w * 3] for y in range(h))
                        self.serial += 1
                        self.frame = DecodedFrame(self.serial, pts, (w, h), raw)
                    finally:
                        buffer.unmap(info)
                self.last_pts = pts
                self.last_frame = time.monotonic()
        if playing and self.state == "READY" and time.monotonic() - self.last_frame > 5:
            self.state = "ERROR"
            self.error = "Video frames have stalled for more than five seconds"
            self.pipeline.set_state(G.State.PAUSED)
        return self.frame, self.health()

    def health(self):
        G = self.Gst
        ok, position = self.pipeline.query_position(G.Format.TIME)
        seconds = max(0, position / G.SECOND) if ok else 0
        if self.state == "ENDED":
            seconds = self.duration
        clock = self.pipeline.get_clock()
        with self.metadata_lock:
            factories = sorted(self.factories)
            audio_factories = sorted(self.audio_factories)
        return {
            "state": self.state,
            "backend": "GStreamer",
            "decoder_factories": factories,
            "audio_factories": audio_factories,
            "clock": clock.get_name() if clock else "preroll",
            "position": seconds,
            "pts": self.last_pts,
            "decoded_frames": self.serial,
            "generation": self.requested_generation if self.state == "ERROR" else self.generation,
            "loop_count": self.loop_count,
            "audio_sink": self.audio_factory,
            "audio_device": self.audio_device or "system default",
            "volume": self.pipeline.get_property("volume"),
            "muted": self.pipeline.get_property("mute"),
            "sync_offset_ms": -self.pipeline.get_property("av-offset") / 1e6,
            "av_skew_ms": None
            if self.last_pts is None
            else round((self.last_pts - seconds) * 1000, 2),
            "stale_seconds": round(time.monotonic() - self.last_frame, 3),
            "error": self.error,
            "warning": self.warning,
            "dropped_frames": self.sink.get_property("dropped")
            if self.sink.find_property("dropped")
            else None,
        }

    def close(self):
        self.pipeline.set_state(self.Gst.State.NULL)


class GstPlayback:
    """Latest-command/latest-frame bridge. Native control never runs on the GL thread."""

    def __init__(self, path, **options):
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.command = None
        self.frame = None
        self.telemetry = {"state": "LOADING", "backend": "GStreamer", "generation": -1}
        self.updated = time.monotonic()
        self.thread = threading.Thread(
            target=self._run, args=(path, options), name="atlas-playback", daemon=True
        )
        self.thread.start()

    def _run(self, path, options):
        pipeline = None
        try:
            pipeline = _Pipeline(path, **options)
            while not self.stop.is_set():
                self.wake.wait(0.01)
                self.wake.clear()
                with self.lock:
                    command = self.command
                if command:
                    frame, health = pipeline.update(**command)
                    with self.lock:
                        self.frame, self.telemetry = frame, health
                        self.updated = time.monotonic()
        except Exception as exc:
            with self.lock:
                self.telemetry = {
                    "state": "ERROR",
                    "backend": "GStreamer",
                    "error": str(exc)[:300],
                    "generation": (self.command or {}).get("generation", -1),
                }
                self.updated = time.monotonic()
        finally:
            if pipeline:
                pipeline.close()

    def update(self, **command):
        with self.lock:
            self.command = {**command, "audio": dict(command.get("audio") or {})}
            health = dict(self.telemetry)
            age = time.monotonic() - self.updated
            if not self.thread.is_alive() or age > 3:
                health.update(
                    state="ERROR",
                    error=health.get("error") or "Native playback worker is unresponsive",
                    generation=command["generation"],
                )
            frame = self.frame
        self.wake.set()
        return frame, health

    def close(self, *, wait=False):
        self.stop.set()
        self.wake.set()
        if wait:
            self.thread.join(timeout=2)
