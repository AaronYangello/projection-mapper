# ruff: noqa: UP032
"""Offline projection controls for the VideoCore IV renderer (Python 3.5+)."""

import argparse
import copy
import ipaddress
import json
import math
import os
import signal
import struct
import subprocess
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PATTERNS = {"show": 0, "grid": 1, "white": 2, "border": 3}
PRIVATE = tuple(
    ipaddress.ip_network(network)
    for network in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
    )
)


def atomic_text(path, data):
    pending = path.with_name("." + path.name + ".new")
    fd = os.open(str(pending), os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(str(pending), str(path))
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if pending.exists():
            pending.unlink()


def quad(value):
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(not isinstance(p, list) or len(p) != 2 for p in value)
    ):
        raise ValueError("Four corner coordinates are required")
    if any(
        type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
        for p in value
        for v in p
    ):
        raise ValueError("Corners must be inside the projector canvas")
    for i in range(4):
        a, b, c = (value[(i + j) % 4] for j in range(3))
        if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) <= 1e-6:
            raise ValueError("Corners must form a clockwise quadrilateral without crossing")
    return value


def audio_data(path, duration):
    with wave.open(str(path), "rb") as pcm:
        if (pcm.getnchannels(), pcm.getsampwidth(), pcm.getframerate(), pcm.getcomptype()) != (
            2,
            2,
            48000,
            "NONE",
        ):
            raise ValueError("Master audio must be 48 kHz stereo 16-bit PCM")
        if abs(pcm.getnframes() / 48000.0 - duration) >= 0.050:
            raise ValueError("Master audio must match the timeline duration")
        frames = min(pcm.getnframes(), round(duration * 48000))
    with path.open("rb") as file:
        file.seek(12)
        while True:
            header = file.read(8)
            if len(header) != 8:
                raise ValueError("Missing PCM data in master audio")
            kind, amount = struct.unpack("<4sI", header)
            if kind == b"data":
                if amount < frames * 4 or file.tell() + amount > path.stat().st_size:
                    raise ValueError("Incomplete master audio")
                return file.tell(), frames
            file.seek(amount + amount % 2, 1)


def supported(renderer):
    if not renderer.is_file() or not Path("/opt/vc/lib/libbrcmEGL.so").is_file():
        return False
    try:
        return b"VideoCore IV HW" in subprocess.check_output(
            [str(renderer), "--probe"], stderr=subprocess.STDOUT, timeout=6
        )
    except (OSError, subprocess.SubprocessError):
        return False


