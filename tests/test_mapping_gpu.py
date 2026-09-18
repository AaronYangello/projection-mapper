import os
import time

import numpy as np
import pytest
from projection_show.mapping import homography


def test_homography_corners_and_interior():
    corners = [(0.1, 0.2), (0.9, 0.05), (0.8, 0.95), (0.2, 0.8)]
    matrix = homography(corners)
    for source, expected in zip([(0, 0), (1, 0), (1, 1), (0, 1)], corners, strict=True):
        point = matrix @ [*source, 1]
        assert point[:2] / point[2] == pytest.approx(expected)
    center = matrix @ [0.5, 0.5, 1]
    inverse = np.linalg.inv(matrix) @ (center / center[2])
    assert inverse[:2] / inverse[2] == pytest.approx([0.5, 0.5])


@pytest.fixture
def gpu():
    if os.environ.get("RUN_GPU_TESTS") != "1":
        pytest.skip("Opt in with RUN_GPU_TESTS=1; context failures then fail the test")
    import glfw
    from projection_show.render.engine import Engine, create_context

    window, context = create_context(width=320, height=240, visible=False)
    engine = Engine(context)
    yield engine
    engine.close()
    context.release()
    glfw.destroy_window(window)
    glfw.terminate()


def frame(demo):
    data = demo.model_dump(mode="json")
    data["canvas"].update(width=320, height=240)
    data["projectors"] = [
        {"id": "p", "enabled": True, "viewport": {"x": 40, "y": 20, "width": 240, "height": 200}}
    ]
    data["surfaces"] = [
        {
            **data["surfaces"][0],
            "id": "s",
            "projector_id": "p",
            "logical": {"width": 128, "height": 128},
            "mapping": {
                "top_left": [0.1, 0.1],
                "top_right": [0.85, 0.2],
                "bottom_right": [0.95, 0.85],
                "bottom_left": [0.15, 0.9],
            },
        }
    ]
    data["scenes"] = [{"id": "red", "color": "#ff0000"}]
    return {
        "project": data,
        "revision": 1,
        "blackout": False,
        "pattern": "show",
        "ambient_time": 0,
        "transport": "RUNNING",
        "scheduler": {"current": {"surface_id": "s", "scene_id": "red"}, "opacity": 1},
    }


@pytest.mark.gpu
def test_gpu_warp_black_outside_and_alpha(gpu, demo):
    f = frame(demo)
    f["project"]["ambient_profiles"] = []
    gpu.render(f)
    pixels = np.array(gpu.image())
    assert tuple(pixels[120, 160]) == (255, 0, 0)
    assert tuple(pixels[10, 10]) == (0, 0, 0)
    inverse = np.linalg.inv(homography(list(f["project"]["surfaces"][0]["mapping"].values())))
    for y in range(0, 240, 7):
        for x in range(0, 320, 7):
            point = inverse @ [(x + 0.5 - 40) / 240, (y + 0.5 - 20) / 200, 1]
            uv = point[:2] / point[2]
            if min(uv) > 0.02 and max(uv) < 0.98:
                assert tuple(pixels[y, x]) == (255, 0, 0)
            if min(uv) < -0.02 or max(uv) > 1.02:
                assert tuple(pixels[y, x]) == (0, 0, 0)
    f["scheduler"]["opacity"] = 0.5
    gpu.render(f)
    assert np.array(gpu.image())[120, 160, 0] == pytest.approx(128, abs=1)
    f["blackout"] = True
    f["pattern"] = "white"
    gpu.render(f)
    assert np.count_nonzero(np.array(gpu.image())) == 0


@pytest.mark.gpu
def test_gpu_particles_patterns_and_resource_reconfigure(gpu, demo):
    f = frame(demo)
    f["scheduler"]["opacity"] = 0
    gpu.render(f)
    first = np.array(gpu.image())
    assert np.count_nonzero(first) > 0
    f["ambient_time"] = 10
    gpu.render(f)
    assert not np.array_equal(first, np.array(gpu.image()))
    f["pattern"] = "grid"
    gpu.render(f)
    assert np.count_nonzero(np.array(gpu.image())) > np.count_nonzero(first)
    assert gpu.jpeg()[:2] == b"\xff\xd8"
    for revision in range(2, 7):
        f["revision"] = revision
        gpu.render(f)
        assert len(gpu.targets) == len(gpu.particles) == 1


@pytest.mark.gpu
def test_gpu_grid_uses_projective_texture_coordinates(gpu, demo):
    f = frame(demo)
    f["project"]["canvas"].update(width=800, height=600)
    f["project"]["projectors"][0]["viewport"] = {"x": 0, "y": 0, "width": 800, "height": 600}
    surface = f["project"]["surfaces"][0]
    surface["logical"] = {"width": 1024, "height": 1024}
    corners = [(0.15, 0.05), (0.9, 0.35), (0.65, 0.95), (0.3, 0.85)]
    surface["mapping"] = dict(zip(surface["mapping"], corners, strict=True))
    f["pattern"] = "grid"
    gpu.render(f)
    pixels = np.array(gpu.image())
    matrix = homography(corners)
    # The projected horizontal crosshair must pass through all these points. An affine
    # warp or a triangle-seam interpolation shortcut misses them on this trapezoid.
    for u in (0.2, 0.35, 0.65, 0.8):
        point = matrix @ [u, 0.5, 1]
        x, y = np.round(point[:2] / point[2] * [800, 600]).astype(int)
        assert np.max(np.min(pixels[y - 1 : y + 2, x - 1 : x + 2], axis=2)) > 235


