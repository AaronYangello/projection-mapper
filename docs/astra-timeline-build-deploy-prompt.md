# Astra implementation prompt: timeline authoring, Mac build/deploy, and Pi 4 runtime

You are Astra. Implement the work described below directly in the existing repository at:

```text
/Users/aaronyangello/Projects/projection-mapper
```

You have no prior conversational context. This document is the complete handoff for the next
major phase of the Projection Show Engine. Do not stop at an architecture proposal or mock UI.
Implement, test, visually verify, document, and leave the repository runnable at the end of every
milestone. Make safe, reversible decisions autonomously, but stop at genuine physical-device,
permission, credential, deployment, or destructive-action boundaries.

## 1. Authority, required reading, and repository safety

Before editing:

1. Read `docs/projection_show_engine_spec.md` completely. It is the original product
   specification and remains authoritative except where this handoff explicitly advances a
   formerly future/out-of-scope feature.
2. Read `README.md`, `docs/architecture.md`, `docs/configuration.md`, `docs/media.md`,
   `docs/raspberry-pi.md`, `docs/verification.md`, and `docs/ux-research-and-review.md`.
3. Inspect `git status`, the complete current diff, recent history, existing tests, and actual
   package versions before making changes.
4. Preserve all pre-existing modifications. The checkout is currently dirty with a substantial
   UX/API refinement workset, including changes to the application shell, Mapping, Media,
   Project editing, styles, Playwright coverage, documentation, and runtime API tests. Treat
   those changes as user-owned current work. Integrate with them; do not replace them with the
   older `HEAD` implementation or revert unrelated files.
5. Do not hard-code the user's present topology into the generic engine. Installation limits
   belong in a named capability/build profile, validation, or project configuration.
6. Do not claim Raspberry Pi compatibility, hardware decoding, HDMI audio, loop quality, or
   thermal stability without physical evidence. Keep desktop, synthetic, and physical-device
   evidence clearly separated.

At handoff time, the dirty workset included these paths; refresh this list from `git status`
rather than assuming it is exhaustive or unchanged:

```text
.gitignore
README.md
backend/projection_show/api.py
docs/configuration.md
docs/desktop-development.md
docs/mapping.md
docs/media.md
docs/troubleshooting.md
docs/verification.md
docs/ux-research-and-review.md
frontend/package.json
frontend/package-lock.json
frontend/playwright.config.ts
frontend/src/App.tsx
frontend/src/MappingPage.tsx
frontend/src/MediaPage.tsx
frontend/src/ProjectEditor.tsx
frontend/src/api.ts
frontend/src/editing.tsx
frontend/src/styles.css
frontend/src/types.ts
frontend/src/useMapping.ts
frontend/tests/
scripts/serve_ux_fixture.py
tests/test_runtime_api.py
```

## 2. Current implementation baseline

The repository currently contains a working desktop prototype:

- Python 3.11+, FastAPI, Pydantic, YAML persistence, and a React/TypeScript/Vite frontend.
- A native ModernGL/GLFW renderer with one logical render target per enabled surface,
  homography-based four-corner mapping, true-black master output, test patterns, and a JPEG
  browser preview.
- A deterministic shuffle-bag scheduler with exactly one current foreground cue.
- Native image/video playback using Pillow and PyAV/FFmpeg. The current video path uses one
  decoder worker, converts frames to RGB24, and uploads one texture from the render thread.
- Media indexing, metadata, thumbnails, clip trim settings, fit/focal controls, manual playback,
  pause, blackout, and error exclusion.
- A responsive UI organized around Playback, Mapping, Media, Project, and Diagnostics in the
  current uncommitted UX workset.
- Versioned `project.yaml` storage. Saves validate, fsync a temporary file, atomically replace
  the project, and preserve a validated `.yaml.bak`.
- Relative media paths below a project's `media/` directory. Cached thumbnails are rebuildable.
- An optional bearer token and same-origin protections for `/api` operations.

Important current constraints:

- `schema_version` is currently `1`.
- `show.mode` currently permits only `shuffle_bag`.
- `max_simultaneous` is currently fixed at `1`.
- A cue contains exactly one `surface_id` and one `scene_id`.
- The renderer owns one `MediaPlayback`, one decoder, and one video texture.
- Audio is ignored.
- There is no browser upload service.
- There is no project-switching, deployment-bundle, or build pipeline.
- The current renderer requests desktop OpenGL 3.3 core and uses GLSL 330 shaders.
- Desktop/native behavior has been tested on an Apple Silicon Mac, but Raspberry Pi hardware
  behavior has not been verified.

