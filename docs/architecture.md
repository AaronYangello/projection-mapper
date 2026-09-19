# Architecture and ownership

The generic projection engine keeps installation topology in project configuration. Named
build profiles constrain a destination; the Pi 4 profile is not a global model limit.
The original specification remains the product foundation; timeline/build/deploy extends
its earlier scope. The implementation record separates desktop evidence from hardware gates.

```text
project.yaml → explicit v1→v2 migration → strict Pydantic model
                                      → Runtime owner (API event-loop thread)
REST commands / WebSocket status       ├─ ShuffleController → Scheduler / Cue
                                      ├─ TimelineController → clock / ActiveLayer[]
                                      └─ copied plain-data bridge → GL main thread
                          GStreamer worker → latest frame / clock / diagnostics ─┘
Browser JPEG preview ← capture bridge ← native master framebuffer

Saved project snapshot → build worker / shared CLI compiler → validated .pshow
Bounded streamed upload → stage / hash / probe / bind IDs → atomic active+previous record
```

## Domain and runtime

`config/` owns strict schema-v2 models, explicit migration and atomic YAML persistence.
Both definitions survive mode changes. Existing shuffle fields stay flat under `show`;
`show.timeline` owns clips, audio and independent surface opacity. Unknown versions fail.
See [model and transport semantics](timeline.md).

`timeline.py` is pure clock/layer evaluation plus a small controller protocol. The seeded
single-cue scheduler remains independent. Timeline intervals are half-open; opacity is
surface-level and continues through empty spans and clip boundaries. A deployed show binds
to a copied local project by stable surface ID; it never applies authoring calibration.

```diff
- renderer reads one current cue for every show
+ controller emits active surface layers
+ shuffle adapter preserves the existing cue path
+ timeline evaluates surface opacity against one authoritative clock
```

`runtime.py` alone owns mutable transport/project state. REST and ticks run on one event
loop. Full saves require stopped transport, matching revision, validation and durable save.
Geometry has a separate leased preview/save revision; mapping changes do not restart media.
Snapshots contain copied plain data; no HTTP worker touches GL objects.

Pause and blackout freeze the clock; blackout overrides every mode/pattern immediately on
the next render frame. Restore returns to prior transport. Stop resets timeline to zero;
shuffle retains its ambient behavior. Compiled playback uses pipeline position, not browser
or API wall time. Generation IDs reject stale positions after seek/stop/source replacement.
Decoder/audio faults pause explicitly. A compiled preview is visibly distinct from an
installed deployment; preview does not change the active pointer.

## Native graphics and media

`render/context.py` selects desktop GL 3.3/ModernGL or EGL/GLES 3.0 explicitly. The small
`render/gles.py` adapter isolates shader dialect and GPU resource operations; no platform
branches enter timeline/business logic. Actual driver/version/limits are reported; software
rasterizers and unsafe version overrides fail qualification. The adapter contract is tested
on desktop GL; a real Pi EGL/GLES context remains unverified.

The main thread owns every texture, framebuffer, shader and vertex array. Homography keeps
clip-space `w` for perspective-correct sampling. Local projector viewport and physical corners
remain independent of atlas UVs. Full-surface opacity follows shape masking; circle exterior
pixels discard instead of blackening lower content. Lights are direct primitives, with only
small calibration targets. Project surface order defines composition; editor row order does
not change projector assignment or physical layering.

Shuffle uses one PyAV worker/latest RGB frame and one native media texture. Raw silent
timeline preview uses a source pool. Compiled shows use one GStreamer playbin decoder,
bounded two-buffer appsink, one latest RGB frame and one GPU texture sampled by all atlas
surfaces. A dedicated worker handles native state/seek/audio calls, so pipeline control
cannot block GL blackout drawing. A worker heartbeat produces an explicit unresponsive
fault. No Python callbacks are installed on native streaming threads (a Mac lock/GIL
interaction was reproduced and removed during verification).

Audio sink/clock, selected decoder factories, PTS/position skew, stale/dropped frames and
host CPU/RAM/temperature/throttling are visible in Diagnostics. Missing metrics remain
unavailable. Mac hardware decode is measured; Pi hardware decode and HDMI are open gates.
RGB conversion/upload is not zero-copy. Segment seeking is attempted for loops; its physical
seam quality is not inferred from software tests.

## Compiler and services

`build/compiler.py` is reusable by CLI and API. It validates profiles/assets, hashes content,
packs deterministic reusable atlas slots, invokes FFmpeg with argument vectors, and publishes
only complete validated artifacts. Separate video/audio/metadata keys support video reuse,
audio-only remux and manifest-only updates. Physical mapping is excluded. A cancellable
per-project file lock serializes cache mutation. See [bundle and cache contracts](build-deploy.md).

`services.py` bounds job workers/history; hashing, scanning, probing, archive validation,
encoding and HTTP deployment are off the API event loop. Jobs survive browser disconnect;
requests/progress/results are serializable for a possible future worker, without distributed
orchestration now. Small settings and atomic pointer commits remain on the runtime owner to
close stop/revision races. Configuration upload and media installation remain stopped-only.

`storage.py` streams bounded uploads, detects hashes/collisions and extracts a strict archive
allowlist without trusting ZIP paths, MIME or metadata sizes. `deployments.py` validates
schema, checksums, media and compatible destination IDs before versioned extraction and one
atomic active+previous record. Failed work leaves the active show; startup revalidates active
and can recover the previous version stopped with a warning. Physical power-loss proof remains
separate from failure-injection tests.

`target.py` holds machine-local masked credentials, checks private origins, disables proxies
and redirects, streams upload and binds action-time confirmation to target/bundle/prior ID.
No shell-command API exists. Bearer auth and same-origin checks remain in `api.py`; deployment
writes additionally require configured application authorization. Tailnet access is separate.

## Frontend and boundaries

React/TypeScript presents authoritative status and explicit drafts. Show tabs never activate
implicitly. The focused `TimelineView` adapter uses domain data, accessible controls/numeric
alternatives and no library playback engine. Projector groups are derived, row order is saved,
and phone authoring is intentionally an overview. Runtime, mapping, uploads and deployment
remain usable on phone. Browser timing never controls native playback.

The system still does not include an NLE, remote Mac worker, multi-machine live sync,
external lighting protocols, mesh/edge blending, automatic project switching or boot service.
The next hardware milestone is [Pi commissioning](pi-commissioning.md), including the choice
whether the measured RGB copy path needs platform optimization.
