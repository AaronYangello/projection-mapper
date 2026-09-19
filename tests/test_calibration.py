import pytest
from fastapi.testclient import TestClient
from projection_show.api import create_app
from projection_show.calibration import Preview
from projection_show.config.models import Mapping
from projection_show.runtime import RenderBridge, Runtime


def changed(mapping):
    data = mapping.model_dump()
    data["top_left"] = [0.13, 0.14]
    return Mapping.model_validate(data)


def test_live_preview_save_and_revert_preserve_running_cue(store):
    runtime = Runtime(store, RenderBridge())
    before_disk = store.path.read_text()
    scheduler, cue = runtime.scheduler, runtime.scheduler.current
    layout_revision = runtime.render_revision
    original = runtime.project.surfaces[0].mapping
    session = runtime.begin_mapping("plane-1", runtime.revision)
    preview = changed(original)
    runtime.preview_mapping(session["id"], Preview(sequence=1, mapping=preview))
    assert runtime.bridge.read()["calibration"]["mapping"] == preview.model_dump(mode="json")
    assert store.path.read_text() == before_disk
    assert runtime.project.surfaces[0].mapping == original
    runtime.save_mapping(session["id"])
    assert store.load().surfaces[0].mapping == preview
    assert runtime.scheduler is scheduler and runtime.scheduler.current == cue
    assert runtime.render_revision == layout_revision
    runtime.preview_mapping(session["id"], Preview(sequence=2, mapping=original))
    runtime.end_mapping(session["id"])
    assert runtime.project.surfaces[0].mapping == preview
    assert runtime.bridge.read()["calibration"] is None


def test_mapping_session_conflicts_and_stale_sequence(store):
    runtime = Runtime(store, RenderBridge())
    session = runtime.begin_mapping("plane-1", 1)
    with pytest.raises(ValueError, match="already active"):
        runtime.begin_mapping("plane-2", 1)
    with pytest.raises(ValueError, match="another client"):
        runtime.preview_mapping("not-the-owner", Preview(sequence=1, mapping=Mapping()))
    runtime.preview_mapping(session["id"], Preview(sequence=3, mapping=Mapping()))
    with pytest.raises(ValueError, match="Out-of-order"):
        runtime.preview_mapping(session["id"], Preview(sequence=2, mapping=Mapping()))
    runtime.command("stop")
    with pytest.raises(ValueError, match="Finish calibration"):
        runtime.apply(runtime.project)


def test_expiry_restores_saved_mapping(store, monkeypatch):
    now = [100.0]
    monkeypatch.setattr("projection_show.calibration.time.monotonic", lambda: now[0])
    runtime = Runtime(store, RenderBridge())
    session = runtime.begin_mapping("plane-1", 1)
    runtime.preview_mapping(session["id"], Preview(sequence=1, mapping=Mapping()))
    now[0] += 46
    runtime.tick(now[0])
    assert runtime.calibration.session is None
    assert runtime.bridge.read()["calibration"] is None
    assert runtime.project == store.load()


@pytest.mark.parametrize("finish", [False, True])
def test_failed_save_keeps_preview_and_disk(store, monkeypatch, finish):
    runtime = Runtime(store, RenderBridge())
    session = runtime.begin_mapping("plane-1", 1)
    runtime.preview_mapping(session["id"], Preview(sequence=1, mapping=Mapping()))
    before = runtime.project.model_dump()

    def fail(project):
        raise OSError("disk full")

    monkeypatch.setattr(store, "save", fail)
    with pytest.raises(OSError):
        runtime.save_mapping(session["id"], finish=finish)
    assert runtime.project.model_dump() == before
    assert runtime.calibration.session.dirty


def test_save_and_finish_is_one_operation_and_preserves_show(store):
    runtime = Runtime(store, RenderBridge())
    scheduler, cue = runtime.scheduler, runtime.scheduler.current
    with TestClient(create_app(runtime)) as client:
        session = client.post("/api/mapping", json={"surface_id": "plane-1", "revision": 1}).json()
        path = f"/api/mapping/{session['id']}"
        preview = changed(runtime.project.surfaces[0].mapping)
        assert client.put(path, json={"sequence": 1, "mapping": preview.model_dump()}).is_success
        assert client.post(path + "/save?finish=true").json()["finished"] is True
        assert client.get("/api/status").json()["calibration"] is None
        assert runtime.bridge.read()["calibration"] is None
        assert store.load().surfaces[0].mapping == preview
        assert runtime.scheduler is scheduler and runtime.scheduler.current == cue
        assert client.post(path + "/save?finish=true").status_code == 409


def test_api_validation_never_applies_invalid_geometry(store):
    with TestClient(create_app(Runtime(store, RenderBridge()))) as client:
        session = client.post("/api/mapping", json={"surface_id": "plane-1", "revision": 1}).json()
        path = f"/api/mapping/{session['id']}"
        invalid = {"sequence": 1, "mapping": {"top_left": [1, 1]}}
        assert client.put(path, json=invalid).status_code == 422
        assert client.post(path + "/heartbeat").json()["mapping"] == session["mapping"]
        assert client.delete(path).status_code == 200
        assert (
            client.put(path, json={"sequence": 2, "mapping": session["mapping"]}).status_code == 409
        )
