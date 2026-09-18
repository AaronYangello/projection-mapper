# Generic Projection Mapping Show Engine
## Comprehensive Build Specification for GPT-5.6 Sol

**Working name:** Projection Show Engine  
**Primary target:** Raspberry Pi 5 running Raspberry Pi OS / Linux  
**Primary control surface:** Responsive web UI accessible from desktop, tablet, or phone  
**Primary display topology:** One logical render canvas split to one or more projectors through external display hardware such as a video-wall controller  
**Primary use case:** A configurable multi-surface projection show in which mapped physical surfaces can display ambient visuals and scheduled or semi-random foreground media  
**Secondary goal:** Make the engine reusable for other projection-mapped elements in a larger Christmas display and for non-Christmas installations.

---

# 1. Mission

Build a self-contained projection-mapping show engine that:

1. Runs continuously and unattended on a Raspberry Pi 5.
2. Renders one fullscreen logical output canvas.
3. Supports any configurable number of projectors and mapped surfaces.
4. Maps rectangular logical content onto arbitrary four-corner quadrilaterals.
5. Supports reusable ambient backgrounds such as snowfall, particles, color fields, image loops, or video loops.
6. Supports foreground media such as video clips and images.
7. Schedules foreground content using configurable rules such as shuffle bags, randomized timing, priorities, exclusions, and per-surface eligibility.
8. Provides a polished local web UI for:
   - setup,
   - projector configuration,
   - surface creation,
   - mapping/calibration,
   - media management,
   - show configuration,
   - live runtime monitoring,
   - manual overrides,
   - diagnostics,
   - system controls.
9. Saves all configuration in human-readable files.
10. Contains no hard-coded assumptions about:
    - four projectors,
    - seven screens,
    - Christmas,
    - snowfall,
    - 2x2 layouts,
    - square content,
    - specific physical screen sizes.
11. Can later be extended to control external hardware such as:
    - projector IR emitters,
    - RS-232 video-wall controllers,
    - relays,
    - GPIO devices,
    - lighting systems.

The software should feel like a small appliance, not a developer demo.

---

# 2. Current Installation Context

The first installation uses:

- Raspberry Pi 5.
- One HDMI output from the Pi.
- An OREI UHD-14VW video-wall controller.
- Up to four physical projectors.
- Seven physical 8 ft x 8 ft projection screens.
- No screen spans multiple projectors.
- Projectors remain installed semi-permanently during the season.
- The Pi will eventually also issue projector wake commands through separate IR emitter circuits.
- Audio is not required for the initial installation.
- Foreground content will primarily be low-stimulation, classic Christmas scenes.
- Source clips will be preprocessed to square crops, typically 1080x1080.
- Only one primary foreground scene is expected to be active at a time in the initial show.
- Inactive surfaces should display a subtle ambient visual, initially dim snowfall.
- Foreground scenes should fade in, play, fade out, pause briefly, and then appear on another eligible surface.
- Screen and clip selection should feel random but avoid ugly repetition.

These facts describe the first deployment only. They must be represented through configuration, not code constants.

---

# 3. Design Principles

## 3.1 Configuration First

Everything meaningful must be configurable through the UI and persisted on disk.

Examples:

- number of projectors,
- render canvas size,
- projector viewport,
- projector names,
- number of surfaces,
- surface names,
- mapping coordinates,
- aspect ratios,
- surface groups/tags,
- media folders,
- ambient layer type,
- scheduler rules,
- fade timing,
- duration ranges,
- output refresh rate,
- startup behavior.

Do not hide important values in source code.

## 3.2 Generic Terminology

Use generic nouns throughout the product.

Preferred terms:

- **Project**
- **Output Canvas**
- **Projector**
- **Surface**
- **Media Asset**
- **Ambient Layer**
- **Foreground Layer**
- **Scene**
- **Playlist**
- **Scheduler**
- **Cue**
- **Show**
- **Mapping**
- **Calibration**
- **Runtime**

Avoid Christmas-specific terminology in architecture and UI.

For example:

Bad:
- Snow Settings
- Christmas Screen
- Santa Video Queue

Good:
- Ambient Layer
- Surface
- Foreground Queue

A built-in snowfall ambient generator is fine, but it should be one option among several.

## 3.3 Appliance-Like Reliability

The system should:

- boot automatically,
- start automatically,
- recover from app crashes,
- preserve configuration,
- recover cleanly from power loss,
- expose clear health status,
- avoid requiring a keyboard or mouse connected to the Pi during normal operation.

## 3.4 Human-Friendly UI

The UI should be clean, calm, and operationally obvious.

Avoid:
- developer-console aesthetics,
- huge forms,
- dense tables everywhere,
- hidden controls,
- cryptic abbreviations,
- modal overload.

Prefer:
- cards,
- visual previews,
- grouped settings,
- live status indicators,
- sensible defaults,
- inline help,
- clear save/apply states,
- drag handles,
- real-time feedback during mapping.

## 3.5 Reusable Architecture

The engine should support multiple projects/configurations.

Example future projects:

- seven-screen Christmas scene installation,
- mapped house-window display,
- animated sign,
- garage-door projection,
- static decorative façade projection,
- small indoor mapped prop.

A user should be able to create a new project without cloning or modifying source code.

---

# 4. Recommended Technical Architecture

Use a modular architecture with these major subsystems:

1. **Render Engine**
2. **Media Engine**
3. **Mapping Engine**
4. **Ambient Generator Engine**
5. **Show Scheduler**
6. **Configuration Store**
7. **Web API**
8. **Web Control UI**
9. **Runtime State Manager**
10. **Diagnostics / Logging**
11. **Hardware Adapter Layer**
12. **Startup / Service Integration**

