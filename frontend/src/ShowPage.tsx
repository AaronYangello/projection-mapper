import { useEffect, useState } from "react";
import { request } from "./api";
import { useUnsavedWarning } from "./editing";
import { TimelineView, validateTimeline } from "./TimelineView";
import { BuildDeploy } from "./BuildDeploy";
import type {
  Capabilities,
  Clip,
  OpacityKey,
  Project,
  Status,
  Timeline,
  Track,
} from "./types";
const ident = () => crypto.randomUUID();
const number = (form: FormData, name: string) => Number(form.get(name));
export function ShowPage({
  project,
  status,
  revision,
  save,
  reload,
}: {
  project: Project;
  status: Status;
  revision: number;
  save: (p: Project) => Promise<void>;
  reload: () => Promise<unknown>;
}) {
  const [tab, setTab] = useState("Timeline");
  const [draft, setDraft] = useState<Timeline>(
    structuredClone(project.show.timeline),
  );
  const [base, setBase] = useState(project.show.timeline);
  const [baseRevision, setBaseRevision] = useState(revision);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [zoom, setZoom] = useState(12);
  const [snap, setSnap] = useState(1 / 30);
  const [editTime, setEditTime] = useState(0);
  const [selection, setSelection] = useState<{
    sid: string;
    clip?: string;
    key?: number;
  }>({ sid: project.surfaces.find((s) => s.enabled)?.id ?? "" });
  const [phone, setPhone] = useState(window.innerWidth < 680);
  const dirty = JSON.stringify(draft) !== JSON.stringify(base);
  const conflict = dirty && revision !== baseRevision;
  const stopped = status.transport === "READY" && !status.calibration;
  const editable = !!caps?.timeline_edit && !phone && !status.deployment;
  useUnsavedWarning(dirty);
  useEffect(() => {
    void request<Capabilities>("capabilities")
      .then(setCaps)
      .catch((e) => setError(e.message));
    const media = matchMedia("(max-width: 679px)");
    const change = () => setPhone(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (
      !dirty ||
      JSON.stringify(project.show.timeline) === JSON.stringify(draft)
    ) {
      setDraft(structuredClone(project.show.timeline));
      setBase(project.show.timeline);
      setBaseRevision(revision);
    }
  }, [project, revision]);
  const track = draft.tracks.find((t) => t.surface_id === selection.sid);
  const surface = project.surfaces.find((s) => s.id === selection.sid);
  const selected = track?.clips.find((c) => c.id === selection.clip);
  const selectedKey =
    selection.key === undefined
      ? undefined
      : track?.opacity.keyframes[selection.key];
  function change(next: Timeline) {
    try {
      validateTimeline(next);
      setDraft(next);
      setError("");
      setMessage("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function editTrack(sid: string, fn: (t: Track) => Track) {
    try {
      const next = structuredClone(draft);
      let t = next.tracks.find((t) => t.surface_id === sid);
      if (!t) {
        t = {
          id: ident(),
          surface_id: sid,
          clips: [],
          opacity: { default: 1, keyframes: [] },
        };
        next.tracks.push(t);
        next.track_order.push(sid);
      }
      next.tracks = next.tracks.map((t) => (t.surface_id === sid ? fn(t) : t));
      change(next);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function move(sid: string, clip: Clip) {
    editTrack(sid, (t) => ({
      ...t,
      clips: t.clips.map((c) => (c.id === clip.id ? clip : c)),
    }));
  }
  function keyChange(sid: string, index: number, key: OpacityKey) {
    editTrack(sid, (t) => ({
      ...t,
      opacity: {
        ...t.opacity,
        keyframes: t.opacity.keyframes
          .map((k, i) => (i === index ? key : k))
          .sort((a, b) => a.time_seconds - b.time_seconds),
      },
    }));
  }
  async function action(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function preset(kind: string) {
    editTrack(selection.sid, (t) => {
      if (kind === "visible" || kind === "dark")
        return {
          ...t,
          opacity: { default: kind === "visible" ? 1 : 0, keyframes: [] },
        };
      const end = Math.min(draft.duration_seconds, editTime + 3);
      if (end === editTime)
        throw new Error("Place edit time before the show ends.");
      const values = kind === "in" ? [0, 1] : [1, 0];
      return {
        ...t,
        opacity: {
          ...t.opacity,
          keyframes: [
            ...t.opacity.keyframes.filter(
              (k) => k.time_seconds < editTime || k.time_seconds > end,
            ),
            {
              time_seconds: editTime,
              value: values[0],
              interpolation: "linear" as const,
            },
            {
              time_seconds: end,
              value: values[1],
              interpolation: "hold" as const,
            },
          ].sort((a, b) => a.time_seconds - b.time_seconds),
        },
      };
    });
  }
  const position = status.timeline?.position ?? 0;
  return (
    <section className="show-workspace">
      <div className="show-tabs" role="tablist" aria-label="Show authoring">
        <button
          role="tab"
          aria-selected={tab === "Shuffle"}
          onClick={() => setTab("Shuffle")}
        >
          Shuffle
        </button>
        <button
          role="tab"
          aria-selected={tab === "Timeline"}
          onClick={() => setTab("Timeline")}
        >
          Timeline
        </button>
        <button
          role="tab"
          aria-selected={tab === "Build & Deploy"}
          onClick={() => setTab("Build & Deploy")}
        >
          Build & Deploy
        </button>
      </div>
      <p className="mode-summary">
        Active mode:{" "}
        <strong>{status.mode === "timeline" ? "Timeline" : "Shuffle"}</strong>
        {status.deployment
          ? status.deployment_kind === "preview"
            ? " · Mac bundle preview"
            : " · Installed bundle"
          : ""}
        . Viewing a tab does not change the show.
      </p>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="notice success" role="status">
          {message}
        </p>
      )}
      <div hidden={tab === "Build & Deploy"} className="section-heading">
        <span>
          {tab === "Timeline"
            ? "Coordinate surfaces, lights, and one audio program."
            : "One foreground scene at a time with the saved shuffle rules."}
        </span>
        <button
          disabled={
            !stopped ||
            busy ||
            dirty ||
            !caps?.timeline_edit ||
            !!status.deployment ||
            project.show.mode ===
              (tab === "Timeline" ? "timeline" : "shuffle_bag")
          }
          onClick={() =>
            void action(async () => {
              await request("show/mode", {
                method: "POST",
                body: JSON.stringify({
                  revision,
                  mode: tab === "Timeline" ? "timeline" : "shuffle_bag",
                }),
              });
              await reload();
              setMessage(`${tab} is now the active mode.`);
            })
          }
        >
          Use this mode
        </button>
      </div>
      {!stopped && tab !== "Build & Deploy" && (
        <p className="subtle">
          Stop the show and finish mapping to save or change modes. Draft
          editing stays local.
        </p>
      )}
      {tab === "Shuffle" && (
        <section className="panel form-panel">
          <h2>Saved shuffle definition</h2>
          <p>
            Fade in {project.show.fade_in_seconds}s, hold{" "}
            {project.show.hold_seconds.min}–{project.show.hold_seconds.max}s,
            fade out {project.show.fade_out_seconds}s, gap{" "}
            {project.show.gap_seconds.min}–{project.show.gap_seconds.max}s.
          </p>
          <p>
            Every eligible surface and scene plays once before reshuffling.
            Change these settings in Project → Automatic playback. The timeline
            definition stays saved when using Shuffle.
          </p>
        </section>
      )}
      <div hidden={tab !== "Timeline"}>
        {!editable && (
          <p className="notice">
            {phone
              ? "Timeline overview on phone. Use a tablet or desktop to edit; Playback, Mapping and deployment remain available."
              : status.deployment
                ? "Unload the bundle preview or active deployment to edit this local project."
                : "Timeline authoring is read-only on the appliance. Edit and build on the authoring Mac."}
          </p>
        )}
        {conflict && (
          <p role="alert" className="notice warning">
            The project changed while you were editing. Your timeline draft is
            retained. Discard to load the current version before saving.
          </p>
        )}
        <div className="timeline-tools">
          <label>
            Duration (seconds)
            <input
              type="number"
              min="0.1"
              max="86400"
              step="0.1"
              value={draft.duration_seconds}
              disabled={!editable}
              onChange={(e) =>
                change({ ...draft, duration_seconds: Number(e.target.value) })
              }
            />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={draft.loop}
              disabled={!editable}
              onChange={(e) => change({ ...draft, loop: e.target.checked })}
            />
            Loop complete show
          </label>
          <label>
            Zoom
            <input
              type="range"
              min="2"
              max="80"
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
            />
          </label>
          <label>
            Snap
            <select
              value={snap}
              onChange={(e) => setSnap(Number(e.target.value))}
            >
              <option value={1 / 30}>1 frame (30 fps)</option>
              <option value={0.1}>0.1 second</option>
              <option value={1}>1 second</option>
              <option value={0}>Off</option>
            </select>
          </label>
        </div>
        <p className="subtle">
          Clips use absolute time; moving one leaves the others in place.
          Opacity applies to the whole surface across clips and gaps.{" "}
          {draft.loop
            ? "End returns to time zero."
            : "At the end, the show pauses at its final time with media dark."}
        </p>
        <TimelineView
          project={project}
          timeline={draft}
          position={position}
          zoom={zoom}
          snap={snap}
          readOnly={!editable}
          onMove={move}
          onKey={keyChange}
          onSelect={(sid, clip, key) => setSelection({ sid, clip, key })}
          onSeek={(time) => {
            setEditTime(time);
            if (status.mode === "timeline" && !dirty)
              void action(() =>
                request("runtime/seek", {
                  method: "POST",
                  body: JSON.stringify({ seconds: time }),
                }),
              );
          }}
          onOrder={(sid, direction) => {
            const p = project.surfaces.find((s) => s.id === sid)?.projector_id;
            const same = project.surfaces
              .filter((s) => s.enabled && s.projector_id === p)
              .sort((a, b) => {
                const rank = (id: string) =>
                  draft.track_order.indexOf(id) < 0
                    ? 1000 + project.surfaces.findIndex((s) => s.id === id)
                    : draft.track_order.indexOf(id);
                return rank(a.id) - rank(b.id);
              })
              .map((s) => s.id);
            const i = same.indexOf(sid);
            if (i + direction < 0 || i + direction >= same.length) return;
            [same[i], same[i + direction]] = [same[i + direction], same[i]];
            const next = structuredClone(draft);
            for (const id of same)
              if (!next.tracks.some((t) => t.surface_id === id))
                next.tracks.push({
                  id: ident(),
                  surface_id: id,
                  clips: [],
                  opacity: { default: 1, keyframes: [] },
                });
            next.track_order = [
              ...next.track_order.filter((id) => !same.includes(id)),
              ...same,
            ];
            change(next);
          }}
        />
        {editable && (
          <div className="timeline-inspectors">
            <section className="panel form-panel">
              <h2>{surface?.name ?? "Choose a surface"}</h2>
              <label>
                Surface
                <select
                  value={selection.sid}
                  onChange={(e) => setSelection({ sid: e.target.value })}
                >
                  {project.surfaces
                    .filter((s) => s.enabled)
                    .map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} · {s.role}
                      </option>
                    ))}
                </select>
              </label>
              {surface?.role === "media" && (
                <form
                  key={
                    selected
                      ? JSON.stringify(selected)
                      : `new-${selection.sid}-${editTime}`
                  }
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.currentTarget);
                    const clip: Clip = {
                      id: selected?.id ?? ident(),
                      scene_id: String(f.get("scene")),
                      start_seconds: number(f, "start"),
                      source_in_seconds: number(f, "trim"),
                      duration_seconds: number(f, "duration"),
                    };
                    editTrack(selection.sid, (t) => ({
                      ...t,
                      clips: selected
                        ? t.clips.map((c) => (c.id === selected.id ? clip : c))
                        : [...t.clips, clip],
                    }));
                  }}
                >
                  <h3>{selected ? "Selected clip" : "Add a clip"}</h3>
                  <label>
                    Source
                    <select
                      name="scene"
                      defaultValue={selected?.scene_id}
                      required
                    >
                      {project.scenes
                        .filter((s) => s.enabled && s.type !== "audio")
                        .map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <div className="fields three">
                    <label>
                      Start (s)
                      <input
                        name="start"
                        type="number"
                        min="0"
                        step="0.001"
                        defaultValue={selected?.start_seconds ?? editTime}
                        required
                      />
                    </label>
                    <label>
                      Source in (s)
                      <input
                        name="trim"
                        type="number"
                        min="0"
                        step="0.001"
                        defaultValue={selected?.source_in_seconds ?? 0}
                        required
                      />
                    </label>
                    <label>
                      Duration (s)
                      <input
                        name="duration"
                        type="number"
                        min="0.001"
                        step="0.001"
                        defaultValue={
                          selected?.duration_seconds ??
                          Math.min(5, draft.duration_seconds - editTime)
                        }
                        required
                      />
                    </label>
                  </div>
                  <button className="primary">
                    {selected ? "Apply clip fields" : "Add clip"}
                  </button>
                  {selected && (
                    <>
                      <button
                        type="button"
                        onClick={() =>
                          editTrack(selection.sid, (t) => ({
                            ...t,
                            clips: [
                              ...t.clips,
                              {
                                ...selected,
                                id: ident(),
                                start_seconds:
                                  selected.start_seconds +
                                  selected.duration_seconds,
                              },
                            ],
                          }))
                        }
                      >
                        Duplicate after
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          editTrack(selection.sid, (t) => ({
                            ...t,
                            clips: t.clips.filter((c) => c.id !== selected.id),
                          }));
                          setSelection({ sid: selection.sid });
                        }}
                      >
                        Delete clip
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelection({ sid: selection.sid })}
                      >
                        Add another
                      </button>
                    </>
                  )}
                </form>
              )}
              {surface?.role === "lighting" && (
                <p>
                  {surface.shape} · {surface.light.color}. Change shape and
                  fixed color in Project → Surfaces. Brightness uses the same
                  surface opacity controls as media.
                </p>
              )}
            </section>
            <section className="panel form-panel">
              <h2>Surface opacity</h2>
              <p>
                Default is 100%. Before the first point use Default; after the
                last point hold its value. Each point controls the interpolation
                leaving it.
              </p>
              <div className="fields">
                <label>
                  Default opacity
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    value={track?.opacity.default ?? 1}
                    onChange={(e) =>
                      editTrack(selection.sid, (t) => ({
                        ...t,
                        opacity: {
                          ...t.opacity,
                          default: Number(e.target.value),
                        },
                      }))
                    }
                  />
                </label>
                <label>
                  Edit time (s)
                  <input
                    type="number"
                    min="0"
                    max={draft.duration_seconds}
                    step="0.1"
                    value={editTime}
                    onChange={(e) => setEditTime(Number(e.target.value))}
                  />
                </label>
              </div>
              <div className="button-row">
                <button onClick={() => preset("in")}>Fade in</button>
                <button onClick={() => preset("out")}>Fade out</button>
                <button onClick={() => preset("visible")}>Set visible</button>
                <button onClick={() => preset("dark")}>Set dark</button>
              </div>
              <p className="subtle">
                Fades add three seconds at Edit time. Set visible/dark replaces
                this surface's entire curve.
              </p>
              <form
                key={
                  selection.key === undefined
                    ? `newkey-${selection.sid}-${editTime}`
                    : `key-${selection.sid}-${selection.key}-${JSON.stringify(selectedKey)}`
                }
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  const key: OpacityKey = {
                    time_seconds: number(f, "time"),
                    value: number(f, "value"),
                    interpolation: String(f.get("interpolation")) as
                      | "linear"
                      | "hold",
                  };
                  if (selection.key !== undefined)
                    keyChange(selection.sid, selection.key, key);
                  else
                    editTrack(selection.sid, (t) => ({
                      ...t,
                      opacity: {
                        ...t.opacity,
                        keyframes: [...t.opacity.keyframes, key].sort(
                          (a, b) => a.time_seconds - b.time_seconds,
                        ),
                      },
                    }));
                }}
              >
                <div className="fields three">
                  <label>
                    Keyframe time (s)
                    <input
                      name="time"
                      type="number"
                      min="0"
                      max={draft.duration_seconds}
                      step="0.001"
                      defaultValue={selectedKey?.time_seconds ?? editTime}
                      required
                    />
                  </label>
                  <label>
                    Opacity (0–1)
                    <input
                      name="value"
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      defaultValue={selectedKey?.value ?? 1}
                      required
                    />
                  </label>
                  <label>
                    Interpolation
                    <select
                      name="interpolation"
                      defaultValue={selectedKey?.interpolation ?? "linear"}
                    >
                      <option value="linear">Linear</option>
                      <option value="hold">Hold</option>
                    </select>
                  </label>
                </div>
                <button>
                  {selection.key === undefined
                    ? "Add opacity point"
                    : "Apply keyframe"}
                </button>
                {selection.key !== undefined && (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        editTrack(selection.sid, (t) => ({
                          ...t,
                          opacity: {
                            ...t.opacity,
                            keyframes: t.opacity.keyframes.filter(
                              (_, i) => i !== selection.key,
                            ),
                          },
                        }));
                        setSelection({ sid: selection.sid });
                      }}
                    >
                      Delete point
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelection({ sid: selection.sid })}
                    >
                      New point
                    </button>
                  </>
                )}
              </form>
            </section>
          </div>
        )}
        {editable && (
          <section className="panel form-panel">
            <h2>Master audio</h2>
            <p>
              Use one finished audio stem. Source alignment is compiled; volume,
              mute and sync offset stay runtime settings.
            </p>
            <form
              key={JSON.stringify(draft.audio)}
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                const scene = String(f.get("scene"));
                change({
                  ...draft,
                  audio: scene
                    ? {
                        scene_id: scene,
                        start_seconds: number(f, "start"),
                        source_in_seconds: number(f, "in"),
                        duration_seconds: number(f, "duration"),
                        volume: number(f, "volume"),
                        muted: f.has("muted"),
                        sync_offset_ms: number(f, "offset"),
                      }
                    : null,
                });
              }}
            >
              <div className="fields three">
                <label>
                  Audio source
                  <select
                    name="scene"
                    defaultValue={draft.audio?.scene_id ?? ""}
                  >
                    <option value="">No audio program</option>
                    {project.scenes
                      .filter((s) => s.enabled && s.type === "audio")
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Audio start (s)
                  <input
                    name="start"
                    type="number"
                    min="0"
                    step="0.001"
                    defaultValue={draft.audio?.start_seconds ?? 0}
                  />
                </label>
                <label>
                  Audio source in (s)
                  <input
                    name="in"
                    type="number"
                    min="0"
                    step="0.001"
                    defaultValue={draft.audio?.source_in_seconds ?? 0}
                  />
                </label>
                <label>
                  Audio duration (s)
                  <input
                    name="duration"
                    type="number"
                    min="0.001"
                    step="0.001"
                    defaultValue={
                      draft.audio?.duration_seconds ?? draft.duration_seconds
                    }
                  />
                </label>
                <label>
                  Volume
                  <input
                    name="volume"
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    defaultValue={draft.audio?.volume ?? 1}
                  />
                </label>
                <label>
                  Sync offset (ms)
                  <input
                    name="offset"
                    type="number"
                    min="-1000"
                    max="1000"
                    defaultValue={draft.audio?.sync_offset_ms ?? 0}
                  />
                </label>
                <label className="check-label">
                  <input
                    name="muted"
                    type="checkbox"
                    defaultChecked={draft.audio?.muted ?? false}
                  />
                  Mute master audio
                </label>
              </div>
              <button>Apply audio fields</button>
            </form>
          </section>
        )}
        <div className="save-bar">
          <span role="status">
            {dirty ? "Unsaved timeline draft" : "Timeline saved"}
          </span>
          <button
            disabled={!dirty || busy}
            onClick={() => {
              setDraft(structuredClone(project.show.timeline));
              setBase(project.show.timeline);
              setBaseRevision(revision);
              setError("");
            }}
          >
            Discard timeline edits
          </button>
          <button
            className="primary"
            disabled={!editable || !dirty || conflict || !stopped || busy}
            onClick={() =>
              void action(async () => {
                validateTimeline(draft);
                await save({
                  ...project,
                  show: { ...project.show, timeline: draft },
                });
                setBase(draft);
                setMessage(
                  "Timeline saved. Build it to preview compiled video and audio or deploy.",
                );
              })
            }
          >
            Save timeline
          </button>
        </div>
      </div>
      <div hidden={tab !== "Build & Deploy"}>
        <BuildDeploy
          project={project}
          status={status}
          revision={revision}
          capabilities={caps}
          dirty={dirty}
        />
      </div>
    </section>
  );
}
export function TimelinePlayback({
  project,
  status,
}: {
  project: Project;
  status: Status;
}) {
  const t = status.timeline;
  const [error, setError] = useState("");
  if (!t) return null;
  return (
    <section className="panel form-panel">
      <h2>
        Timeline · {t.position.toFixed(2)} / {t.duration.toFixed(2)} s
      </h2>
      <label>
        Seek saved show
        <input
          type="range"
          min="0"
          max={t.duration}
          step="0.033333"
          value={t.position}
          onChange={(e) =>
            void request("runtime/seek", {
              method: "POST",
              body: JSON.stringify({ seconds: Number(e.target.value) }),
            }).catch((e) => setError(e.message))
          }
        />
      </label>
      <p>
        {t.loop ? "Loop enabled" : "Pause at end"} ·{" "}
        {status.deployment
          ? `${status.deployment_kind === "preview" ? "Local bundle preview" : "Installed bundle"} ${status.deployment.id.slice(0, 12)}`
          : "Authoring preview · local output"}
      </p>
      {status.renderer.timeline_clock && (
        <p className="subtle">
          Playback: {status.renderer.timeline_clock.state ?? "Connecting"} ·{" "}
          Audio: {status.renderer.timeline_clock.audio_sink ?? "Unavailable"}
          {status.renderer.timeline_clock.audio_device
            ? ` / ${status.renderer.timeline_clock.audio_device}`
            : ""}
          {status.renderer.timeline_clock.muted ? " · Muted" : ""}
          {status.renderer.timeline_clock.audio_sink === "fakesink"
            ? " · Silent test output"
            : ""}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <ul className="active-layers">
        {t.layers.map((l) => (
          <li key={l.id}>
            <strong>
              {project.surfaces.find((s) => s.id === l.surface_id)?.name ??
                l.surface_id}
            </strong>{" "}
            ·{" "}
            {l.role === "lighting"
              ? "Light"
              : l.source_id
                ? "Media"
                : "Empty span"}{" "}
            · {Math.round(l.opacity * 100)}% surface opacity
          </li>
        ))}
      </ul>
      <details>
        <summary>Upcoming events</summary>
        {t.upcoming.map((e, i) => (
          <p key={i}>
            {e.time.toFixed(2)} s ·{" "}
            {project.surfaces.find((s) => s.id === e.surface_id)?.name ??
              e.surface_id}{" "}
            · {e.kind}
          </p>
        ))}
      </details>
    </section>
  );
}