Preserve the runtime ownership rule: OpenGL objects stay on the renderer thread. API/runtime
communication crosses the existing bridge as copied plain-data snapshots.

## 3. User goals and decided workflow

Implement a second, coordinated timeline mode while preserving the current random mode.

The target coordinated installation is:

- Raspberry Pi 4 appliance runtime.
- One 1920x1080 projector/output.
- Up to four simultaneously active video surfaces.
- Up to sixteen additional lighting surfaces.
- One audio program delivered over HDMI.
- No overlapping media clips on the same surface track.
- Optional automatic looping of the complete show.
- Full-surface opacity timing is a primary requirement.
- Lighting surfaces are fixed-color rectangles or circles whose opacity changes over time.
- The present installation does not require animated lighting color, but the data model should
  allow a later color-automation extension without redesigning the timeline.

The chosen workflow is:

```text
third-party video editor
  -> finished source videos
  -> Projection Show Engine on the Mac Studio
  -> align surface tracks, audio, lighting, and surface opacity
  -> build a Pi-optimized deployment bundle on the Mac
  -> upload/deploy that bundle to the Pi over Tailscale
  -> Pi validates and atomically activates the bundle
  -> Pi retains local physical mapping/calibration
```

The Mac build/deploy workflow is required. Pi-side compilation is not required. A Pi-initiated
remote Mac build worker is explicitly deferred; preserve an extension point by making build jobs
serializable and compiler logic reusable, but do not add distributed job orchestration now.

The user will use ordinary third-party nonlinear editing software for cutting, effects, titles,
color correction, speed changes, complex audio work, and preparation of full-length per-surface
video stems. Do not build a companion NLE or reproduce those capabilities.

## 4. Product boundary and non-goals

The Projection Show Engine owns:

- projectors and mapped surfaces;
- media/library metadata;
- shuffle behavior;
- coordinated surface tracks and absolute timing;
- one master audio track;
- full-surface opacity automation;
- lighting-surface shape, color, and opacity timing;
- projector grouping and track ordering;
- deterministic build inputs and deployment packaging;
- physical mapping/calibration on the destination appliance;
- playback, blackout, monitoring, and diagnostics.

It does not own:

- general-purpose video editing;
- clip splitting, ripple editing, filters, effects, titles, or color grading;
- arbitrary transition libraries;
- overlapping media clips on one surface;
- per-clip opacity automation in timeline mode;
- Pi-side transcoding as a required workflow;
- a remote Mac worker service;
- multi-machine live playback synchronization;
- DMX/Art-Net, OSC, MQTT, or external lighting protocols;
- public internet exposure or Tailscale Funnel;
- camera-based calibration, mesh mapping, edge blending, or color calibration.

Keep the random/shuffle experience behaviorally compatible. Random mode may continue using its
existing cue fade opacity. Timeline opacity is a separate surface-level system.

## 5. Required architecture

### 5.1 Separate show controllers with one renderer-facing contract

Do not stretch the existing single-cue scheduler until it becomes a mode-filled god class.
Create a small controller/protocol boundary so shuffle and timeline modes produce a common
renderer-facing snapshot.

Representative direction:

```diff
- current: Cue | None
- renderer playback: one MediaPlayback
+ show controller: ShuffleController | TimelineController
+ active layers: list[ActiveLayer]
+ playback resources: pool keyed by active source/build stream
```

An `ActiveLayer` or equivalent should provide the render thread only what it needs, such as:

- stable layer/track identifier;
- target `surface_id`;
- source/build identifier;
- source timestamp or atlas UV region;
- complete surface opacity at current show time;
- state/health metadata;
- lighting mask/color information where applicable.

Keep show-clock evaluation pure and deterministic wherever possible. Pause, seek, blackout,
restore, stop, and loop must have explicit semantics and tests.

### 5.2 Schema version 2 with explicit migration

Introduce an explicit schema-version migration rather than silently mutating schema version 1.
Existing valid v1 projects must load and migrate without losing shuffle settings, mappings,
scenes, or media paths. Unknown future versions must still fail closed.

The exact clean Pydantic shape is yours to implement, but it must represent the following
semantics. This example is illustrative rather than a requirement to copy field names blindly:

```yaml
schema_version: 2

show:
  mode: timeline                 # shuffle_bag | timeline
  auto_start: true

  shuffle:
    fade_in_seconds: 2.5
    hold_seconds: { min: 5, max: 8 }
    fade_out_seconds: 3
    gap_seconds: { min: 0.5, max: 2 }
    queue_length: 6
    seed: 42
    surfaces: { include_tags: [], exclude_tags: [] }
    scenes: { include_tags: [], exclude_tags: [] }

  timeline:
    loop: true
    duration_seconds: 240
    track_order:
      - video-left
      - video-right
      - light-window-1

    tracks:
      - id: video-left-track
        surface_id: video-left
        clips:
          - id: video-left-program
            scene_id: video-left-full
            start_seconds: 0
            source_in_seconds: 0
            duration_seconds: 240
        opacity:
          default: 0
          keyframes:
            - { time_seconds: 0, value: 0, interpolation: linear }
            - { time_seconds: 3, value: 1, interpolation: linear }
            - { time_seconds: 90, value: 0.4, interpolation: linear }
            - { time_seconds: 120, value: 0, interpolation: hold }

    audio:
      scene_id: master-audio
      start_seconds: 0
      source_in_seconds: 0
      volume: 1
      muted: false
      sync_offset_ms: 0
```

Required validation includes:

- stable unique IDs and valid references;
- finite non-negative timing;
- timeline duration and source-range bounds;
- ordered opacity keyframes inside the timeline;
- opacity values in `[0, 1]`;
- interpolation limited initially to `linear` and `hold`;
- no temporal overlap between clips on the same surface track;
- different surface tracks may run simultaneously;
- exactly zero or one master audio track;
- audio source validity;
- compatible surface role/source assignment;
- timeline references to enabled destination surfaces;
- profile warnings/errors for unsupported simultaneous workload.

Do not hard-code four videos and sixteen lights into the global project model. Put these limits
in a named `pi4-1080p` capability/build profile. The generic desktop model should remain capable
of representing other installations.

### 5.3 Full-surface opacity automation

This is more important than per-clip opacity and must not be reduced to clip fade handles.

Each timeline surface track has an independent opacity function evaluated against the
authoritative show clock. It multiplies the complete surface after content composition and shape
masking but before/finally during alpha composition into the mapped output.

```text
video / image / solid / lighting content
                    -> surface mask
                    -> full-surface opacity automation
                    -> homography / projector viewport
                    -> master output
```

Required behavior:

- opacity continues through clip boundaries and empty spans;
- lighting and media surfaces use the same automation evaluator;
- opacity is deterministic on play, pause, seek, resume, and loop;
- the evaluator supports `linear` and `hold` keyframes;
- missing automation has an explicit documented default;
- circle masks discard or alpha-mask outside pixels rather than painting a black rectangle;
- opacity-only edits do not require re-encoding the atlas video;
- random mode retains its existing cue-transition opacity behavior.

Do not implement per-clip opacity automation in the first timeline version unless it falls out
essentially for free and does not confuse the UI or data model. Surface automation is the
authoritative user-facing control.

### 5.4 Lighting surfaces

Represent lighting as ordinary mapped surfaces with explicit role/capabilities, not as a
hard-coded second renderer. A clean equivalent to the following is acceptable:

```yaml
role: lighting                  # media | lighting
shape: circle                  # rectangle | circle
light:
  color: "#ffcc88"
```

Requirements:

- fixed color is sufficient initially;
- the data model leaves room for later color keyframes;
- rectangles fill their mapped logical surface;
- circles are centered, preserve the intended logical aspect, and have transparent/discarded
  pixels outside the circle;
- all lighting brightness is driven by the track's full-surface opacity automation;
- render simple lights without allocating wasteful 1080p video framebuffers when a direct warped
  primitive or small procedural target will do;
- sixteen lights plus four video surfaces remain data/configuration, not engine constants.

### 5.5 Timeline authoring UI

Add a clear Show-authoring workspace without undoing the current Playback-centered UX work.
Provide an intuitive switch between the two saved show definitions:

- `Shuffle`
- `Timeline`

Viewing a tab must not silently change live mode. Show which mode is active and provide an
explicit `Use this mode` action while stopped. Switching modes preserves both configurations.

Timeline requirements:

- one lane per mapped surface;
- projector-group headers derived from each surface's `projector_id`;
- collapsible projector groups;
- persisted track ordering within groups;
- moving/reordering a row must not silently reassign the mapped surface to another projector;
- media blocks positioned against absolute show time;
- a single audio lane;
- a visible shared playhead;
- zoom, horizontal pan, seek, snapping, and precise numeric fields;
- add, move, duplicate, and delete clips;
- reject or visibly prevent same-track overlaps;
- no ripple editing, clip splitting, effects, or professional NLE tools;
- a compact opacity automation lane/curve for every surface;
- draggable opacity keyframes plus precise time/value fields;
- quick actions for `Fade in`, `Fade out`, `Set visible`, and `Set dark`;
- loop checkbox and clear duration/end behavior;
- unsaved-draft protection consistent with the current Mapping/Media/Project UX;
- desktop/tablet authoring as the primary experience;
- phone UI may be read-only/simplified for the timeline while retaining excellent runtime,
  blackout, deployment, and mapping controls.

