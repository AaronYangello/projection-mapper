# Project configuration

Projects live outside the Python package. Pass an explicit `--project /path/to/project.yaml`
to select one. Copy `projects/demo/` for a new project; there is no project-switching UI yet.
The API returns normalized JSON; disk storage is human-readable YAML, schema version 1.

## Contract

| Field | Meaning |
| --- | --- |
| `id`, `name`, `description` | Stable project ID, editable display name, description |
| `canvas` | Width/height, refresh rate, fullscreen preference, zero-based monitor index |
| `projectors[]` | Stable ID/name, enabled flag, integer-pixel viewport within the canvas |
| `surfaces[]` | Projector ID, logical dimensions, normalized mapping, enabled/foreground flags, tags, ambient profile |
| `ambient_profiles[]` | `none`, `solid`, or `particles`; color, opacity, count, speed, size, drift, seed, foreground dimming |
| `scenes[]` | Named enabled `color`, `image`, or `video` sources, arbitrary tags; file paths, fit and clip settings for media |
| `show` | Shuffle-bag mode, one foreground cue, fades, hold/gap ranges, queue length, optional seed, tag selectors, auto-start |

IDs contain letters, digits, underscores, or hyphens. Names may contain spaces and need not be
unique. Referential validation is based on IDs. Unknown keys and unsupported types fail.
Future configuration migration must be explicit; schema versions other than 1 are rejected.

Projector viewports use top-left canvas coordinates. Surface corners use top-left projector
coordinates normalized to [0,1] and ordered top_left, top_right, bottom_right, bottom_left.
Each mapping must be convex and clockwise in this coordinate system. Off-viewport, concave,
self-crossing, or collapsed quadrilaterals are rejected. Viewports may intentionally overlap;
they are not automatically rearranged. Surface rendering follows project array order.

Logical surface dimensions control texture resolution and particle sizes, not where a
surface lands. Canvas and logical dimensions accept 16–8192 pixels, subject to an aggregate
100 megapixel target budget and the actual GPU maximum texture size.

Ambient particle speed and drift are normalized surface-units per second; size is logical
pixels. A stable seed plus surface ID yields repeatable particle populations. Opacity and
foreground_opacity are 0–1. Foreground dimming interpolates with cue opacity.

`show.surfaces` and `show.scenes` have `include_tags` and `exclude_tags`. Include matches any
listed tag, with an empty list matching all; any excluded tag disqualifies an item. Enabled
flags and projector status apply before tags. Empty eligibility produces a visible warning
and ambient-only output. Hold minimum must be positive; fades and gaps may be zero. Timing
values have an upper bound of one hour. This milestone supports exactly one foreground cue.

## Safe editing

1. Open Project, make edits, and stop the show using the persistent transport controls.
2. Save & apply validates the complete project, checks its revision, writes/fsyncs a temporary
   file, and atomically replaces the saved file. The previous valid file becomes `.yaml.bak`.
3. The runtime rebuilds its schedule; the renderer observes one new project revision.
4. Press Start show. A restart reconstructs state from the same YAML. Transient queue position
   is intentionally not persisted.

Projector and surface forms handle names, enabled state, viewports, sizes, assignments, and
background selection. The advanced editor can also change counts, geometry, ambient settings, source definitions, and
selectors. Closing it validates without saving. Invalid edits stay visible for correction.
Revert edits reloads the currently loaded project; Diagnostics → Reload saved project reads
external disk changes while stopped. Another client's intervening save yields a conflict,
not a silent overwrite. Refresh to load the latest revision before reapplying your changes.
Fullscreen/monitor changes require relaunch; canvas geometry and refresh rate apply on save.

Live Mapping is a separate operation: select a surface, preview geometry, and save just its
corners while playback continues. Its lease blocks full project changes until mapping ends.

File-backed scenes use project-relative `media/...` paths. `fit` is cover/contain/stretch/native;
`focal_point` is a normalized pair. Videos add `playback` (full_clip/timed), `end_behavior`
(hold/loop), `start_seconds`, and optional `end_seconds`. Missing or unreadable files produce
runtime warnings and are excluded from the queue; they do not invalidate the whole project.
Full-clip timing comes from inspected duration. See [media behavior](media.md).

## First installation

The demo already demonstrates a 3840×2160 master split into four 1920×1080 viewports and
seven square logical planes. Its coordinates are illustrative and must be calibrated to the
real screens. No physical output ordering is assumed. Replace the demo's scene timing with
2.5-second fade-in, 20–45-second hold, 3-second fade-out, and 0.5–2-second gaps when appropriate.
The optional sample video illustrates a file-backed source. Replace it and the ambient profiles
with installation-specific content when ready.
