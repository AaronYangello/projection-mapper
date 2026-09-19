# Raspberry Pi 4 appliance: provisional setup

**No physical Pi was available for v0.3 verification.** These are researched setup choices,
not a qualified image or performance claim. The target is one 1920×1080 output at 30 fps,
one H.264 atlas decoder, up to four simultaneous media surfaces, sixteen lights, and HDMI
audio. Generic engine/project topology remains independent of that build profile.

Use **64-bit Raspberry Pi OS Desktop (Trixie)** provisionally. The official OS guide lists
Pi 4 support; BCM2711 documentation lists GLES 3.0 and H.264 1080p60 capability. Neither
proves this application's EGL, driver, codec or audio path. Use the graphical session's
existing Mesa/EGL stack and `--graphics-backend gles`; ModernGL's desktop GL 3.3 requirement
is not a supported Pi 4 assumption. Never use Mesa version overrides to make checks pass.

Sources: [Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/os.html),
[BCM2711](https://www.raspberrypi.com/documentation/computers/processors.html),
[ModernGL](https://github.com/moderngl/moderngl).

## Initial application installation

Build the frontend on the Mac (`cd frontend && npm ci && npm run build`) and transfer the
application source release plus `frontend/dist/`. Show updates need only `.pshow` bundles;
the Pi needs no Node, encoder, source stems, or Mac build worker. Target-platform Python
binaries and system libraries are still needed for initial application installation.

Candidate distribution packages below must be checked on the selected image before use:

```sh
sudo apt update
sudo apt install python3 python3-venv python3-gi python3-opengl libglfw3 \
  libegl1 libgles2 libgl1-mesa-dri gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-alsa alsa-utils
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --only-binary=:all: .
```

`--system-site-packages` exposes distribution GI/OpenGL bindings. `--only-binary` avoids
making dependency compilation a required Pi workflow: if a wheel is unavailable, resolve
an OS binary package or prepare a matching arm64 wheel elsewhere. Do not copy the Mac
virtual environment or its lock to the Pi. The application itself changes no OS packages,
boot services, display configuration or system audio routes.

In the real desktop session, set HDMI to 1920×1080 and the intended refresh rate. Collect:

```sh
.venv/bin/projection-show graphics-report --graphics-backend gles --fullscreen
gst-inspect-1.0 playbin
gst-inspect-1.0 appsink
gst-inspect-1.0 | rg -i 'h264|v4l2|video4linux'
aplay -L
```

The graphics report identifies GPU/vendor, GL/GLSL/EGL versions, texture limit, actual
output dimensions, fullscreen refresh and software-renderer detection. Runtime Diagnostics
identifies the decoder/audio factories. Factory availability is not proof it was selected
or used hardware. Do not assume a stateless V4L2 element on an image using a stateful driver.
If context creation fails, stop the graphics gate and record the error. API-only mode
cannot pass native output acceptance.

## Installation-local configuration and audio

Prepare a destination project with a 1920×1080 canvas, full-canvas projector and matching
stable surface IDs, roles and logical sizes. Calibrate **on the Pi**. Authoring physical
corners are never applied by a show bundle. Set `show.auto_start` only after supervised
playback/restart checks. Fullscreen uses the monitor's current mode.

```sh
.venv/bin/projection-show run --project projects/installation/project.yaml \
  --role appliance --data-root appliance-data --graphics-backend gles --fullscreen
```

Configure bearer authentication in the launch environment without committing or logging
its value. Deployment writes require `PROJECTION_SHOW_TOKEN`, even on a tailnet. Select
Diagnostics → Audio on this machine → ALSA and an HDMI PCM device reported by `aplay -L`;
Apply while stopped. Auto uses GStreamer device selection and must be verified. An explicit
HDMI device requires ALSA. `--audio-sink fake` is a silent test, never HDMI evidence. CLI
routing supplies initial defaults; saved machine-local audio settings take precedence.
No arbitrary sink expression or shell command is accepted.

The pipeline clock drives video, opacity, lights and show time. With real audio, inspect
the actual clock/sink. Master volume/mute/offset can be overridden locally without remuxing.
Prepare a visible flash and simultaneous click, measure at the viewing/listening position,
and delay audio by the observed projector lag using positive milliseconds (−1000…+1000 ms).
Repeat after changing projector processing mode. PTS/clock skew is not physical latency.

Sources: [playbin](https://gstreamer.freedesktop.org/documentation/playback/playbin.html),
[audio sinks and clocks](https://gstreamer.freedesktop.org/documentation/additional/design/audiosinks.html),
[autoaudiosink](https://gstreamer.freedesktop.org/documentation/autodetect/autoaudiosink.html).

## Private remote access

Prefer loopback binding and an authorized Tailscale Serve configuration for private HTTPS.
Once the device and tailnet permissions are available:

```sh
tailscale serve --bg http://127.0.0.1:8000
tailscale serve status
```

Use the actual HTTPS origin returned by Serve in the Mac target settings. Serve is private
to the tailnet; bearer authorization is a separate layer. Do not enable Funnel.
`--host 0.0.0.0` deliberately exposes LAN/tailnet interfaces; use only with intentional
firewall/access policy. Plain HTTP on a private network is not TLS. No Tailscale
configuration was changed in this milestone.

References: [Serve](https://tailscale.com/docs/features/tailscale-serve),
[CLI](https://tailscale.com/docs/reference/tailscale-cli/serve).

## Deployment and qualification

Follow [Build & Deploy](build-deploy.md) for staging, confirmation, validation, activation
and rollback. Stop before activation. A sleeping Mac has no role in appliance playback.
Active/previous pointers persist; calibration remains local.

Complete the [physical checklist](pi-commissioning.md) before calling this a supported Pi
appliance. RGB copies/upload, GLES driver behavior, HDMI clock/offset, loop seams, thermals
and a one-hour soak remain gates. Startup supervision and power-loss behavior need the real
display session; no unattended service has been installed or claimed complete.
