# Pi performance review plan

Status: root cause confirmed; implementation and post-deploy verification in progress. This
document records the evidence, chosen 4K/30 target and regression-test plan.

## Preserved installation topology

The required topology is one 3840×2160 logical canvas split into four 1920×1080 viewports.
One 4K HDMI signal passes through the external video-wall controller to four projectors. Neither
the runtime change nor the `pi5-4k30` build profile collapses that canvas to 1080p. The separate
1920×1080 profile dimensions describe only the compiled video atlas decoded at runtime.

The selected installation settings are 3840×2160 at 30 Hz, a 480-pixel-wide preview at 1 fps,
and the existing four viewports/calibration. Preview can be disabled with `preview_fps: 0` for
comparison without touching output topology.

They must not overwrite the current Pi-local 4K project or its physical mapping. Renderer
changes are a later, separate repository decision, only if the measurements justify them.

## Measured baseline

On 2026-09-19, the deployed commit was `15b5105` on the Raspberry Pi 5.

| Item | Observation |
| --- | --- |
| Display | 3840×2160 at 60 Hz via HDMI-A-1 |
| Project | 3840×2160 canvas, 60 FPS, four 1920×1080 viewports, seven 1080×1080 media surfaces |
| Graphics | Broadcom V3D GLES 3.1, EGL 1.5, no software fallback, maximum texture size 4096 |
| Initial long-running runtime | 14.5 FPS, 2,921 late frames |
| Decode | Idle, so video decode is not the current limiting path |
| Thermal | 58.2 °C; `vcgencmd get_throttled` reported `0x0` |

The 4K master target is already at the reported maximum texture dimension, so increasing
resolution is not an option. The initial 14.5 FPS condition did not reproduce after a display
mode cycle and process restart, so it remains a separate stale/long-run symptom to watch during
the soak rather than the confirmed steady-state limit.

## Controlled findings

Tests used copied Pi-local projects and restored the installation source/config after each run.

| Configuration | Result |
| --- | --- |
| 4K/30, preview disabled | Sustained 30.0 FPS; late counter held at 2 for 60 seconds |
| 4K/30, old 960 px / 2 fps preview | 30.0 FPS, but preview intervals produced growing late frames |
| 4K/60, preview disabled | Approximately 37.4–37.9 FPS |
| Fresh 4K/60, old preview | Approximately 35.4–36.1 FPS |

Temporary stage timing showed normal 4K/30 render work at about 4–5 ms and presentation at
about 14–15 ms. Each old preview capture added about 28–35 ms, producing 48–56 ms frames. At
4K/60, presentation alone was about 19–20 ms and the old preview path about 49–56 ms. CPU,
memory and thermals remained modest with no throttle flags.

The confirmed 30 FPS issue is synchronous preview downscale/readback/JPEG work on the renderer
thread. The 60 FPS target is also beyond the measured present budget, but 60 FPS is not required.

## Implemented mitigation

1. Preview rate and width are installation settings, defaulting to 1 fps and 480 pixels.
2. Downscale/readback stays on the GL-owning render thread, but JPEG encoding moves to one
   bounded background worker with at most one queued frame.
3. A slow encoder drops preview opportunities instead of accumulating latency.
4. `/api/status` emits interval render/present/frame timing plus preview readback, encoding,
   frame age, captures and skips; Diagnostics exposes the same data.
5. The named `pi5-4k30` profile keeps a 4K destination canvas/four viewports while retaining
   a 1080p/30 compiled atlas.

## Post-deploy acceptance test

Run two comparable 60-second samples at 3840×2160/30 with the same content and clients:

1. Preview enabled at 1 fps / 480 pixels.
2. Preview disabled at 0 fps.

Record actual FPS, cumulative and interval late frames, all stage timings, preview worker stats,
CPU/RSS, temperature, throttling flags and configured viewport rectangles. Success is sustained
30 FPS, no continuing late-frame growth outside isolated preview captures, no preview backlog,
and unchanged four-quadrant topology. The physical image across all four projectors remains a
human visual acceptance gate.

## Remaining qualification

With the selected output mode, vary one factor at a time: enabled media surfaces, logical
surface resolution, particle profiles, and active video. Use the compiled atlas/GStreamer
playback path for a real multi-video show test. The current baseline had an idle decoder, so
decode optimization is not the first action.

## Git hygiene

`frontend/dist/`, artifacts, project builds/caches, runtime data, uploads, and virtual
environments are already ignored. Root `tmp/` is ignored to keep disposable local output out
of reviews. Generated `.pshow` bundles remain ignored through the existing project-build and
artifact rules; no blanket `dist/` or `*.pshow` rule is proposed.
