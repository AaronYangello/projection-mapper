# Native media playback

The Media page indexes files in the selected project's `media/` directory. Images and muted
video are decoded in Python using Pillow and PyAV/FFmpeg, uploaded to native OpenGL textures,
and composed through the same per-surface framebuffer and projective warp as color scenes.
The browser only receives a JPEG preview; it does not play or time the show video.

## Try the sample

From the repository root:

```sh
.venv/bin/python scripts/download_sample.py
.venv/bin/projection-show run --windowed
```

The optional download is a 4.2 MB H.264 Sintel trailer, 854×480 at 24 fps, lasting about
52.2 seconds. The script verifies a pinned SHA-256 and never silently replaces a different
existing file. See [credits, source, and license](../projects/demo/media/README.md).
The sample is ignored by Git; the demo still runs color scenes if it is absent. Startup never
requires a download or an internet connection.

## Library and controls

1. Upload with the file picker or drop zone, or copy a file into `projects/<your-project>/media/`. Supported video extensions are `.mp4`,
   `.m4v`, `.mov`, `.mkv`, `.webm`, `.avi`; images are `.png`, `.jpg`, `.jpeg`, `.webp`.
   Audio sources include `.wav`, `.mp3`, `.aac`, `.m4a`, `.flac`, and `.ogg`.
   Actual codec support depends on the installed FFmpeg build.
2. Stop the show, open Media, and choose **Scan folder**. Cards show inspected dimensions,
   frame rate, duration, codec, thumbnail, and any errors. Scanning is explicit.
3. **Add to show** persists a reusable scene definition. Choose an enabled foreground surface
   and **Play on surface** to interrupt the current cue; automatic queued playback resumes afterward.
4. While stopped, edit the display name, enabled state, tags, and that scene's fit, focal point, clip range, and playback settings, then
   save. Search matches names, paths, and tags; type filters also include Needs attention.
   Drafts stay in place when changing pages. These are project settings, not per-browser player settings.

Fit modes are **cover** (crop), **contain** (black bars), **stretch**, and **native** (one source
pixel per logical surface pixel). Focal points in [0,1] choose the crop center; letterboxing
remains centered.
The visible result is subsequently warped to the mapped quadrilateral.

**Full clip** schedules the selected clip range including fade-in and fade-out. If the clip is
shorter than their sum, both fades shrink proportionally. **Timed** uses show hold timings;
when the selected clip runs out, **Hold** retains its final frame and **Loop** repeats it.
The clip start/end settings are seconds within the inspected source duration. Pause and
blackout freeze the cue clock and requested video timestamp. Restore retains the prior
transport state. Skip, stop, and restart replace/release playback without blocking the GL loop.

## Failure and resource behavior

A native decoder worker retains a bounded latest request and published RGB frame. It seeks
when playback moves backward or jumps forward, reuses unchanged paused frames, and reports
state, presentation timestamp, and decoded frame count. Each active foreground cue owns one
source instance; the scheduler still permits exactly one foreground cue.

Missing, corrupt, or unsupported sources produce library/diagnostic errors and are excluded
from automatic selection. A failure during playback skips that cue and excludes the source
until a stopped rescan. File-backed scenes resolve only within the project's `media/` directory;
absolute paths, traversal, and escaping symlinks are rejected. Scans are capped at 500 files,
and decoded image/video dimensions at 32 megapixels. Thumbnails are cached under project
`cache/`, outside configuration. Browser uploads stream to a bounded partial-file namespace, are probed and hashed, and
install atomically only while stopped. Exact duplicates are reused/reported; name collisions
never overwrite files. Upload never adds a scene or starts playback. See [limits, cancellation
and installation semantics](build-deploy.md#storage-limits).

Shuffle and raw silent timeline previews use **CPU decoding with GPU composition**.
Compiled timeline playback uses one GStreamer atlas with one master audio program; actual
decoder/sink/clock appear in Diagnostics. Mac hardware decode was measured, but Pi decode
and HDMI remain unverified. Neither path claims zero-copy video. Shuffle ignores audio. Images are converted to RGB (alpha is not
composited); EXIF image orientation is supported. Video rotation metadata, HDR/color-managed
output, and color-management normalization are outside the current source-preview path. The
[desktop compiler](build-deploy.md) produces H.264/AAC atlas bundles from prepared sources. Pi decode/upload throughput and sustained thermal behavior require physical testing.

For the first installation, muted H.264 MP4, yuv420p, and 30 fps are reasonable preparation
choices. Source dimensions and aspect ratios remain generic; square content is not required.

## Coordinated sources

Add audio as a reusable scene, then select it in Show → Timeline → Master audio.
Video-embedded audio is ignored; use one separate mixed stem. Timeline Source in/Duration
are independent of shuffle clip settings. See [source preparation and authoring](timeline.md).
