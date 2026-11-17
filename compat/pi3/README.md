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

On the authoring computer, **Project → Identity & output → Pi 3 texture atlas**
sets the playback detail. The setting is saved as `pi3_texture_size`.
Choose **Auto** or set **384**, **512**, **768**, or **1024** manually. A three-video show
gets 192 × 192, 256 × 256, 384 × 384, or 512 × 512 pixels per video respectively. All sizes
use 30 fps RGB565. A manual choice uses that size on the Pi and can drop frames
on busy clips. You can test a different size without rebuilding the original
`.pshow` by running the converter again with `--texture-size 768`, for example.

Auto always prepares 512 × 512 and adds larger candidates where the source and
surface sizes could benefit. The Pi tests a busy section of each candidate,
starting with the largest, and selects one that reaches at least 36 fps
offscreen to leave room for 30 fps playback. It falls back to 512 if neither
larger size passes. Check smoothness with the finished show and HDMI audio.
Long or busy shows can hit the 2 GiB limit for an individual atlas.

Under **Project → Surfaces**, **Match timeline video** copies the assigned
video dimensions from the media catalog into the surface's content size. Width
and height can also be entered directly. The action keeps the mapped corners.
If the surface has videos of different sizes, enter the intended size yourself.
Rebuild the `.pshow` after changing the content dimensions.

Transfer the entire `builds/pi3/` directory, including any `atlas-*.psp` files,
along with the referenced master WAV. The control page displays the installed
texture dimensions for the selected video surface. HDMI output uses the
connected display's negotiated mode, with the saved show geometry scaled
uniformly. The renderer uses ALSA sample position for timing and VideoCore
for projection warps.

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
