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
the target budget; they are not a decoder drop count. Video is currently CPU-decoded, so
also inspect decoder state/PTS and try a smaller source on constrained hardware.

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
failed decoding, stop and rescan to make it eligible again. Audio is intentionally muted;
hardware decoding is not enabled in this milestone.
