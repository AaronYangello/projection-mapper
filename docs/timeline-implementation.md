# Coordinated show implementation record

## A — baseline and risk decisions

Baseline `2d67d8e` already includes the user-owned UX refinement; the checkout was clean.
Read the full original specification and all handoff-required guides before changes.
Baseline: 57 non-GPU tests, 6 real GPU tests, 11 browser workflows, production build,
Ruff and Prettier all pass on the Apple M3 Ultra Mac.

Installed versions: Python 3.14.7, PyAV 17.1.0, ModernGL 5.12.0, GLFW 2.10.2,
FastAPI 0.141.1, Pydantic 2.13.5; Node 26.7.0, React 19.3.0, Vite 6.4.3.

Local FFmpeg 7.1 from imageio-ffmpeg 0.6.0 encoded a 3-second synthetic four-region
1920×1080/30 atlas plus stereo AAC. VideoToolbox with `-allow_sw 0` succeeded in
0.334 s; libx264 fast succeeded in 0.175 s. PyAV verified H.264/yuv420p, AAC stereo,
and representative red/green/blue/yellow pixels. This tiny constant-color workload
does not predict full-show compile speed. Evidence: ignored `artifacts/phase3-spikes/`.

`@xzdarcy/react-timeline-editor` 1.0.0 has an MIT license and React >=18 peers.
Its package/source spike exposes controlled rows and drag callbacks, but couples its
internal engine, has no keyboard/ARIA handling in the action component, and does not
directly supply grouped surface opacity lanes. Use a focused local timeline view
adapter with native buttons/numeric fields. No library data or playback engine enters
the saved project. [Source](https://github.com/xzdarcy/react-timeline-editor).

## Physical risk register — unverified

The user confirmed the Pi 4 is unavailable. No device connections, deployment, HDMI
commands, or OS configuration changes have been made. Decisions below are provisional.

| Decision | Basis | Required later evidence |
| --- | --- | --- |
| One 1080p30 H.264 atlas | BCM2711 documentation lists H.264 1080p60 decode and GLES 3.0 | Actual OS codec element, hardware usage, throughput and sustained temperatures |
| Separate GLES backend boundary | ModernGL documents desktop OpenGL 3.3+, not supported GLES | Real EGL/GLES context, fullscreen mode, alpha/UV pixel tests; no version overrides |
| GStreamer playbin/appsink with a configured audio sink | Mature clock, seek, audio and bounded-frame APIs | Actual decoder factory; HDMI sink/device; A/V latency and loop seam |
| RGB upload as initial fallback | Reuses tested native texture composition; about 187 MB/s at 1080p30 | Measure CPU, copies, late/stale frames; optimize with DMA-BUF only if needed |
| No automatic hardware-success claims | Plugins depend on kernel, device permissions and OS packaging | Record device-specific diagnostics before appliance commissioning |

Primary references: [BCM2711](https://www.raspberrypi.com/documentation/computers/processors.html),
[ModernGL requirements](https://github.com/moderngl/moderngl),
[GStreamer playbin](https://gstreamer.freedesktop.org/documentation/playback/playbin.html),
[seeking](https://gstreamer.freedesktop.org/documentation/additional/design/seeking.html),
[V4L2 codec discovery](https://gstreamer.freedesktop.org/documentation/v4l2codecs/index.html).
Plugin names must be detected on the device; stateless decoder documentation is not
proof that a given Pi image uses that driver. CPU/RAM/temperature and one-hour soak,
HDMI audio offset, physical loop inspection and power-loss commissioning remain gates.

## B–H — implemented software and evidence boundaries

| Milestone | Implemented | Remaining gate |
| --- | --- | --- |
| B: domain | Schema 2, explicit non-mutating v1 migration, separate controllers, clip/audio/light references and bounds, pure surface opacity, loop/seek/blackout semantics | None for tested domain behavior |
| C: uploads | Streamed media jobs/probe/hash/cancel/atomic install; bounded ZIP validation and adversarial coverage | Real Pi storage/network-load measurements |
| D: authoring | Show tabs, explicit mode activation, projector groups/order, absolute clips, numeric/drag editing, audio, opacity curves/presets, draft/conflict protection, phone overview | Physical touch/device review |
| E: compiler | Shared CLI/service, deterministic atlas/profile/keys, VT and software fallback, audio remux, metadata reuse, progress/cancel, export | Representative full-length production-source benchmark |
| F: deployment | Local masked target settings, read-only test, confirmed streaming deploy, strict staged validation, atomic active/previous state, rollback/restart recovery | Actual Mac-to-Pi Tailscale deployment and interrupted-power test |
| G: native runtime | Isolated GLES adapter, one GStreamer atlas, native clock, direct lights/masks/opacity, local audio routing/offset, diagnostics and worker isolation | Pi EGL/GLES, hardware decode, HDMI, latency and audible loop seam |
| H: reliability/docs | Migration/security/cache/failure tests, operating/API/commissioning guides, responsive/native review | One-hour physical soak, thermal qualification and supervised boot service |

The provisional OS choice is 64-bit Raspberry Pi OS Desktop / Trixie. Official OS support
and BCM2711 specifications are inputs to this decision, not test evidence. See the
[Pi guide](raspberry-pi.md) for sources, dependencies and commands, and
[commissioning record](pi-commissioning.md) for unresolved acceptance checks.

### Mac compiler and playback measurements

A reproducible 12-second fixture uses four moving 640×360 source stems, sixteen alternating
rectangle/circle lights and stereo 48 kHz timing pulses. Generated by
`scripts/create_timeline_fixture.py`; no third-party media is needed for these tests.

- First full auto build in the restricted environment reported VideoToolbox failure and
  explicit libx264 fallback: **1.186 s**.
- Explicit VideoToolbox with normal Mac hardware access: **1.181 s**, hardware encoding
  required (`-allow_sw 0`). Final stream is 1920×1080/30 H.264 yuv420p plus stereo AAC.
- These tiny synthetic moving bars compress easily. Neither number predicts production
  long-form performance. The earlier constant-color spike is recorded above separately.
- Corrected native runtime: Apple M3 Ultra, desktop GL 4.1 Metal 90.5, internal 1920×1080,
  window 1280×720, GStreamer 1.28.7, `vtdec_hw` video, `avdec_aac`, silent `fakesink` and
  `GstSystemClock`. This confirms Mac decode, not HDMI audio/clock behavior.
- 65 one-second samples spanning 64.63 s: **29.9–30.0 FPS**, **0 late frames**, **0 appsink
  drops**, process CPU **24.1–36.0%** (100% = one core), peak-RSS metric **333.1–333.9 MiB**,
  PTS-minus-clock **−35.56…−0.76 ms**, stale-frame age **0–0.032 s**, loop count **1→7**.
  No pipeline error/warning in that sample. This is a short Mac sample, not a soak or
  physical A/V skew measurement.

Two native issues found in real integration were fixed: a Python native-stream callback
could deadlock against playbin state/property locking; native control now stays on a bounded
worker with no streaming callbacks. The software-volume flag is also required for real
volume/mute control when a sink has no mixer; the native regression checks the actual mixer.
Reference: [GStreamer play flags](https://gstreamer.freedesktop.org/documentation/playback/playsink.html).

Raw evidence is ignored under `artifacts/phase3-spikes/` and `artifacts/timeline-review/`
(`hardware-build-evidence.jsonl`, `build-evidence.jsonl`, `runtime-evidence.json`). Current
verified test counts and screenshots are in [verification](verification.md). No remote Pi,
projector, real HDMI audio, physical fullscreen mode, thermals, or service was tested.
