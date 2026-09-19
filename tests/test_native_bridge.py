import threading
import time

from projection_show.media import gstreamer


def test_native_control_does_not_block_render_and_reports_worker_fault(monkeypatch, tmp_path):
    entered, release = threading.Event(), threading.Event()

    class Pipeline:
        def __init__(self, *args, **kwargs):
            pass

        def update(self, **command):
            entered.set()
            release.wait(2)
            raise ValueError("Synthetic decoder fault")

        def close(self):
            pass

    monkeypatch.setattr(gstreamer, "_Pipeline", Pipeline)
    player = gstreamer.GstPlayback(tmp_path / "unused.mp4")
    try:
        player.update(generation=7, playing=True)
        assert entered.wait(1)
        start = time.monotonic()
        player.update(generation=7, playing=False)  # blackout request while native call is blocked
        assert time.monotonic() - start < 0.1
        release.set()
        player.thread.join(1)
        _, health = player.update(generation=7, playing=False)
        assert health["state"] == "ERROR" and health["generation"] == 7
        assert health["error"] == "Synthetic decoder fault"
    finally:
        release.set()
        player.close(wait=True)
