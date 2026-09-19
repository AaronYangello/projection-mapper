"""Opt-in real local pipeline evidence; fakesink tests never imply HDMI/audio listening proof."""

import os
import time

import pytest
from projection_show.media.gstreamer import GstPlayback

pytestmark = [
    pytest.mark.gst,
    pytest.mark.skipif(
        os.environ.get("RUN_GSTREAMER_TESTS") != "1",
        reason="Opt in to local GStreamer integration tests",
    ),
]


def test_real_pipeline_clock_pause_seek_and_loop(compiled_project, monkeypatch):
    from types import SimpleNamespace

    import projection_show.media.gstreamer as gst_module

    elapsed = [0]
    monkeypatch.setattr(
        gst_module, "time", SimpleNamespace(monotonic=lambda: time.monotonic() + elapsed[0])
    )
    from projection_show.build.compiler import compile_show
    from projection_show.storage import StorageLimits, extract_bundle

    project, root = compiled_project
    compile_show(project, root, root / "show.pshow", encoder="libx264")
    extract_bundle(root / "show.pshow", root / "bundle", StorageLimits(free_bytes=0))
    native_instances = []
    native_factory = gst_module._Pipeline

    def capture_native(*args, **kwargs):
        native = native_factory(*args, **kwargs)
        native_instances.append(native)
        return native

    monkeypatch.setattr(gst_module, "_Pipeline", capture_native)
    player = GstPlayback(root / "bundle" / "playback.mp4", audio_sink="fake", duration=2)

    def tick(seconds=0, generation=1, playing=True, loop=False, volume=1, muted=False):
        began = time.monotonic()
        frame, health = player.update(
            seconds=seconds,
            generation=generation,
            playing=playing,
            loop=loop,
            audio={"volume": volume, "muted": muted, "sync_offset_ms": 50},
        )
        assert time.monotonic() - began < 0.1  # GL caller only exchanges a bounded snapshot.
        assert health["state"] != "ERROR", health
        return frame, health

    try:
        start = time.monotonic()
        frame = None
        while time.monotonic() - start < 1.3:
            frame, health = tick()
            time.sleep(0.02)
        assert frame is not None and health["position"] > 0.3
        assert health["decoder_factories"] and health["sync_offset_ms"] == 50
        tick(volume=0.25, muted=True)
        time.sleep(0.1)
        # Verify a real mixer receives the controls, not only playbin's cached values.
        pipeline = native_instances[0].pipeline
        iterator = pipeline.iterate_recurse()
        mixers = []
        while True:
            result, element = iterator.next()
            if result != native_instances[0].Gst.IteratorResult.OK:
                break
            factory = element.get_factory()
            if factory and factory.get_name() == "volume":
                mixers.append(element)
        assert mixers and mixers[0].get_property("volume") == pytest.approx(0.25)
        assert mixers[0].get_property("mute")
        assert not health["warning"]
        tick(playing=False)
        time.sleep(0.1)
        _, a = tick(playing=False)
        time.sleep(0.1)
        _, b = tick(playing=False)
        assert b["position"] == pytest.approx(a["position"], abs=0.02)
        elapsed[0] = 10  # Long pause/blackout must not trigger a false stale-frame fault.
        time.sleep(0.05)  # Let the paused worker publish fresh health on the advanced clock.
        tick(playing=True)
        time.sleep(0.05)
        tick(playing=True)
        tick(playing=False)
        for _ in range(15):
            frame, health = tick(seconds=0.7, generation=2, playing=False)
            time.sleep(0.02)
        assert health["position"] == pytest.approx(0.7, abs=0.05)
        for _ in range(130):
            frame, health = tick(seconds=1.7, generation=3, loop=True)
            time.sleep(0.02)
        assert health["loop_count"] >= 1
        assert health["audio_sink"] == "fakesink"
    finally:
        player.close(wait=True)
        assert not player.thread.is_alive()