The rendering process and web server may run in one application initially if that simplifies deployment, but the code should keep these responsibilities separated.

---

# 5. Recommended Technology Stack

The implementation agent may choose a different stack if it has a strong technical reason, but the default recommendation is:

## Backend / Runtime

- Python 3.11+ or 3.12+
- FastAPI for local web API
- Pydantic for config models
- Uvicorn for serving
- asyncio for orchestration

## Rendering

Preferred options, in order:

1. ModernGL / OpenGL
2. SDL2 + OpenGL
3. GStreamer/OpenGL integration where useful

The render path should be GPU accelerated.

Avoid rendering the main show with a browser unless there is a compelling measured reason. A native GPU renderer is preferred for predictable fullscreen output and efficient video composition.

## Video Decode

Use a mature Linux-native pipeline such as:

- GStreamer, preferred,
- FFmpeg/libav bindings if needed.

Do not implement decoding manually.

The initial expected workload is light:
- usually one active 1080x1080 H.264 foreground video,
- several cheap procedural ambient layers,
- one 3840x2160 output canvas.

## Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- a clean component library such as shadcn/ui if useful

Use responsive layouts suitable for:
- desktop,
- tablet,
- phone.

## Persistence

Initial version:
- YAML or JSON files for project configuration.
- SQLite may be used for media indexing/runtime history if helpful.

Prefer human-readable configuration for project files.

## Process Supervision

- systemd service
- Restart=always or equivalent
- journal logging

---

# 6. Core Data Model

Use stable unique IDs internally. Display names must be editable.

## 6.1 Project

A project is the top-level reusable installation definition.

Example fields:

```yaml
id: christmas-main
name: Main Christmas Screens
description: Seven-screen outdoor Christmas installation

canvas:
  width: 3840
  height: 2160
  refresh_rate: 60
  fullscreen: true

startup:
  auto_start_show: true
  start_delay_seconds: 5
  initial_blackout_seconds: 3

scheduler:
  mode: shuffle
  active_foreground_limit: 1
```

A project contains:
- output canvas,
- projectors,
- surfaces,
- ambient definitions,
- media sources,
- playlists,
- show rules,
- hardware adapters.

## 6.2 Output Canvas

Represents the single framebuffer rendered by the application.

Fields:

- width
- height
- refresh rate
- fullscreen mode
- target monitor/output
- optional render scale

Example:

```yaml
canvas:
  width: 3840
  height: 2160
  refresh_rate: 60
```

## 6.3 Projector

A projector is a logical region within the output canvas.

A projector does not need to correspond to a directly attached GPU output. In the initial installation, the external video-wall controller divides one 4K canvas into four 1080p outputs.

Fields:

```yaml
projectors:
  - id: projector-a
    name: Projector A
    viewport:
      x: 0
      y: 0
      width: 1920
      height: 1080
    enabled: true
```

The UI must allow:
- adding projector,
- deleting projector,
- renaming,
- repositioning viewport,
- resizing viewport,
- enabling/disabling,
- assigning test pattern.

Provide common layout helpers:

- 1x1
- 2x1
- 1x2
- 2x2
- custom

But helpers must only generate configuration. Do not constrain the system to those layouts.

## 6.4 Surface

A Surface is the main mapping primitive.

A surface is a logical 2D content plane mapped into a quadrilateral.

Fields:

```yaml
surfaces:
  - id: screen-1
    name: Screen 1
    projector_id: projector-a
    enabled: true

    logical:
      width: 1080
      height: 1080

    mapping:
      top_left: [130, 75]
      top_right: [1000, 92]
      bottom_right: [1042, 954]
      bottom_left: [102, 970]

    tags:
      - main-screen
      - outdoor

    ambient_profile: subtle-snow
    foreground_enabled: true
```

Coordinates may be stored:
- relative to the projector viewport, preferred,
or
- normalized 0..1 coordinates.

Normalized coordinates are strongly preferred for portability.

Example:

```yaml
mapping:
  top_left: [0.07, 0.05]
  top_right: [0.52, 0.06]
  bottom_right: [0.54, 0.89]
  bottom_left: [0.05, 0.90]
```

The renderer should use a homography/perspective transform.

Future extensibility:
- polygon/mesh surfaces may be added later,
- but v1 only needs four-corner surfaces.

## 6.5 Surface Groups

Allow arbitrary tags/groups.

Examples:

- main-screens
- windows
- left-yard
- garage
- upper-level
- foreground-eligible
- ambient-only

Scheduler rules should be able to target groups.

## 6.6 Media Asset

Fields:

```yaml
id: snowy-village
name: Snowy Village
type: video
path: media/scenes/snowy-village.mp4
duration_seconds: 38.2
width: 1080
height: 1080
fps: 30

tags:
  - classic
  - low-stimulation
  - exterior

enabled: true
```

Support:
- video,
- image,
- image sequence later if useful.

The media indexer should inspect files automatically.

## 6.7 Playlist

A playlist is a named collection/query of media assets.

Example:

```yaml
playlists:
  - id: classic-scenes
    name: Classic Scenes
    include_tags:
      - classic
    exclude_tags:
      - disabled
```

Also support manually curated asset lists.

## 6.8 Ambient Profile

Ambient visuals must be modular.

Example:

