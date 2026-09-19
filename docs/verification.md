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

## v0.3 coordinated authoring/build/deployment · 2026-09-18

Baseline for this phase was clean `2d67d8e`, including the prior UX work. The original demo
YAML/media/calibration were preserved; native review used `artifacts/timeline-review/`.
The authoritative specification and required guides were read before editing.

### Final automated checks

| Command | Result |
| --- | --- |
| `.venv/bin/pytest -q -m 'not gpu'` | 113 passed; 1 optional GStreamer test skipped; 8 GPU tests deselected |
| `RUN_GPU_TESTS=1 .venv/bin/pytest -q -m gpu` | 8 passed on real Mac GL; no skips |
| `RUN_GSTREAMER_TESTS=1 .venv/bin/pytest -q -m gst` | 1 passed with real GStreamer, silent sink, actual volume/mute mixer, pause/long-pause/seek/loop/offset and nonblocking bridge |
| `.venv/bin/ruff check backend tests scripts` | Passed |
| `.venv/bin/ruff format --check backend tests scripts` | Passed |
| `cd frontend && npm run build` | TypeScript and Vite passed |
| `cd frontend && npm run format:check` | Passed |
| `cd frontend && npm run test:ui` | 19 workflows passed against disposable project/Chrome |
| `.venv/bin/projection-show validate --project projects/demo/project.yaml` | Passed; v1 source remains unchanged |
| `git diff --check` | Passed |

This is **122 backend/native tests in total** when both optional native groups are run.
Upstream Starlette/httpx and AnyIO deprecation warnings remain. The ZIP adversarial test
intentionally emits a duplicate-member warning; it verifies rejection, not acceptance.

New coverage includes migration/round-trip/reference/range/overlap validation; deterministic
surface opacity and transport; real four-lane atlas pixels/gaps/H.264/AAC alignment; cache
invalidation/reuse/corruption and cancellation; literal process arguments; streamed uploads,
duplicate/collision/probe/space/concurrency cleanup; ZIP traversal/link/duplicate/ratio/member/
expansion/hash checks; incompatible destinations; failed atomic activation and rollback;
restart fallback; private target protocol/auth/masked credentials; renderer UV/circle/alpha/
four-media-plus-sixteen-lights; authoritative pipeline generations and worker isolation.

Browser tests cover mode activation, grouping/order, clip drag/duplicate/overlap, opacity
editing/presets, draft/conflict protection, real build/export/staleness, upload probe/duplicate/
error/cancel and phone controls. Remote deployment and rollback confirmation/failure UI
responses are **explicitly synthetic**. Real local backend activation/recovery is tested
separately; neither substitutes for a remote Pi deployment.

### Native and interactive review