@pytest.mark.gpu
def test_live_mapping_updates_without_reallocating_textures(gpu, demo):
    f = frame(demo)
    gpu.render(f)
    texture = gpu.targets["s"].texture.glo
    before = np.array(gpu.image())
    original = f["project"]["surfaces"][0]["mapping"]
    f["geometry_revision"] = 1
    f["calibration"] = {
        "surface_id": "s",
        "mapping": {
            "top_left": [0.3, 0.3],
            "top_right": [0.7, 0.3],
            "bottom_right": [0.7, 0.7],
            "bottom_left": [0.3, 0.7],
        },
        "pattern": "white",
        "black_others": True,
    }
    gpu.render(f)
    assert gpu.targets["s"].texture.glo == texture
    assert not np.array_equal(before, np.array(gpu.image()))
    f["calibration"]["pattern"] = "grid"
    gpu.render(f)
    assert gpu.label_texture is not None
    assert tuple(np.array(gpu.image())[10, 10]) == (0, 0, 0)
    f["calibration"] = None
    f["geometry_revision"] = 2
    gpu.render(f)
    assert np.array_equal(before, np.array(gpu.image()))
    assert f["project"]["surfaces"][0]["mapping"] == original


@pytest.mark.gpu
def test_native_video_texture_playback_hold_loop_and_blackout(gpu, demo, movie):
    root, _ = movie
    f = frame(demo)
    f["project"]["ambient_profiles"] = []
    f["project"]["surfaces"][0]["mapping"] = {
        "top_left": [0.1, 0.1],
        "top_right": [0.9, 0.1],
        "bottom_right": [0.9, 0.9],
        "bottom_left": [0.1, 0.9],
    }
    f["project"]["scenes"] = [
        {
            "id": "v",
            "type": "video",
            "path": "media/fixture.mp4",
            "fit": "contain",
            "focal_point": [0.5, 0.5],
            "playback": "timed",
            "start_seconds": 0,
            "end_behavior": "hold",
        }
    ]
    f["project_root"] = str(root)
    f["media_durations"] = {"v": 2}
    f["playback_generation"] = 1
    f["scheduler"].update(current={"id": 1, "surface_id": "s", "scene_id": "v"}, elapsed=0.2)

    def present(seconds, expected_pts):
        f["scheduler"]["elapsed"] = seconds
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            gpu.render(f)
            if (
                abs((gpu.playback.health.get("pts") or 0) - expected_pts) < 0.03
                and gpu.playback.texture
            ):
                return np.array(gpu.image())
            time.sleep(0.005)
        raise AssertionError(gpu.playback.health)

    first = present(0.2, 0.2)
    assert first[120, 160, 0] > 200 and first[120, 160, 2] < 40
    assert tuple(first[50, 160]) == (0, 0, 0)  # contain letterbox
    f["transport"] = "PAUSED"
    assert np.array_equal(first, present(0.2, 0.2))
    f["transport"] = "RUNNING"
    second = present(1.2, 1.2)
    assert second[120, 160, 2] > 200
    assert present(5, 1.9)[120, 160, 2] > 200  # hold final frame
    f["project"]["scenes"][0]["end_behavior"] = "loop"
    assert present(2.2, 0.2)[120, 160, 0] > 200
    f["blackout"] = True
    gpu.render(f)
    assert np.count_nonzero(np.array(gpu.image())) == 0
    f["blackout"] = False
    assert present(2.2, 0.2)[120, 160, 0] > 200
    f["scheduler"]["phase"] = "GAP"
    f["scheduler"]["opacity"] = 0
    gpu.render(f)
    assert gpu.playback.decoder is None


@pytest.mark.gpu
def test_image_texture_orientation(gpu, demo, tmp_path):
    from PIL import Image

    pixels = np.zeros((40, 40, 3), dtype=np.uint8)
    pixels[:20, :, 0] = 240
    pixels[20:, :, 2] = 240
    (tmp_path / "media").mkdir()
    Image.fromarray(pixels).save(tmp_path / "media" / "orientation.png")
    f = frame(demo)
    f["project"]["ambient_profiles"] = []
    f["project"]["surfaces"][0]["mapping"] = {
        "top_left": [0.1, 0.1],
        "top_right": [0.9, 0.1],
        "bottom_right": [0.9, 0.9],
        "bottom_left": [0.1, 0.9],
    }
    f["project"]["scenes"] = [
        {
            "id": "i",
            "type": "image",
            "path": "media/orientation.png",
            "fit": "stretch",
            "focal_point": [0.5, 0.5],
        }
    ]
    f["project_root"] = str(tmp_path)
    f["scheduler"].update(current={"id": 1, "surface_id": "s", "scene_id": "i"}, elapsed=0)
    for _ in range(100):
        gpu.render(f)
        if gpu.playback.texture:
            break
        time.sleep(0.01)
    actual = np.array(gpu.image())
    assert actual[75, 160, 0] > 220 and actual[75, 160, 2] < 10
    assert actual[170, 160, 2] > 220 and actual[170, 160, 0] < 10
    # A valid indexed image may exceed a device's GL dimension limit. Reject it
    # as a source failure without crashing the native output or retaining stale pixels.
    gpu.playback.max_texture_size = 32
    gpu.playback.serial = -1
    gpu.render(f)
    assert gpu.playback.health["state"] == "ERROR"
    assert "GPU texture dimension limit" in gpu.playback.health["error"]
    assert gpu.playback.texture is None
