import { useEffect, useRef, useState } from "react";
import {
  CornerDownLeft,
  Save,
  Undo2,
  Redo2,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
} from "lucide-react";
import { useUnsavedWarning } from "./editing";
import type { Project } from "./types";
import { cornerNames, useMapping, type Corners } from "./useMapping";

export function MappingPage({
  project,
  revision,
  reload,
  connected,
  initialSurface,
  onDirtyChange,
}: {
  initialSurface?: string;
  onDirtyChange: (dirty: boolean) => void;
  project: Project;
  revision: number;
  reload: () => Promise<unknown>;
  connected: boolean;
}) {
  const editor = useMapping(reload);
  const [projectorId, setProjectorId] = useState(
    project.surfaces.find((s) => s.id === initialSurface)?.projector_id ??
      project.projectors[0]?.id ??
      "",
  );
  const surfaces = project.surfaces.filter(
    (s) => s.projector_id === projectorId,
  );
  const [surfaceId, setSurfaceId] = useState(
    initialSurface ?? surfaces[0]?.id ?? "",
  );
  const projector = project.projectors.find((p) => p.id === projectorId);
  const surface = surfaces.find((s) => s.id === surfaceId);
  const mapping = editor.mapping ?? surface?.mapping;
  const [selected, setSelected] = useState<keyof Corners>("top_left");
  const [history, setHistory] = useState<Corners[]>([]);
  const [redo, setRedo] = useState<Corners[]>([]);
  const [zoom, setZoom] = useState(100);
  const [step, setStep] = useState(1);
  const dirty = editor.dirty;
  const canAdjust =
    connected && !editor.busy && !!surface?.enabled && !!projector?.enabled;
  useUnsavedWarning(dirty);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  const board = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!editor.editing) {
      setHistory([]);
      setRedo([]);
    }
  }, [editor.editing, surfaceId]);
  function preview(next: Corners) {
    if (!canAdjust || !surface) return false;
    return editor.preview(next, {
      surfaceId,
      revision,
      original: surface.mapping,
    });
  }
  const drag = useRef<{ pointer: number; before: Corners } | null>(null);
  function remember(before: Corners) {
    setRedo([]);
    setHistory((items) => [...items.slice(-49), structuredClone(before)]);
  }
  function moveCorner(key: keyof Corners, x: number, y: number, undo = true) {
    if (!mapping || !canAdjust) return;
    const next = {
      ...mapping,
      [key]: [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))],
    } as Corners;
    if (JSON.stringify(next) === JSON.stringify(mapping)) return;
    if (preview(next) && undo) remember(mapping);
  }
  return (
    <section className="mapping-page">
      <div className="section-heading">
        <div>
          <h2>Align a surface</h2>
          <p>
            Move a corner to adjust the live output. Save keeps the new
            alignment; Revert restores the saved corners.
          </p>
        </div>
        <span className="badge">
          {editor.editing
            ? editor.dirty
              ? "Live preview · unsaved"
              : "Saved geometry"
            : surface
              ? "Ready to adjust"
              : "Select a surface"}
        </span>
      </div>
      {editor.error && (
        <div role="alert" className="notice error">
          {editor.error}
        </div>
      )}
      <div className="panel form-panel">
        <div className="mapping-selectors">
          <label>
            Projector
            <select
              value={projectorId}
              disabled={!!editor.editing}
              onChange={(e) => {
                setProjectorId(e.target.value);
                setSurfaceId(
                  project.surfaces.find(
                    (s) => s.projector_id === e.target.value,
                  )?.id ?? "",
                );
              }}
            >
              {project.projectors.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.enabled ? "" : " (disabled)"}
                </option>
              ))}
            </select>
          </label>
          <label>
            Surface
            <select
              value={surfaceId}
              disabled={!!editor.editing}
              onChange={(e) => setSurfaceId(e.target.value)}
            >
              {surfaces.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.enabled ? "" : " (disabled)"}
                </option>
              ))}
            </select>
          </label>
          <div className="mapping-commit-actions">
            <button
              disabled={!editor.editing || editor.busy || !connected}
              onClick={() => void editor.end()}
              title="Discard this adjustment and return to show content"
            >
              <CornerDownLeft size={16} /> Revert
            </button>
            <button
              className="primary"
              disabled={!editor.editing || editor.busy || !connected}
              onClick={() => void editor.save()}
            >
              <Save size={16} /> {editor.busy ? "Applying…" : "Save mapping"}
            </button>
          </div>
        </div>
        <p className="mapping-ack" role="status">
          {editor.message ||
            (editor.editing
              ? "Live preview · save or revert when finished"
              : "Drag a corner, nudge, or enter coordinates to adjust")}
        </p>
        {projector && mapping ? (
          <>
            <div className="mapping-view-tools">
              <span className="subtle">
                Projector coordinates · {projector.viewport.width} ×{" "}
                {projector.viewport.height}
              </span>
              <label>
                Editor zoom
                <select
                  value={zoom}
                  onChange={(e) => setZoom(Number(e.target.value))}
                >
                  <option value={100}>Fit</option>
                  <option value={150}>150%</option>
                  <option value={200}>200%</option>
                  <option value={300}>300%</option>
                </select>
              </label>
            </div>
            <div
              className="mapping-scroll"
              tabIndex={zoom > 100 ? 0 : undefined}
              aria-label="Scrollable mapping editor"
            >
              <div
                ref={board}
                className={`mapping-board ${editor.editing ? "editing" : ""}`}
                style={{
                  aspectRatio:
                    projector.viewport.width / projector.viewport.height,
                  width: `calc(${zoom}% - 48px)`,
                  maxWidth:
                    zoom === 100
                      ? `${(46 * projector.viewport.width) / projector.viewport.height}vh`
                      : undefined,
                }}
                aria-label="Projector mapping canvas"
              >
                <svg
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  <defs>
                    <pattern
                      id="mapping-grid"
                      width="50"
                      height="50"
                      patternUnits="userSpaceOnUse"
                    >
                      <path
                        d="M 50 0 L 0 0 0 50"
                        fill="none"
                        stroke="#2c3b33"
                        strokeWidth="1"
                      />
                    </pattern>
                  </defs>
                  <rect width="1000" height="1000" fill="url(#mapping-grid)" />
                  {surfaces.map((s) => (
                    <polygon
                      key={s.id}
                      className={
                        s.id === surfaceId
                          ? "selected-surface"
                          : "other-surface"
                      }
                      points={cornerNames
                        .map((k) => {
                          const [x, y] = (
                            s.id === surfaceId ? mapping : s.mapping
                          )[k];
                          return `${x * 1000},${y * 1000}`;
                        })
                        .join(" ")}
                    />
                  ))}
                </svg>
                <span
                  className="mapping-name"
                  style={{
                    left: `${cornerNames.reduce((sum, k) => sum + mapping[k][0], 0) * 25}%`,
                    top: `${cornerNames.reduce((sum, k) => sum + mapping[k][1], 0) * 25}%`,
                  }}
                >
                  {surface?.name}
                  <small>
                    {surface?.logical.width} × {surface?.logical.height}
                  </small>
                </span>
                {surface?.enabled &&
                  projector.enabled &&
                  cornerNames.map((key, index) => (
                    <button
                      key={key}
                      className={`corner-handle ${selected === key ? "selected" : ""}`}
                      aria-label={`Move ${key.replaceAll("_", " ")} corner`}
                      style={{
                        left: `${mapping[key][0] * 100}%`,
                        top: `${mapping[key][1] * 100}%`,
                      }}
                      disabled={!canAdjust}
                      onFocus={() => setSelected(key)}
                      onPointerDown={(e) => {
                        e.preventDefault();
                        e.currentTarget.focus();
                        e.currentTarget.setPointerCapture(e.pointerId);
                        setSelected(key);
                        drag.current = {
                          pointer: e.pointerId,
                          before: structuredClone(mapping),
                        };
                      }}
                      onPointerMove={(e) => {
                        if (
                          drag.current?.pointer !== e.pointerId ||
                          !board.current
                        )
                          return;
                        const r = board.current.getBoundingClientRect();
                        moveCorner(
                          key,
                          (e.clientX - r.left) / r.width,
                          (e.clientY - r.top) / r.height,
                          false,
                        );
                      }}
                      onPointerUp={(e) => {
                        if (drag.current) {
                          if (
                            JSON.stringify(mapping) !==
                            JSON.stringify(drag.current.before)
                          )
                            remember(drag.current.before);
                          drag.current = null;
                          e.currentTarget.releasePointerCapture(e.pointerId);
                        }
                      }}
                      onPointerCancel={() => {
                        drag.current = null;
                      }}
                      onKeyDown={(e) => {
                        if (
                          ![
                            "ArrowUp",
                            "ArrowDown",
                            "ArrowLeft",
                            "ArrowRight",
                          ].includes(e.key)
                        )
                          return;
                        e.preventDefault();
                        setSelected(key);
                        const step = e.shiftKey ? 10 : 1;
                        moveCorner(
                          key,
                          mapping[key][0] +
                            (e.key === "ArrowLeft"
                              ? -step
                              : e.key === "ArrowRight"
                                ? step
                                : 0) /
                              projector.viewport.width,
                          mapping[key][1] +
                            (e.key === "ArrowUp"
                              ? -step
                              : e.key === "ArrowDown"
                                ? step
                                : 0) /
                              projector.viewport.height,
                        );
                      }}
                    >
                      {index + 1}
                    </button>
                  ))}
              </div>
            </div>
            <div className="mapping-caption">
              <span>
                {projector.viewport.width} × {projector.viewport.height}{" "}
                projector viewport
              </span>
              <span>Arrow keys: 1 px · Shift: 10 px</span>
            </div>
          </>
        ) : (
          <p className="empty">
            Add a projector and surface in the Project editor to begin.
          </p>
        )}
        {mapping && surface?.enabled && projector?.enabled && (
          <>
            <div className="nudge-controls" aria-label="Nudge a corner">
              <label>
                Selected corner
                <select
                  value={selected}
                  onChange={(e) => setSelected(e.target.value as keyof Corners)}
                >
                  {cornerNames.map((k, i) => (
                    <option key={k} value={k}>
                      {i + 1} · {k.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Nudge step
                <select
                  value={step}
                  onChange={(e) => setStep(Number(e.target.value))}
                >
                  <option value={1}>1 pixel</option>
                  <option value={10}>10 pixels</option>
                </select>
              </label>
              <div className="nudge-buttons">
                {[
                  { label: "left", x: -1, y: 0, Icon: ArrowLeft },
                  { label: "up", x: 0, y: -1, Icon: ArrowUp },
                  { label: "down", x: 0, y: 1, Icon: ArrowDown },
                  { label: "right", x: 1, y: 0, Icon: ArrowRight },
                ].map(({ label, x, y, Icon }) => (
                  <button
                    key={label}
                    aria-label={`Nudge ${label}`}
                    title={`Move selected corner ${label}`}
                    disabled={!canAdjust}
                    onClick={() =>
                      moveCorner(
                        selected,
                        mapping[selected][0] +
                          (x * step) / (projector?.viewport.width ?? 1),
                        mapping[selected][1] +
                          (y * step) / (projector?.viewport.height ?? 1),
                      )
                    }
                  >
                    <Icon size={18} />
                  </button>
                ))}
              </div>
            </div>
            <div className="mapping-tools">
              <label>
                Pattern while adjusting
                <select
                  value={editor.pattern}
                  onChange={(e) => editor.setPattern(e.target.value)}
                >
                  {["grid", "white", "border", "show"].map((p) => (
                    <option key={p} value={p}>
                      {p === "show"
                        ? "Show content"
                        : p[0].toUpperCase() + p.slice(1)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={editor.blackOthers}
                  onChange={(e) => editor.setBlackOthers(e.target.checked)}
                />
                Black other surfaces
              </label>
              <div className="mapping-history">
                <button
                  disabled={!history.length || !canAdjust}
                  onClick={() => {
                    const previous = history.at(-1);
                    if (previous) {
                      setRedo((items) => [...items, structuredClone(mapping)]);
                      preview(previous);
                      setHistory(history.slice(0, -1));
                    }
                  }}
                >
                  <Undo2 size={15} />
                  Undo
                </button>
                <button
                  disabled={!redo.length || !canAdjust}
                  onClick={() => {
                    const next = redo.at(-1);
                    if (next) {
                      setHistory((items) => [
                        ...items,
                        structuredClone(mapping),
                      ]);
                      preview(next);
                      setRedo(redo.slice(0, -1));
                    }
                  }}
                >
                  <Redo2 size={15} />
                  Redo
                </button>
                <button
                  disabled={!canAdjust}
                  onClick={() => {
                    remember(mapping);
                    preview({
                      top_left: [0.1, 0.1],
                      top_right: [0.9, 0.1],
                      bottom_right: [0.9, 0.9],
                      bottom_left: [0.1, 0.9],
                    });
                  }}
                >
                  Reset to inset rectangle
                </button>
              </div>
            </div>
            <details className="coordinate-details">
              <summary>Exact coordinates · normalized 0–1</summary>
              <p className="hint">
                X goes left to right, Y goes top to bottom. 0 and 1 are the
                projector edges.
              </p>
              <div className="corner-inputs">
                {cornerNames.map((key, i) => (
                  <fieldset key={key}>
                    <legend>
                      {i + 1}. {key.replaceAll("_", " ")}
                    </legend>
                    {(["x", "y"] as const).map((axis, j) => (
                      <label key={axis}>
                        {axis.toUpperCase()}
                        <input
                          aria-label={`${key.replaceAll("_", " ")} ${axis}`}
                          type="number"
                          min="0"
                          max="1"
                          step="0.001"
                          value={Number(mapping[key][j].toFixed(4))}
                          onChange={(e) =>
                            moveCorner(
                              key,
                              j === 0
                                ? Number(e.target.value)
                                : mapping[key][0],
                              j === 1
                                ? Number(e.target.value)
                                : mapping[key][1],
                            )
                          }
                        />
                      </label>
                    ))}
                  </fieldset>
                ))}
              </div>
            </details>
          </>
        )}
        <p className="hint">
          Save stores the corners and returns to show content without restarting
          playback. Revert discards the adjustment. If this browser disconnects,
          the preview reverts to saved geometry after 45 seconds.
        </p>
      </div>
    </section>
  );
}
