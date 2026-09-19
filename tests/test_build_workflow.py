import json
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from projection_show.api import create_app
from projection_show.build.compiler import compile_show, plan, video_args
from projection_show.config.store import ProjectStore
from projection_show.runtime import RenderBridge, Runtime
from projection_show.services import Services
from projection_show.storage import StorageLimits
from projection_show.target import TargetSettings, deploy, private_url


def wait_job(client, job):
    deadline = time.monotonic() + 20
    while job["state"] in ("running", "queued") and time.monotonic() < deadline:
        time.sleep(0.01)
        job = client.get("/api/builds/" + job["id"]).json()
    return job


def test_real_build_streaming_export_preview_and_staleness(compiled_project):
    p, root = compiled_project
    store = ProjectStore(root / "project.yaml")
    store.save(p)
    r = Runtime(store, RenderBridge())
    with TestClient(create_app(r)) as client:
        job = wait_job(
            client,
            client.post("/api/builds", json={"revision": r.revision, "encoder": "libx264"}).json(),
        )
        assert job["state"] == "complete", job
        assert client.get("/api/builds/download").status_code == 401
        response = client.post("/api/builds/latest/download")
        assert (
            "HttpOnly" in response.headers["set-cookie"]
            and "SameSite=strict" in response.headers["set-cookie"]
        )
        assert client.get(response.json()["url"]).content[:2] == b"PK"
        assert client.get(response.json()["url"]).status_code == 401  # one use
        before = store.path.read_bytes()
        assert client.post("/api/builds/latest/preview").status_code == 200
        assert r.status()["deployment_kind"] == "preview"
        assert store.path.read_bytes() == before
        assert client.post("/api/builds/preview/unload").status_code == 200
        job = wait_job(
            client,
            client.post(
                "/api/builds/inspect", json={"revision": r.revision, "encoder": "libx264"}
            ).json(),
        )
        assert job["result"]["change"] == "current"


def test_cache_recovers_and_shell_metacharacters_are_literal(compiled_project):
    p, root = compiled_project
    out = root / "safe.pshow"
    first = compile_show(p, root, out, encoder="libx264")
    record = root / "cache" / "compiler" / (first["manifest"]["video_key"] + ".json")
    record.write_text("interrupted")
    second = compile_show(p, root, out, encoder="libx264")
    assert not second["reused_video"]
    source = p.scenes[0]
    strange = "media/$(touch INJECTED); literal.mp4"
    (root / source.path).rename(root / strange)
    source.path = strange
    build_plan = plan(p, root, encoder="libx264")
    args = video_args(p, root, build_plan["atlas"], "libx264", root / "out.mp4")
    assert str(root / strange) in args
    compile_show(p, root, out, encoder="libx264")
    assert not (root / "INJECTED").exists()


def test_cancel_during_encoding_publishes_nothing(compiled_project, monkeypatch):
    p, root = compiled_project
    cancelled = threading.Event()

    def cancellation(*args):
        cancelled.set()
        raise ValueError("Build cancelled")

    monkeypatch.setattr("projection_show.build.compiler.run_ffmpeg", cancellation)
    with pytest.raises(ValueError, match="cancelled"):
        compile_show(p, root, root / "partial.pshow", cancel=cancelled)
    assert not (root / "partial.pshow").exists()
    assert not list((root / "cache/compiler").glob(".build-*"))


def test_recovery_after_corrupt_active_bundle_and_explicit_unload(compiled_project):
    p, root = compiled_project
    store = ProjectStore(root / "project.yaml")
    store.save(p)
    r = Runtime(store, RenderBridge())
    s = Services(r, data_root=root / "data", limits=StorageLimits(free_bytes=0))
    compile_show(p, root, root / "one.pshow", encoder="libx264")
    one = s.deployments.stage(root / "one.pshow", p)
    s.deployments.activate(one, None)
    p.show.timeline.loop = True
    compile_show(p, root, root / "two.pshow", encoder="libx264")
    two = s.deployments.stage(root / "two.pshow", p)
    s.deployments.activate(two, one["manifest"]["id"])
    (Path(two["directory"]) / "playback.mp4").write_bytes(b"corrupted")
    s.jobs.close()
    r = Runtime(store, RenderBridge())
    s = Services(r, data_root=root / "data")
    assert s.deployments.state()["active"] == one["manifest"]["id"]
    assert r.state == "READY" and "recovered previous" in r.deployment_warning
    s.deployments.unload(one["manifest"]["id"])
    r.unload_deployment()
    assert s.deployments.state()["active"] is None and r.deployment is None
    s.jobs.close()


def test_audio_settings_apply_and_restart_are_machine_local(store):
    r = Runtime(store, RenderBridge())
    r.command("stop")
    original = store.path.read_bytes()
    with TestClient(create_app(r)) as c:
        assert (
            c.put("/api/runtime/audio", json={"volume": 0.5, "sync_offset_ms": 1001}).status_code
            == 422
        )
        assert (
            c.put(
                "/api/runtime/audio",
                json={"audio_sink": "fake", "volume": 0.5, "sync_offset_ms": 75},
            ).status_code
            == 200
        )
        r.command("start")
        assert (
            c.put(
                "/api/runtime/audio", json={"audio_sink": "alsa", "audio_device": "hw:1,0"}
            ).status_code
            == 409
        )
        assert (
            c.put("/api/runtime/audio", json={"audio_sink": "fake", "muted": True}).status_code
            == 200
        )
        assert r.bridge.read()["audio_overrides"] == {"muted": True}
    assert store.path.read_bytes() == original
    second = Runtime(store, RenderBridge())
    services = Services(second)
    assert second.playback_options["audio_sink"] == "fake" and second.audio_overrides["muted"]
    services.jobs.close()