```yaml
ambient_profiles:
  - id: subtle-snow
    name: Subtle Snow
    type: particles

    generator: snowfall

    settings:
      density: 0.15
      speed_min: 8
      speed_max: 22
      size_min: 1.5
      size_max: 5
      opacity: 0.18
      drift: 0.15

    transition:
      foreground_behavior: fade_down
      foreground_opacity: 0.02
      fade_seconds: 2.0
```

Required ambient types for v1:

1. none
2. solid color
3. procedural snowfall
4. procedural generic particles
5. looping image
6. looping video

Architecture should allow future generators.

## 6.9 Show / Scheduler

A show describes runtime behavior.

Example:

```yaml
show:
  active: true

  foreground:
    playlist: classic-scenes
    max_simultaneous: 1

    surface_selector:
      include_tags:
        - main-screen
      mode: shuffle_bag
      avoid_immediate_repeat: true

    media_selector:
      mode: shuffle_bag
      avoid_immediate_repeat: true

    transitions:
      fade_in_seconds: 2.5
      fade_out_seconds: 3.0

    playback:
      use_full_clip: true
      duration_min_seconds: 20
      duration_max_seconds: 45

    gaps:
      min_seconds: 0.5
      max_seconds: 2.0
```

Scheduler rules should remain generic.

---

# 7. Render Model

The renderer should conceptually operate as:

```text
Output Canvas
  └── Projector Viewports
        └── Surfaces
              ├── Ambient Layer
              ├── Foreground Layer
              └── Optional overlays/debug visuals
```

Each Surface owns a logical render target.

Example:

```text
1080 x 1080 logical texture
       ↓
ambient composition
       ↓
foreground composition
       ↓
opacity / transitions
       ↓
perspective warp
       ↓
projector viewport
       ↓
master canvas
```

## 7.1 Surface Content

A surface should support at least:

- background fill
- ambient visual
- foreground media
- debug overlay

## 7.2 Blending

Use alpha blending.

Transitions must be smooth and time-based.

Avoid frame-count-based timing.

## 7.3 Mapping

For v1:

- exactly four editable corners,
- homography transform,
- no edge blend required,
- no overlap correction required.

Do not use projector keystone for mapping unless unavoidable. Prefer software mapping so configuration remains inside the system.

## 7.4 Black Outside Surfaces

Every pixel outside configured mapped surfaces should remain true black.

This is important for projection installations.

---

# 8. Scheduler Behavior

The scheduler is a critical subsystem.

## 8.1 Shuffle Bag

Do not use naive independent random choice.

For surface selection:

1. Build bag of eligible surfaces.
2. Shuffle.
3. Pop until empty.
4. Refill and reshuffle.
5. Prevent the first item of a new bag from matching the last item of the old bag when possible.

Same behavior for media.

## 8.2 Timing

Timing values must support:
- fixed duration,
- random range,
- full-clip duration,
- per-asset overrides.

Initial installation default:

- fade in: ~2.5 sec
- foreground active: 20–45 sec or full clip
- fade out: ~3 sec
- gap: 0.5–2 sec

## 8.3 Surface Eligibility

Surfaces may be:

- ambient only
- foreground eligible
- disabled
- members of groups

## 8.4 Asset Eligibility

Media may be:
- enabled/disabled,
- tagged,
- included/excluded by playlist,
- restricted to certain surfaces/groups later.

## 8.5 Future Scheduling

Design the scheduler so future modes can be added:

- timeline
- fixed sequence
- time-of-day
- calendar-based
- event-triggered
- weighted random
- rule-based
- synchronized multi-surface scenes

Do not implement all of those in v1. Preserve extensibility.

---

# 9. Runtime State and Queue Preview

This is important.

The Runtime page should make the show understandable at a glance.

Show:

- whether output is live,
- elapsed runtime,
- current active foreground surface,
- current media asset,
- time remaining,
- fade state,
- next several surfaces,
- next several media assets,
- scheduler mode,
- ambient status,
- FPS,
- dropped frames,
- decode health,
- canvas resolution,
- connected web clients,
- system CPU/RAM/temp,
- application log summary.

Example:

```text
LIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Current
Surface: Screen 4
Media: Snowy Village
State: Playing
Remaining: 00:18
Transition: 100%

Up Next

1. Screen 1   • Fireplace
2. Screen 7   • Carolers
3. Screen 3   • Toy Shop
4. Screen 6   • Winter Train

Scheduler
Mode: Shuffle Bag
Surfaces remaining in bag: 3 / 7
Media remaining in bag: 8 / 12
```

The queue preview does not need to be mathematically immutable if configuration changes. It should represent the scheduler's current planned sequence.

Provide controls:

- Pause
- Resume
- Skip current
- Fade out now
- Blackout
- Restore output
- Play specific media
- Activate specific surface
- Restart show
- Reload configuration

Manual overrides must return gracefully to automatic scheduling.

---

# 10. Web UI Information Architecture

Primary navigation:

1. Dashboard
2. Runtime
3. Mapping
4. Surfaces
5. Projectors
6. Media
7. Ambient
8. Show
9. Hardware
10. System

On mobile, use a drawer/bottom-friendly navigation.

---

# 11. Dashboard

Purpose:
quick installation health.

Show:

- Project name
- Output status
- Show status
- number of configured projectors
- number of enabled surfaces
- media asset count
- active ambient profile(s)
- current foreground content
- system health
- warnings

Quick actions:

- Start Show
- Stop Show
- Blackout
- Open Runtime
- Open Mapping
- Test All Surfaces

Warnings should be visible but not obnoxious.

Examples:

- media file missing
- unmapped surface
- projector viewport overlaps incorrectly
- output resolution mismatch
- renderer stopped
- high temperature
- dropped frames

---

