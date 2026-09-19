"""Machine-local target settings and private-network deployment client. Never log secrets."""

import ipaddress
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .config.store import atomic_write


def private_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError(
            "Use a private HTTP(S) origin without a path, query, or embedded credentials"
        )
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as exc:
        raise ValueError("Target hostname could not be resolved") from exc
    tailnet = ipaddress.ip_network("100.64.0.0/10")
    if not addresses or any(
        not (a.is_private or a.is_loopback or (a.version == 4 and a in tailnet)) for a in addresses
    ):
        raise ValueError("Target must resolve exclusively to a private LAN or tailnet address")
    return f"{parsed.scheme}://{parsed.netloc}"


class TargetSettings:
    def __init__(self, data_root):
        self.path = Path(data_root) / "target-settings.json"

    def read(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {"url": "", "token": ""}

    def public(self):
        s = self.read()
        return {"url": s["url"], "token_saved": bool(s["token"])}

    def save(self, url, token=None):
        origin = private_url(url)
        saved = self.read()
        if token is not None and (len(token) > 4096 or any(ord(c) < 32 for c in token)):
            raise ValueError("Invalid target token")
        atomic_write(
            self.path,
            json.dumps({"url": origin, "token": saved["token"] if token is None else token}),
        )
        self.path.chmod(0o600)
        return self.public()

    def client(self, saved=None):
        saved = saved or self.read()
        if not saved["url"]:
            raise ValueError("Configure the target URL first")
        origin = private_url(saved["url"])
        return httpx.Client(
            base_url=origin,
            headers={"Authorization": "Bearer " + saved["token"]} if saved["token"] else {},
            timeout=30,
            follow_redirects=False,
            trust_env=False,
        )


def safe_response(response):
    if not response.is_success:
        # Avoid including a sensitive remote URL, headers or a malicious server response.
        raise ValueError(
            f"Target returned HTTP {response.status_code}; "
            "check authorization, stopped playback and compatibility"
        )
    return response.json()


def test_connection(settings):
    try:
        with settings.client() as c:
            caps = safe_response(c.get("/api/capabilities"))
            state = safe_response(c.get("/api/deployments"))
            return {
                "connected": True,
                "capabilities": caps,
                "active": state["active"],
                "previous": state["previous"],
            }
    except httpx.HTTPError as exc:
        raise ValueError(
            "Cannot connect to target; check private network, URL and TLS certificate"
        ) from exc


def deploy(
    settings, bundle, expected_active, cancel, progress, *, saved=None, expected_bundle=None
):
    """Confirmed deployment; remote activation is a separate final request."""
    try:
        with settings.client(saved) as c:
            current = safe_response(c.get("/api/deployments"))
            if current["active"] != expected_active:
                raise ValueError("Target deployment changed; test connection and confirm again")
            size = bundle.stat().st_size

            def chunks():
                sent = 0
                with bundle.open("rb") as f:
                    while chunk := f.read(256 * 1024):
                        if cancel.is_set():
                            raise ValueError("Deployment cancelled")
                        sent += len(chunk)
                        progress(sent / size * 0.7, "Uploading bundle")
                        yield chunk

            job = safe_response(
                c.post(
                    "/api/deployments/upload",
                    content=chunks(),
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(size),
                    },
                )
            )
            while job["state"] in ("queued", "running"):
                if cancel.wait(0.25):
                    c.delete("/api/builds/" + job["id"])
                    raise ValueError("Deployment cancelled before activation")
                job = safe_response(c.get("/api/builds/" + job["id"]))
                progress(0.7 + job.get("progress", 0) * 0.25, "Pi validating bundle")
            if job["state"] != "complete":
                raise ValueError(
                    "Target rejected bundle: " + str(job.get("error", "Validation failed"))[:500]
                )
            if cancel.is_set():
                raise ValueError("Deployment cancelled before activation")
            ident = job["result"]["manifest"]["id"]
            if expected_bundle and ident != expected_bundle:
                raise ValueError("Target validated an unexpected bundle; activation cancelled")
            progress(0.98, "Activating validated deployment")
            # After dispatch, cancellation cannot undo an activation. Report returned target state.
            result = safe_response(
                c.post(
                    "/api/deployments/" + ident + "/activate",
                    json={"confirmed": True, "expected_active": expected_active},
                )
            )
            if result.get("active") != ident:
                raise ValueError("Target did not confirm the requested active deployment")
            progress(1, "Target confirmed active deployment")
            return {**result, "activation_confirmed": True}
    except httpx.HTTPError as exc:
        raise ValueError(
            "Target connection interrupted. Check its active deployment before retrying"
        ) from exc
