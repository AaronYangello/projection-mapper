# Verification record

Verified on 2026-09-17 (America/New_York) / 2026-09-18 UTC in the working repository.
Host: macOS arm64, Apple M3 Ultra; Python 3.14.7; Node.js 26.7.0.

## Completed scope

Milestones 1–2 and Prototype Zero from specification section 65 are implemented:

- Python backend, React/TypeScript frontend, versioned/validated project model.
- Configurable output canvas, arbitrary projector viewports, four-corner surfaces, logical sizes.
- Native GPU window, master framebuffer, per-surface composition, projective warp, test patterns.
- Generic particle ambient, configured solid-color scene sources, time-based fades/hold/gaps.
- Independent shuffle bags, stable upcoming cue queue, live status and actual native preview.
- Start/pause/resume/stop/skip/fade-out, immediate blackout with transport-preserving restore.
- Explicit project editing, save validation, atomic persistence, backup, conflict detection.
- Windowed desktop operation and documented fullscreen/display-mismatch handling.

## Automated results

`RUN_GPU_TESTS=1 .venv/bin/pytest -q`: **40 passed** (37 non-GPU, 3 native GPU tests).

The suite covers configuration/reference/geometry validation, arbitrary non-square topology,
4000 shuffle selections, no immediate repeats, deterministic timing across tick rates,
forced fades, zero transitions, disabled outputs, empty eligibility, pause/blackout semantics,
API and WebSocket state, token/origin checks, optimistic saves, save-failure preservation,
reload across runtime instances, non-mutating validation, and snapshot isolation.

GPU tests use the real OpenGL context. Pixel checks cover black outside a warped quad, its
interior foreground color, half-opacity alpha, blackout overriding white test output,
time-varying particles, grid output, reconfiguration cleanup, and perspective-correct
crosshair sampling on a strongly skewed surface. No GPU test was skipped in this run.

Also passed:

- Ruff lint and format checks across backend, tests, and scripts.
- TypeScript checking and Vite production build.
- Prettier checks for the frontend.
- Project CLI validation and `git diff --check`.

Two upstream TestClient deprecation warnings remain (Starlette/httpx and AnyIO portal alias).
They do not cause failures. Exact installed Python versions are recorded in
`requirements-lock.txt`; frontend dependencies are in `frontend/package-lock.json`.

## Live application checks

The application was launched with its native window and web server. Reported GPU:
**Apple M3 Ultra**. Configured framebuffer: **3840×2160**. Actual development window:
**1280×720**, preserving aspect ratio. This is a 4K internal render check, not a physical 4K
HDMI or Raspberry Pi result.

After correcting sleep-deadline accumulation, a 12-second sample (one measurement per second)
reported **60.0 FPS** throughout and **zero additional late frames**. This is a short desktop
sample; it is not sustained appliance/performance qualification.

Browser checks at desktop width and 390×844:

- Real GPU preview appeared; live queue and surface states updated.
- Pause froze position; blackout then restore retained PAUSED and the exact cue position.
- Resume and skip consumed the planned cue correctly.
- Saved a project rename from the UI, verified the API result, and restored the original name.
- Submitted invalid advanced JSON; the server returned 422, the editable draft stayed open,
  and the application remained usable. Corrected JSON closed successfully.
- Grid/Show buttons changed native pattern state.
- Runtime and project editor had no horizontal overflow on the mobile viewport.
- No unexpected browser errors during normal operation. The intentional invalid-config
  test produced its expected 422 network console entry; stopping the server produced expected
  reconnect failures while it was offline.

Local, git-ignored evidence:

- `artifacts/runtime-desktop.png`
- `artifacts/runtime-mobile.png`
- `artifacts/native-grid.png` (full 3840×2160 deterministic GPU capture)

## Scope at the Prototype Zero baseline

Physical Pi 5 graphics and decode paths, real projectors/controller routing, physical fullscreen
mode, thermal stability, reboot/autostart, power interruption, and extended unattended soak
remain unverified. No hardware commands were sent and no system service was installed.

