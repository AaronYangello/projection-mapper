# Projection Show Engine

A local projection-mapping engine with native GPU output and a responsive web control room.
**v0.2:** configurable projectors and surfaces, live draggable mapping, native image/video
playback, procedural particles, time-based fades, shuffle bags, and a live queue.

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

The Media page can scan your own files from the project’s `media/` directory.
See [media playback and sample credits](docs/media.md).

## Controls

- **Runtime:** start, pause/resume, skip, fade out, stop, blackout, restore; current cue and
  six planned cues; GPU preview, actual FPS, and per-surface state.
- **Dashboard:** installation inventory and live output.
- **Mapping:** drag or nudge corners during playback, isolate a surface with labeled patterns,
  undo, revert, and save geometry without restarting the cue.
- **Media:** inspect files and thumbnails, add reusable scenes, configure fit/clip timing, and
  play a source immediately on a selected surface.
- **Project:** canvas and timing forms, plus a validated JSON editor for the complete project.
  Stop the show before saving. Saves are atomic, retain a `.yaml.bak`, and reject stale edits.
- **Diagnostics:** grid, white, color, and border test patterns; renderer telemetry and recent
  activity. Choose **Show** to leave test mode. Blackout overrides every test pattern.

Pause freezes the cue, video frame, and ambient clock. Blackout cuts output immediately and freezes the
show; Restore returns to its previous transport state. Stop clears the foreground and leaves
ambient output running. Test patterns replace content while the scheduler keeps its position
in time; pause it first if needed.

## Development and checks

```sh
.venv/bin/pytest -q -m 'not gpu'
RUN_GPU_TESTS=1 .venv/bin/pytest -q -m gpu
.venv/bin/ruff check backend tests
.venv/bin/ruff format --check backend tests
cd frontend
npm run build
npm run format:check
```

GPU tests need display-server access even though their window is hidden. Opted-in GPU tests
fail if a context cannot be created; they do not silently substitute a software approximation.
For frontend development, run `npm run dev` in `frontend/` alongside the native application.
Vite proxies `/api` and WebSockets to port 8000. `--api-only` runs without graphics and explicitly
reports the renderer as offline.

## Scope and next milestones

This is a working desktop prototype, **not the completed appliance MVP**. Live mapping and
native media extend the verified Prototype Zero foundation. Dedicated projector/surface CRUD,
playlist management, media uploads/normalization, hardware control, and reboot commissioning
remain future work. Video currently uses native CPU decoding and GPU composition.

Pi 5 performance, physical HDMI/projector output, fullscreen commissioning, thermal soak,
power-loss recovery, and boot autostart require hardware verification. Desktop GPU results
are not Pi performance claims. See [verification](docs/verification.md).

## Documentation

- [Desktop development](docs/desktop-development.md)
- [Architecture and decisions](docs/architecture.md)
- [Project configuration](docs/configuration.md)
- [Mapping and calibration](docs/mapping.md)
- [Raspberry Pi setup and commissioning](docs/raspberry-pi.md)
- [Native media playback](docs/media.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Full supplied specification](docs/projection_show_engine_spec.md)

API documentation is at [localhost:8000/docs](http://127.0.0.1:8000/docs).
The application defaults to loopback. For a trusted LAN, choose `--host 0.0.0.0`; optionally set
`PROJECTION_SHOW_TOKEN` to require a bearer token for API access. Enter it in the control UI.
No cloud account, external fonts, telemetry, or internet connection is needed after install.
