# Mapping and calibration

Open **Mapping** and select a projector and surface. Moving a corner, nudging, or changing
coordinates begins a live adjustment automatically. Merely selecting a surface or a pattern
does not change output. Calibration does not restart the current cue.

1. Drag any numbered corner. The editor accepts mouse, pen, and touch pointer events.
2. With a corner focused, use arrow keys for one projector pixel; Shift+arrow moves ten pixels.
   Tap-to-nudge controls offer the same 1/10 px steps. Expand Exact coordinates for X/Y
   values normalized to 0–1. Editor zoom enlarges the canvas without changing projection.
3. Use Grid, White, Border, or Show to inspect alignment. Grid includes the surface and
   projector names, logical resolution, corner numbers, border, and center crosshair.
4. **Black other surfaces** isolates the selected surface. Global blackout still overrides it.
5. **Undo/Redo** steps through local edits; **Reset to inset rectangle** previews a
   rectangle spanning 10%–90% of the projector.
   **Revert** restores the saved geometry and ends the live adjustment.
6. **Save mapping** writes only the selected geometry, keeping the current show and decoder
   running, then returns to normal output in the same operation. Save and Revert sit beside
   the projector/surface selectors; there is no separate Start/Finish step. Dirty edits prompt
   you to keep editing or discard before leaving this page. The selectors remain locked during
   an adjustment so movement cannot accidentally target a different surface.

Corners are normalized within a projector: `[0,0]` is top-left, `[1,1]` is bottom-right.
Order is TL, TR, BR, BL; keep the quadrilateral convex and clockwise. Geometry is rejected if
it crosses, collapses, becomes concave, or leaves the projector viewport. Logical content
aspect ratio is independent of the projector viewport. Disabled surfaces cannot be calibrated.

## Live editing contract

A single session owns calibration at a time, with a 45-second lease renewed every ten seconds.
If a browser disappears, expiry restores saved geometry. A sequence number rejects stale
updates. The browser sends the latest drag position at a 35 ms interval, serializes requests,
and flushes pending changes before saving. Save checks the persistent project revision and
uses the same atomic persistence as full project edits. The first drag keeps its latest position
while ownership is being acquired. Save/Revert wait for in-flight requests; failed saves retain
the preview for retry. `POST /api/mapping/{id}/save?finish=true` saves and releases ownership
without a second request; omitting `finish` preserves the earlier API's save-and-continue behavior.

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
