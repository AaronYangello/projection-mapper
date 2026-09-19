import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from projection_show.api import create_app
from projection_show.runtime import RenderBridge, Runtime
from projection_show.storage import REQUIRED_FILES, StorageLimits, Uploads, extract_bundle


def picture(color="red"):
    b = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(b, format="PNG")
    return b.getvalue()


def install(uploads, name, data):
    job = uploads.begin(name, len(data))
    handle = uploads.start(job["id"])
    uploads.append(job["id"], handle, data)
    handle.close()
    return uploads.install(job["id"], uploads.validate(job["id"]))


def test_upload_probe_hash_duplicate_collision_and_safe_name(tmp_path):
    u = Uploads(tmp_path, StorageLimits(free_bytes=0))
    r = install(u, "My image.png", picture())
    assert (
        r["state"] == "complete"
        and r["path"].startswith("media/upload-")
        and r["path"].endswith("-My-image.png")
    )
    assert install(u, "Other.png", picture())["state"] == "duplicate"
    with pytest.raises(ValueError, match="different file"):
        install(u, "My image.png", picture("blue"))
    for name in ["../bad.png", "/bad.png", "bad\\x.png", "bad.exe"]:
        with pytest.raises(ValueError):
            u.begin(name, 20)


def test_upload_limits_interrupt_cleanup_corrupt(tmp_path):
    u = Uploads(tmp_path, StorageLimits(media_bytes=100, free_bytes=0, concurrent=1))
    with pytest.raises(ValueError, match="size"):
        u.begin("x.png", 101)
    j = u.begin("x.png", 10)
    with pytest.raises(ValueError, match="busy"):
        u.begin("y.png", 10)
    h = u.start(j["id"])
    u.append(j["id"], h, b"abc")
    h.close()
    with pytest.raises(ValueError, match="Incomplete"):
        u.validate(j["id"])
    u.cancel(j["id"])
    assert not u.path(j["id"]).exists()
    j = u.begin("bad.png", 3)
    h = u.start(j["id"])
    u.append(j["id"], h, b"bad")
    h.close()
    with pytest.raises(ValueError, match="Cannot install"):
        u.validate(j["id"])
    Uploads(tmp_path, StorageLimits(free_bytes=0))
    assert not u.path(j["id"]).exists()


def test_symlink_and_free_space(tmp_path, monkeypatch):
    other = tmp_path / "elsewhere"
    other.mkdir()
    (tmp_path / "media").symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        Uploads(tmp_path)
    (tmp_path / "media").unlink()
    monkeypatch.setattr(
        "projection_show.storage.shutil.disk_usage", lambda p: type("Space", (), {"free": 0})()
    )
    with pytest.raises(ValueError, match="space"):
        Uploads(tmp_path).begin("a.png", 50)


def archive(tmp_path, extra=None, corrupt=False):
    files = {name: b"{}" for name in REQUIRED_FILES - {"checksums.json"}}
    files["checksums.json"] = json.dumps(
        {
            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in files.items()
        }
    ).encode()
    if corrupt:
        files["atlas.json"] = b"[]"
    path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
        if extra is not None:
            z.writestr(extra, b"x")
    return path


@pytest.mark.parametrize("extra", ["../x", "/x", "unexpected", "atlas.json"])
def test_unsafe_archives(tmp_path, extra):
    path = archive(tmp_path, extra)
    with pytest.raises(ValueError):
        extract_bundle(path, tmp_path / "out", StorageLimits(free_bytes=0))
    assert not list((tmp_path / "out").glob("*"))


def test_checksum_links_bomb_and_expansion(tmp_path):
    path = archive(tmp_path, corrupt=True)
    with pytest.raises(ValueError, match="checksum"):
        extract_bundle(path, tmp_path / "out", StorageLimits(free_bytes=0))
    path = archive(tmp_path)
    with pytest.raises(ValueError, match="expansion"):
        extract_bundle(path, tmp_path / "out", StorageLimits(expanded_bytes=1, free_bytes=0))
    with zipfile.ZipFile(path, "a") as z:
        info = zipfile.ZipInfo("authoring-project.yaml")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        z.writestr(info, "elsewhere")
    with pytest.raises(ValueError, match="link"):
        extract_bundle(path, tmp_path / "out", StorageLimits(free_bytes=0))


def test_upload_api_stopped_explicit_scan_and_cancel(store):
    runtime = Runtime(store, RenderBridge())
    runtime.command("stop")
    with TestClient(create_app(runtime)) as c:
        data = picture()
        job = c.post("/api/media/uploads", json={"name": "test.png", "size": len(data)}).json()
        response = c.post("/api/media/upload", params={"upload_id": job["id"]}, content=data)
        assert response.status_code == 200 and response.json()["state"] == "complete"
        assert not any(e["type"] == "image" for e in c.get("/api/media").json()["assets"])
        assert any(e["type"] == "image" for e in c.post("/api/media/scan").json()["assets"])
        assert not any(s.type == "image" for s in runtime.project.scenes)
        job = c.post("/api/media/uploads", json={"name": "cancel.png", "size": 10}).json()
        assert c.delete("/api/media/uploads/" + job["id"]).json()["state"] == "cancelled"
        assert (
            c.post("/api/media/upload", params={"upload_id": job["id"]}, content=b"x").status_code
            == 409
        )
        c.post("/api/runtime/start")
        assert c.post("/api/media/uploads", json={"name": "x.png", "size": 10}).status_code == 409


def test_zip_ratio_count_and_backslash_limits(tmp_path):
    path = archive(tmp_path)
    with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("authoring-project.yaml", b"0" * 100000)
    with pytest.raises(ValueError, match="expansion"):
        extract_bundle(path, tmp_path / "out", StorageLimits(free_bytes=0, compression_ratio=10))
    path = archive(tmp_path)
    with pytest.raises(ValueError, match="member"):
        extract_bundle(path, tmp_path / "out", StorageLimits(free_bytes=0, zip_members=2))
    path = archive(tmp_path, extra="folder\\name")
    with pytest.raises(ValueError):
        extract_bundle(path, tmp_path / "out", StorageLimits(free_bytes=0))