See [implementation measurements](timeline-implementation.md#mac-compiler-and-playback-measurements)
for exact encoder timing, actual Mac decoder and 65-sample performance figures. The reviewed
native output visibly contains four moving atlas regions and sixteen alpha-modulated
rectangle/circle lights. The final run reports `vtdec_hw` / `avdec_aac`, `fakesink`, and
`GstSystemClock`; no HDMI/speaker output was used or claimed. Browser preview is a capture
of that native frame, not a browser video simulation.

Interactive review used desktop 1440×900, tablet 768×1024, phone 390×844, supported dark theme.
Reviewed timeline lanes/controls, grouping, opacity, numeric fields, build states and runtime.
No page-level horizontal overflow; timeline pan is intentionally contained. Playback hides
shuffle-only controls. Audio timelines explain the compiled-preview prerequisite and disable
premature Start; preview validation has a visible in-progress state. Exact pause → blackout →
restore position was **6.460822583 s** before and after, with PAUSED retained. Earlier manual
Start-before-validation returned the expected guarded error and led to the UI clarification.
The final native run has no pipeline warnings; normal browser use has no console errors.
Server shutdown/reconnect and deliberately rejected actions are not counted as normal errors.
Manual keyboard opacity review also caught stale numeric fields after a point move; the
inspector now updates with the curve (1.00 → 0.95), with a browser regression assertion.
The discarded review draft did not change the saved fixture.

Ignored screenshot evidence:

- `artifacts/timeline-editor-final-desktop.png`
- `artifacts/timeline-editor-final-tablet.png`
- `artifacts/timeline-playback-final-desktop.png`
- `artifacts/timeline-playback-final-phone.png`
- `artifacts/timeline-build-final-phone.png`
- `artifacts/timeline-opacity-inspector-desktop.png`

### Unverified boundaries and next gate

The Pi was unavailable, as confirmed by the user. No Pi SSH/Tailscale commands, remote
activation, HDMI device configuration, fullscreen projector test or boot service occurred.
GLES adapter contracts passed on desktop GL, **not on a Pi EGL context**. Pi hardware decode,
HDMI clock/output/offset, visible/audible loop seam, physical touch/network behavior, thermal
throttling, one-hour soak, reboot and real power interruption remain unverified. Deployment
network-loss/activation tests use local files or mocked HTTP; real private Serve connectivity
remains a device/permission gate. Long-form production media throughput is also unmeasured.

The safest next milestone is the [Pi 4 commissioning checklist](pi-commissioning.md), starting
with GPU/EGL/GLES and single-stream HDMI playback before approving deployment/performance.
Remaining deliberate limits include RGB copies (no zero-copy claim), phone timeline overview,
YAML/JSON for topology creation, no NLE/remote build worker/external lighting protocols,
no automatic pruning of old deployments, and no installed unattended startup service.

## Operator polish and remote upload check — 2026-09-19

This targeted follow-up changes mapping interaction, error visibility, control spacing, HTTP
upload IDs and live-channel keepalive handling. It does not qualify Pi graphics or A/V output.

- Backend: **116 passed, 1 skipped, 8 deselected** with `pytest -q -m 'not gpu'`;
  the skipped optional GStreamer group was not rerun for these UI/API changes.
- Native Mac GPU regressions: **8 passed**. These are desktop renderer checks.
- Browser suite: **23 passed**, including first movement opening exactly one mapping lease,
  delayed begin followed by Save/Revert, durable save and lease release, legacy-backend save
  fallback, draft protection, media error visibility without duplicate banners, and preserving
  clip-range warnings. Upload, timeline and build workflows also run with `crypto.randomUUID`
  unavailable, matching the relevant private HTTP browser restriction.
- TypeScript/Vite production build, Prettier check, Ruff lint/format checks and `git diff --check`
  pass. Existing upstream TestClient/AnyIO warnings and intentional adversarial ZIP warning remain.
- Interactive local review used a disposable API-only fixture at desktop **1440×1000**,
  tablet **768×1024**, and phone **390×844**, in the supported dark theme. Reviewed expanded
  media errors, card warnings, select/disclosure spacing, keyboard mapping, Save/Revert and
  responsive placement. Fixture renderer-offline warnings are intentional. DOM width checks
  distinguish browser screenshot cropping/sticky-element artifacts from actual page overflow.
  These views await user review; automated checks do not constitute user approval.

The existing Pi live connection disconnected after **40.025 seconds** with WebSocket **1011,
keepalive ping timeout**. It had delivered 396 regular status messages first. Inspection found
the no-token browser hello was never consumed, causing Uvicorn SansIO to pause incoming reads.
The repaired local real SansIO server stayed **PAUSED for 65.02 seconds**, delivered **640
messages**, maximum interval **0.104 seconds**, with **zero disconnects**, using deliberately
short **0.2-second ping interval and timeout**. This proves the local receive-path repair;
it is not evidence that the Pi has received the backend update.

An actual authorized Sintel upload to the Pi succeeded through the streamed HTTP API:

- **4,372,373 bytes**, installed as `media/upload-b670602fa00934ca-sintel-trailer.mp4`.
- SHA-256 on source and destination matched:
  `b670602fa00934ca27c4351bb0efe7ea7a07fae57284e44226025eeed7c51254`.
- Explicit scan returned **H.264, 854×480, 24 fps, 52.2083 seconds**, no probe error and a thumbnail.
  The real Pi browser subsequently displayed this healthy source alongside the earlier missing one.
- Project snapshot stayed identical and transport stayed `READY`. No scene was added, playback
  started, mapping changed or deployment activated. The original missing `media/sintel-trailer.mp4`
  reference was intentionally not overwritten by the uploaded source.

The automated Chrome file chooser failed before submitting a file, so that interaction is
**not** counted as a successful Pi browser upload. The HTTP ID fix is verified in local browser
regressions; actual Pi evidence covers upload installation, hashing, probing, scanning and UI
library display. Application deployment/restart and post-update Pi UI verification remain an
explicit approval gate. Physical projected playback, HDMI audio and hardware performance were
not exercised in this follow-up.
