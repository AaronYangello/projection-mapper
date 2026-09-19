# Troubleshooting

**The server starts but there is no web UI.** Run `npm ci && npm run build` in `frontend/`, then
launch from the repository root. If launched elsewhere, provide `--project` and `--frontend`
with explicit paths. Interactive API docs remain at `/docs`.

**OpenGL context fails or the process aborts before opening a window.** Check desktop/display
server access. On macOS, a restricted sandbox can block WindowServer access; native graphics
needs a desktop process with that permission. On Linux, ensure the graphical session and
GLFW/Mesa runtime are available. `--api-only` verifies the server but reports renderer OFFLINE.

**Output appears smaller than the canvas.** Windowed mode intentionally scales and letterboxes
the full logical framebuffer. The UI reports both the configured canvas and actual output
window dimensions. Fullscreen output mismatch is a warning, not automatic OS mode switching.

**The image is black.** Check blackout first, then enabled projectors/surfaces, ambient opacity,
and scene eligibility. Stop preserves ambient, which may be subtle. Use Diagnostics → White
to isolate mapping. Choose Show to return to normal content.

**Cues move in the UI but a grid stays projected.** Test pattern mode affects output separately
from scheduling. Select Show. Pause before calibration to hold the cue position.

**Project or media save is unavailable.** Stop the show and finish any mapping session. Blackout alone does not stop its transport. Unsaved
edits stay in the project editor when switching between pages. Full project changes are
intentionally guarded while running or paused.

**Save fails.** Read the inline validation path. Common errors include duplicate IDs, missing
references, invalid corner order, out-of-canvas viewports, and reversed timing ranges. Disk
errors retain the runtime project. Conflicting browser revisions require refresh before saving.
The last validated saved file is preserved as `project.yaml.bak`; restore it manually with the
application stopped if needed.

**No upcoming cues.** At least one enabled foreground surface on an enabled projector and one
enabled scene must match their tag selectors. Ambient-only installations remain valid.

**Connection lost.** Commands are disabled when live updates disconnect. The UI reconnects
automatically and fetches the active project again. If authentication is configured, reload
and enter the matching token. Session storage keeps it only within this browser tab session.

**Low FPS.** Read actual FPS in Playback/Diagnostics. Preview is intentionally only 2 fps and
can cost some GPU readback time. Test a smaller canvas or fewer/lower-resolution surfaces;
observe actual behavior on the target GPU. Late frames count native loop work exceeding 1.5×
the target budget; they are not a decoder drop count. Shuffle/raw source preview is CPU-decoded. Compiled playback reports its actual decoder;
inspect pipeline state/PTS/stale/dropped frames and the output-mode/profile workload.

**Tests warn about Starlette/httpx deprecations.** The current dependency set passes integration
tests but emits upstream TestClient deprecation warnings. These are recorded in verification;
do not mistake warnings for passing native or hardware tests.


**Mapping is in use or expired.** Finish mapping in the other browser, or let its 45-second
lease expire after it disconnects. An expired preview restores saved geometry. Finish the
stale session, refresh, and start mapping again. Save mapping is allowed during playback;
full project/media edits are not.

**Sample video is missing.** Run `.venv/bin/python scripts/download_sample.py`, then stop and
Scan folder or restart. The download is optional; colors remain playable without it. Put your
own supported files inside the project's `media/` directory, scan, then Add to show.

**Media is indexed but not selected.** Check the error shown on its card, scene enabled state,
and show tag filters. Play on surface needs an enabled foreground surface. After fixing a file that
failed decoding, stop and rescan to make it eligible again. Shuffle ignores audio. Master audio belongs to a compiled Timeline bundle; source selection
alone does not insert a timeline clip or switch mode.

## Timeline, build and deployment

**Start asks for a compiled preview.** Save and activate Timeline, Build, then wait for
Preview built show to finish validation before Start. Stop and Unload preview before editing.
Audio-bearing timelines cannot use the silent raw-source preview. Viewing the Timeline tab
does not activate it. Source bounds are checked against indexed media on save and actual
bytes on build; stop and rescan after externally replacing a source.

