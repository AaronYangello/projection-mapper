import pytest
from fastapi.testclient import TestClient
from PIL import Image
from projection_show.api import create_app
from projection_show.config.models import Project
from projection_show.media.catalog import scan
from projection_show.runtime import RenderBridge, Runtime


def test_missing_file_delete_clears_saved_references_and_survives_rescan(store, movie, monkeypatch):
    root, video = movie
    Image.new("RGB", (32, 32), "blue").save(root / "media" / "keep.png")
    runtime = Runtime(store, RenderBridge())
    runtime.state = "READY"
    asset = next(e for e in runtime.media if e["path"] == "media/fixture.mp4")
    runtime.add_media(asset["id"])
    data = runtime.project.model_dump(mode="json")
    data["show"].update(shuffle_media_mode="selected", shuffle_media_paths=[asset["path"]])
    data["show"]["timeline"] = {
        "duration_seconds": 2,
        "tracks": [
            {
                "id": "track",
                "surface_id": "plane-1",
                "clips": [{"id": "clip", "scene_id": asset["id"], "duration_seconds": 1}],
            }
        ],
    }
    runtime.apply(Project.model_validate(data))
    video.unlink()
    runtime = Runtime(store, RenderBridge())
    before_media = runtime.media.copy()
    before_project = store.path.read_bytes()
    with TestClient(create_app(runtime)) as client:
        client.post("/api/runtime/stop")
        body = {"revision": runtime.revision}
        url = f"/api/media/{asset['id']}"
        assert client.request("DELETE", url, json={"revision": 0}).status_code == 409
        with monkeypatch.context() as patch:

            def fail_save(project):
                raise OSError("disk unavailable")

            patch.setattr(store, "save", fail_save)
            assert client.request("DELETE", url, json=body).status_code == 500
        assert runtime.media == before_media
        assert store.path.read_bytes() == before_project
        result = client.request("DELETE", url, json=body)
        assert result.status_code == 200 and result.json()["file_missing"] is True
        assert runtime.project.show.shuffle_media_paths == []
        assert runtime.project.show.timeline.tracks[0].clips == []
        assert not any(s.path == asset["path"] for s in runtime.project.scenes if s.type != "color")
        assert not any(e["id"] == asset["id"] for e in runtime.media)
        assert (root / "media" / "keep.png").is_file()
        assert client.post("/api/media/scan").status_code == 200
        assert not any(e["id"] == asset["id"] for e in runtime.media)
        assert store.load() == runtime.project


@pytest.mark.parametrize("kind", ["symlink", "parent_symlink", "traversal", "directory"])
def test_missing_file_cleanup_preserves_delete_path_guards(store, movie, tmp_path, kind):
    root, _ = movie
    external = tmp_path / "outside"
    external.mkdir()
    if kind == "symlink":
        (root / "media" / "missing.mp4").symlink_to(external / "missing.mp4")
        relative = "media/missing.mp4"
    elif kind == "parent_symlink":
        (root / "media" / "linked").symlink_to(external, target_is_directory=True)
        relative = "media/linked/missing.mp4"
    elif kind == "directory":
        (root / "media" / "directory.mp4").mkdir()
        relative = "media/directory.mp4"
    else:
        relative = "media/../outside/missing.mp4"
    runtime = Runtime(store, RenderBridge())
    runtime.state = "READY"
    runtime.media.append({"id": "unsafe-entry", "path": relative, "error": "missing"})
    previous = store.path.read_bytes()
    with pytest.raises(ValueError):
        runtime.delete_media("unsafe-entry", runtime.revision)
    assert store.path.read_bytes() == previous
    assert external.is_dir()


def test_file_removed_after_indexing_can_be_deleted(store, movie):
    root, video = movie
    runtime = Runtime(store, RenderBridge())
    runtime.state = "READY"
    entry = next(e for e in scan(root) if e["path"] == "media/fixture.mp4")
    video.unlink()
    assert runtime.delete_media(entry["id"], runtime.revision)["file_missing"] is True
