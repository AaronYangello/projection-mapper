from fastapi.testclient import TestClient
from projection_show.api import create_app
from projection_show.runtime import RenderBridge, Runtime


def test_frontend_reload_serves_current_build(store, tmp_path):
    frontend = tmp_path / "frontend"
    (frontend / "assets").mkdir(parents=True)
    index = frontend / "index.html"
    index.write_text('<script src="/assets/first.js"></script>')
    with TestClient(create_app(Runtime(store, RenderBridge()), frontend)) as client:
        response = client.get("/")
        assert response.headers["cache-control"] == "no-store"
        assert "first.js" in response.text
        index.write_text('<script src="/assets/second.js"></script>')
        response = client.get("/")
        assert response.headers["cache-control"] == "no-store"
        assert "second.js" in response.text


def test_pause_blackout_restore_freeze_exact_position(store, monkeypatch):
    now = [100.0]
    monkeypatch.setattr("projection_show.runtime.time.monotonic", lambda: now[0])
    runtime = Runtime(store, RenderBridge())
    now[0] += 1
    runtime.tick(now[0])
    before = runtime.scheduler.elapsed
    runtime.command("pause")
    now[0] += 30
    runtime.tick(now[0])
    assert runtime.scheduler.elapsed == before
    runtime.command("blackout")
    runtime.command("restore")
    assert runtime.state == "PAUSED"
    runtime.command("resume")
    runtime.command("blackout")
    now[0] += 30
    runtime.tick(now[0])
    assert runtime.scheduler.elapsed == before
    runtime.command("restore")
    now[0] += 1
    runtime.tick(now[0])
    assert runtime.scheduler.elapsed == before + 1


def test_runtime_commands_and_websocket(store):
    runtime = Runtime(store, RenderBridge())
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect("/api/live") as socket:
            assert socket.receive_json()["renderer"]["status"] == "OFFLINE"
        first = client.get("/api/status").json()["current"]["id"]
        assert client.post("/api/runtime/skip").json()["current"]["id"] != first
        assert client.post("/api/runtime/pause").json()["state"] == "PAUSED"
        assert client.post("/api/runtime/blackout").json()["state"] == "BLACKOUT"
        assert client.post("/api/runtime/restore").json()["state"] == "PAUSED"
        assert client.post("/api/runtime/stop").json()["state"] == "READY"
        assert client.post("/api/runtime/start").json()["state"] == "RUNNING"
        assert client.post("/api/runtime/unknown").status_code == 400
        assert client.get("/api/preview.jpg").status_code == 503


def test_save_validates_conflicts_and_survives_restart(store):
    runtime = Runtime(store, RenderBridge())
    with TestClient(create_app(runtime)) as client:
        data = client.get("/api/project").json()
        data["project"]["name"] = "Reusable project"
        assert client.put("/api/project", json=data).status_code == 409
        client.post("/api/runtime/stop")
        assert client.put("/api/project", json=data).status_code == 200
        assert client.put("/api/project", json=data).status_code == 409
        bad = client.get("/api/project").json()
        bad["project"]["surfaces"][0]["projector_id"] = "missing"
        assert client.put("/api/project", json=bad).status_code == 422
    assert Runtime(store, RenderBridge()).project.name == "Reusable project"


def test_failed_save_retains_runtime_configuration(store, monkeypatch):
    runtime = Runtime(store, RenderBridge())
    runtime.command("stop")
    old = runtime.project

    def fail(project):
        raise OSError("disk full")

    monkeypatch.setattr(store, "save", fail)
    with TestClient(create_app(runtime)) as client:
        data = client.get("/api/project").json()
        data["project"]["name"] = "Must not apply"
        assert client.put("/api/project", json=data).status_code == 500
    assert runtime.project is old


def test_patterns_and_origin_protection(store):
    with TestClient(create_app(Runtime(store, RenderBridge()))) as client:
        assert client.put("/api/pattern", json={"pattern": "grid"}).json()["pattern"] == "grid"
        assert client.put("/api/pattern", json={"pattern": "invalid"}).status_code == 422
        assert (
            client.post(
                "/api/runtime/blackout", headers={"Origin": "http://evil.example"}
            ).status_code
            == 403
        )


def test_optional_token(store, monkeypatch):
    monkeypatch.setenv("PROJECTION_SHOW_TOKEN", "test-only-token")
    with TestClient(create_app(Runtime(store, RenderBridge()))) as client:
        assert client.get("/api/project").status_code == 401
        assert (
            client.get(
                "/api/project", headers={"Authorization": "Bearer test-only-token"}
            ).status_code
            == 200
        )
        with client.websocket_connect("/api/live") as socket:
            socket.send_json({"token": "test-only-token"})
            assert socket.receive_json()["state"] == "RUNNING"


def test_renderer_staleness_is_not_reported_live(monkeypatch):
    bridge = RenderBridge()
    monkeypatch.setattr("projection_show.runtime.time.monotonic", lambda: 100)
    bridge.report(status="LIVE")
    monkeypatch.setattr("projection_show.runtime.time.monotonic", lambda: 105)
    assert bridge.telemetry()["status"] == "UNRESPONSIVE"


def test_validate_without_mutation(store):
    runtime = Runtime(store, RenderBridge())
    before = store.path.read_text()
    with TestClient(create_app(runtime)) as client:
        assert client.post("/api/project/validate", json={}).status_code == 422
        data = runtime.project.model_dump(mode="json")
        data["name"] = "Preview only"
        response = client.post("/api/project/validate", json=data)
        assert response.status_code == 200
        assert response.json()["name"] == "Preview only"
    assert runtime.project.name != "Preview only"
    assert store.path.read_text() == before


def test_snapshot_does_not_change_after_publish(store):
    bridge = RenderBridge()
    runtime = Runtime(store, bridge)
    original = bridge.read()
    original_cue = original["scheduler"]["current"]["id"]
    runtime.command("skip")
    assert original["scheduler"]["current"]["id"] == original_cue
    assert bridge.read()["scheduler"]["current"]["id"] != original_cue