# 12. Projector Configuration UI

Projectors page should visually display the Output Canvas.

Example:

```text
Output Canvas 3840x2160

┌───────────────────┬───────────────────┐
│ Projector A       │ Projector B       │
│ 1920x1080         │ 1920x1080         │
├───────────────────┼───────────────────┤
│ Projector C       │ Projector D       │
│ 1920x1080         │ 1920x1080         │
└───────────────────┴───────────────────┘
```

Features:

- Add Projector
- Delete
- Duplicate
- Rename
- drag/resize viewport
- enter exact numeric values
- apply layout preset
- test selected projector
- display:
  - white,
  - black,
  - color,
  - numbered grid,
  - border,
  - resolution label.

The software must not assume external video-wall controller output ordering.

Use a projector identification test:

```text
PROJECTOR A
TOP LEFT
1920 x 1080
```

Large readable text.

---

# 13. Surface Configuration UI

Surface list should show:

- name
- assigned projector
- enabled
- logical aspect ratio
- ambient profile
- foreground enabled
- tags
- mapping status

Surface editor should provide:

- name
- logical dimensions
- projector assignment
- tags
- foreground eligibility
- ambient profile
- mapping controls
- preview

Provide duplicate surface.

---

# 14. Mapping / Calibration UI

This is one of the highest-priority UX features.

The calibration UI should be usable while standing outdoors with a phone or laptop.

## 14.1 Workflow

1. Select projector.
2. Select surface.
3. Put output into calibration mode.
4. The selected surface renders a visible test pattern.
5. All other output may optionally be blacked out.
6. User drags four corner points in browser.
7. Projection updates live.
8. Save.
9. Select next surface.

## 14.2 Calibration Pattern

Provide:

- border
- corner markers
- center crosshair
- grid
- surface name
- logical resolution
- projector name
- optional checkerboard

Example projected pattern:

```text
┌───────────────────────────┐
│ +                     +   │
│                           │
│         SCREEN 4          │
│          1080x1080        │
│             +             │
│                           │
│ +                     +   │
└───────────────────────────┘
```

## 14.3 Browser Interaction

The browser preview should show the projector viewport and surface quadrilateral.

Support:

- drag corners,
- arrow-key nudging on desktop,
- optional numeric coordinate fields,
- reset,
- undo,
- revert to saved,
- save.

On touch:
- large draggable handles,
- pinch/zoom of the preview if necessary,
- avoid tiny targets.

## 14.4 Live Update

Calibration changes should be sent through WebSocket or equivalent low-latency channel.

Do not require pressing Save after every movement to see projector changes.

"Save" commits persistent configuration.

---

# 15. Media Library UI

Features:

- scan/import media folders
- thumbnail generation
- metadata inspection
- enable/disable
- rename display name
- tags
- preview
- duration
- resolution
- codec
- FPS
- file path
- warnings

Allow filtering by:
- tags,
- type,
- enabled,
- playlist.

Media normalization should be a separate optional tool.

---

# 16. Media Preparation Tool

Provide a command-line utility and, if practical, a simple UI workflow to normalize source material.

Desired canonical format for the first installation:

- MP4
- H.264
- 1080x1080
- 30 fps
- yuv420p
- no audio

The conversion tool should support:

- center square crop,
- left/right crop bias,
- manual crop position,
- optional trimming,
- removal of audio,
- transcode.

Example CLI:

```bash
projection-show media normalize input.mp4 \
  --size 1080x1080 \
  --crop center \
  --fps 30 \
  --no-audio
```

Do not make normalized media mandatory. The renderer should handle reasonable input media.

Normalization is for reliability and consistency.

---

# 17. Ambient System

Ambient visuals are reusable low-priority backgrounds.

## Required v1 ambient modes

### None

Black background.

### Solid Color

Configurable:
- RGB/hex
- opacity

### Snowfall

Configurable:
- density
- speed range
- size range
- opacity
- drift
- softness
- direction
- random seed

### Generic Particles

Configurable:
- count
- direction
- velocity
- size
- opacity
- shape

### Image

Static image with:
- fit mode,
- opacity.

### Looping Video

Looping video with:
- fit mode,
- opacity,
- mute.

## Foreground Interaction

Each ambient profile should specify behavior while foreground content is active:

- remain unchanged,
- fade down,
- fade out,
- pause,
- continue behind foreground.

---

# 18. Show Configuration UI

Use intuitive sections.

## General

- Enabled
- Auto-start
- Scheduler mode
- Max simultaneous foreground surfaces

## Surface Selection

- Included surfaces
- Included tags
- Excluded tags
- shuffle behavior

## Media Selection

- Playlist
- tags
- shuffle behavior

## Timing

- fade in
- foreground duration mode
- min/max duration
- fade out
- min/max gap

## Ambient Interaction

- keep
- dim
- hide

## Advanced

- random seed
- logging verbosity
- skip unavailable media
- fallback behavior

Provide live summaries in plain English.

Example:

> Play one foreground clip at a time across surfaces tagged "main-screen". Visit every eligible surface once before reshuffling. Choose media from "Classic Scenes" the same way. Fade in over 2.5 seconds, play 20–45 seconds, fade out over 3 seconds, then wait 0.5–2 seconds.

This summary is valuable for preventing configuration mistakes.

---

# 19. Manual Control

Provide a Manual Control panel.

Functions:

- select surface
- select media
- play
- stop
- fade in
- fade out
- set surface black
- enable ambient
- disable ambient
- test all surfaces
- blackout all
- restore automatic show

Manual actions should not corrupt the scheduler.

