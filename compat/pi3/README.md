# Projection Mapper on VideoCore IV

The Pi 3 compatibility runtime uses the Pi's Broadcom OpenGL ES 2 stack for projector
output. A Python 3.5 HTTP server provides calibration and playback controls. The local
project contains the show and calibration, so playback and mapping work without an
authoring computer. The installed calibration is read on each start.

The compatibility path supports one projector, continuous compiled video lanes,
fixed-color lights and opacity curves, circle masks, multiply faces, and full-length
48 kHz stereo PCM master audio. The browser has a geometry editor. It omits the
live video preview, show authoring, media management, and browser bundle deployment.

## Prepare and copy a show

The existing `.pshow` combines the aligned face videos, lighting timeline, and master
audio. Transfer that bundle with the authoring project's `project.yaml` and master WAV.
Run the compatibility converter once per new show on a machine with FFmpeg and the
normal Python environment. It uses the existing bundle rather than editing the show.

```sh
.venv/bin/python compat/pi3/prepare.py path/to/project.yaml path/to/show.pshow \
  path/to/extracted/playback.mp4 path/to/project/builds/pi3
```

Transfer `builds/pi3/atlas.psp` and `builds/pi3/show.json` along with the referenced
master WAV. The converter makes a seekable 512 × 512 RGB565 texture atlas at 30 fps.
With four faces, that is a 256 × 256 texture per atlas slot. HDMI output uses the
connected display's negotiated mode, with the saved show geometry scaled uniformly.
The renderer uses ALSA sample position for timing and VideoCore for projection warps.

On device, use the same launcher for automatic capability selection:

```sh
./scripts/run-compatible.sh --project path/to/project.yaml --host 127.0.0.1
```

Use the Pi's local IP for on-site access. The server accepts private IPv4 clients on
IPv4 loopback, LAN, and Tailscale ranges. If binding all interfaces, use a trusted
local network. The default audio device is the Stretch on-board HDMI PCM and can be
changed with `--audio-device`.

The launcher selects the compatibility runtime on 32-bit Linux with Broadcom's
VideoCore libraries and device access. A native EGL probe verifies hardware support
before the controls start. On systems without those libraries it launches the normal
Projection Mapper.

Use the projector pattern and **Isolate surface** while moving the corners. Save
updates the separate `pi3-mapping.json` on the Pi. Back up that file to retain alignment
between show imports. Changes to corner positions never require rebuilding the atlas.
