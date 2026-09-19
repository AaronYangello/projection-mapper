import copy
import threading

import av
import numpy as np
import pytest
from projection_show.build.compiler import change_kind, compile_show, plan
from projection_show.build.profile import layout, validate_profile
from projection_show.config.models import Project
from projection_show.storage import StorageLimits, extract_bundle


def test_real_atlas_cache_audio_and_metadata(compiled_project):
    pytest.importorskip("imageio_ffmpeg")
    project, root = compiled_project
    out = root / "show.pshow"
    r = compile_show(project, root, out, encoder="libx264")
    assert not r["reused_video"] and r["manifest"]["encoder_backend"] == "libx264"
    extracted = root / "extracted"
    extract_bundle(out, extracted, StorageLimits(free_bytes=0))
    with av.open(str(extracted / "playback.mp4")) as c:
        frames = list(c.decode(video=0))
        black = frames[3].to_ndarray(format="rgb24")
        frame = frames[30].to_ndarray(format="rgb24")
        assert black.max() < 10
        for i, (x, y) in enumerate([(480, 270), (1440, 270), (480, 810), (1440, 810)]):
            pixel = frame[y, x]
            assert pixel[i if i < 3 else 0] > 200
    with av.open(str(extracted / "playback.mp4")) as c:
        samples = np.concatenate([f.to_ndarray().reshape(-1) for f in c.decode(audio=0)])
        assert np.max(np.abs(samples[:20000])) < 0.001
        assert np.max(np.abs(samples[60000:80000])) > 0.1
    before = plan(project, root, encoder="libx264")
    project.show.timeline.tracks[0].opacity.default = 0.2
    project.show.timeline.loop = True
    assert change_kind(plan(project, root, encoder="libx264"), before) == "manifest_only"
    r2 = compile_show(project, root, out, encoder="libx264")
    assert r2["reused_video"] and r2["reused_audio"]
    project.show.timeline.audio.start_seconds = 0.75
    r3 = compile_show(project, root, out, encoder="libx264")
    assert r3["reused_video"] and not r3["reused_audio"]
    before = plan(project, root, encoder="libx264")
    project.surfaces[0].mapping.top_left = (0.08, 0.08)
    assert change_kind(plan(project, root, encoder="libx264"), before) == "current"
    project.show.timeline.tracks[0].clips[0].source_in_seconds = 1
    with pytest.raises(ValueError, match="range"):
        plan(project, root)


def test_profile_slot_reuse_and_limits(compiled_project):
    p, root = compiled_project
    assert len({r["slot"] for r in layout(p)["regions"]}) == 4
    data = p.model_dump()
    surface = copy.deepcopy(data["surfaces"][0])
    surface["id"] = "fifth"
    data["surfaces"].append(surface)
    t = copy.deepcopy(data["show"]["timeline"]["tracks"][0])
    t["id"] = "fifth"
    t["surface_id"] = "fifth"
    t["clips"][0]["id"] = "fifth"
    data["show"]["timeline"]["tracks"].append(t)
    with pytest.raises(ValueError, match="simultaneous"):
        validate_profile(Project.model_validate(data))
    t["clips"][0].update(start_seconds=0, duration_seconds=0.5)
    assert len({r["slot"] for r in layout(Project.model_validate(data))["regions"]}) == 4


def test_cancel_failure_keep_output(compiled_project, monkeypatch):
    p, root = compiled_project
    out = root / "show.pshow"
    out.write_bytes(b"previous")
    event = threading.Event()
    event.set()
    with pytest.raises(ValueError, match="cancelled"):
        compile_show(p, root, out, cancel=event)
    assert out.read_bytes() == b"previous"

    def fail(*args, **kwargs):
        raise ValueError("FFmpeg failed")

    monkeypatch.setattr("projection_show.build.compiler.run_ffmpeg", fail)
    with pytest.raises(ValueError, match="FFmpeg failed"):
        compile_show(p, root, out, encoder="libx264")
    assert out.read_bytes() == b"previous"
    assert not list(out.parent.glob(".bundle-*"))