---

# 20. Blackout

Blackout must be a first-class feature.

A blackout command should immediately:

- fade or cut foreground to black,
- suppress ambient visuals,
- maintain renderer process.

Provide:
- immediate blackout,
- graceful fade blackout,
- restore previous state.

Use a prominent but confirmation-safe UI control.

---

# 21. Hardware Adapter Layer

External hardware should be represented through adapters.

Do not intertwine hardware logic with the renderer.

Example interface:

```python
class HardwareAdapter:
    async def initialize(self): ...
    async def shutdown(self): ...
    async def health(self): ...
```

Potential adapters:

- IR projector wake controller
- RS-232 video-wall controller
- GPIO relay
- smart plug
- lighting controller

## Initial Placeholder Adapters

Implement configuration structure and a mock adapter.

Example:

```yaml
hardware:
  adapters:
    - id: wall-controller
      type: rs232
      enabled: false
      config:
        device: /dev/ttyUSB0
        baud: 115200
```

The first release does not need to fully automate OREI control unless straightforward.

Keep it ready.

---

# 22. OREI UHD-14VW Integration Notes

The initial installation uses the OREI UHD-14VW.

Do not make this a hard-coded dependency.

Represent it as an optional adapter.

Desired eventual startup behavior:

- power on controller,
- select HDMI input,
- set 2x2 mode,
- select 1080p60 outputs,
- configure expected EDID/input mode,
- optionally mute audio.

Use a USB-to-RS232 adapter or proper RS232 level converter.

Do not connect Raspberry Pi TTL UART directly to RS-232 signaling.

---

# 23. Projector IR Integration Notes

The installation will have an external IR emitter box controlled by the Raspberry Pi.

It supports individually addressable projector IR emitters.

Treat this as a future hardware adapter.

Desired eventual actions:

- Wake All
- Wake Selected Projector
- Power Off Selected Projector
- Power Off All
- resend command
- test emitter

The projection application should not assume IR is available.

---

# 24. Startup Sequence

Implement a startup state machine.

Suggested flow:

```text
Application start
      ↓
Load configuration
      ↓
Validate configuration
      ↓
Initialize renderer
      ↓
Open black fullscreen canvas
      ↓
Initialize hardware adapters
      ↓
Optional hardware setup
      ↓
Optional projector wake
      ↓
Wait configured warmup duration
      ↓
Initialize ambient layers
      ↓
Start scheduler
      ↓
RUNNING
```

Every step should:
- log success/failure,
- expose state to the web UI.

If optional hardware fails:
- warn,
- continue when safe.

---

# 25. Shutdown Sequence

Suggested flow:

```text
Stop scheduler
      ↓
Fade to black
      ↓
Optional projector shutdown commands
      ↓
Stop renderer
      ↓
Close hardware adapters
      ↓
Exit
```

Provide configurable behavior.

---

# 26. Crash Recovery

Run under systemd.

Suggested service settings:

```ini
Restart=always
RestartSec=3
```

The app should:
- write config atomically,
- never leave a partially written project file,
- rebuild runtime state from saved configuration after restart.

Transient scheduler position does not need to persist in v1.

---

# 27. Logging

Use structured logging.

Log:

- startup
- configuration load
- validation warnings
- media scan
- render initialization
- scheduler choices
- foreground changes
- manual overrides
- dropped frames
- decoder errors
- web/API errors
- hardware actions
- shutdown

UI should show:
- recent events,
- warnings,
- errors.

Provide downloadable logs.

Do not spam logs every frame.

---

# 28. Diagnostics

System page should show:

- application version
- uptime
- renderer status
- render FPS
- target FPS
- dropped frames
- current canvas resolution
- CPU usage
- RAM usage
- Pi temperature
- disk usage
- media folder availability
- web server status
- hardware adapter health

Provide:
- restart application
- reboot Pi
- shutdown Pi

Dangerous system actions should require confirmation.

---

# 29. API

Use REST for configuration and commands.

Use WebSocket or SSE for live runtime updates.

Representative endpoints:

```text
GET    /api/status
GET    /api/project
PUT    /api/project

GET    /api/projectors
POST   /api/projectors
PUT    /api/projectors/{id}
DELETE /api/projectors/{id}

GET    /api/surfaces
POST   /api/surfaces
PUT    /api/surfaces/{id}
DELETE /api/surfaces/{id}

GET    /api/media
POST   /api/media/rescan

GET    /api/ambient
GET    /api/show

POST   /api/runtime/start
POST   /api/runtime/pause
POST   /api/runtime/resume
POST   /api/runtime/skip
POST   /api/runtime/blackout
POST   /api/runtime/restore

POST   /api/manual/play

POST   /api/mapping/preview
POST   /api/mapping/save

WS     /api/live
```

Exact path design may vary.

Document API using OpenAPI.

---

# 30. Configuration Validation

Validate on load and save.

Examples:

- duplicate IDs
- missing projector references
- invalid quadrilateral coordinates
- surface outside viewport
- missing ambient profile
- missing playlist
- missing media file
- invalid timing range
- unsupported media
- impossible canvas values

Warnings should distinguish:
- fatal errors,
- non-fatal warnings.

---

# 31. Project Files

Use a project directory structure like:

```text
projects/
  main-christmas/
    project.yaml

    media/
      foreground/
      ambient/

    thumbnails/

    cache/

    logs/
```

Application-wide settings may live separately.

Do not bury user project configuration inside a package directory.

---

# 32. Multiple Projects

Support multiple saved projects.

UI should allow:

- create project
- rename
- duplicate
- archive/delete
- switch active project

