import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from projection_show.api import create_app
from projection_show.config.models import Project, VideoScene
from projection_show.media.catalog import playback_plan, probe, resolve_media, scan
from projection_show.media.decoder import Decoder, VideoReader, fit_transform
from projection_show.runtime import RenderBridge, Runtime
from projection_show.scheduler import Scheduler
from pydantic import ValidationError


def wait_frame(decoder, seconds):
    decoder.request(seconds)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        frame, health = decoder.snapshot()
        if frame and abs(frame.seconds - seconds) < 0.11:
            return frame, health
        if health["state"] == "ERROR":
            raise AssertionError(health)
        time.sleep(0.005)
    raise AssertionError("Decoder did not present the requested PTS")


def test_native_probe_decode_seek_and_eof(movie):
    root, path = movie
    metadata = probe(root, "media/fixture.mp4")
    assert metadata["error"] is None
    assert metadata["duration_seconds"] == pytest.approx(2)
    assert metadata["fps"] == 10
    reader = VideoReader(path)
    try:
        assert reader.at(0.2).to_ndarray(format="rgb24")[15, 30, 0] > 200
        assert reader.at(1.5).to_ndarray(format="rgb24")[15, 30, 2] > 200
        assert reader.at(0.1).to_ndarray(format="rgb24")[15, 30, 0] > 200
        assert reader.timestamp(reader.at(1.99)) == pytest.approx(1.9)
        assert reader.eof
    finally:
        reader.close()


def test_decoder_is_bounded_and_repeated_time_holds_frame(movie):
    root, _ = movie
    decoder = Decoder(root, {"type": "video", "path": "media/fixture.mp4"})
    try:
        first, _ = wait_frame(decoder, 0.2)
        repeat, _ = wait_frame(decoder, 0.2)
        assert repeat.serial == first.serial
        second, _ = wait_frame(decoder, 1.2)
        assert second.rgb != first.rgb
        rewind, _ = wait_frame(decoder, 0.2)
        assert rewind.rgb == first.rgb
        assert len(rewind.rgb) == 64 * 32 * 3
    finally:
        decoder.close()
    assert not decoder.thread.is_alive()


def test_image_source_and_corrupt_media(movie):
    root, _ = movie
    Image.new("RGB", (24, 48), (10, 80, 140)).save(root / "media" / "still.png")
    (root / "media" / "broken.mp4").write_bytes(b"invalid media")
    entries = scan(root)
    assert len(entries) == 3
    assert next(e for e in entries if e["path"] == "media/broken.mp4")["error"]
    decoder = Decoder(root, {"type": "image", "path": "media/still.png"})
    try:
        frame, _ = wait_frame(decoder, 0)
        assert frame.size == (24, 48)
        assert frame.rgb[:3] == bytes([10, 80, 140])
    finally:
        decoder.close()


def test_empty_decode_fails_instead_of_staying_loading(movie, monkeypatch):
    root, _ = movie

    def no_frames(reader, seconds, stopped):
        reader.eof = True
        return None

    # A source can change after a successful index. EOF before the first frame
    # must be actionable so runtime recovery can advance to the next cue.
    monkeypatch.setattr(VideoReader, "at", no_frames)
    decoder = Decoder(root, {"type": "video", "path": "media/fixture.mp4"})
    try:
        decoder.request(0)
        deadline = time.monotonic() + 3
        while decoder.snapshot()[1]["state"] != "ERROR" and time.monotonic() < deadline:
            time.sleep(0.005)
        frame, health = decoder.snapshot()
        assert frame is None
        assert health["state"] == "ERROR"
        assert "No decodable" in health["error"]
    finally:
        decoder.close()


@pytest.mark.parametrize(
    "path",
    [
        "../secret.mp4",
        "/etc/passwd",
        "https://example.com/video.mp4",
        "media/../../secret.mp4",
        "media\\secret.mp4",
    ],
)
def test_untrusted_paths_rejected(path):
    with pytest.raises(ValidationError):
        VideoScene(id="v", name="Video", type="video", path=path)