Investigate `@xzdarcy/react-timeline-editor` as a replaceable view/interaction component. It is
acceptable to use after a bounded spike if its license, React compatibility, grouping strategy,
controlled state, accessibility, and build health fit this project. Wrap it behind a local
adapter and never persist its library-specific data shape or use its playback engine. If it
fights the required UX, build a focused custom timeline; the target has a small track count and
does not need a full NLE framework.

### 5.6 Desktop compiler and build profile

Implement the compiler as a reusable backend/service module with a headless CLI. The UI must call
the same underlying build service rather than duplicate build logic in React.

Required command shape (exact flags may improve if documented):

```bash
projection-show build \
  --project projects/my-show/project.yaml \
  --profile pi4-1080p \
  --output builds/my-show.pshow
```

The required `pi4-1080p` deployment profile is:

- 1920x1080 output;
- 30 fps target;
- no more than four simultaneously active compiled video surface lanes;
- no more than sixteen live lighting surfaces;
- one master HDMI audio program;
- no same-surface clip overlap;
- H.264 video, yuv420p;
- a broadly compatible stereo audio codec such as AAC in the playback container;
- one atlas stream decoded on the Pi, not four independent full-resolution streams.

The compiler must:

1. Validate the project and selected profile before doing expensive work.
2. Probe all referenced assets and fail with actionable per-asset errors.
3. Resolve clip timing, trims, gaps, and simultaneous surface content.
4. Pack the active video surface outputs into deterministic atlas regions within a 1920x1080
   playback stream. Do not bake physical homography/projector calibration into the video.
5. Generate black/empty atlas content where a track has no media.
6. Mux the single master audio track at its configured alignment.
7. Prefer Apple VideoToolbox hardware encoding on supported Apple Silicon systems, with a clear
   reported backend and a tested software fallback. Never silently claim hardware acceleration.
8. Invoke FFmpeg or equivalent with an argument vector, not an interpolated shell command.
9. Emit structured progress, cancellation, warnings, and final diagnostics.
10. Write to a temporary build location and publish only a complete validated bundle.
11. Use content-derived cache keys so unchanged expensive video work is reusable.
12. Record the exact input hashes, build profile, tool versions, encoder backend, and output
    checksum in the manifest.

Hardware encoder bitstreams need not be byte-identical across machines. The inputs, manifest,
cache-key derivation, atlas layout, and logical output must be deterministic and testable.

Do not bake these into the atlas video:

- destination homographies;
- projector viewport assignments beyond stable surface IDs;
- full-surface opacity keyframes;
- lighting surfaces;
- loop policy.

Those stay in runtime metadata so mapping, lighting, opacity, and loop changes can avoid video
re-encoding. If only audio changes, remux without re-encoding video where safely possible. If
only opacity, lighting, loop, or destination mapping changes, rebuild only manifests/bundle
metadata.

### 5.7 Deployment bundle

Define and document a versioned `.pshow` deployment bundle. ZIP is acceptable. A representative
layout is:

```text
my-show.pshow
  bundle.json                 # schema, compatibility, build/tool information
  playback.mp4                # one H.264 atlas plus master audio
  atlas.json                  # stable surface IDs and UV regions
  automation.json             # full-surface opacity and lighting automation
  checksums.json              # file sizes and cryptographic hashes
  authoring-project.yaml      # optional snapshot for provenance, never blindly applied
```

The bundle must not overwrite the Pi's physical projector mapping or calibration. It references
stable destination `surface_id` values. Before activation, the Pi validates that required
surfaces exist and are compatible with the installed project. Report missing/extra/incompatible
surface IDs clearly.

Implement atomic deployment:

1. Stream upload into a bounded temporary location.
2. Enforce configurable upload and free-space limits.
3. Validate ZIP paths; reject absolute paths, traversal, links, duplicate members, decompression
   bombs, unexpected files, and excessive expanded size.
4. Verify manifest schema, profile, sizes, and cryptographic checksums.
5. Probe the playback media and confirm expected video/audio streams.
6. Validate destination surface compatibility.
7. Extract into a versioned deployment directory.
8. Atomically switch an active-deployment pointer only after all checks pass.
9. Retain at least the previous known-good deployment and expose rollback.
10. Leave the currently active show untouched if upload, validation, or activation fails.

The UI should show upload/build/deploy progress, active deployment identity, build timestamp,
target profile, source project, validation state, prior deployment, and actionable failures.

### 5.8 Mac-side Build & Deploy