def test_remote_protocol_stream_cancel_and_activation_response(tmp_path):
    calls = []
    bundle = tmp_path / "example.pshow"
    bundle.write_bytes(b"bundle" * 10000)
    cancellation = threading.Event()

    def respond(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/deployments":
            return httpx.Response(200, json={"active": "previous"})
        if request.url.path.endswith("/upload"):
            assert request.read() == bundle.read_bytes()
            return httpx.Response(200, json={"id": "job", "state": "running"})
        if request.url.path == "/api/builds/job":
            return httpx.Response(
                200, json={"state": "complete", "result": {"manifest": {"id": "bundle-id"}}}
            )
        if request.url.path.endswith("/activate"):
            assert json.loads(request.content) == {"confirmed": True, "expected_active": "previous"}
            return httpx.Response(200, json={"active": "bundle-id", "previous": "previous"})
        raise AssertionError(request.url.path)

    class Settings:
        def client(self, saved=None):
            return httpx.Client(
                transport=httpx.MockTransport(respond), base_url="https://private.test"
            )

    result = deploy(
        Settings(), bundle, "previous", cancellation, lambda *a: None, expected_bundle="bundle-id"
    )
    assert result["activation_confirmed"] and calls[-1][1].endswith("/activate")
    calls.clear()
    cancellation.set()
    with pytest.raises(ValueError, match="cancelled"):
        deploy(Settings(), bundle, "previous", cancellation, lambda *a: None)
    assert not any(path.endswith("/activate") for _, path in calls)


@pytest.mark.parametrize(
    "url",
    [
        "https://8.8.8.8",
        "http://name:password@127.0.0.1",
        "http://127.0.0.1/path",
        "file:///tmp",
        "http://127.0.0.1?token=x",
    ],
)
def test_target_rejects_public_and_sensitive_urls(url):
    with pytest.raises(ValueError):
        private_url(url)


def test_target_masks_tokens_and_does_not_use_environment_proxy(tmp_path):
    s = TargetSettings(tmp_path)
    s.save("http://127.0.0.1:8080", "test-only-value")
    s.save("http://127.0.0.1:8081", None)
    assert s.public() == {"url": "http://127.0.0.1:8081", "token_saved": True}
    assert "token" not in s.public()
    with s.client() as c:
        assert c._trust_env is False


def test_compiled_pipeline_clock_controls_time_and_faults(compiled_project, monkeypatch):
    p, root = compiled_project
    store = ProjectStore(root / "project.yaml")
    store.save(p)
    now = [10.0]
    monkeypatch.setattr("projection_show.runtime.time.monotonic", lambda: now[0])
    r = Runtime(store, RenderBridge())
    # No hardware needed to test the renderer-facing clock contract.
    r.deployment = {"manifest": {"id": "synthetic"}, "automation": {"surfaces": []}}
    r.state = "RUNNING"
    generation = r.playback_generation
    r.bridge.report(timeline_clock={"state": "READY", "generation": generation, "position": 0.65})
    now[0] += 20
    r.tick(now[0])
    assert r.controller.position == 0.65  # wall-clock delta does not drive compiled output
    r.command("blackout")
    r.bridge.report(timeline_clock={"state": "READY", "generation": generation, "position": 1.5})
    now[0] += 20
    r.tick(now[0])
    assert r.controller.position == 0.65
    r.command("restore")
    r.seek(0.3)
    r.tick(now[0])
    assert r.controller.position == 0.3  # old-generation telemetry cannot undo the seek
    r.bridge.report(
        timeline_clock={
            "state": "ERROR",
            "generation": r.playback_generation,
            "error": "Audio lost",
        }
    )
    r.tick(now[0])
    assert r.state == "PAUSED" and "Audio lost" in " ".join(r.status()["warnings"])


def test_bundle_upload_disk_failure_releases_slot_and_preview_error(compiled_project, monkeypatch):
    p, root = compiled_project
    store = ProjectStore(root / "project.yaml")
    store.save(p)
    monkeypatch.setenv("PROJECTION_SHOW_TOKEN", "test-only")
    r = Runtime(store, RenderBridge())
    s = Services(r, limits=StorageLimits(free_bytes=0, concurrent=1))
    with TestClient(create_app(r, services=s), headers={"Authorization": "Bearer test-only"}) as c:
        with monkeypatch.context() as m:

            def no_space(*args):
                raise ValueError("Insufficient free disk space")

            m.setattr("projection_show.build_api.free_space", no_space)
            response = c.post("/api/deployments/upload", content=b"not-a-zip")
            assert response.status_code == 409 and "space" in response.text
            assert not list(s.deployments.staging.iterdir())
        response = c.post("/api/deployments/upload", content=b"not-a-zip")
        assert response.status_code == 200  # slot released despite pre-file failure
        assert wait_job(c, response.json())["state"] == "error"
        job = wait_job(
            c, c.post("/api/builds", json={"revision": r.revision, "encoder": "libx264"}).json()
        )
        Path(job["result"]["bundle_path"]).unlink()
        response = c.post("/api/builds/latest/preview")
        assert response.status_code == 409
        assert r.deployment is None and s.deployments.state()["active"] is None