Only one project needs to render at a time.

Switching project while live should require stopping or safely transitioning the current show.

---

# 33. Initial Default Project

Include a generic demo project.

Example:
- canvas 1920x1080
- one projector
- three mapped demo surfaces
- generic particles ambient
- simple color/image assets

Do not ship a Christmas-specific default.

---

# 34. Initial Installation Preset

Optionally provide a preset generator for:

- 3840x2160 canvas
- 2x2 projector layout
- four projectors at 1920x1080

This is a convenience preset only.

The application must still support arbitrary configurations.

---

# 35. Performance Expectations

Target hardware:
Raspberry Pi 5.

Initial target workload:

- 3840x2160 master canvas
- 60 Hz output desired
- up to four projector viewports
- at least seven mapped surfaces
- procedural ambient visuals on all surfaces
- one simultaneous 1080x1080 H.264 30fps foreground video
- responsive web UI

Goals:

- no obvious stutter
- stable memory usage
- no continuous growth/leak
- calibration changes visible within roughly 100 ms to 250 ms on LAN
- UI runtime state update at least once per second
- preferably 5–10 updates/sec for transitions/status

Gracefully lower internal render rates if necessary while preserving smooth video.

Measure rather than assume.

---

# 36. Security Model

This is a local-LAN appliance.

Initial security can be simple.

Requirements:

- bind web interface to configurable address
- optional simple authentication
- no cloud dependency
- no external telemetry by default
- no internet dependency after installation
- sanitize file paths
- prevent arbitrary command execution from API
- protect reboot/shutdown endpoints

---

# 37. User Experience Details

The application should feel polished.

## Good empty states

Example:

> No surfaces yet. Add a surface, assign it to a projector, then map its four corners.

## Helpful warnings

Example:

> Screen 4 references ambient profile "subtle-snow", but that profile no longer exists.

## Immediate visual feedback

When editing:
- show dirty state,
- show saved confirmation,
- avoid ambiguous autosave unless intentionally implemented.

## Responsive controls

Phone calibration must be genuinely usable.

---

# 38. Visual Style

Aim for:

- dark UI by default,
- high contrast,
- minimal visual noise,
- modern control-panel aesthetic,
- rounded cards,
- readable typography,
- restrained color.

Status colors:

- green: healthy/running
- amber: warning
- red: fault/blackout/error
- blue or neutral accent: editable/configuration

Do not overuse gradients or flashy effects.

Projection shows are visually loud enough. The control UI should be calm.

---

# 39. Runtime Page Detailed Mockup

Approximate structure:

```text
┌──────────────────────────────────────────────────────────────┐
│ Projection Show Engine                         ● LIVE        │
├──────────────────────────────────────────────────────────────┤
│ Current                                                      │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Surface: Screen 4                                       │ │
│ │ Media: Snowy Village                                    │ │
│ │ State: Playing                         00:18 remaining    │ │
│ │ ████████████████████████──────────────                 │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ Up Next                                                      │
│  1  Screen 1      Fireplace                                 │
│  2  Screen 7      Carolers                                  │
│  3  Screen 3      Toy Shop                                  │
│  4  Screen 6      Winter Train                              │
│                                                              │
│ Surfaces                                                     │
│ [1 snow] [2 snow] [3 snow] [4 LIVE] [5 snow] [6 snow] [7]  │
│                                                              │
│ Scheduler                                                    │
│ Shuffle Bag                                                  │
│ Surfaces remaining: 3/7                                      │
│ Media remaining: 8/12                                        │
│                                                              │
│ [Pause] [Skip] [Fade Out] [Blackout]                         │
└──────────────────────────────────────────────────────────────┘
```

Surface chips/cards should indicate:
- ambient
- foreground
- disabled
- manual override
- error

---

# 40. Mapping Page Detailed Mockup

```text
┌────────────────────────────────────────────────────────────┐
│ Mapping                                                    │
├─────────────┬──────────────────────────────────────────────┤
│ Projectors  │                                              │
│             │   Projector A                                │
│ A           │                                              │
│ B           │     ●──────────────────●                     │
│ C           │     │                  │                     │
│ D           │     │     Screen 1     │                     │
│             │     │                  │                     │
│ Surfaces    │     ●──────────────────●                     │
│             │                                              │
│ Screen 1    │                                              │
│ Screen 2    │                                              │
│ Screen 3    │                                              │
│             │                                              │
├─────────────┴──────────────────────────────────────────────┤
│ [Grid] [White] [Black Others] [Reset] [Save Mapping]      │
└────────────────────────────────────────────────────────────┘
```

On mobile:
- surface selector at top,
- preview full width,
- controls below.

---

# 41. Testing Strategy

## Unit Tests

Test:

- config validation
- shuffle bag
- no immediate repeat logic
- scheduler timing
- project serialization
- surface selection
- playlist filtering
- transition interpolation
- hardware adapter mocks

## Integration Tests

Test:

- API CRUD
- project load/save
- runtime start/pause/skip
- WebSocket state updates
- media scan
- calibration update path

## Renderer Tests

Provide deterministic visual test scenes.

Examples:

- solid surface colors
- grid
- perspective warp
- alpha fade
- overlapping surfaces
- projector viewport boundaries

When possible, support headless/offscreen render tests.

## Pi Hardware Test

Create a commissioning checklist:
- boot
- fullscreen
- 4K canvas
- sustained playback
- web control
- mapping latency
- thermal stability
- restart recovery.

---

# 42. Development Modes

Provide:

## Desktop Development Mode

Run on macOS/Linux without projectors.

