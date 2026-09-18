# Raspberry Pi setup and commissioning

Target: Pi 5, 64-bit Raspberry Pi OS with a graphical session and Mesa desktop OpenGL 3.3+.
This path is documented but **has not been executed on physical Pi hardware** for this desktop
milestone. Full unattended service behavior belongs to the reliability milestone.

## Installation

Install the distribution's Python/venv/development tools, C/C++ build tools, GLFW runtime,
and Mesa graphics drivers. Typical Raspberry Pi OS/Debian package names:

```sh
sudo apt update
sudo apt install python3 python3-venv python3-dev build-essential libglfw3 libgl1-mesa-dri libglx-mesa0
```

Install Node.js 20+ and npm using your chosen supported distribution, then clone the repository
and run `./scripts/install.sh`. Python wheels, including PyAV/FFmpeg, may vary by OS/Python version. No OS packages or
display settings are changed by our installer.

In the desktop session:

```sh
.venv/bin/projection-show validate --project projects/demo/project.yaml
.venv/bin/projection-show run --project projects/demo/project.yaml --fullscreen --host 0.0.0.0
```

Visit the Pi's LAN IP on port 8000. Bind to loopback unless LAN control is needed. Optional
`PROJECTION_SHOW_TOKEN` adds shared-token access; HTTP on a trusted LAN is not encryption.
There are no reboot, shell, or hardware-write API endpoints in this milestone.

Configure the physical HDMI mode in the OS before starting. Fullscreen uses the selected
monitor's existing mode. Confirm 3840×2160 and the refresh rate across the complete HDMI chain
if using the initial four-output controller. A mismatch produces a UI warning and letterbox
output, not a silent geometry stretch. The controller is not a software dependency.

Do not enable boot autostart until desktop rendering, correct output selection, and clean
shutdown pass. Future systemd integration needs the actual display-session environment and
user permissions; a generic unattended service has deliberately not been installed here.

## Hardware commissioning checklist

- [ ] Driver identifies the intended GPU; no software-rendering fallback.
- [ ] Correct monitor index, physical 4K mode, refresh rate, fullscreen, hidden cursor.
- [ ] Controller output order identified; no surface crosses projector viewports.
- [ ] All seven demo surfaces render; black outside surfaces; homography alignment checked.
- [ ] Same-LAN phone control, reconnect, pause, skip, blackout, restore.
- [ ] Save/reload and application restart preserve project geometry.
- [ ] Sustained frame-rate, CPU/RAM, temperature, and thermal-throttling measurements.
- [ ] At least one-hour soak without memory growth or visible stutter.
- [ ] Loss of display, process crash, interrupted save, and recovery behavior inspected.
- [ ] Supervised start after reboot verified once service integration is implemented.
- [ ] Actual native video decode/upload rate, seeking, pause, EOF, and error recovery measured.
- [ ] Live touch mapping latency and save/revert checked on the target LAN.

Keep desktop, synthetic/software-rendered, and physical Pi evidence separate in reports.
