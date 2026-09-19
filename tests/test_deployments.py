from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from projection_show.api import create_app
from projection_show.build.compiler import compile_show
from projection_show.config.store import ProjectStore
from projection_show.deployments import Deployments
from projection_show.runtime import RenderBridge, Runtime
from projection_show.services import Services
from projection_show.storage import StorageLimits


def test_atomic_activation_rollback_restart_and_local_mapping(compiled_project):
    p, root = compiled_project
    store = ProjectStore(root / "project.yaml")
    store.save(p)
    bundle = root / "first.pshow"
    compile_show(p, root, bundle, encoder="libx264")
    d = Deployments(root / "data", StorageLimits(free_bytes=0))
    a = d.stage(bundle, p)
    before = store.path.read_bytes()
    mapping = p.surfaces[0].mapping.model_dump()
    assert d.state()["active"] is None
    d.activate(a, None)
    assert d.state()["active"] == a["manifest"]["id"]
    p.show.timeline.loop = True
    compile_show(p, root, root / "second.pshow", encoder="libx264")
    b = d.stage(root / "second.pshow", p)
    with patch(
        "projection_show.config.store.os.replace", side_effect=OSError("power interruption")
    ):
        with pytest.raises(OSError):
            d.activate(b, a["manifest"]["id"])
    assert d.state()["active"] == a["manifest"]["id"]
    d.activate(b, a["manifest"]["id"])
    assert d.state()["previous"] == a["manifest"]["id"]
    previous = d.prepare_activation(d.state()["previous"], p)
    d.activate(previous, b["manifest"]["id"])
    r = Runtime(store, RenderBridge())
    services = Services(r, data_root=root / "data")
    assert r.deployment["manifest"]["id"] == a["manifest"]["id"]
    assert (
        r.project.surfaces[0].mapping.model_dump() == mapping and store.path.read_bytes() == before
    )
    assert r.mode == "timeline"
    services.jobs.close()
    missing = p.model_copy(deep=True)
    missing.surfaces.pop()
    with pytest.raises(ValueError, match="Missing"):
        d.prepare_activation(a["manifest"]["id"], missing)
    (Path(a["directory"]) / "playback.mp4").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        d.prepare_activation(a["manifest"]["id"], p)


def test_deployment_auth_confirmation_and_mode_revision(compiled_project, monkeypatch):
    p, root = compiled_project
    store = ProjectStore(root / "project.yaml")
    store.save(p)
    r = Runtime(store, RenderBridge())
    services = Services(r, data_root=root / "data")
    with TestClient(create_app(r, services=services)) as c:
        assert c.post("/api/deployments/upload", content=b"bad").status_code == 403
        assert (
            c.post("/api/show/mode", json={"revision": 999, "mode": "shuffle_bag"}).status_code
            == 409
        )
        revision = r.revision
        assert (
            c.post("/api/show/mode", json={"revision": revision, "mode": "shuffle_bag"}).status_code
            == 200
        )
        assert r.project.show.timeline.audio is not None
        c.post("/api/runtime/start")
        assert (
            c.post("/api/show/mode", json={"revision": r.revision, "mode": "timeline"}).status_code
            == 409
        )
    monkeypatch.setenv("PROJECTION_SHOW_TOKEN", "test-token-only")
    r = Runtime(store, RenderBridge())
    r.command("stop")
    services = Services(r, data_root=root / "other-data")
    with TestClient(
        create_app(r, services=services), headers={"Authorization": "Bearer test-token-only"}
    ) as c:
        assert (
            c.post(
                "/api/deployments/rollback", json={"confirmed": False, "expected_active": None}
            ).status_code
            == 422
        )
        assert c.post("/api/deployments/upload", content=b"not-a-zip").status_code == 200
        assert (
            c.post(
                "/api/target/deploy", json={"confirmed": True, "expected_active": None}
            ).status_code
            == 409
        )
        target = c.put(
            "/api/target", json={"url": "http://127.0.0.1:8000", "token": "local-secret-only"}
        ).json()
        assert target == {"url": "http://127.0.0.1:8000", "token_saved": True}
        assert "local-secret-only" not in c.get("/api/target").text
        assert (services.data_root / "target-settings.json").stat().st_mode & 0o777 == 0o600
