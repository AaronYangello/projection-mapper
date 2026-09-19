# Mac builds and atomic show deployment

`--role authoring` (default) enables the editor/compiler. `--role appliance` makes timeline
editing read-only and exposes upload/install, physical mapping, runtime and diagnostics.
Roles are explicit; OS detection does not decide which workspace to show. Hardware encoder
detection may use the host platform, but the result always reports the backend actually used.

## Compiler setup and commands

On the Mac:

```sh
./scripts/install.sh
# Native compiled preview also needs GStreamer and its Python bridge:
brew install gstreamer pygobject3
.venv/bin/python -m pip install '.[appliance]'
.venv/bin/projection-show build --project projects/my-show/project.yaml \
  --profile pi4-1080p --output projects/my-show/builds/my-show.pshow
```

The compiler uses system FFmpeg if present, otherwise the binary from the `compiler`
extra (`imageio-ffmpeg`). `--encoder auto` prefers VideoToolbox on macOS with software
fallback explicitly reported. `--encoder h264_videotoolbox` requires hardware success;
`--encoder libx264` explicitly chooses software. Hardware bitstreams need not be identical
across hosts. Test outputs were inspected with PyAV/FFmpeg (FFprobe-equivalent stream/frame
inspection); a separate FFprobe executable is optional:

```sh
ffprobe -v error -show_streams -show_format -of json playback.mp4
```

The reusable service lives in `build/compiler.py`; the CLI and API call the same compiler.
Build requests/job progress/results are plain serializable data. No remote build-worker
or distributed orchestration is installed. The Pi needs no source-video transcode or Node
build for a show update. For initial application installation, copy this source release and
the Mac-built `frontend/dist/`; use target-platform binary wheels/OS packages as described
in the [Pi guide](raspberry-pi.md).

## Profile, cache and artifacts

`pi4-1080p` v1 requires a 1920×1080 canvas, one enabled full-canvas projector, 30 fps,
at most four concurrent media clips, sixteen lighting tracks, one audio program, and
1024 compiled clips (a compiler resource budget). More than four total media surfaces can
share slots when their intervals do not overlap. Generic projects are not limited to these
counts. Use another profile for another installation; only this profile currently ships.

Packing is deterministic by start time, surface ID and clip ID. Reusable slots form a
1×1, 2×1 or 2×2 grid. Atlas gaps are black. Output is H.264 High/4.1, yuv420p, 30 fps,
with stereo 48 kHz AAC when a master audio source exists. The single stream carries timing
and baked source fit; **physical corners, viewport calibration, surface opacity, lighting,
audio gain/mute/offset, and loop policy are not baked into its video**.

| Saved change | Work |
| --- | --- |
| Source bytes, media timing/trim/fit, logical media dimensions, atlas layout, duration, encoder/tool/profile | Video recompilation |
| Audio source bytes, alignment, trim or duration | Audio encoding/remux with copied video |
| Opacity, lighting color/shape, loop, audio volume/mute/offset, names or ordering | Manifest/bundle metadata; video and audio caches reused |
| Physical corners/calibration, compatible destination viewport/mapping | No rebuild |

Changing a **media shape mask** is runtime metadata too. Profile-incompatible output changes
are rejected; “no mapping rebuild” is not permission to deploy a 4K project under this profile.
The UI's Check build inputs hashes files and explains the actual change category, rather
than predicting it from a generic revision badge. Cache files under `cache/compiler/` are
checksum-verified and rebuildable; corrupt cache records are misses. A cancellable file lock
serializes concurrent CLI/API builds for one project. FFmpeg receives an argument vector,
never a shell string. Source hashes are rechecked before publishing to catch mid-build edits.

Build jobs use at most two service workers, one job of each kind at a time. CLI progress is
JSON on stdout; API progress is polled independently of WebSocket playback. Browser disconnect
does not cancel a build. Cancellation stops FFmpeg, removes temporary work, and keeps prior
published artifacts. Output uses a fsynced temporary ZIP followed by atomic rename.

## `.pshow` bundle version 1

| Member | Contents |
| --- | --- |
| `bundle.json` | v1 bundle / v2 engine compatibility, ID, profile, compiler and FFmpeg versions, actual encoder, timestamp, input SHA-256s, cache keys, source project identity, required surfaces, playback hash |
| `playback.mp4` | One atlas video plus optional master AAC audio |
| `atlas.json` | v1 dimensions and per-clip surface ID, interval, slot, pixel rectangle and UV rectangle |
| `automation.json` | v1 full timeline, surface role/logical size/shape/fixed light color |
| `checksums.json` | Exact byte count and SHA-256 for every other member |
| `authoring-project.yaml` | Optional provenance only; compiler currently omits it; destination never applies it |

