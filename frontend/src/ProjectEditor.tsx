import { useEffect, useState } from "react";
import { Check, Save } from "lucide-react";
import { useUnsavedWarning } from "./editing";
import { request } from "./api";
import type { Project } from "./types";

export function ProjectEditor({
  project,
  canSave,
  save,
}: {
  project: Project;
  canSave: boolean;
  save: (p: Project) => Promise<void>;
}) {
  const [draft, setDraft] = useState(project);
  const [base, setBase] = useState(project);
  const [raw, setRaw] = useState(JSON.stringify(project, null, 2));
  const [advanced, setAdvanced] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (
      raw === JSON.stringify(base, null, 2) ||
      raw === JSON.stringify(project, null, 2)
    ) {
      setDraft(project);
      setBase(project);
      setRaw(JSON.stringify(project, null, 2));
    }
  }, [project]);
  const dirty = raw !== JSON.stringify(base, null, 2);
  const conflict = dirty && JSON.stringify(base) !== JSON.stringify(project);
  useUnsavedWarning(dirty);
  function update(next: Project) {
    setDraft(next);
    setRaw(JSON.stringify(next, null, 2));
    setMessage("");
  }
  async function commit() {
    setError("");
    setMessage("");
    setSaving(true);
    try {
      await save(JSON.parse(raw));
      setMessage("Project saved and applied.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="editor">
      <div className="section-heading">
        <div>
          <h2>Project configuration</h2>
          <p>
            Changes are applied together. The running show keeps using the saved
            project until you save.
          </p>
        </div>
        <span className="badge">
          {dirty ? "Unsaved changes" : "Saved on disk"}
        </span>
      </div>
      {!canSave && (
        <div className="notice">
          Stop show and finish any active mapping session before saving. Your
          draft stays here when you switch pages.
        </div>
      )}
      {conflict && (
        <div role="alert" className="notice error">
          The project changed while you were editing. Discard edits to load the
          current version before saving.
        </div>
      )}
      <section className="panel form-panel">
        <h3>Identity & output</h3>
        <div className="fields">
          <label>
            Project name
            <input
              value={draft.name}
              disabled={advanced}
              onChange={(e) => update({ ...draft, name: e.target.value })}
            />
          </label>
          {(["width", "height", "refresh_rate"] as const).map((key) => (
            <label key={key}>
              {key === "refresh_rate"
                ? "Target refresh rate (Hz)"
                : `Canvas ${key} (px)`}
              <input
                type="number"
                disabled={advanced}
                value={draft.canvas[key]}
                onChange={(e) =>
                  update({
                    ...draft,
                    canvas: { ...draft.canvas, [key]: Number(e.target.value) },
                  })
                }
              />
            </label>
          ))}
        </div>
        <p className="hint">
          When changing the canvas, update projector viewports below to keep
          them within its bounds. Fullscreen and monitor changes take effect on
          the next application launch.
        </p>
        <div className="fields">
          <label>
            Browser preview rate (fps)
            <input
              type="number"
              min="0"
              max="10"
              step="0.25"
              disabled={advanced}
              value={draft.canvas.preview_fps}
              onChange={(e) =>
                update({
                  ...draft,
                  canvas: {
                    ...draft.canvas,
                    preview_fps: Number(e.target.value),
                  },
                })
              }
            />
          </label>
          <label>
            Browser preview width (px)
            <input
              type="number"
              min="160"
              max="1920"
              disabled={advanced}
              value={draft.canvas.preview_width}
              onChange={(e) =>
                update({
                  ...draft,
                  canvas: {
                    ...draft.canvas,
                    preview_width: Number(e.target.value),
                  },
                })
              }
            />
          </label>
        </div>
        <p className="hint">
          Preview is downscaled and encoded in the background. Set its rate to 0
          to disable capture without changing the native output.
        </p>
      </section>
      <section className="panel form-panel">
        <h3>Automatic playback</h3>
        <label className="check-label">
          <input
            type="checkbox"
            checked={draft.show.auto_start}
            disabled={advanced}
            onChange={(e) =>
              update({
                ...draft,
                show: { ...draft.show, auto_start: e.target.checked },
              })
            }
          />
          Start show when the application launches
        </label>
        <p>
          Each eligible surface and scene plays once before reshuffling. Hold
          time applies to colors, images, and timed videos. Full-clip videos use
          their own duration. Gap is the ambient-only interval between cues.
        </p>
        <div className="fields">
          {(["fade_in_seconds", "fade_out_seconds"] as const).map((key) => (
            <label key={key}>
              {key === "fade_in_seconds" ? "Fade in (s)" : "Fade out (s)"}
              <input
                type="number"
                min="0"
                step="0.1"
                disabled={advanced}
                value={draft.show[key]}
                onChange={(e) =>
                  update({
                    ...draft,
                    show: { ...draft.show, [key]: Number(e.target.value) },
                  })
                }
              />
            </label>
          ))}
          {(["hold_seconds", "gap_seconds"] as const).flatMap((key) =>
            (["min", "max"] as const).map((end) => (
              <label key={key + end}>
                {key === "hold_seconds" ? "Hold" : "Gap"} {end} (s)
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  disabled={advanced}
                  value={draft.show[key][end]}
                  onChange={(e) =>
                    update({
                      ...draft,
                      show: {
                        ...draft.show,
                        [key]: {
                          ...draft.show[key],
                          [end]: Number(e.target.value),
                        },
                      },
                    })
                  }
                />
              </label>
            )),
          )}
        </div>
      </section>
      <section className="panel form-panel">
        <div className="section-heading">
          <div>
            <h3>Projectors, surfaces & sources</h3>
            <p>
              Rename, enable, and size your outputs here. Use Mapping for corner
              alignment and Media for playback settings.
            </p>
          </div>
          <button
            onClick={async () => {
              if (advanced) {
                try {
                  const valid = await request<Project>("project/validate", {
                    method: "POST",
                    body: raw,
                  });
                  update(valid);
                  setAdvanced(false);
                  setError("");
                } catch (e) {
                  setError(
                    e instanceof Error
                      ? e.message
                      : "Fix the project definition before closing the editor.",
                  );
                }
              } else setAdvanced(true);
            }}
          >
            {advanced ? "Validate & close JSON" : "Advanced JSON"}
          </button>
        </div>
        {advanced ? (
          <label className="json-label">
            Complete project definition
            <textarea
              aria-label="Project JSON"
              spellCheck={false}
              value={raw}
              onChange={(e) => {
                setRaw(e.target.value);
                setMessage("");
              }}
            />
          </label>
        ) : (
          <div className="topology-editor">
            <details>
              <summary>Projectors · {draft.projectors.length}</summary>
              <p className="hint">
                Viewports are rectangles within the output canvas. Edit X/Y to
                position them; overlapping viewports are allowed.
              </p>
              {draft.projectors.map((p, index) => (
                <fieldset className="topology-row" key={p.id}>
                  <legend>{p.name}</legend>
                  <div className="fields">
                    <label>
                      Projector name
                      <input
                        value={p.name}
                        onChange={(e) =>
                          update({
                            ...draft,
                            projectors: draft.projectors.map((v, i) =>
                              i === index ? { ...v, name: e.target.value } : v,
                            ),
                          })
                        }
                      />
                    </label>
                    <label className="check-label">
                      <input
                        type="checkbox"
                        checked={p.enabled}
                        onChange={(e) =>
                          update({
                            ...draft,
                            projectors: draft.projectors.map((v, i) =>
                              i === index
                                ? { ...v, enabled: e.target.checked }
                                : v,
                            ),
                          })
                        }
                      />
                      Enabled
                    </label>
                    {(["x", "y", "width", "height"] as const).map((key) => (
                      <label key={key}>
                        {key[0].toUpperCase() + key.slice(1)} (pixels)
                        <input
                          type="number"
                          min={key === "width" || key === "height" ? 16 : 0}
                          value={p.viewport[key]}
                          onChange={(e) =>
                            update({
                              ...draft,
                              projectors: draft.projectors.map((v, i) =>
                                i === index
                                  ? {
                                      ...v,
                                      viewport: {
                                        ...v.viewport,
                                        [key]: Number(e.target.value),
                                      },
                                    }
                                  : v,
                              ),
                            })
                          }
                        />
                      </label>
                    ))}
                  </div>
                </fieldset>
              ))}
            </details>
            <details>
              <summary>Surfaces · {draft.surfaces.length}</summary>
              <p className="hint">
                A surface is a mapped shape on a projector. Disabling foreground
                excludes it from the queue while keeping its background.
              </p>
              {draft.surfaces.map((surface, index) => {
                const change = (value: Partial<typeof surface>) =>
                  update({
                    ...draft,
                    surfaces: draft.surfaces.map((v, i) =>
                      i === index ? { ...v, ...value } : v,
                    ),
                  });
                return (
                  <fieldset className="topology-row" key={surface.id}>
                    <legend>{surface.name}</legend>
                    <div className="fields">
                      <label>
                        Surface name
                        <input
                          value={surface.name}
                          onChange={(e) => change({ name: e.target.value })}
                        />
                      </label>
                      <label>
                        Projector
                        <select
                          value={surface.projector_id}
                          onChange={(e) =>
                            change({ projector_id: e.target.value })
                          }
                        >
                          {draft.projectors.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Surface role
                        <select
                          value={surface.role}
                          onChange={(e) =>
                            change({
                              role: e.target.value as "media" | "lighting",
                            })
                          }
                        >
                          <option value="media">Media</option>
                          <option value="lighting">Lighting</option>
                        </select>
                      </label>
                      <label>
                        Shape
                        <select
                          value={surface.shape}
                          onChange={(e) =>
                            change({
                              shape: e.target.value as "rectangle" | "circle",
                            })
                          }
                        >
                          <option value="rectangle">Rectangle</option>
                          <option value="circle">Circle</option>
                        </select>
                      </label>
                      {surface.role === "lighting" && (
                        <label>
                          Light color
                          <input
                            type="color"
                            value={surface.light.color}
                            onChange={(e) =>
                              change({ light: { color: e.target.value } })
                            }
                          />
                        </label>
                      )}
                      <label>
                        Background
                        <select
                          value={surface.ambient_profile ?? ""}
                          onChange={(e) =>
                            change({ ambient_profile: e.target.value || null })
                          }
                        >
                          <option value="">None</option>
                          {draft.ambient_profiles.map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="check-label">
                        <input
                          type="checkbox"
                          checked={surface.enabled}
                          onChange={(e) =>
                            change({ enabled: e.target.checked })
                          }
                        />
                        Enabled
                      </label>
                      <label className="check-label">
                        <input
                          type="checkbox"
                          checked={surface.foreground_enabled}
                          onChange={(e) =>
                            change({ foreground_enabled: e.target.checked })
                          }
                        />
                        Allow foreground cues
                      </label>
                      {(["width", "height"] as const).map((key) => (
                        <label key={key}>
                          Content {key} (pixels)
                          <input
                            type="number"
                            min={16}
                            value={surface.logical[key]}
                            onChange={(e) =>
                              change({
                                logical: {
                                  ...surface.logical,
                                  [key]: Number(e.target.value),
                                },
                              })
                            }
                          />
                        </label>
                      ))}
                    </div>
                  </fieldset>
                );
              })}
            </details>
          </div>
        )}
        <p className="hint">
          Advanced JSON exposes the complete project, including adding or
          removing entries, tags, and background profiles. IDs stay stable when
          you rename an item. All changes are validated before saving.
        </p>
      </section>
      {error && (
        <div role="alert" className="notice error">
          {error}
        </div>
      )}
      {message && (
        <div role="status" className="notice success">
          <Check size={16} />
          {message}
        </div>
      )}
      <div className="editor-actions project-savebar">
        <button
          onClick={() => {
            setDraft(project);
            setBase(project);
            setRaw(JSON.stringify(project, null, 2));
            setMessage("");
            setError("");
          }}
          disabled={!dirty}
        >
          Discard edits
        </button>
        <button
          className="primary"
          disabled={!dirty || !canSave || saving || conflict}
          onClick={() => void commit()}
        >
          <Save size={16} />
          {saving ? "Saving…" : "Save & apply project"}
        </button>
      </div>
    </div>
  );
}