class Appliance:
    def __init__(self, show_file, project, audio_device, hidden):
        self.show = json.loads(show_file.read_text())
        self.atlas = str(show_file.with_name("atlas.psp"))
        if not Path(self.atlas).is_file():
            raise ValueError("Pi 3 atlas.psp is missing next to show.json")
        self.project = project
        self.audio_device = audio_device
        self.hidden = hidden
        self.audio = project / self.show["audio_path"] if self.show["audio_path"] else None
        self.audio_info = audio_data(self.audio, self.show["duration"]) if self.audio else (0, 0)
        self.calibration = project / "pi3-mapping.json"
        self.geometry = project / "pi3-render-geometry.txt"
        self.lock = threading.RLock()
        self.saved = {}
        self.draft = {}
        self.revision = 0
        self.position = 0
        self.transport = "stopped"
        self.blackout = False
        self.pattern = "show"
        self.isolate = None
        self.renderer = {"state": "ready", "fps": 0, "error": None, "dropped": 0}
        self.process = None
        self.by_id = {s["id"]: (i, s) for i, s in enumerate(self.show["surfaces"])}
        if len(self.by_id) != len(self.show["surfaces"]) or not 1 <= len(self.by_id) <= 20:
            raise ValueError("Invalid Pi 3 surface list")
        for sid, (_, surface) in self.by_id.items():
            quad(surface["points"])
            self.saved[sid] = surface["points"]
        if self.calibration.exists():
            for sid, value in json.loads(self.calibration.read_text()).items():
                if sid in self.by_id:
                    self.saved[sid] = quad(value)
        self.draft = copy.deepcopy(self.saved)

    def state(self):
        return dict(
            project_name=self.show["project_name"],
            width=self.show["width"],
            height=self.show["height"],
            duration=self.show["duration"],
            position=self.position,
            transport=self.transport,
            blackout=self.blackout,
            pattern=self.pattern,
            isolate=self.isolate,
            renderer=self.renderer.copy(),
            revision=self.revision,
            capabilities={"backend": "videocore-iv", "web_preview": False, "authoring": False},
            surfaces=[
                dict(
                    id=s["id"],
                    name=s["name"],
                    role=s["role"],
                    shape=s["shape"],
                    points=self.draft[s["id"]],
                    dirty=self.draft[s["id"]] != self.saved[s["id"]],
                )
                for s in self.show["surfaces"]
            ],
        )

    def write_geometry(self):
        show = self.show
        offset, frames = self.audio_info
        rows = [
            "{} {} {} {} {} {} {} {}".format(
                len(self.by_id),
                show["width"],
                show["height"],
                show["duration"],
                int(show["loop"]),
                int(bool(self.audio)),
                offset,
                frames,
            )
        ]
        for surface in show["surfaces"]:
            rgb = surface["color"].lstrip("#")
            keys = surface["opacity"]["keyframes"]
            logical = surface["logical"]
            values = [
                int(surface["role"] == "media"),
                int(surface["shape"] == "circle"),
                int(surface["blend_mode"] == "multiply"),
                logical["width"],
                logical["height"],
            ]
            values.extend(int(rgb[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
            values.extend([surface["opacity"]["default"], len(keys)])
            values.extend(surface["uv"])
            values.extend(v for p in self.draft[surface["id"]] for v in p)
            rows.append(" ".join(map(str, values)))
            rows.extend(
                "{} {} {}".format(k["time_seconds"], k["value"], int(k["interpolation"] == "hold"))
                for k in keys
            )
        atomic_text(self.geometry, "\n".join(rows) + "\n")

    def launch(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.write_geometry()
        args = [
            str(ROOT / "renderer"),
            str(self.geometry),
            self.atlas,
            str(self.audio or ""),
            self.audio_device,
        ]
        if self.hidden:
            args.append("--hidden")
        self.renderer = {"state": "starting", "fps": 0, "error": None, "dropped": 0}
        self.process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )
        thread = threading.Thread(target=self.read_renderer, args=(self.process,))
        thread.daemon = True
        thread.start()
        if self.blackout:
            self.process.stdin.write("blackout\n")
        if self.pattern != "show":
            index = self.by_id[self.isolate][0] if self.isolate else -1
            self.process.stdin.write("pattern {} {}\n".format(PATTERNS[self.pattern], index))
        self.process.stdin.flush()

    def read_renderer(self, process):
        for line in process.stdout:
            line = line.strip()
            with self.lock:
                if self.process is not process:
                    return
                if line == "READY":
                    self.renderer["state"] = "live"
                elif line.startswith("STATE "):
                    _, position, self.transport, fps, dropped = line.split()
                    self.position = float(position)
                    self.renderer.update(fps=float(fps), dropped=int(dropped))
                elif line.startswith("GPU "):
                    self.renderer["gpu"] = line[4:]
                elif line.startswith("ERROR ") or not line.startswith("END "):
                    self.renderer.update(
                        state="error", error=line[6:] if line.startswith("ERROR ") else line
                    )
        process.wait()
        with self.lock:
            if self.process is process:
                self.transport = "stopped"
                self.renderer["state"] = "error" if process.returncode else "ready"

    def send(self, value):
        self.launch()
        try:
            self.process.stdin.write(value + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise ValueError(
                "Projector renderer exited. Retry after checking the renderer status."
            ) from exc

    def apply(self, request):
        action = request.get("action")
        sid = request.get("id")
        if action in ("mapping", "save", "revert", "pattern") and sid is not None:
            if not isinstance(sid, str) or sid not in self.by_id:
                raise ValueError("Choose an available surface")
        with self.lock:
            if action in ("mapping", "save", "revert"):
                if sid is None or request.get("revision") != self.revision:
                    raise ValueError("Mapping changed. Refresh and retry.")
                current = (
                    self.saved[sid]
                    if action == "revert"
                    else quad(request.get("points", self.draft[sid]))
                )
                old = self.draft[sid]
                self.draft[sid] = current
                try:
                    self.send(
                        "map {} {}".format(
                            self.by_id[sid][0], " ".join(str(v) for point in current for v in point)
                        )
                    )
                    if action == "save":
                        saved = dict(self.saved, **{sid: current})
                        atomic_text(self.calibration, json.dumps(saved, indent=2) + "\n")
                        self.saved = saved
                        self.revision += 1
                except Exception:
                    self.draft[sid] = old
                    if self.process and self.process.poll() is None:
                        try:
                            self.send(
                                "map {} {}".format(
                                    self.by_id[sid][0],
                                    " ".join(str(v) for point in old for v in point),
                                )
                            )
                        except ValueError:
                            pass
                    raise
            elif action == "pattern":
                pattern = request.get("pattern")
                if not isinstance(pattern, str) or pattern not in PATTERNS:
                    raise ValueError("Unknown projector pattern")
                isolate = sid if request.get("isolate") and pattern != "show" else None
                self.send(
                    "pattern {} {}".format(
                        PATTERNS[pattern], self.by_id[isolate][0] if isolate else -1
                    )
                )
                self.pattern, self.isolate = pattern, isolate
            elif action == "seek":
                seconds = request.get("seconds")
                if (
                    type(seconds) not in (int, float)
                    or not math.isfinite(seconds)
                    or not 0 <= seconds <= self.show["duration"]
                ):
                    raise ValueError("Seek time is outside the installed show")
                self.send("seek {:.6f}".format(seconds))
                self.position = seconds
                if self.transport == "stopped":
                    self.transport = "paused"
            elif action in ("play", "pause", "stop", "blackout", "restore"):
                self.send(action)
                if action in ("blackout", "restore"):
                    self.blackout = action == "blackout"
                if action == "stop":
                    self.transport, self.position = "stopped", 0
                elif action in ("pause", "blackout") and self.transport == "playing":
                    self.transport = "paused"
            else:
                raise ValueError("Unknown control")
            return self.state()

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


class ControlServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    def trusted(self):
        client = ipaddress.ip_address(self.client_address[0])
        host = (self.headers.get("Host") or "").split(":")[0]
        if host != "localhost":
            try:
                ipaddress.IPv4Address(host)
            except ValueError:
                return False
        return any(client in network for network in PRIVATE)

    def answer(self, status, data, content_type="application/json"):
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.trusted():
            self.answer(403, {"error": "Open the Pi's local IP address on a private network"})
        elif self.path == "/":
            self.answer(200, (ROOT / "control.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            with self.server.appliance.lock:
                self.answer(200, self.server.appliance.state())
        else:
            self.answer(404, {"error": "Page unavailable on this system"})

    def do_POST(self):
        origin = self.headers.get("Origin")
        if not self.trusted() or (origin and urlparse(origin).netloc != self.headers.get("Host")):
            self.answer(403, {"error": "Only commands from the Pi control page are allowed"})
            return
        if self.path != "/api/control":
            self.answer(404, {"error": "Feature unavailable on this system"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096 or self.headers.get_content_type() != "application/json":
                raise ValueError("Invalid control request")
            self.connection.settimeout(4)
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("Expected a control object")
            result = self.server.appliance.apply(body)
        except (TypeError, ValueError) as exc:
            self.answer(409, {"error": str(exc)})
        except OSError as exc:
            self.answer(503, {"error": "Projector or calibration storage unavailable: " + str(exc)})
        else:
            self.answer(200, result)

    def log_message(self, *args):
        pass


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", required=True, type=lambda p: Path(p).resolve())
    p.add_argument("--show", type=lambda p: Path(p).resolve())
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--audio-device", default="plughw:CARD=ALSA,DEV=1")
    p.add_argument("--hidden", action="store_true", help="Use offscreen output for testing")
    args = p.parse_args()
    if not supported(ROOT / "renderer"):
        p.exit(2, "Hardware VideoCore IV rendering is unavailable on this system.\n")
    project = args.project.parent if args.project.is_file() else args.project
    show = args.show or project / "builds/pi3/show.json"
    appliance = Appliance(show, project, args.audio_device, args.hidden)
    server = ControlServer((args.host, args.port), Handler)
    server.appliance = appliance

    def interrupt(sig, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    print(
        "Projection Mapper Pi 3 compatibility controls on {}:{}".format(args.host, args.port),
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        appliance.close()


if __name__ == "__main__":
    main()