Show render canvas in a window.

This lets development happen comfortably before Pi deployment.

## Pi Production Mode

- fullscreen
- hidden cursor
- no desktop chrome
- service-managed
- optimized rendering.

## Simulator Mode

Very useful.

Render the output canvas into a browser or desktop preview so the seven-screen show can be tested without physical projectors.

---

# 43. CLI

Provide useful CLI commands.

Example:

```bash
projection-show run
projection-show run --project main-christmas
projection-show validate
projection-show media scan
projection-show media normalize input.mp4
projection-show test-pattern
projection-show version
```

Exact command name may differ.

---

# 44. Installation

Provide an install script or documented process for Raspberry Pi OS.

Target experience:

```bash
git clone ...
cd projection-show
./install.sh
```

Installer should:

- create virtual environment
- install dependencies
- build frontend
- create runtime directories
- optionally install systemd service
- explain required permissions
- optionally enable autostart

Do not silently change unrelated Pi configuration.

---

# 45. systemd Integration

Provide a service template.

Requirements:

- start after network and graphical/display target as necessary
- restart on failure
- log to journal
- configurable environment file
- clean shutdown

Example concept:

```ini
[Service]
ExecStart=/opt/projection-show/bin/projection-show run
Restart=always
RestartSec=3
```

Exact implementation depends on renderer/display stack.

---

# 46. Pi Display Handling

The application must document how the Pi should be configured for the desired output canvas.

Initial expected canvas:

- 3840x2160
- 60 Hz when supported by the full HDMI chain

The application should expose the actual detected output resolution.

If actual resolution differs from project configuration:
- warn clearly,
- do not silently distort mappings.

---

# 47. Rendering Fit Modes

Foreground and ambient image/video sources should support:

- cover
- contain
- stretch
- native
- configurable crop focal point

For the initial square-screen installation:
- most foreground assets will already be 1:1,
- default should be cover.

---

# 48. Crop / Focal Point Metadata

Support a normalized focal point:

```yaml
focal_point:
  x: 0.62
  y: 0.50
```

This allows smart positioning of non-square source media.

UI should permit dragging the focal point on a thumbnail.

---

# 49. State Machine

Model runtime states explicitly.

Suggested states:

- STARTING
- READY
- RUNNING
- PAUSED
- MANUAL_OVERRIDE
- BLACKOUT
- ERROR
- STOPPING

Surface states:

- DISABLED
- AMBIENT
- FADING_IN
- FOREGROUND
- FADING_OUT
- MANUAL
- ERROR

Expose states through API.

---

# 50. Scheduler Queue Model

Maintain a planned queue.

Example:

```python
[
  Cue(surface_id="screen-4", asset_id="snowy-village"),
  Cue(surface_id="screen-1", asset_id="fireplace"),
  Cue(surface_id="screen-7", asset_id="carolers"),
]
```

Keep enough queued items for runtime preview, e.g. 5–10.

If configuration changes:
- invalidate and rebuild future queue safely,
- do not necessarily interrupt current cue.

---

# 51. Cue Model

A Cue should be generic.

Fields might include:

```yaml
surface_id: screen-4
asset_id: snowy-village
fade_in_seconds: 2.5
hold_seconds: 30
fade_out_seconds: 3
```

Future cues may target:
- multiple surfaces,
- ambient changes,
- hardware commands.

Design for extension without implementing all features now.

---

# 52. Configuration Editing Behavior

Prefer edit-copy-apply semantics for risky runtime changes.

Example:
- mapping changes preview live,
- Save Mapping persists.

For normal metadata:
- saving a form can apply immediately.

Avoid accidentally restarting the entire renderer on every field change.

---

# 53. Versioned Configuration

Add a schema version.

Example:

```yaml
schema_version: 1
```

Implement migration hooks.

Future software updates should not strand old project files.

---

# 54. Backup / Export

UI should support:

- Export Project
- Import Project
- Backup configuration

A project export should include:
- project config
- optional media metadata
- optionally media files

Use a ZIP format if convenient.

---

# 55. First Installation Configuration

Create documentation demonstrating how the first real project should be represented.

Example:

```text
Project: Main Christmas Screens

Canvas:
3840x2160 @ 60

Projectors:
A: 0,0,1920,1080
B: 1920,0,1920,1080
C: 0,1080,1920,1080
D: 1920,1080,1920,1080

Surfaces:
7
Each mapped to one projector
Logical size 1080x1080

Ambient:
Subtle Snow

Foreground:
Classic Scenes playlist

Scheduler:
one foreground surface at a time
shuffle-bag surfaces
shuffle-bag media
2.5 sec fade in
20-45 sec hold
3 sec fade out
0.5-2 sec gap
```

Do not hard-code this.

---

# 56. MVP Scope

Build the MVP in this order.

## Milestone 1: Skeleton

- repository structure
- backend starts
- frontend starts
- project config model
- basic dashboard

## Milestone 2: Renderer

- fullscreen/windowed canvas
- projector viewport model
- surface model
- solid-color mapped surfaces
- four-corner homography
- test patterns

## Milestone 3: Web Mapping

- projector management
- surface management
- mapping UI
- live corner updates
- save/reload

## Milestone 4: Ambient

- none
- solid color
- snowfall
- generic particles

## Milestone 5: Media

- scan media
- video decode
- image support
- surface playback
- transitions

## Milestone 6: Scheduler

- playlists
- shuffle bags
- timing
- fades
- gaps
- queue preview

## Milestone 7: Runtime UI

- current cue
- next cues
- surface states
- pause
- skip
- blackout
- manual controls