Live mapping and media were subsequently implemented; see the v0.2 evidence below. Remaining
appliance and physical-hardware boundaries still apply.


## v0.2 · Live mapping and native media

Verified on the same development host, 2026-09-17 / 2026-09-18 UTC.

`RUN_GPU_TESTS=1 .venv/bin/pytest -q`: **62 passed**, including **6 real native GPU tests**.
New coverage includes calibration leases, stale sequences, expiry/revert, geometry save without
scheduler reset, disk failure, invalid geometry, indexed media and thumbnails, confined paths,
corrupt sources, timestamp seeking, bounded decoding, image orientation, fit/focal transforms,
clip ranges, full-clip fade timing, manual queue return, empty-decode failure, and decoder-error
exclusion/recovery.
GPU checks verify homography changes preserve texture identity, native calibration labels,
actual decoded RGB video pixels, contain bars, pause, hold/loop, blackout, oriented images,
and source rejection at GPU texture dimension limits.

Live application checks:

- Dragged a corner during RUNNING and reverted it. Numeric change reached renderer geometry
  acknowledgement in 90 ms in one local measurement, preserving the current cue.
- Saved changed geometry during playback, verified the project file, then saved its original
  geometry again. No demo calibration changes were left behind.
- Scanned and added the actual Sintel H.264 trailer through the UI, then played it on Plane 1.
  Native output showed the warped decoded image, with READY decoder state and 60 FPS renderer
  telemetry. The source is 854×480, 24 fps, approximately 52.208 seconds. This is software decode
  plus GPU rendering on the Mac; it is not hardware-decoder or Pi qualification.
- Paused at about 21.7 seconds; presentation timestamp remained 21.666 seconds across repeated
  samples. Blackout/restore retained PAUSED and the same frame; resume continued playback.

- At 390×844, browser-emulated touch dragging moved a corner from X=0.07 to X=0.1407.
  Revert restored it; keyboard nudge changed X to 0.0705 and Undo restored X=0.07. Mapping
  and Media had no horizontal overflow. Physical phone/LAN touch remains unverified.
- Saved fit/focal settings through Media and verified their API values; restored demo defaults.
  Thumbnails loaded at 400 px width, and rescan refreshed them. Native labels showed the
  selected surface name/projector/resolution/corner numbers with all other surfaces black.
- The actual full-length manual trailer returned to an automatic color cue in the native log;
  subsequent automatic color/video cues continued for more than ten minutes without failure.
- Ruff lint/format, frontend production build/format, project validation, and diff whitespace
  checks passed. Two pre-existing upstream TestClient deprecation warnings remain.

Additional local evidence: `artifacts/mapping-desktop.png`, `artifacts/mapping-mobile.png`,
`artifacts/media-mobile.png`, `artifacts/native-calibration-labels.jpg`, and
`artifacts/native-video-runtime.png`.

The optional sample has pinned download verification and source/license attribution. Raw media
and generated thumbnails/evidence are ignored by Git. Missing sample media leaves the demo
runnable with color scenes. Remaining work includes the physical Pi pipeline, extended soak,
appliance startup, playlists, dedicated topology forms, and media preparation/upload tooling.

## Operator UX review · 2026-09-18

The [research and review](ux-research-and-review.md) documents the navigation, mapping,
media, draft protection, and project-form changes with primary research sources.
`RUN_GPU_TESTS=1 .venv/bin/pytest -q` passes all **63 tests**, including six real GPU tests.
`cd frontend && npm run test:ui` passes **11 browser workflow tests** and builds production assets.
Native review used a separate copied project; the user's project configuration was preserved.
All five pages were checked at desktop, tablet, and phone widths in the supported dark theme.
Ruff, frontend formatting, and diff checks pass. The main app remains running with its prior
stopped transport and blackout state. Existing topology now has form controls; adding/removing
entries still uses the complete JSON editor. Physical Pi/LAN validation remains outstanding.
