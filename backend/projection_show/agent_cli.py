"""JSON-first HTTP client intended for agents and shell automation."""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

RUNTIME_ACTIONS = (
    "start",
    "pause",
    "resume",
    "stop",
    "restart",
    "skip",
    "fade-out",
    "blackout",
    "restore",
    "reload",
)
PATTERNS = ("show", "grid", "white", "color", "border")


class AgentCliError(Exception):
    def __init__(
        self,
        message: str,
        *,
        kind: str = "usage",
        status: int | None = None,
        details: Any = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.details = details


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise AgentCliError(message)


class AgentClient:
    def __init__(
        self,
        url: str,
        *,
        token: str = "",
        timeout: float = 10,
        transport: httpx.BaseTransport | None = None,
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(
            base_url=url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
            trust_env=False,
        )

    def close(self):
        self.client.close()

    def request(self, method: str, path: str, *, body: Any = None) -> Any:
        if not path.startswith("/") or path.startswith("//"):
            raise AgentCliError("API paths must begin with one slash")
        try:
            response = self.client.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise AgentCliError(str(exc), kind="connection") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        if response.is_error:
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            raise AgentCliError(
                str(detail), kind="http", status=response.status_code, details=payload
            )
        return payload

    def download(self, path: str, output: Path, *, force: bool = False) -> dict:
        if output.exists() and not force:
            raise AgentCliError(f"Output already exists: {output}; pass --force to replace it")
        try:
            response = self.client.get(path)
        except httpx.HTTPError as exc:
            raise AgentCliError(str(exc), kind="connection") from exc
        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            raise AgentCliError(
                str(detail), kind="http", status=response.status_code, details=payload
            )
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=output.parent, prefix=f".{output.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(response.content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, output)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return {
            "path": str(output),
            "bytes": len(response.content),
            "content_type": response.headers.get("content-type"),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        prog="projection-show agent",
        description="JSON-first control client for a running Projection Show Engine.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("PROJECTION_SHOW_URL", "http://127.0.0.1:8000"),
        help="Server base URL (or PROJECTION_SHOW_URL)",
    )
    parser.add_argument(
        "--timeout", type=float, default=10, help="HTTP timeout in seconds (default: 10)"
    )
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    commands = parser.add_subparsers(dest="agent_command", required=True)

    commands.add_parser("describe", help="Read the machine-readable automation contract")
    commands.add_parser("capabilities", help="Read role and build/deployment capabilities")
    commands.add_parser("status", help="Read one runtime status snapshot")
    commands.add_parser("snapshot", help="Read status, capabilities, project, and media together")

    project = commands.add_parser("project", help="Inspect, validate, or apply project JSON")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    project_commands.add_parser("get", help="Get project and optimistic revision")
    project_commands.add_parser("schema", help="Get the Project JSON Schema from OpenAPI")
    validate = project_commands.add_parser("validate", help="Validate without saving")
    validate.add_argument("file", help="JSON file, or - for stdin")
    apply = project_commands.add_parser("apply", help="Validate or atomically apply project JSON")
    apply.add_argument("file", help="JSON file, or - for stdin")
    apply.add_argument("--expected-revision", type=int)
    apply.add_argument(
        "--confirm",
        action="store_true",
        help="Actually save; without this flag the command only validates",
    )

    command = commands.add_parser("command", help="Issue a runtime transport command")
    command.add_argument("action", choices=RUNTIME_ACTIONS)
    pattern = commands.add_parser("pattern", help="Select output/test pattern")
    pattern.add_argument("value", choices=PATTERNS)

    media = commands.add_parser("media", help="Inspect or scan project media")
    media.add_argument("action", choices=("list", "scan"))
    play = commands.add_parser("play", help="Play one saved scene on one surface")
    play.add_argument("--surface", required=True)
    play.add_argument("--scene", required=True)
    preview = commands.add_parser("preview", help="Atomically save the current GPU preview JPEG")
    preview.add_argument("--output", type=Path, required=True)
    preview.add_argument("--force", action="store_true")

    wait = commands.add_parser("wait", help="Poll until explicit runtime conditions match")
    wait.add_argument("--state")
    wait.add_argument("--transport")
    wait.add_argument("--renderer")
    wait.add_argument("--revision", type=int)
    wait.add_argument("--no-warnings", action="store_true")
    wait.add_argument("--wait-timeout", type=float, default=30)
    wait.add_argument("--interval", type=float, default=0.5)

    api = commands.add_parser("api", help="Call another documented /api endpoint")
    api.add_argument("method", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    api.add_argument("path", help="Path beginning with /api/")
    api.add_argument("--data", help="Inline JSON or @path/to/file.json")
    api.add_argument(
        "--confirm-write",
        action="store_true",
        help="Required for POST, PUT, PATCH, and DELETE",
    )
    return parser


def _read_json(value: str) -> Any:
    try:
        text = sys.stdin.read() if value == "-" else Path(value).read_text()
        return json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentCliError(f"Could not read JSON: {exc}") from exc


def _project_document(value: Any) -> tuple[dict, int | None]:
    if not isinstance(value, dict):
        raise AgentCliError("Project input must be a JSON object")
    if "revision" in value and "project" in value:
        return value["project"], value["revision"]
    if (
        isinstance(value.get("project"), dict)
        and {
            "revision",
            "project",
        }
        <= value["project"].keys()
    ):
        wrapper = value["project"]
        return wrapper["project"], wrapper["revision"]
    return value, None


def _raw_body(value: str | None) -> Any:
    if value is None:
        return None
    if value.startswith("@"):
        return _read_json(value[1:])
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise AgentCliError(f"--data must be JSON: {exc}") from exc


def _conditions(args, status: dict) -> tuple[bool, dict]:
    checks = {}
    if args.state is not None:
        checks["state"] = status.get("state") == args.state
    if args.transport is not None:
        checks["transport"] = status.get("transport") == args.transport
    if args.renderer is not None:
        checks["renderer"] = status.get("renderer", {}).get("status") == args.renderer
    if args.revision is not None:
        checks["revision"] = status.get("revision") == args.revision
    if args.no_warnings:
        checks["no_warnings"] = not status.get("warnings")
    if not checks:
        raise AgentCliError("wait requires at least one condition")
    return all(checks.values()), checks


def execute(args, client: AgentClient) -> tuple[Any, int]:
    command = args.agent_command
    if command == "describe":
        return client.request("GET", "/api/agent/manifest"), 0
    if command == "capabilities":
        return client.request("GET", "/api/capabilities"), 0
    if command == "status":
        return client.request("GET", "/api/status"), 0
    if command == "snapshot":
        return client.request("GET", "/api/agent/snapshot"), 0
    if command == "project":
        if args.project_command == "get":
            return client.request("GET", "/api/project"), 0
        if args.project_command == "schema":
            spec = client.request("GET", "/openapi.json")
            schemas = spec["components"]["schemas"]
            return {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$ref": "#/components/schemas/Project",
                "components": {"schemas": schemas},
            }, 0
        document, revision = _project_document(_read_json(args.file))
        validated = client.request("POST", "/api/project/validate", body=document)
        if args.project_command == "validate" or not args.confirm:
            return {"valid": True, "applied": False, "project": validated}, 0
        revision = args.expected_revision if args.expected_revision is not None else revision
        if revision is None:
            raise AgentCliError(
                "Applying a bare project requires --expected-revision; use `project get` "
                "to retain compare-and-swap protection"
            )
        result = client.request(
            "PUT", "/api/project", body={"revision": revision, "project": validated}
        )
        return {"valid": True, "applied": True, **result}, 0
    if command == "command":
        return client.request("POST", f"/api/runtime/{args.action}"), 0
    if command == "pattern":
        return client.request("PUT", "/api/pattern", body={"pattern": args.value}), 0
    if command == "media":
        method = "GET" if args.action == "list" else "POST"
        return client.request(method, "/api/media" + ("" if method == "GET" else "/scan")), 0
    if command == "play":
        return client.request(
            "POST",
            "/api/manual/play",
            body={"surface_id": args.surface, "scene_id": args.scene},
        ), 0
    if command == "preview":
        return client.download("/api/preview.jpg", args.output, force=args.force), 0
    if command == "wait":
        if args.wait_timeout < 0 or args.interval <= 0:
            raise AgentCliError("wait timeout must be non-negative and interval must be positive")
        started = time.monotonic()
        while True:
            status = client.request("GET", "/api/status")
            matched, checks = _conditions(args, status)
            elapsed = time.monotonic() - started
            if matched:
                return {
                    "matched": True,
                    "elapsed_seconds": round(elapsed, 3),
                    "checks": checks,
                    "status": status,
                }, 0
            if elapsed >= args.wait_timeout:
                return {
                    "matched": False,
                    "elapsed_seconds": round(elapsed, 3),
                    "checks": checks,
                    "status": status,
                }, 4
            time.sleep(min(args.interval, max(0, args.wait_timeout - elapsed)))
    if command == "api":
        if not args.path.startswith("/api/"):
            raise AgentCliError("The guarded raw client only accepts /api/ paths")
        if args.method != "GET" and not args.confirm_write:
            raise AgentCliError("Mutating raw API calls require --confirm-write")
        return client.request(args.method, args.path, body=_raw_body(args.data)), 0
    raise AgentCliError(f"Unknown command: {command}")


def main(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except AgentCliError as exc:
        error = {"ok": False, "error": {"kind": exc.kind, "message": str(exc)}}
        print(json.dumps(error, sort_keys=True), file=sys.stderr)
        return 2
    if args.timeout <= 0:
        error = {"ok": False, "error": {"kind": "usage", "message": "timeout must be positive"}}
        print(json.dumps(error), file=sys.stderr)
        return 2
    client = AgentClient(
        args.url,
        token=os.environ.get("PROJECTION_SHOW_TOKEN", ""),
        timeout=args.timeout,
        transport=transport,
    )
    try:
        payload, code = execute(args, client)
        print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=True))
        return code
    except AgentCliError as exc:
        error = {
            "ok": False,
            "error": {"kind": exc.kind, "message": str(exc), "http_status": exc.status},
        }
        if exc.details is not None:
            error["error"]["details"] = exc.details
        print(
            json.dumps(error, indent=None if args.compact else 2, sort_keys=True),
            file=sys.stderr,
        )
        return 3 if exc.kind in ("http", "connection") else 2
    finally:
        client.close()