The same application/codebase has two operational roles; do not create a separate companion
application:

- **Authoring/Desktop:** full timeline editing, compiler, preview, bundle export, and deployment.
- **Appliance/Pi:** bundle upload/install, physical mapping, runtime playback, diagnostics, and
  blackout. Timeline editing may be view-only or capability-limited when no compiler exists.

Use explicit capabilities or an explicit launch/configuration mode rather than guessing the OS.
The UI must explain unavailable capabilities instead of showing disconnected buttons.

Provide `Build`, `Export bundle`, and `Build & Deploy` actions on the authoring system.
`Build & Deploy` must:

1. Build or reuse the current valid bundle.
2. Connect to a user-configured Pi URL over the private network.
3. Upload with visible progress and cancellation.
4. Ask for action-time confirmation before replacing the active deployment.
5. Wait for server-side validation and activation result.
6. Report the active deployment returned by the Pi rather than assuming success.

Store the Pi URL and any bearer token as machine-local application settings, not in project YAML,
deployment bundles, logs, tests, source control, or chat output. Mask saved secrets and require an
explicit Edit action before replacing them. Support a connection test that performs no deploy.

Do not implement a Pi-initiated remote Mac worker now. Keep build requests/progress serializable
so that a future `projection-show build-worker` can expose the same compiler safely.

### 5.9 Browser media upload

Add a real media upload workflow so a remote operator does not need SCP or FTP. It remains useful
for shuffle-mode media, images, audio sources, and one-off appliance maintenance even though the
primary coordinated workflow uploads compiled bundles.

Requirements:

- drag-and-drop and file picker;
- per-file progress and cancellation;
- stream to disk; never buffer an entire upload in memory;
- configurable size, count, disk-space, and concurrency limits;
- sanitized display names and server-chosen safe destination names;
- extension allowlist followed by actual media probing; never trust browser MIME alone;
- temporary partial-file namespace and cleanup after failure/restart;
- atomic final rename;
- no silent overwrite; detect exact duplicates by hash and make name collisions explicit;
- upload only below the selected project's media directory;
- preserve existing traversal/symlink protections;
- generate metadata/thumbnail after success;
- do not automatically add the source to a show or start playback;
- require an explicit scan/add/save operation consistent with current Media semantics;
- initially require stopped playback for final indexing/installation if concurrent storage I/O
  risks appliance playback;
- tests for traversal, collisions, limits, interrupted uploads, corrupt media, and cleanup.

Simple streamed multipart uploads are sufficient initially. Resumable/TUS uploads are a future
enhancement unless implementation falls out cleanly without expanding scope.

### 5.10 Pi playback pipeline and HDMI audio

The coordinated Pi runtime decodes exactly one compiled playback stream. Prefer a mature native
pipeline such as GStreamer for hardware-assisted decode, audio output, clocking, pause/seek, and
loop control. Do not assume PyAV automatically uses Pi hardware decode.

Requirements:

- one H.264 atlas stream feeds the mapped video surfaces;
- each surface samples its assigned atlas UV rectangle;
- opacity automation remains a runtime multiplier per surface;
- sixteen lighting surfaces are drawn cheaply by the GPU without video decoders;
- one muxed audio program outputs over the configured HDMI device;
- audio/pipeline position is the authoritative show clock while audio is active;
- video frames, opacity, lighting, playhead, and status derive from that clock;
- configurable audio mute, volume, HDMI device, and bounded `sync_offset_ms` for projector
  processing latency;
- pause, resume, seek, blackout, restore, stop, and loop have defined A/V behavior;
- looping should use prebuffered/segment seeking where supported and must be measured for visible
  or audible gaps;
- decoder state, media position, A/V skew, stale/dropped frames, backend, CPU/RAM, temperature,
  and throttling appear in diagnostics;
- a decoder or audio failure must produce an explicit fault, not silently drift or freeze.

Keep the existing image/video path available for shuffle mode unless replacing it is clearly
safer and regression-tested. Avoid a risky all-at-once rewrite.

### 5.11 Raspberry Pi 4 graphics compatibility is an early risk gate

The current renderer requires desktop OpenGL 3.3 core and GLSL 330. Raspberry Pi 4's supported
path is OpenGL ES/Mesa and must not be assumed compatible.

Before investing deeply in the full feature set, perform a bounded renderer spike:

1. Detect and report the actual Pi 4 GPU, renderer, EGL/GL/ES versions, texture limits, output
   mode, and whether software rendering is active.
2. Prove a hardware-accelerated fullscreen 1920x1080 context on the target OS.
3. Either add a clean OpenGL ES 3.x/EGL shader/context backend or prove the existing desktop
   path on the actual supported image. Do not rely on unsafe version overrides.
