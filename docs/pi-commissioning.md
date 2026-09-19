# Pi 4 physical acceptance record

Status: **unverified — device unavailable**. Keep desktop/native, synthetic, API-only and
physical evidence separate. Record exact device/image/package versions; retain local logs
and screenshots without credentials. A submitted command is not a passed check.

## Before activation

- [ ] Back up destination project, media and runtime deployment state.
- [ ] Record Pi model/RAM, power, cooling, OS/image, kernel, Mesa, GLFW, GStreamer, Python,
      decoder plugins, projector and HDMI chain.
- [ ] Graphics report: hardware GPU, EGL/GLES/GLSL versions, texture limits, 1920×1080
      actual fullscreen output and intended refresh; no software fallback/version override.
      Photograph physical output as well.
- [ ] Rectangle/circle alpha, homography and four atlas UV regions show expected pixels;
      circle exteriors preserve lower content. Save/reload physical calibration.
- [ ] One H.264 stream uses the reported hardware decoder; verify CPU/device evidence,
      not merely plugin presence. Fail explicitly if unsuitable.
- [ ] Confirm HDMI sink/device and audible output. No fakesink or wrong output route.
- [ ] Real Mac private Serve connection, bearer auth and deployment confirmation succeed;
      read back the returned active ID.

## Transport and timing

- [ ] Four media regions plus sixteen rectangle/circle lights follow independent opacity
      across clip boundaries and empty spans.
- [ ] Audio clock drives video/lights; record PTS/clock skew and separately measure physical
      latency with flash/click content. Verify positive/negative offset.
- [ ] Pause/resume, forward/backward seek, stop/restart and blackout/restore (running/paused)
      preserve documented position/audio behavior. Blackout stays responsive under load.
- [ ] Inspect ten loop seams visually and audibly. Measure gaps and record segment-seek
      support/fallback. A loop counter increment is insufficient.
- [ ] Non-loop end pauses without frozen media; lights hold evaluated end values.
- [ ] Decoder/audio failure visibly faults and pauses instead of silently drifting.
- [ ] Browser disconnect and sleeping/offline Mac do not disturb Pi playback.

## One-hour soak

Run the intended bundle at the real output mode for at least one hour. Save time-stamped
`/api/status` samples, for example every five seconds, and manual observations. Never save
authorization headers. Record the start, maximum/range and final value of each metric:

| Metric | Start | Maximum / range | End |
| --- | --- | --- | --- |
| Output FPS / late frames | pending | pending | pending |
| Decoder / sink / clock | pending | pending | pending |
| Dropped / stale frames | pending | pending | pending |
| Video PTS minus pipeline clock | pending | pending | pending |
| Physical A/V latency / drift | pending | pending | pending |
| Process CPU (100% = one core) | pending | pending | pending |
| RSS / memory growth | pending | pending | pending |
| Temperature / throttle flags | pending | pending | pending |
| Free disk / playback I/O | pending | pending | pending |
| Visible / audible loop gap | pending | pending | pending |

- [ ] No progressive leak, thermal throttling, drift or visible stutter.
- [ ] Phone runtime/blackout/mapping stays responsive during upload/validation; activation
      remains stopped-only. Record network/storage load.
- [ ] Agree on measured acceptance thresholds with the owner. Mac benchmarks do not supply
      a Pi performance guarantee.

## Persistence and recovery

- [ ] Supervised process restart restores active bundle and local calibration.
- [ ] Installation auto-start true/false behaves correctly.
- [ ] Corrupt checksum, incompatible IDs, interrupted upload and cancelled validation keep
      the current show. Rollback revalidates and restores the previous version.
- [ ] Controlled power-loss/interrupted-activation test on backed-up test data recovers old
      or complete new state. Atomic-file tests do not prove real filesystem/power behavior.
- [ ] Reboot/graphical-session startup and stop work under the chosen supervisor. Record its
      unit only after establishing actual display/device permissions.
- [ ] Projector/HDMI-audio disconnect and reconnect recovery or intervention is documented.

The next engineering decision follows this evidence: qualify RGB upload, or optimize its
frame boundary (for example DMA-BUF) if measured CPU/bandwidth/frame pacing fails. Keep
platform changes out of timeline models, bundle format and mapping logic.
