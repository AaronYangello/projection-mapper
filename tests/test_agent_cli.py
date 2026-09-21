import json

import httpx
from projection_show.agent_cli import main


def transport(handler):
    return httpx.MockTransport(handler)


def response(request, payload, status=200):
    return httpx.Response(status, json=payload, request=request)


def test_status_is_json_and_uses_environment_token(monkeypatch, capsys):
    monkeypatch.setenv("PROJECTION_SHOW_TOKEN", "secret")

    def handler(request):
        assert request.headers["authorization"] == "Bearer secret"
        return response(request, {"state": "RUNNING", "revision": 3})

    assert main(["status"], transport=transport(handler)) == 0
    assert json.loads(capsys.readouterr().out) == {"revision": 3, "state": "RUNNING"}


def test_snapshot_collects_agent_context(capsys):
    payload = {
        "status": {"state": "READY"},
        "capabilities": {"role": "authoring"},
        "project": {"revision": 4, "project": {"id": "demo"}},
        "media": {"assets": []},
    }

    def handler(request):
        assert request.url.path == "/api/agent/snapshot"
        return response(request, payload)

    assert main(["snapshot"], transport=transport(handler)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["project"]["revision"] == 4
    assert data["capabilities"]["role"] == "authoring"


def test_project_apply_is_dry_run_without_confirmation(tmp_path, capsys):
    source = tmp_path / "project.json"
    source.write_text(json.dumps({"revision": 7, "project": {"id": "demo"}}))

    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/project/validate"
        return response(request, request.read() and json.loads(request.content))

    assert main(["project", "apply", str(source)], transport=transport(handler)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is True
    assert result["applied"] is False


def test_project_apply_preserves_revision_and_conflict(tmp_path, capsys):
    source = tmp_path / "project.json"
    source.write_text(json.dumps({"revision": 7, "project": {"id": "demo"}}))

    def handler(request):
        if request.url.path.endswith("validate"):
            return response(request, {"id": "demo"})
        assert json.loads(request.content)["revision"] == 7
        return response(request, {"detail": "Project changed; reload before saving"}, 409)

    assert main(["project", "apply", str(source), "--confirm"], transport=transport(handler)) == 3
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["http_status"] == 409


def test_raw_writes_require_explicit_confirmation(capsys):
    assert main(["api", "POST", "/api/runtime/stop"], transport=transport(lambda _: None)) == 2
    assert "confirm-write" in json.loads(capsys.readouterr().err)["error"]["message"]


def test_wait_returns_distinct_timeout_code(capsys):
    def handler(request):
        return response(request, {"state": "RUNNING", "renderer": {"status": "OFFLINE"}})

    code = main(
        ["wait", "--renderer", "LIVE", "--wait-timeout", "0"],
        transport=transport(handler),
    )
    assert code == 4
    assert json.loads(capsys.readouterr().out)["matched"] is False


def test_preview_is_atomic_and_refuses_overwrite(tmp_path, capsys):
    output = tmp_path / "preview.jpg"

    def handler(request):
        return httpx.Response(
            200,
            content=b"jpeg-data",
            headers={"content-type": "image/jpeg"},
            request=request,
        )

    assert main(["preview", "--output", str(output)], transport=transport(handler)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["bytes"] == 9
    assert output.read_bytes() == b"jpeg-data"
    assert main(["preview", "--output", str(output)], transport=transport(handler)) == 2
    assert "--force" in json.loads(capsys.readouterr().err)["error"]["message"]
