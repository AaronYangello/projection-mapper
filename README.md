# Projection Show Engine

A local projection-mapping engine with native GPU output and a responsive web control room.
**v0.3:** live mapping, native media and shuffle playback, coordinated timelines, surface
opacity, lighting, Mac atlas builds, streamed uploads, and atomic show bundles. The desktop
workflow is tested; the Pi 4 graphics/HDMI/soak qualification remains an explicit hardware gate.

## Run on a desktop

Requires Python 3.11+, Node.js 20+, and a desktop OpenGL 3.3 driver. macOS and Linux are the
development targets. Run these commands from this repository:

```sh
./scripts/install.sh
.venv/bin/projection-show validate
.venv/bin/projection-show run --windowed
```

Open **[localhost:8000](http://127.0.0.1:8000)**. A separate native window shows the output.
The browser preview is a downscaled capture of that GPU output, refreshed twice per second.
The configured 4K framebuffer is retained even when the desktop window is smaller.
Close the output window, press Escape, or use Ctrl+C to exit the application.

The generic [demo project](projects/demo/project.yaml) supplies seven planes, four viewports,
five color scenes, an optional video scene, and a particle profile. Those counts, names, positions, source colors, and
timings are configuration, not engine constants. Use `--project path/to/project.yaml` for
another installation. Copy the demo directory to create another project in this milestone.

To try native video, download the small licensed sample once and restart the engine:

```sh
.venv/bin/python scripts/download_sample.py
```

The Media page can upload and scan your own files from the project’s `media/` directory.
See [media playback and sample credits](docs/media.md).

## Controls

- **Playback:** start, pause/resume, skip, fade out, stop, blackout, restore; current cue and
  six planned cues; GPU preview, actual FPS, and per-surface state.
- **Show:** separate Shuffle/Timeline definitions, explicit stopped mode activation, grouped
  surface lanes, clips, master audio, full-surface opacity, Build/Export/Build & Deploy.
- **Mapping:** drag, zoom, or tap to nudge corners during playback, isolate a surface with labeled patterns,
  undo/redo, revert, and save geometry without restarting the cue.
- **Media:** search files and thumbnails, add reusable scenes, edit names/tags and fit/clip timing,
  and play a saved source on a selected surface. Selection alone never changes output.
- **Project:** canvas, timing, projector, and surface forms, plus a validated JSON editor for the complete project.
  Stop the show before saving. Saves are atomic, retain a `.yaml.bak`, and reject stale edits.
- **Diagnostics:** grid, white, color, and border test patterns; renderer telemetry and recent
  activity. Choose **Show** to leave test mode. Blackout overrides every test pattern.

Pause freezes the cue, video frame, and ambient clock. Blackout cuts output immediately and freezes the
show; Restore returns to its previous transport state. Stop clears shuffle foreground and leaves ambient output running; timeline stop darkens
its surfaces and returns to zero. Test patterns replace content while the scheduler keeps its position
in time; pause it first if needed.

## Development and checks

```sh
.venv/bin/pytest -q -m 'not gpu'
RUN_GPU_TESTS=1 .venv/bin/pytest -q -m gpu
RUN_GSTREAMER_TESTS=1 .venv/bin/pytest -q -m gst # optional installed native pipeline
.venv/bin/ruff check backend tests
.venv/bin/ruff format --check backend tests
cd frontend
npm run build
npm run format:check
npm run test:ui # disposable local project; requires Google Chrome
```

GPU tests need display-server access even though their window is hidden. Opted-in GPU tests
fail if a context cannot be created; they do not silently substitute a software approximation.
For frontend development, run `npm run dev` in `frontend/` alongside the native application.
Vite proxies `/api` and WebSockets to port 8000. `--api-only` runs without graphics and explicitly
reports the renderer as offline.

## Scope and next milestones

The authoring/build/storage workflow is implemented and tested on the Mac. The Pi 4 runtime
has an isolated GLES backend and GStreamer atlas/audio pipeline, but **physical Pi support
is unverified**. HDMI audio, fullscreen output, loop quality, thermals, one-hour soak,
power-loss recovery and boot supervision require the target device. No service or remote
deployment has been installed. See [evidence and limits](docs/verification.md).

Prepare finished per-surface stems in your video editor, then align tracks/audio/opacity
in [Show](docs/timeline.md). Build on the Mac with the shared UI/CLI compiler:

```sh
.venv/bin/projection-show build --project projects/my-show/project.yaml \
  --profile pi4-1080p --output projects/my-show/builds/my-show.pshow
```

Native compiled preview needs GStreamer; see [setup and Build & Deploy](docs/build-deploy.md).
A reproducible synthetic four-video/sixteen-light/audio installation is available without
an online download:

```sh
.venv/bin/python scripts/create_timeline_fixture.py --output artifacts/timeline-review
.venv/bin/projection-show run --project artifacts/timeline-review/project.yaml --windowed
```

The generator refuses to overwrite an existing fixture. Build it in Show, choose Preview
built show, then Start. Use `--audio-sink fake` only for explicitly silent testing.
General NLE tools, multi-project switching, external lighting protocols and a remote Mac
build worker remain outside this phase. Adding/removing topology still uses YAML/JSON.

## Documentation

- [Desktop development](docs/desktop-development.md)
- [UX research and review](docs/ux-research-and-review.md)
- [Architecture and decisions](docs/architecture.md)
- [Project configuration](docs/configuration.md)
- [Timeline, opacity, audio and source preparation](docs/timeline.md)
- [Mac build/export/deployment and bundle format](docs/build-deploy.md)
- [API operations](docs/api.md)
- [Pi 4 physical commissioning checklist](docs/pi-commissioning.md)
- [Implementation decisions and risk register](docs/timeline-implementation.md)
- [Mapping and calibration](docs/mapping.md)
- [Raspberry Pi setup and commissioning](docs/raspberry-pi.md)
- [Native media playback](docs/media.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Full supplied specification](docs/projection_show_engine_spec.md)

API documentation is at [localhost:8000/docs](http://127.0.0.1:8000/docs).
The application defaults to loopback. Prefer private Tailscale Serve HTTPS for remote control.
`--host 0.0.0.0` deliberately exposes LAN/tailnet interfaces. Set `PROJECTION_SHOW_TOKEN`
for bearer access; it is required for deployment mutations. Enter it in the control UI.
No cloud account, external fonts, telemetry, or internet connection is needed after install.