**No timeline light or a black interval.** Check the surface track, default/keyframe opacity,
clip interval and light role. Missing media intervals draw no content; opacity is independent.
Set visible/dark replaces the curve. A key's interpolation controls the interval leaving it.
At a non-loop end, media ends while lights retain their end values. Stop darkens all tracks.

**Build rejects the demo.** The original generic demo is 4K/multi-projector; `pi4-1080p`
requires 1920×1080, one full-canvas projector, four concurrent media clips and sixteen lights.
Create a compatible authoring project; do not distort the reusable engine to fit the profile.
The synthetic fixture generator supplies a compatible test installation.

**Encoder unavailable or slow.** Read the actual backend/warning in the build result. Auto
tries VideoToolbox on Mac and reports a software fallback. Explicit hardware mode fails if
unavailable. A sandbox can prevent hardware access. Install the compiler extra or FFmpeg;
never infer acceleration from an encoder name in the installed list. Check build inputs
separates video work, audio remux, manifest-only change and no rebuild for mapping.

**Upload/build disk error.** Observe configured per-file/expanded-size/reserved-free-space
limits. The compiler reserves a conservative working budget. Cancel preserves old artifacts;
partial namespaces are cleaned on restart. A different file with the same display name is
rejected; rename it explicitly. Exact hash duplicates are reported. Do not delete active
runtime data to free space; export/back up and remove only identified unused generated files.

**Bundle incompatible/corrupt.** Read missing/extra/incompatible surface IDs. Destination
IDs, role, enabled state and logical dimensions must match; physical corners need not.
Checksums, stream properties and atlas metadata are revalidated before activation. Rebuild
from the source project for malformed artifacts; do not hand-edit checksums to bypass checks.

**Deployment is disabled.** Configure server bearer authentication and use a private target
origin. The saved secret is masked; Edit is required to replace it. The authoring role enables
builds; appliance role does not. A connection test never deploys. Stop the destination, confirm
the exact target/new/prior IDs, then wait for the returned active ID. If the final response is
lost, test/read target status before retrying; activation may already have succeeded.

**Old deployment still loaded after restart.** Startup revalidates integrity and falls back
to previous only with a warning and stopped transport. Inspect the failed version and repair
via a new validated upload. Rollback revalidates; neither action overwrites physical mapping.

## Native pipeline and hardware

**GStreamer unavailable or ERROR.** Install native GStreamer/GI dependencies, check the
actual plugin names and reported error. An unresponsive worker faults explicitly; native
control is isolated from GL drawing so blackout remains available. Stop, correct the cause,
and reload/retry the bundle. `--api-only` cannot test the decoder, audio or projected pixels.

**Audio is silent or wrong device.** Confirm the bundle contains the master audio source,
then check mute/volume, machine overrides and actual sink/clock. `fakesink` is intentionally
silent. On Pi, select ALSA plus a real HDMI PCM device from `aplay -L` while stopped. Auto
selection must be inspected. Video-embedded audio is not a substitute for the master lane.
A fallback to a silent sink is an explicit fault. Software volume is enabled even when the
sink has no mixer. No physical HDMI route was verified on the development Mac.

**A/V offset or loop gap.** Positive offset delays audio; measure flash/click latency at the
installation. PTS-minus-clock telemetry does not measure projector processing delay. Segment
seek support and visible/audible gaps depend on decoder/sink; inspect physically. If a gap
remains, record duration/backend and retain this as a commissioning failure, not a passed loop.

**Pi GLES/context failure.** Follow [Pi prerequisites](raspberry-pi.md), use a real graphical
session and record driver/EGL/GLES versions. Never force a fake GL version. Desktop adapter
pixel tests do not prove Pi context creation. RGB upload is the initial boundary; optimize
only after measuring CPU, frame pacing and thermals on the device.