Bundle ID derives from video/audio/metadata keys. Files and ZIP metadata need not be byte
identical across builds (timestamps/hardware output differ); input keys/layout are deterministic.
All current members are flat files. The archive is stored without further compression.

## UI workflow

Save the timeline, stop, and explicitly activate Timeline mode. In Show → Build & Deploy:

1. **Build** validates assets/profile and shows progress, backend, reuse and errors.
2. **Export bundle** performs a native streamed browser download. An authenticated POST
   issues a one-use, 60-second HttpOnly/SameSite cookie; tokens never appear in download URLs.
3. **Preview built show** validates and loads a Mac preview while stopped. It does not
   change the installation's active pointer. Stop and Unload preview to continue editing.
4. **Edit target** stores a private origin and optional application bearer token in
   `<data-root>/target-settings.json`, mode 0600. Token reads return only `token_saved`;
   blank on edit keeps the saved value. It is excluded from project YAML, bundles and logs.
5. **Test connection** reads capabilities/deployment identity only. Use the Pi's private
   Tailscale Serve HTTPS origin. Embedded credentials, paths, queries, public addresses
   and redirects are rejected. The client ignores environment proxy settings.
6. **Build & Deploy** builds/reuses, tests the target, then asks for confirmation showing
   the exact target, new ID and prior ID. Only Confirm uploads and requests activation.
   The server binds confirmation to the bundle and target URL, streams progress, polls Pi
   validation, and reports the active ID returned by the Pi. Changed target/current IDs
   require another review. Cancel before activation keeps the prior show; after the activation
   request is dispatched, read the returned/queried target state rather than assuming reversal.

The target must be stopped to activate. A disconnected browser or sleeping Mac does not
affect a running Pi show. A lost connection during final activation has an uncertain outcome:
test/read the Pi's active ID before retrying. There is no automatic retry of that write.

## Destination validation and recovery

Application bearer authentication **must be configured** for bundle upload/activation/rollback
even if read-only status is otherwise available. Private tailnet membership is a separate layer.
Uploads are staged and cannot activate themselves. Validation rejects traversal/absolute paths,
links/special files, duplicate names, encryption, unexpected members, excessive count, expansion
and compression ratio. It verifies all hashes/sizes, strict metadata, deterministic atlas layout,
H.264/AAC stream properties and destination surface IDs/roles/logical dimensions/enabled flags.
Missing/incompatible IDs fail; extra local surfaces are reported and remain dark in the show.

Validated versions move to `<data-root>/deployments/<id>/`. One fsynced, atomically replaced
`deployment-state.json` holds **both** active and previous IDs, avoiding a two-pointer tear.
Activation never writes `project.yaml`, projector viewports or physical mapping. It loads the
show and leaves playback stopped; press Start after checking it. Startup loads the active
version and honors installation `show.auto_start`. If that version fails integrity checks,
startup tries the previous validated version and stops for inspection with a diagnostic warning.

Roll back revalidates the previous bundle and atomically swaps IDs. Unload bundle returns to
the local project and retains the bundle for rollback. Both require stopped transport and
confirmation. A failed upload, cancelled validation or failed pointer replacement keeps the
old active ID. Versions are retained rather than automatically deleted; monitor disk space.
Back up local `project.yaml` and deployment data together. Caches/builds can be regenerated;
source media and calibration cannot. A show bundle is not a complete authoring backup.

## Storage limits

`--data-root` chooses installation-local state (default `<project>/runtime-data`).
`--storage-limits path.json` overrides `StorageLimits` fields; positive integer byte/count
limits are validated (`free_bytes` may be zero). Defaults: media 2 GiB/file, bundle 4 GiB,
expanded archive 8 GiB, reserved free space 512 MiB, 500 media files, two concurrent uploads,
eight archive members, compression ratio at most 100. Metadata members are capped at 8 MiB.
Temporary `.uploads/` and `.deployment-staging/` files are cleaned after failure/restart.

Raw media upload uses an initialized job plus a streamed octet body. Names are sanitized;
the server chooses `upload-<hash-prefix>-<name>.<ext>`, checks actual decoded media and exact
duplicates, and rejects different content with the same display filename. Final rename/index
installation requires stopped, unchanged project state. Uploads never add scenes or start
playback; scan/add/save remain explicit. There is no resumable upload or remote file deletion.