4. Render mapped solid rectangles and circles with alpha.
5. Render one atlas texture into four mapped surfaces.
6. Prove one H.264 stream plus HDMI audio through the chosen playback pipeline.

Keep backend differences isolated. Do not fork the whole renderer or sprinkle platform checks
through shaders and business logic. If physical Pi access is unavailable, implement the clean
backend boundary and tests possible on desktop, document the exact unverified gate, and do not
claim the spike passed.

### 5.12 Tailscale and security posture

The Pi is at another geographic location and is reached through the user's tailnet.

- Prefer keeping the application on localhost and using Tailscale Serve for private HTTPS when
  the installed Tailscale environment supports it.
- Document the existing `--host 0.0.0.0` option only as a deliberate LAN/tailnet exposure mode.
- Never use or recommend Tailscale Funnel for this private control plane.
- Preserve application bearer-token support and same-origin protections.
- Treat Tailscale access and application authorization as separate layers.
- Do not log bearer tokens, source cookies, secrets, authorization headers, or sensitive URLs.
- Restrict deploy endpoints and future destructive/system controls more strongly than read-only
  status endpoints.
- No API may accept arbitrary shell commands.

## 6. UI and operational behavior

### 6.1 Mode selection

- Preserve the existing random clip workflow and settings.
- Give the Show workspace obvious `Shuffle` and `Timeline` authoring tabs.
- Indicate which definition is active.
- An explicit action while stopped changes the active mode.
- Mode switching does not delete or reset the inactive definition.
- Playback/Runtime adapts terminology: queue for shuffle; current time, active surfaces, and
  upcoming events for timeline.

### 6.2 Timeline runtime preview

Show at a glance:

- authoritative playhead/time and total duration;
- loop state;
- active media surfaces;
- each surface's evaluated opacity;
- active lighting surfaces and brightness;
- audio state/device/position;
- build/deployment identity and whether it is stale;
- decoder/backend health;
- next clip/light/opacity events where helpful;
- clear differentiation between authoring preview and actual Pi output.

The browser interpolates a displayed playhead between server updates if useful, but the Pi/server
clock remains authoritative. Browser timing must never drive appliance playback.

### 6.3 Staleness and build feedback

The authoring UI must explain why a build is current or stale. Distinguish:

- video recompilation required;
- audio remux required;
- manifest-only update required;
- destination mapping change only, no rebuild required.

Do not simply display a generic `dirty` badge for an operation that could take a long time.

### 6.4 Safety and failure behavior

- Editing never changes projected output until an explicit save/apply/deploy action.
- Bundle upload never activates until validation completes.
- Build/deploy cancellation keeps the previous valid artifact/deployment.
- A disconnected browser does not stop playback or invalidate a build.
- A sleeping/offline Mac does not affect the Pi's current show.
- Power loss during upload or activation recovers to the previous or complete new deployment,
  never a partial deployment.
- Blackout remains immediate and independent of show mode.

## 7. Storage and portability

Continue using project-relative human-readable configuration. Keep authoring assets, generated
builds, caches, and installed deployments distinct:

```text
projects/<project>/
  project.yaml
  media/
  cache/
  builds/                 # generated, content-addressed or versioned

appliance-data/
  deployments/<id>/       # validated extracted bundles
  active-deployment       # atomic pointer/record
  previous-deployment
```

Exact appliance paths must be configurable and appropriate for local development/tests. Do not
write outside the project/runtime data roots implicitly.

The editable project may contain projector/mapping data for desktop simulation, but deployment
must not overwrite destination calibration. An eventual complete-project export and show-only
export may both exist; this milestone's `.pshow` is a show deployment that binds to stable
surface IDs on the destination.

Generated build outputs, uploaded source media, temporary files, and test artifacts must not be
accidentally committed. Update `.gitignore` narrowly; do not hide real source/config fixtures.

## 8. API direction

Exact REST paths may vary, but expose cohesive typed operations for:

```text
GET/PUT  /api/show/timeline
POST     /api/show/mode

POST     /api/media/upload
GET      /api/media/uploads/{id}
DELETE   /api/media/uploads/{id}

POST     /api/builds
GET      /api/builds/{id}
DELETE   /api/builds/{id}
GET      /api/builds/{id}/bundle

POST     /api/deployments/upload
GET      /api/deployments
POST     /api/deployments/{id}/activate
POST     /api/deployments/rollback

POST     /api/runtime/seek
```

Use WebSocket/SSE or the existing live channel for build, upload, deployment, and playback
progress where appropriate. Do not block the API event loop with scanning, FFmpeg, hashing,
archive validation, or compilation. Bound workers and cancellation explicitly.

