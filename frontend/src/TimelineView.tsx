/** Replaceable view adapter. It never owns playback or persists a UI-library shape. */
import { useRef, useState } from "react";
import type { Project, Timeline, Clip, OpacityKey } from "./types";
export function validateTimeline(t: Timeline) {
  if (!Number.isFinite(t.duration_seconds) || t.duration_seconds <= 0)
    throw new Error("Show duration must be positive.");
  const ids = new Set<string>();
  for (const track of t.tracks) {
    const clips = [...track.clips].sort(
      (a, b) => a.start_seconds - b.start_seconds,
    );
    for (let i = 0; i < clips.length; i++) {
      const c = clips[i];
      if (ids.has(c.id)) throw new Error("Duplicate clip ID.");
      ids.add(c.id);
      if (
        ![c.start_seconds, c.source_in_seconds, c.duration_seconds].every(
          Number.isFinite,
        ) ||
        c.start_seconds < 0 ||
        c.source_in_seconds < 0 ||
        c.duration_seconds <= 0 ||
        c.start_seconds + c.duration_seconds > t.duration_seconds + 1e-6
      )
        throw new Error(
          "Clip must have a positive duration and fit within the show.",
        );
      if (
        i &&
        clips[i - 1].start_seconds + clips[i - 1].duration_seconds >
          c.start_seconds + 1e-6
      )
        throw new Error("Clips cannot overlap on the same surface.");
    }
    const keys = track.opacity.keyframes;
    if (
      !Number.isFinite(track.opacity.default) ||
      track.opacity.default < 0 ||
      track.opacity.default > 1
    )
      throw new Error("Default opacity must be between 0 and 1.");
    for (let i = 0; i < keys.length; i++) {
      const k = keys[i];
      if (
        ![k.time_seconds, k.value].every(Number.isFinite) ||
        k.time_seconds < 0 ||
        k.time_seconds > t.duration_seconds ||
        k.value < 0 ||
        k.value > 1
      )
        throw new Error(
          "Opacity time must be inside the show and value between 0 and 1.",
        );
      if (i && keys[i - 1].time_seconds >= k.time_seconds)
        throw new Error("Opacity points need distinct increasing times.");
    }
  }
  const a = t.audio;
  if (
    a &&
    (![
      a.start_seconds,
      a.source_in_seconds,
      a.duration_seconds,
      a.volume,
      a.sync_offset_ms,
    ].every(Number.isFinite) ||
      a.start_seconds < 0 ||
      a.source_in_seconds < 0 ||
      a.duration_seconds <= 0 ||
      a.start_seconds + a.duration_seconds > t.duration_seconds ||
      a.volume < 0 ||
      a.volume > 1 ||
      !Number.isInteger(a.sync_offset_ms) ||
      Math.abs(a.sync_offset_ms) > 1000)
  )
    throw new Error(
      "Audio must fit within the show with volume 0–1 and an integer sync offset within ±1000 ms.",
    );
}
export function TimelineView({
  project,
  timeline,
  position,
  zoom,
  snap,
  readOnly,
  onMove,
  onKey,
  onSelect,
  onSeek,
  onOrder,
}: {
  project: Project;
  timeline: Timeline;
  position: number;
  zoom: number;
  snap: number;
  readOnly: boolean;
  onMove: (sid: string, clip: Clip) => void;
  onKey: (sid: string, index: number, key: OpacityKey) => void;
  onSelect: (sid: string, clipId?: string, keyIndex?: number) => void;
  onSeek: (time: number) => void;
  onOrder: (sid: string, direction: number) => void;
}) {
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const drag = useRef<{
    x: number;
    y: number;
    start: number;
    value: number;
    sid: string;
    clip?: Clip;
    index?: number;
    key?: OpacityKey;
  } | null>(null);
  const width = (Math.max(600, timeline.duration_seconds * 12) * zoom) / 12;
  const scale = width / timeline.duration_seconds;
  const step = Math.max(1, Math.ceil(50 / scale));
  const round = (n: number) => (snap ? Math.round(n / snap) * snap : n);
  const move = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    (e.currentTarget as HTMLElement).style.transform = "";
    drag.current = null;
    const time = Math.min(
      timeline.duration_seconds,
      Math.max(0, round(d.start + (e.clientX - d.x) / scale)),
    );
    if (d.clip) {
      if (Math.abs(e.clientX - d.x) > 3)
        onMove(d.sid, { ...d.clip, start_seconds: time });
    } else if (d.key && d.index !== undefined)
      onKey(d.sid, d.index, {
        ...d.key,
        time_seconds: time,
        value: Math.max(0, Math.min(1, d.value - (e.clientY - d.y) / 48)),
      });
  };
  return (
    <div
      className="timeline-scroll"
      tabIndex={0}
      aria-label="Surface timeline. Scroll horizontally to pan."
    >
      <div className="timeline-grid" style={{ minWidth: width + 170 }}>
        <div className="timeline-ruler">
          <span className="lane-label">Show time</span>
          <div style={{ width }}>
            {Array.from(
              { length: Math.floor(timeline.duration_seconds / step) + 1 },
              (_, i) => (
                <button
                  key={i}
                  style={{ left: i * step * scale }}
                  aria-label={`Seek to ${i * step} seconds`}
                  onClick={() => onSeek(i * step)}
                >
                  {i * step}s
                </button>
              ),
            )}
          </div>
        </div>
        {project.projectors
          .filter((p) => p.enabled)
          .map((p) => {
            const surfaces = project.surfaces
              .filter((s) => s.enabled && s.projector_id === p.id)
              .sort((a, b) => {
                const rank = (id: string) => {
                  const i = timeline.track_order.indexOf(id);
                  return i < 0
                    ? 10000 + project.surfaces.findIndex((s) => s.id === id)
                    : i;
                };
                return rank(a.id) - rank(b.id);
              });
            return (
              <section
                className="timeline-group"
                key={p.id}
                aria-label={p.name}
              >
                <button
                  className="projector-group"
                  aria-expanded={!collapsed.includes(p.id)}
                  onClick={() =>
                    setCollapsed((old) =>
                      old.includes(p.id)
                        ? old.filter((id) => id !== p.id)
                        : [...old, p.id],
                    )
                  }
                >
                  {collapsed.includes(p.id) ? "▸" : "▾"} {p.name} ·{" "}
                  {surfaces.length} surfaces
                </button>
                {!collapsed.includes(p.id) &&
                  surfaces.map((s) => {
                    const track = timeline.tracks.find(
                      (t) => t.surface_id === s.id,
                    );
                    const keys = track?.opacity.keyframes ?? [];
                    const points = [
                      `0,${48 * (1 - (track?.opacity.default ?? 1))}`,
                    ];
                    keys.forEach((k, i) => {
                      if (!i)
                        points.push(
                          `${k.time_seconds * scale},${48 * (1 - (track?.opacity.default ?? 1))}`,
                        );
                      if (i && keys[i - 1].interpolation === "hold")
                        points.push(
                          `${k.time_seconds * scale},${48 * (1 - keys[i - 1].value)}`,
                        );
                      points.push(
                        `${k.time_seconds * scale},${48 * (1 - k.value)}`,
                      );
                    });
                    points.push(
                      `${width},${48 * (1 - (keys.at(-1)?.value ?? track?.opacity.default ?? 1))}`,
                    );
                    return (
                      <div key={s.id} className="surface-lane">
                        <div className="timeline-row">
                          <div className="lane-label">
                            <button
                              className="lane-name"
                              onClick={() => onSelect(s.id)}
                            >
                              {s.name}
                              <small>
                                {s.role === "lighting"
                                  ? `${s.shape} light`
                                  : "Media"}
                              </small>
                            </button>
                            {!readOnly && (
                              <span className="lane-order">
                                <button
                                  aria-label={`Move ${s.name} up`}
                                  onClick={() => onOrder(s.id, -1)}
                                >
                                  ↑
                                </button>
                                <button
                                  aria-label={`Move ${s.name} down`}
                                  onClick={() => onOrder(s.id, 1)}
                                >
                                  ↓
                                </button>
                              </span>
                            )}
                          </div>
                          <div className="lane-canvas" style={{ width }}>
                            {s.role === "lighting" && (
                              <div
                                className="light-band"
                                style={{ background: s.light.color }}
                              >
                                Fixed color · surface opacity below
                              </div>
                            )}
                            {track?.clips.map((c) => (
                              <button
                                key={c.id}
                                className="timeline-clip"
                                aria-label={`Clip ${project.scenes.find((s) => s.id === c.scene_id)?.name ?? c.scene_id}`}
                                style={{
                                  left: c.start_seconds * scale,
                                  width: Math.max(
                                    8,
                                    c.duration_seconds * scale,
                                  ),
                                }}
                                onClick={() => onSelect(s.id, c.id)}
                                onPointerDown={(e) => {
                                  if (readOnly) return;
                                  onSelect(s.id, c.id);
                                  e.currentTarget.setPointerCapture(
                                    e.pointerId,
                                  );
                                  drag.current = {
                                    x: e.clientX,
                                    y: e.clientY,
                                    start: c.start_seconds,
                                    value: 0,
                                    sid: s.id,
                                    clip: c,
                                  };
                                }}
                                onPointerMove={(e) => {
                                  const d = drag.current;
                                  if (d)
                                    (
                                      e.currentTarget as unknown as HTMLElement
                                    ).style.transform =
                                      `translate(${e.clientX - d.x}px,${d.clip ? 0 : e.clientY - d.y}px)`;
                                }}
                                onPointerUp={move}
                                onPointerCancel={(e) => {
                                  e.currentTarget.style.transform = "";
                                  drag.current = null;
                                }}
                              >
                                {project.scenes.find((s) => s.id === c.scene_id)
                                  ?.name ?? c.scene_id}
                              </button>
                            ))}
                            <i
                              className="timeline-playhead"
                              style={{ left: position * scale }}
                            />
                          </div>
                        </div>
                        <div className="timeline-row opacity-row">
                          <button
                            className="lane-label"
                            onClick={() => onSelect(s.id)}
                          >
                            Surface opacity
                          </button>
                          <div className="lane-canvas" style={{ width }}>
                            <svg
                              width={width}
                              height={56}
                              aria-label={`${s.name} opacity curve`}
                            >
                              <polyline
                                points={points.join(" ")}
                                fill="none"
                                stroke="#9cc3ff"
                                strokeWidth="2"
                                transform="translate(0,4)"
                              />
                              {keys.map((k, i) => (
                                <circle
                                  key={i}
                                  role="button"
                                  tabIndex={readOnly ? -1 : 0}
                                  aria-label={`${s.name} opacity point ${i + 1}`}
                                  cx={k.time_seconds * scale}
                                  cy={4 + 48 * (1 - k.value)}
                                  r="6"
                                  stroke="transparent"
                                  strokeWidth="12"
                                  fill="#d9e9ff"
                                  onClick={() => onSelect(s.id, undefined, i)}
                                  onKeyDown={(e) => {
                                    if (
                                      !readOnly &&
                                      [
                                        "ArrowLeft",
                                        "ArrowRight",
                                        "ArrowUp",
                                        "ArrowDown",
                                      ].includes(e.key)
                                    ) {
                                      e.preventDefault();
                                      onKey(s.id, i, {
                                        ...k,
                                        time_seconds: Math.max(
                                          0,
                                          Math.min(
                                            timeline.duration_seconds,
                                            k.time_seconds +
                                              (e.key === "ArrowLeft"
                                                ? -(snap || 1 / 30)
                                                : e.key === "ArrowRight"
                                                  ? snap || 1 / 30
                                                  : 0),
                                          ),
                                        ),
                                        value: Math.max(
                                          0,
                                          Math.min(
                                            1,
                                            k.value +
                                              (e.key === "ArrowUp"
                                                ? 0.05
                                                : e.key === "ArrowDown"
                                                  ? -0.05
                                                  : 0),
                                          ),
                                        ),
                                      });
                                    }
                                  }}
                                  onPointerDown={(e) => {
                                    if (readOnly) return;
                                    onSelect(s.id, undefined, i);
                                    e.currentTarget.setPointerCapture(
                                      e.pointerId,
                                    );
                                    drag.current = {
                                      x: e.clientX,
                                      y: e.clientY,
                                      start: k.time_seconds,
                                      value: k.value,
                                      sid: s.id,
                                      index: i,
                                      key: k,
                                    };
                                  }}
                                  onPointerMove={(e) => {
                                    const d = drag.current;
                                    if (d)
                                      (
                                        e.currentTarget as unknown as HTMLElement
                                      ).style.transform =
                                        `translate(${e.clientX - d.x}px,${d.clip ? 0 : e.clientY - d.y}px)`;
                                  }}
                                  onPointerUp={move}
                                  onPointerCancel={() => {
                                    drag.current = null;
                                  }}
                                />
                              ))}
                            </svg>
                            <i
                              className="timeline-playhead"
                              style={{ left: position * scale }}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
              </section>
            );
          })}
        <div className="timeline-row audio-lane">
          <span className="lane-label">Master audio</span>
          <div className="lane-canvas" style={{ width }}>
            {timeline.audio && (
              <div
                className="audio-block"
                style={{
                  left: timeline.audio.start_seconds * scale,
                  width: timeline.audio.duration_seconds * scale,
                }}
              >
                {project.scenes.find((s) => s.id === timeline.audio?.scene_id)
                  ?.name ?? "Master audio"}
              </div>
            )}
            <i
              className="timeline-playhead"
              style={{ left: position * scale }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