## Milestone 8: Reliability

- systemd
- clean startup
- recovery
- diagnostics
- logs

## Milestone 9: Hardware Adapter Framework

- generic adapter API
- mock adapter
- placeholders/config for RS232/IR

Do not block the MVP on external hardware control.

---

# 57. Prototype Zero

Before building full video support, create a very small end-to-end prototype.

Requirements:

- 3840x2160 or configurable canvas
- seven configurable demo surfaces
- procedural ambient particles
- scheduler activates one surface at a time
- foreground is initially just a solid color
- fade in
- hold
- fade out
- queue preview in web UI

This proves:
- renderer
- scheduler
- UI
- live state
- configuration.

Then replace foreground color with actual media.

---

# 58. Acceptance Criteria for MVP

The MVP is complete when a user can:

1. Open the web UI.
2. Create a new project.
3. Configure canvas resolution.
4. Add arbitrary projectors.
5. Position/size projector viewports.
6. Add arbitrary surfaces.
7. Assign surfaces to projectors.
8. Map each surface using four draggable corners.
9. Save mapping.
10. Define ambient visual per surface.
11. Add/index video media.
12. Create a playlist.
13. Configure shuffle-bag scheduling.
14. Start show.
15. See one or more configured foreground cues play correctly.
16. Observe ambient visuals on inactive surfaces.
17. See current and upcoming cues in Runtime view.
18. Pause.
19. Skip.
20. Blackout.
21. Restore output.
22. Restart the application and retain configuration.
23. Run the show automatically after reboot using systemd.
24. Use the UI from a phone on the same LAN.
25. Run without a locally connected keyboard/mouse.

---

# 59. Out of Scope for Initial MVP

Do not let these derail the build:

- 3D mesh mapping
- camera-based automatic calibration
- edge blending
- projector color matching
- multi-machine synchronization
- DMX
- audio synchronization
- complex timeline authoring
- cloud services
- mobile native app
- computer vision
- AI-generated media
- arbitrary shader authoring UI

Preserve architectural room for future work.

---

# 60. Future Features

Likely useful later:

- multi-surface synchronized scenes
- cue timeline
- time-of-day scheduling
- multiple independent show zones
- hardware command cues
- RS232 projector/controller presets
- IR control
- OSC
- MQTT
- DMX/Art-Net
- audio
- remote health monitoring
- auto calibration
- polygon/mesh surfaces
- edge blend
- color calibration
- content effects/shaders
- transition library
- browser preview stream
- show recording
- scene templates
- project-level reusable presets.

---

# 61. Code Quality Requirements

Use:

- clear modules
- type hints
- meaningful names
- docstrings where useful
- tests
- formatting/linting
- no giant god classes
- no business logic inside React components
- no direct renderer mutation from arbitrary API code
- no global mutable config state without a clear owner

Prefer simple explicit architecture over clever abstractions.

---

# 62. Repository Structure

A reasonable starting point:

```text
projection-show/
  README.md
  pyproject.toml

  backend/
    app/
      api/
      config/
      runtime/
      scheduler/
      media/
      render/
      mapping/
      ambient/
      hardware/
      diagnostics/

  frontend/
    src/
      components/
      pages/
      hooks/
      api/
      state/

  projects/
    demo/

  scripts/

  tests/

  deploy/
    systemd/
```

Adjust if a better structure emerges.

---

# 63. Documentation Requirements

Write:

1. README
2. Raspberry Pi install guide
3. Desktop development guide
4. Project configuration guide
5. Mapping/calibration guide
6. Media preparation guide
7. Troubleshooting guide
8. Architecture overview

Do not leave setup knowledge only in chat or code comments.

---

# 64. Implementation Instructions to GPT-5.6 Sol

You are responsible for implementing this application, not merely proposing an architecture.

Work incrementally.

For each milestone:

1. Inspect the existing repository first.
2. State the concrete implementation plan briefly.
3. Implement working code.
4. Run tests/builds.
5. Fix failures.
6. Update documentation.
7. Leave the repository in a runnable state.
8. Summarize:
   - what changed,
   - how to run it,
   - known limitations,
   - what should be built next.

Do not repeatedly ask the user questions when a safe, reversible implementation choice can be made.

Prefer sensible defaults.

When a choice materially affects hardware compatibility, configuration format, or future architecture, explain it before committing to a difficult-to-reverse direction.

Do not stop at mockups.

Do not create fake UI controls that are not connected to functionality unless clearly labeled as unavailable.

Keep the application runnable throughout development.

---

# 65. First Task for the Implementation Agent

Start with Milestones 1 and 2 plus Prototype Zero.

Deliver:

- repository skeleton,
- backend,
- frontend,
- config model,
- configurable canvas,
- configurable projector viewports,
- configurable four-corner surfaces,
- GPU-rendered test surfaces,
- procedural particle ambient background,
- simple scheduler,
- solid-color foreground cue,
- fade transitions,
- live Runtime page,
- queue preview,
- desktop development mode.

Create a demo project through configuration, not hard-coded data.

The first demo should prove that the architecture works without requiring projectors or Raspberry Pi hardware.

After this works cleanly on desktop, proceed to live mapping and real video playback.

---

# 66. Guiding Product Vision

The finished product should make projection mapping feel less like specialized event-production software and more like configuring a reliable appliance.

A technically capable user should be able to:

1. define the outputs,
2. add surfaces,
3. drag them into alignment,
4. choose ambient visuals,
5. add media,
6. describe show behavior,
7. press Start,
8. walk away.

The implementation should optimize for that experience.