Preserve optimistic revision checks and stale-edit protection for project/timeline saves.

## 9. Implementation sequence

Keep every milestone runnable and tested. A sensible sequence is:

### Milestone A: Baseline and risk spikes

- Reconcile and preserve the dirty UX workset.
- Run the current backend, frontend, browser, and GPU checks that are available.
- Prototype Mac FFmpeg/VideoToolbox atlas generation with synthetic four-lane input.
- Perform the Pi 4 GLES/context and single-stream HDMI A/V spike if the physical device is
  accessible. Record exact evidence and blockers.
- Establish backend/capability interfaces without rewriting working shuffle playback.

### Milestone B: Schema v2 and pure timeline domain

- Implement v1 -> v2 migration.
- Add timeline/audio/light/opacity models and validation.
- Implement pure opacity evaluation and timeline active-layer evaluation.
- Add unit tests for interpolation, seeking, looping, clip boundaries, and overlap rejection.
- Preserve v1 fixture compatibility and shuffle behavior.

### Milestone C: Upload foundations

- Add streamed media upload with progress, limits, cleanup, probing, and UI.
- Add archive/deployment-safe extraction helpers with adversarial tests.
- Keep upload work independent of compiler availability.

### Milestone D: Timeline authoring UX

- Add Show workspace and explicit mode activation.
- Add projector-grouped lanes, clips, audio, playhead, loop, and opacity automation.
- Integrate current draft/conflict-protection conventions.
- Add browser regression tests at desktop/tablet/phone widths.

### Milestone E: Desktop compiler and artifacts

- Implement reusable compiler service and CLI.
- Add `pi4-1080p` profile, atlas layout, audio muxing, manifests, caching, cancellation, and
  progress.
- Add synthetic deterministic fixtures and inspect outputs with FFprobe.
- Add authoring UI build/export/staleness behavior.

### Milestone F: Atomic Mac-to-Pi deployment

- Add local target settings with masked secret handling and connection test.
- Add Build & Deploy.
- Add Pi upload validation, activation, active/previous status, and rollback.
- Add failure-injection tests for partial upload, corruption, checksum mismatch, incompatible
  surfaces, cancellation, and interrupted activation.

### Milestone G: Pi runtime atlas, lighting, opacity, and HDMI audio

- Integrate the qualified GL/ES backend.
- Add atlas sampling into mapped surfaces.
- Add direct rectangle/circle lighting primitives.
- Add authoritative surface-opacity automation.
- Add GStreamer/native single-stream H.264 + HDMI audio playback and clock integration.
- Add loop, seek, sync-offset, diagnostics, and recovery.
- Preserve random mode regressions.

### Milestone H: Reliability, documentation, and commissioning

- Update architecture, configuration, media, desktop, Pi, troubleshooting, API, and verification
  docs.
- Add a Pi 4 commissioning checklist and sustained soak procedure.
- Verify build/install/restart persistence and previous-deployment recovery.
- Document every remaining hardware or deployment boundary honestly.

If a risk spike exposes a fundamental incompatibility, do not conceal it or continue building UI
on a false premise. Preserve completed reusable work, report evidence, and choose the smallest
reversible adjustment consistent with the product goals.

## 10. Required tests

At minimum, add coverage for:

### Models and migration

- valid v1 project migrates to v2 without semantic loss;
- invalid/unknown versions fail;
- both show definitions round-trip;
- stable IDs and references;
- timeline duration/source bounds;
- no same-track overlap;
- simultaneous clips on different tracks;
- audio validation;
- lighting shape/color validation;
- profile limit warnings/errors.

### Timeline and opacity

- before/at/between/after keyframes;
- linear and hold interpolation;
- missing/default automation;
- exact clip start/end behavior;
- pause/resume/seek;
- loop boundary;
- blackout/restore;
- media and lighting surfaces share the evaluator;
- opacity remains surface-level across clip changes.

### Compiler

- four synthetic video lanes become one 1920x1080 atlas;
- atlas regions contain the correct source at representative timestamps;
- gaps are black;
- master audio starts at the configured alignment;
- output is H.264/yuv420p plus expected audio;
- cache invalidation is correct;
- opacity/light/mapping-only changes avoid video encoding;
- FFmpeg failure/cancellation leaves no published partial build;
- paths and process arguments cannot inject shell commands.

### Upload and deployment security

- traversal, absolute paths, symlinks, duplicate ZIP members, expansion limits;
- incorrect checksums and unexpected files;
- interrupted upload and temporary cleanup;
- exact duplicate and filename collision behavior;
- insufficient disk space;
- incompatible/missing surface IDs;
- failed activation keeps current deployment;
- rollback restores the previous bundle.