def test_symlink_cannot_escape_media(movie, tmp_path):
    root, _ = movie
    external = root / "private.mp4"
    external.write_bytes(b"private")
    (root / "media" / "escape.mp4").symlink_to(external)
    with pytest.raises(ValueError, match="escapes"):
        resolve_media(root, "media/escape.mp4")


def test_fit_modes_and_focal_point():
    assert fit_transform((200, 100), (100, 100), "cover") == ((0.5, 1), (0.25, 0))
    assert fit_transform((200, 100), (100, 100), "cover", (1, 0.5))[1] == (0.5, 0)
    assert fit_transform((200, 100), (100, 100), "contain") == ((1, 2), (0, -0.5))
    assert fit_transform((200, 100), (100, 100), "stretch") == ((1, 1), (0, 0))
    assert fit_transform((200, 100), (100, 100), "native") == ((0.5, 1), (0.25, 0))


def test_full_clip_duration_includes_fades_and_manual_returns_to_queue(demo, movie):
    root, _ = movie
    data = demo.model_dump()
    data["scenes"] = [
        {"id": "video", "name": "Video", "type": "video", "path": "media/fixture.mp4"}
    ]
    project = Project.model_validate(data)
    durations, unavailable, warnings = playback_plan(project, scan(root))
    scheduler = Scheduler(project, durations, unavailable)
    assert not warnings
    assert scheduler.queue[0].duration == pytest.approx(2)
    assert scheduler.queue[0].hold == 0
    planned = scheduler.queue.copy()
    scheduler.play("plane-1", "video")
    assert scheduler.current.manual
    scheduler.tick(scheduler.current.duration + scheduler.current.gap + 0.01)
    assert scheduler.current == planned[0]


def test_trim_validation_missing_media_and_timed_duration(demo, movie):
    root, _ = movie
    data = demo.model_dump()
    data["scenes"] = [
        {
            "id": "video",
            "name": "Video",
            "type": "video",
            "path": "media/fixture.mp4",
            "start_seconds": 0.5,
            "end_seconds": 1.5,
        }
    ]
    project = Project.model_validate(data)
    durations, _, _ = playback_plan(project, scan(root))
    assert durations["video"] == 1
    project.scenes[0].playback = "timed"
    scheduler = Scheduler(project, durations)
    assert scheduler.queue[0].duration > 1
    _, unavailable, warnings = playback_plan(project, [])
    assert unavailable == {"video"} and warnings
    with pytest.raises(ValidationError):
        VideoScene(
            id="v", name="v", type="video", path="media/v.mp4", start_seconds=2, end_seconds=1
        )


def test_media_api_index_add_play_and_failed_decode_recovery(store, movie):
    root, path = movie
    # Store fixture lives in the same per-test root as movie.
    if path.parent != store.path.parent / "media":
        raise AssertionError("Fixture directories must share the project root")
    runtime = Runtime(store, RenderBridge())
    with TestClient(create_app(runtime)) as client:
        assets = client.get("/api/media").json()["assets"]
        asset = assets[0]
        assert client.get(f"/api/media/{asset['id']}/thumbnail").status_code == 200
        assert client.post(f"/api/media/{asset['id']}/add").status_code == 409
        client.post("/api/runtime/stop")
        assert client.post("/api/media/scan").status_code == 200
        assert client.post(f"/api/media/{asset['id']}/add").status_code == 200
        result = client.post(
            "/api/manual/play", json={"surface_id": "plane-1", "scene_id": asset["id"]}
        )
        assert result.status_code == 200 and result.json()["current"]["manual"]
        cue = runtime.scheduler.current
        runtime.bridge.report(
            decoder={
                "state": "ERROR",
                "cue_id": cue.id,
                "generation": runtime.playback_generation,
                "error": "file became unavailable",
            }
        )
        runtime.tick(time.monotonic())
        assert cue.scene_id in runtime.failed_media
        assert all(c.scene_id != cue.scene_id for c in runtime.scheduler.queue)
        assert runtime.scheduler.current.scene_id != cue.scene_id
        client.post("/api/runtime/stop")
        client.post("/api/media/scan")
        assert not runtime.failed_media
