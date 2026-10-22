import pytest
from fastapi.testclient import TestClient
from PIL import Image
from projection_show.api import create_app
from projection_show.config.models import Project
from projection_show.config.store import ProjectStore
from projection_show.runtime import RenderBridge, Runtime


def test_batch_membership_is_atomic_revisioned_and_keeps_files(store, movie, monkeypatch):
    root, video = movie
    Image.new("RGB", (32, 32), "red").save(root / "media" / "still.png")
    (root / "media" / "broken.mp4").write_bytes(b"not a movie")
    runtime = Runtime(store, RenderBridge())
    indexed_ids = {entry["id"] for entry in runtime.media}
    ids = [
        e["id"]
        for e in runtime.media
        if e["path"] in {"media/fixture.mp4", "media/still.png", "media/broken.mp4"}
    ]
    with TestClient(create_app(runtime)) as client:
        client.post("/api/runtime/stop")
        revision = runtime.revision
        body = {"revision": revision, "asset_ids": ids, "action": "add"}
        invalid = client.post(
            "/api/media/show-membership", json={**body, "asset_ids": [*ids, "missing-id"]}
        )
        assert invalid.status_code == 409
        assert runtime.revision == revision
        result = client.post("/api/media/show-membership", json=body)
        assert result.status_code == 200 and result.json()["changed"] == 2
        assert runtime.revision == revision + 1
        added = runtime.project.model_dump(mode="json")
        saved = store.path.read_bytes()
        assert client.post("/api/media/show-membership", json=body).status_code == 409
        noop = client.post(
            "/api/media/show-membership", json={**body, "revision": runtime.revision}
        )
        assert noop.json()["changed"] == 0
        assert runtime.revision == revision + 1
        body.update(action="remove", revision=runtime.revision)
        with monkeypatch.context() as patch:

            def fail_save(project):
                raise OSError("disk unavailable")

            patch.setattr(store, "save", fail_save)
            assert client.post("/api/media/show-membership", json=body).status_code == 500
        assert store.path.read_bytes() == saved
        assert runtime.project.model_dump(mode="json") == added
        assert runtime.revision == revision + 1
        result = client.post("/api/media/show-membership", json=body)
        assert result.status_code == 200 and result.json()["changed"] == 2
        assert video.exists() and (root / "media" / "still.png").exists()
        assert {entry["id"] for entry in runtime.media} == indexed_ids
        assert not any(
            s.path in {"media/fixture.mp4", "media/still.png"}
            for s in runtime.project.scenes
            if s.type != "color"
        )
        assert store.load() == runtime.project
        client.post("/api/runtime/start")
        body.update(action="add", revision=runtime.revision)
        assert client.post("/api/media/show-membership", json=body).status_code == 409


def test_remove_cleans_timeline_and_audio_without_deleting_sources(compiled_project):
    project, root = compiled_project
    store = ProjectStore(root / "project.yaml")
    store.save(project)
    runtime = Runtime(store, RenderBridge())
    runtime.state = "READY"
    paths = {"media/0.mp4", "media/1.mp4", "media/tone.wav"}
    ids = [entry["id"] for entry in runtime.media if entry["path"] in paths]
    result = runtime.update_media_membership(ids, "remove", runtime.revision)
    assert result["changed"] == 3
    assert runtime.project.show.timeline.audio is None
    assert runtime.project.show.timeline.tracks[0].clips == []
    assert runtime.project.show.timeline.tracks[1].clips == []
    assert runtime.project.show.timeline.tracks[2].clips
    assert all((root / path).exists() for path in paths)


def test_folder_removal_survives_scan_and_selected_sources_can_be_added_back(store, movie):
    root, _ = movie
    Image.new("RGB", (32, 32), "blue").save(root / "media" / "still.png")
    runtime = Runtime(store, RenderBridge())
    runtime.state = "READY"
    data = runtime.project.model_dump(mode="json")
    data["show"]["shuffle_media_mode"] = "all_folder"
    runtime.apply(Project.model_validate(data))
    entry = next(e for e in runtime.media if e["path"] == "media/fixture.mp4")
    runtime.update_media_membership([entry["id"]], "remove", runtime.revision)
    assert runtime.project.show.shuffle_media_mode == "selected"
    assert runtime.project.show.shuffle_media_paths == ["media/still.png"]
    runtime.install_media_index(runtime.media)
    assert not any(s.path == entry["path"] for s in runtime.project.scenes if s.type != "color")
    runtime.update_media_membership([entry["id"]], "add", runtime.revision)
    assert entry["path"] in runtime.project.show.shuffle_media_paths
    assert any(s.path == entry["path"] for s in runtime.project.scenes if s.type != "color")


def test_add_reenables_existing_sources_and_avoids_id_collisions(store, movie):
    runtime = Runtime(store, RenderBridge())
    runtime.state = "READY"
    entry = next(e for e in runtime.media if e["path"] == "media/fixture.mp4")
    data = runtime.project.model_dump(mode="json")
    data["scenes"][0]["id"] = entry["id"]
    runtime.apply(Project.model_validate(data))
    runtime.update_media_membership([entry["id"]], "add", runtime.revision)
    source = next(
        s for s in runtime.project.scenes if s.type == "video" and s.path == entry["path"]
    )
    assert source.id == f"{entry['id']}-2"
    data = runtime.project.model_dump(mode="json")
    next(s for s in data["scenes"] if s["id"] == source.id)["enabled"] = False
    runtime.apply(Project.model_validate(data))
    assert runtime.update_media_membership([entry["id"]], "add", runtime.revision)["changed"] == 1
    assert next(s for s in runtime.project.scenes if s.id == source.id).enabled


@pytest.mark.parametrize("asset_ids,action", [([], "add"), (["any"], "delete")])
def test_membership_rejects_invalid_payload(store, asset_ids, action):
    runtime = Runtime(store, RenderBridge())
    with TestClient(create_app(runtime)) as client:
        assert (
            client.post(
                "/api/media/show-membership",
                json={"revision": runtime.revision, "asset_ids": asset_ids, "action": action},
            ).status_code
            == 422
        )
