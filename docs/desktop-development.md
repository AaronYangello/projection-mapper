# Desktop development

From the repository root, `./scripts/install.sh` creates a local virtual environment, installs
Python development/compiler dependencies, installs frontend dependencies from its lockfile, and builds
the web application. It does not install services or alter display settings. Python 3.11+ and
Node 20+ are prerequisites; a C/C++ compiler may be needed if a Python GPU wheel is unavailable.

```sh
.venv/bin/projection-show run --windowed
# Open http://127.0.0.1:8000
```

GLFW uses the main thread; do not move the native renderer into an async worker or launch it
inside `uvicorn --reload`. For frontend hot reload, start the native app and in a second shell:

```sh
cd frontend
npm run dev
```

Open the Vite URL (normally port 5173). Its proxy handles both API and WebSocket traffic.
For API-only development: `.venv/bin/projection-show run --api-only`; the UI reports no output.
There is no browser-only fallback misrepresented as native output.

The native window starts maximized and focused, using a 1280×720 initial window size and
letterboxing the configured canvas. Use `--fullscreen` to use the configured monitor's current
video mode; set that mode in the OS.
Fullscreen hides the cursor. A canvas/display resolution mismatch appears as a warning and
remains letterboxed rather than stretched. `--windowed` overrides the project's fullscreen flag.

## Repeatable checks

```sh
.venv/bin/pytest -q -m 'not gpu'
RUN_GPU_TESTS=1 .venv/bin/pytest -q -m gpu
RUN_GSTREAMER_TESTS=1 .venv/bin/pytest -q -m gst
.venv/bin/ruff check backend tests scripts
.venv/bin/ruff format --check backend tests scripts
cd frontend
npm run build
npm run format:check
```

Hidden-window GPU tests still require a graphical session. In restrictive sandboxes on macOS,
run them with access to the display server. Linux CI can use Xvfb/Mesa, but software-rendered
test success is not evidence of Pi GPU performance. `RUN_GPU_TESTS=1` makes context failures
fatal. The normal suite excludes GPU tests explicitly.

Capture a deterministic full-resolution GPU fixture:

```sh
.venv/bin/python scripts/render_fixture.py --output artifacts/native-grid.png
```

`--hidden --duration 10` on `projection-show run` performs a bounded native/server smoke run.
Runtime event logs go to stderr; framebuffer screenshots and browser QA captures belong in
ignored `artifacts/`. The initial verification record is in `docs/verification.md`.

`requirements-lock.txt` records the exact Python environment verified on this macOS host.
`pyproject.toml` is the cross-platform dependency contract; the installer resolves a compatible
set on its target Python/platform. Pin a Pi-tested lock after commissioning there.


## Browser workflow regressions

`cd frontend && npm run test:ui` builds the UI and starts a disposable API-only project on
127.0.0.1:8012. It uses the installed Google Chrome browser through Playwright. No user project
is changed. Keep this port free for the fixture. This complements the actual native GPU suite;
browser tests alone do not prove decoded or projected pixels. See the UX research/review report.

## Compiled native preview

The compiler extra supplies FFmpeg when no system executable is available. macOS native
compiled playback additionally needs `brew install gstreamer pygobject3`, then
`.venv/bin/python -m pip install '.[appliance]'`. Linux can use distribution GI/GStreamer
packages. The Mac requirements lock includes these installed versions; it is not a Pi lock.
See [build setup and encoder selection](build-deploy.md). GStreamer tests opt in explicitly;
a skipped test is not audio evidence. Use `--audio-sink fake` for silent automated tests.

`--role authoring` enables the compiler/editor; `--role appliance` disables timeline editing
and building while retaining upload/activation/mapping/runtime. `--data-root` and
`--storage-limits` keep host settings separate from portable project YAML. No service,
Tailscale setup, remote worker or device configuration is installed automatically.
