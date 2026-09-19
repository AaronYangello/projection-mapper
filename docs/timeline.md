# Timeline authoring and schema v2

The engine keeps both show definitions. **Show → Shuffle / Timeline** chooses an editor;
it never changes live mode. Stop playback and press **Use this mode** to activate a saved
definition. Shuffle keeps its existing cue fades, queue, seed and tag selectors.

## Source preparation

Use your ordinary video editor for cutting, titles, grading, speed, effects, transitions,
and audio mixing. Export one finished video stem per media surface, ideally starting at
the same time zero. Use progressive constant-frame-rate 30 fps, square pixels, SDR Rec.709,
H.264/yuv420p MP4. Match the surface's logical aspect ratio. Four concurrent atlas slots
share the output pixels: each gets 960×540; a single slot gets 1920×1080, two get 960×1080.
Keep full-resolution masters outside the generated cache. The compiler applies saved
fit/focal settings, then scales logical surface content into its atlas slot.

Export one finished stereo 48 kHz WAV audio stem. Video-embedded audio is ignored;
select the separate audio source in the Master audio lane. Complex mixing belongs in
the third-party editor. Alpha images, HDR conversion, and rotation-metadata correction
are not implemented; flatten/convert/orient exports in the editor first.

In Media, stop playback, upload or copy sources under `media/`, **Scan folder**, then
**Add to show**. Upload and selection never start playback or insert timeline clips.

## Authoring

1. Configure stable projector/surface IDs in Project; use Mapping for physical corners.
   Existing surfaces have role, shape, fixed light color, logical size and projector controls.
   Adding/removing topology still uses the complete JSON editor or YAML while stopped.
2. Open Show → Timeline. Set total duration and loop behavior. One lane appears per
   enabled mapped surface. Projector headers collapse. Up/down moves stay in that group;
   `track_order` stores surface IDs and does not change projector assignment or drawing order.
3. Select a media surface, choose a source, enter absolute Start, Source in and Duration,
   then Add clip. Select a block to apply numeric changes, duplicate after it, or delete it.
   Drag to move with the chosen snap increment. Overlaps on the same surface are rejected;
   clips on different surfaces may overlap. There is no ripple or split operation.
4. Use the independent Surface opacity curve. Drag a point, use arrow keys, or select it
   and apply exact time/value/interpolation fields. Fade in/out inserts a three-second
   ramp at Edit time (shortened at the show end). Set visible/dark replaces the whole curve.
   The default is 1; an untracked lighting surface is dark until a track is created.
5. Select one audio source and apply its timing fields. Audio start/source-in/duration
   affect the mux; volume/mute/sync offset remain runtime metadata.
6. Save timeline while stopped. Drafts survive navigation; remote revision changes retain
   your draft and block stale saves. Browser unload is guarded. Build uses only saved data.
7. On desktop, Build → Preview built show → Start show plays synchronized compiled video
   and audio. Stop → Unload preview returns to editing; preview never activates a deployment
   pointer. A raw timeline without audio can preview sources directly via PyAV. Audio-bearing
   timelines require the compiled preview, avoiding an unsynchronized silent approximation.

The horizontal scroll area pans absolute time; Zoom changes scale. The ruler selects edit
time and seeks the saved live timeline when no draft is pending. Playback's seek bar also
uses the server clock. Phone authoring is an overview; runtime, blackout, mapping, upload,
and deployment controls remain available. Desktop/tablet provides the full editor.

## Exact storage and migration

Disk is schema **2**. `config/migrations.py` explicitly deep-copies v1 to v2 on load;
it does not rewrite the original file. The next explicit save writes v2 and retains the
validated old file in `project.yaml.bak`. Unknown versions and v2-only fields in a v1
document fail. IDs, paths, mappings, scenes, and shuffle settings survive migration.

Shuffle fields remain directly under `show`, avoiding unnecessary churn to the existing
API/editor. `max_simultaneous: 1` applies to shuffle only. Timeline capacity is validated
against a named build profile, not this field. A new v1 migration receives an empty,
60-second, non-looping timeline. Both definitions round-trip together.

```yaml
schema_version: 2
# canvas, projectors, surfaces, scenes, and ambient_profiles omitted here
show:
  mode: timeline
  auto_start: false
  max_simultaneous: 1       # shuffle only
  fade_in_seconds: 2.5     # existing shuffle fields remain here
  timeline:
    duration_seconds: 12
    loop: true
    track_order: [video-1, light-1]
    tracks:
      - id: program-1
        surface_id: video-1
        clips:
          - id: stem-1
            scene_id: video-source
            start_seconds: 0
            source_in_seconds: 0
            duration_seconds: 12
        opacity:
          default: 0
          keyframes:
            - {time_seconds: 0, value: 0, interpolation: linear}
            - {time_seconds: 3, value: 1, interpolation: hold}
      - id: light-track
        surface_id: light-1
        opacity: {default: 0.5, keyframes: []}
    audio:
      scene_id: master-audio
      start_seconds: 0
      source_in_seconds: 0
      duration_seconds: 12
      volume: 1
      muted: false
      sync_offset_ms: 0
```

A lighting surface is an ordinary mapped surface with `role: lighting`,
`shape: rectangle | circle`, and `light: {color: '#ffcc88'}`. Media defaults to
`role: media, shape: rectangle`. Lighting has no media clips or decoder. Its `light`
definition and track automation are separate, leaving future color automation room
without changing clip timing. Fixed colors are the only current color channel.

Timings are finite, non-negative, and bounded to 24 hours; positive clip/audio durations
must fit the show. Clip IDs are unique across the show; track IDs and destinations are
unique. References must resolve to enabled compatible surfaces/scenes/projectors. Trims
apply to video/audio, not images/colors. Saves check indexed source ranges; builds re-probe
and hash actual sources. Timeline mode ignores a scene's shuffle trim/end-behavior settings.

## Opacity and transport semantics

At times before the first key, use `default`. At a key use its exact value. Its interpolation
governs the interval *leaving* that key: `linear` blends to the next value; `hold` keeps the
current value until the next key. After the final key, hold its value. Missing automation
defaults to fully visible. Values are 0–1 and keys are strictly increasing within duration.

```text
content → shape mask → surface opacity → homography → alpha composition → master output
```

Clips occupy `[start, end)`. Opacity continues across boundaries and empty spans. Empty
media spans draw nothing; lighting keeps following its curve. Circle masks use logical
pixel aspect and discard their exterior, preserving content beneath. Lights draw directly;
only a small 64×64 calibration target is retained. Project surface array order controls
composition when mapped surfaces overlap; lane ordering is an authoring preference.

Pause freezes pipeline and timeline. Seek sets absolute time and invalidates old decoder
generations. Resume continues; starting after a completed non-looping show returns to zero.
Stop resets to zero and darkens timeline surfaces. Blackout clears output and pauses the
pipeline without destroying transport; Restore returns to the previous state. At a
non-looping end media is dark, lights hold their evaluated end value, and transport pauses.
Loop uses GStreamer segment seeking where supported; visible/audible seam quality requires
physical measurement. Test patterns replace pixels while the show clock continues.

Diagnostics → Audio on this machine stores local sink/device and optional volume/mute/offset
overrides. Blank overrides use bundle settings. Apply is explicit; changing routing requires
stopped playback. Positive offset delays audio to compensate projector latency; range is
−1000…+1000 ms. This is device compensation, not an alternative show clock.