### Renderer/runtime

- atlas UV sampling;
- mapping remains independent of atlas compilation;
- rectangle and circle masks;
- transparent circle exterior does not black out lower content;
- full-surface alpha at representative values;
- four media surfaces plus sixteen lights in a deterministic synthetic frame;
- audio-clock-derived show time;
- stale/dropped frame diagnostics;
- loop/seek state;
- existing shuffle, pause, blackout, mapping, and media tests remain green.

### Frontend

- mode tabs do not activate implicitly;
- mode activation requires stopped state and explicit action;
- projector grouping and ordering;
- clip movement and overlap rejection;
- opacity keyframe editing and presets;
- unsaved-draft protection;
- build staleness explanations;
- build/export/deploy progress and errors;
- upload progress/cancel/error states;
- deployment confirmation and rollback;
- phone runtime remains usable even if authoring controls are simplified.

## 11. Physical acceptance gates

The coordinated Pi 4 feature is not complete until these are verified on the target class of
hardware or explicitly left as unverified gates:

- hardware renderer is identified; no software rasterizer fallback;
- stable 1920x1080 fullscreen output at the intended refresh rate;
- one compiled H.264 atlas decodes through the reported backend;
- four atlas regions render on four mapped video surfaces;
- sixteen rectangle/circle lighting surfaces animate opacity correctly;
- one HDMI audio track stays acceptably synchronized;
- configurable audio offset corrects projector latency;
- pause, seek, blackout, restore, and automatic loop behave correctly;
- loop seam is inspected both visually and audibly;
- UI remains responsive during playback and deployment;
- CPU, RAM, disk, temperature, throttling, dropped/stale frames, and A/V skew are recorded;
- at least one hour of playback without leak, thermal failure, drift, or visible stutter;
- application/process restart returns to the active deployment;
- corrupt/incomplete new deployment leaves the previous show available.

Do not substitute Mac playback, API-only tests, a generated file, or a submitted hardware command
for physical Pi/display/audio proof.

## 12. Verification commands and evidence

Preserve and extend the existing checks. Run the applicable commands after each milestone and a
clean final pass:

```bash
.venv/bin/pytest -q -m 'not gpu'
RUN_GPU_TESTS=1 .venv/bin/pytest -q -m gpu
.venv/bin/ruff check backend tests
.venv/bin/ruff format --check backend tests

cd frontend
npm run build
npm run format:check
npm run test:ui
```

Add focused compiler/build commands and FFprobe inspection to documentation and CI-friendly
tests. Native GPU tests require real display permission; hardware acceleration and HDMI tests
require the target device.

For visual work, inspect the live UI at supported desktop, tablet, and phone widths. Do not treat
automated accessibility or screenshot checks as a substitute for interactive workflow review.

## 13. Documentation deliverables

Update or add documentation for:

- schema v2 and migration;
- shuffle versus timeline modes;
- full-surface opacity semantics;
- lighting surfaces and masks;
- third-party editing boundary and recommended source-stem preparation;
- desktop compiler setup and FFmpeg/VideoToolbox detection;
- build profiles, cache invalidation, and artifact contents;
- Mac Build & Deploy and machine-local target credentials;
- streamed media and deployment uploads;
- Tailscale-private access without Funnel;
- Pi 4 graphics/backend prerequisites;
- H.264 atlas playback and HDMI audio selection;
- audio offset calibration;
- deployment activation/rollback;
- backup/export and which data is authoring versus installation-local;
- troubleshooting build, codec, disk, network, GLES, HDMI, loop, and sync failures;
- exact desktop and physical-device verification evidence.

Do not leave operational knowledge only in code comments or your final response.

## 14. Final deliverable and handoff

When finished, report:

1. What was implemented, organized by milestone.
2. The exact schema and migration behavior.
3. How to prepare sources in a third-party editor.
4. How to author timeline, audio, lighting, and surface opacity.
5. How to build and export on the Mac.
6. How Build & Deploy reaches and authenticates to the Pi without exposing secrets.
7. How the Pi validates, activates, and rolls back a bundle.
8. The measured compiler backend and performance on the tested Mac.
9. The measured renderer/decode/audio backend and performance on the tested Pi, if physically
   verified.
10. Complete test/build/visual-verification results.
11. Every unverified physical, deployment, permission, or hardware boundary.
12. Remaining limitations and the safest next milestone.

Do not report a target, mock, configuration, generated artifact, or desktop test as verified Pi
behavior. The intended outcome is a reliable, inspectable show-authoring and appliance-deployment
workflow—not merely a new timeline screen.
