# Mapping and calibration

Open **Mapping**, select a projector and surface, then choose **Start mapping**. Changes reach
native output while the show runs; calibration does not restart the current cue.

1. Drag any numbered corner. The editor accepts mouse, pen, and touch pointer events.
2. With a corner focused, use arrow keys for one projector pixel; Shift+arrow moves ten pixels.
   Tap-to-nudge controls offer the same 1/10 px steps. Expand Exact coordinates for X/Y
   values normalized to 0–1. Editor zoom enlarges the canvas without changing projection.
3. Use Grid, White, Border, or Show to inspect alignment. Grid includes the surface and
   projector names, logical resolution, corner numbers, border, and center crosshair.
4. **Black other surfaces** isolates the selected surface. Global blackout still overrides it.
5. **Undo/Redo** steps through local edits; **Reset to inset rectangle** previews a
   rectangle spanning 10%–90% of the projector.
   **Revert** restores the most recently saved geometry.
6. **Save mapping** writes only the selected geometry, keeping the current show and decoder
   running. **Finish mapping** returns to normal output. Dirty edits prompt you to keep editing
   or discard; leaving this page uses the same protection and ends the preview.

Corners are normalized within a projector: `[0,0]` is top-left, `[1,1]` is bottom-right.
Order is TL, TR, BR, BL; keep the quadrilateral convex and clockwise. Geometry is rejected if
it crosses, collapses, becomes concave, or leaves the projector viewport. Logical content
aspect ratio is independent of the projector viewport. Disabled surfaces cannot be calibrated.

## Live editing contract

A single session owns calibration at a time, with a 45-second lease renewed every ten seconds.
If a browser disappears, expiry restores saved geometry. A sequence number rejects stale
updates. The browser sends the latest drag position at a 35 ms interval, serializes requests,
and flushes pending changes before saving. Save checks the persistent project revision and
uses the same atomic persistence as full project edits.

Geometry has its own render revision. Changing it updates homographies without reallocating
surface textures or resetting playback. A local browser-to-renderer acknowledgement was
measured at 90 ms on the development Mac; this is not a Pi or LAN latency guarantee. The
2 fps browser image is an inspection capture, not the live mapping update frequency.

Full project edits are blocked during a mapping session. Projector viewport, surface count,
and logical resolution changes remain available through the stopped Project editor. Add/remove
projector/surface forms and projector-wide identification are future work. Current test
patterns cover mapped surfaces; unused canvas pixels remain black.

Do not assume external video-wall output order or treat the demo corners as measured screen
calibration. Pause the show first if you want a still cue while aligning physical screens.
