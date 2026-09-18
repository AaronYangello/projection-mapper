# Architecture · desktop engine

The supplied specification is the product roadmap. This implementation completes its first
task (Milestones 1–2 plus Prototype Zero), live mapping, and native image/video playback;
remaining MVP behavior is explicitly identified as future work. The repository started from one README, with no existing application to preserve.

## Boundaries

```text
Versioned project.yaml → Pydantic validation → Runtime owner (API event-loop thread)
                                              ├─ pure Scheduler / shuffle bags / Cue
Browser → REST commands ────────────────────────┤
Browser ← WebSocket status (10 Hz) ─────────────┤
                                              └─ snapshot bridge → Native GPU (main thread)
Browser ← JPEG preview (2 Hz) ← telemetry/preview bridge ←─────────────┘
```

- `config/`: strict versioned models and atomic YAML persistence. Unknown fields fail so a
  typo or unsupported setting cannot silently change a show. A migration entry point rejects
  unknown versions until an explicit migration is implemented.
- `scheduler.py`: independent seeded shuffle bags for eligible surfaces and scenes, a planned
  queue, monotonic elapsed time, fades, hold, gap, and forced fade. It has no I/O or GPU imports.
- `runtime.py`: the sole owner of mutable project/transport state. Commands and ticks execute
  on one event loop. The thread bridge publishes fresh snapshots and separately locks telemetry
  and preview bytes. Published snapshots are read-only by convention.
- `api.py`: validates HTTP inputs and dispatches runtime commands. It never calls OpenGL or
  mutates renderer internals. Configuration changes require stopped transport, a matching
  revision, successful validation, and a durable save before applying. Mapping has a separate
  leased preview/save API that can operate while playing.
- `render/`: GLFW and ModernGL on the main thread, required by macOS's native window model.
  Surface FBOs compose ambient and foreground. The master FBO receives projective surface
  draws. Native output and browser capture use the same master image.
- `calibration.py`: one leased geometry draft, ordered updates, atomic save, and expiry/revert.
- `media/`: local file indexing, metadata/thumbnails, native FFmpeg decoding workers, and fit
  transforms. `render/media.py` owns GPU uploads and playback lifetime on the GL thread.
- `frontend/`: React/TypeScript. The engine hook owns requests, reconnect, and transient
  connection state. UI components present authoritative server state; they do not schedule cues.

## Decisions

**Native OpenGL 3.3 core via ModernGL/GLFW.** This follows the preferred render path, permits
actual GPU pixel tests on this desktop, and provides a Mesa desktop-OpenGL target for Pi OS.
It is not a claim that every Pi/display driver combination has been qualified. The browser
does not implement a second renderer; its preview is a downscaled native-frame capture.
Reference APIs: [ModernGL context](https://moderngl.readthedocs.io/en/latest/reference/context.html)
and [GLFW getting started](https://www.glfw.org/docs/latest/quick.html).

**One process, two ownership domains.** Keep native GL on main and runtime/API on one worker
event loop. The snapshot boundary can become IPC later without making rendering depend on
HTTP handlers. If the native loop exits, the server shuts down; if the server exits, the render
loop stops. Failures exit nonzero for future process supervision.

**Discriminated source definitions.** Scenes form a strict `color | image | video` union.
Scheduling chooses source IDs and timings independently of decoding. The runtime inspects
media once, excludes unavailable sources, and gives full-clip cues their inspected duration.
PyAV/FFmpeg produces timestamped RGB frames on a worker with bounded latest-request/latest-frame
buffers; GL consumes them without waiting for decode. Paused timestamps reuse their texture.
This is native software decoding; hardware decode and zero-copy are not claimed.

**Normalized projector-relative corners.** Logical texture dimensions, projector viewport
pixels, and surface corner positions are independent. A true 3×3 homography is preserved
in the vertex shader's clip-space `w`, ensuring perspective-correct sampling across triangles.

```diff
- output_position = four_corner_affine_interpolation(uv)
+ p = homography * vec3(uv, 1)
+ gl_Position = vec4(canvas_clip_coordinates(p), 0, p.z)
```

This is a representative explanation of the transform, not an earlier implementation.

**Separate geometry and project revisions.** Full project changes require stopped transport
and rebuild the schedule/targets once after Save. A leased mapping preview updates only
homographies and calibration patterns. Persistent geometry saves do not restart the cue or
media decoder. Expiry, page exit, and discard restore the saved mapping.

```diff
- full_project_apply_for_each_corner_move()
+ calibration.preview(sequence, corners)  # update homography, preserve textures/cue
+ calibration.save(project_revision)     # atomic geometry persistence
```

This illustrates the ownership decision, not a historical implementation.

**No fixed installation topology.** The supplied 4K/four-projector/seven-plane demo is YAML.
The engine loops over configured objects. A one-projector, non-square, single-surface project
is covered by tests. GPU allocation is capped by pixel budget and actual texture limits.

## Runtime semantics

Transport is READY, RUNNING, or PAUSED. Blackout overlays transport without destroying it.
The public state becomes BLACKOUT while the previous transport is retained. Scheduler phases
are IDLE, FADING_IN, FOREGROUND, FADING_OUT, GAP. Cue IDs are transient and queue order is
authoritative until project reload/restart. A single eligible item necessarily repeats.

Pause and blackout freeze time; skip consumes the next planned cue. Forced fade begins at
the current opacity, preventing a flash during fade-in. Stop resets the queue and preserves
ambient. Pattern mode affects output only; blackout supersedes patterns. Disabled projectors
exclude their surfaces from both rendering and scheduling. Array order defines surface
composition order for overlaps; there is no edge blending.

## Deliberate next steps

1. Dedicated projector/surface CRUD forms, playlist queries, multi-project switching, richer
   ambient profiles, media uploads and preparation tools.
2. Qualify native decode/upload on Pi before promising sustained playback performance;
   evaluate hardware decode behind the existing frame-source boundary.
3. Supervised appliance startup, thermal diagnostics, sustained Pi soak, hardware adapters.

Production platform migration, hardware writes, and unattended boot have not been implemented
or simulated as completed features.
