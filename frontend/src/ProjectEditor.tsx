import { useEffect, useState } from "react";
import { Check, Save } from "lucide-react";
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
  const [raw, setRaw] = useState(JSON.stringify(project, null, 2));
  const [advanced, setAdvanced] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setDraft(project);
    setRaw(JSON.stringify(project, null, 2));
  }, [project]);
  const dirty = raw !== JSON.stringify(project, null, 2);
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
          <p>One project file. Any number of outputs and surfaces.</p>
        </div>
        <span className="badge">
          {dirty ? "Unsaved changes" : "Saved on disk"}
        </span>
      </div>
      {!canSave && (
        <div className="notice">
          Stop the show before applying configuration. Your edits stay here
          while you use the runtime controls.
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
      </section>
      <section className="panel form-panel">
        <h3>Show timing</h3>
        <p>
          Visit every eligible surface and scene once before reshuffling,
          avoiding immediate repeats when possible.
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
              Prototype editor · normalized corners are relative to each
              projector.
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
            {advanced ? "Close editor" : "Edit project JSON"}
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
          <div className="inventory">
            {project.projectors.map((p) => (
              <div key={p.id}>
                <strong>{p.name}</strong>
                <span>
                  {p.viewport.width} × {p.viewport.height} at {p.viewport.x},{" "}
                  {p.viewport.y}
                </span>
                <small>
                  {
                    project.surfaces.filter((s) => s.projector_id === p.id)
                      .length
                  }{" "}
                  surfaces
                </small>
              </div>
            ))}
          </div>
        )}
        <p className="hint">
          Add, remove, rename, or disable entries in the project definition. IDs
          remain stable; names are editable. Save validates all geometry and
          references before replacing the file.
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
      <div className="editor-actions">
        <button
          onClick={() => {
            setDraft(project);
            setRaw(JSON.stringify(project, null, 2));
            setMessage("");
            setError("");
          }}
          disabled={!dirty}
        >
          Revert edits
        </button>
        <button
          className="primary"
          disabled={!dirty || !canSave || saving}
          onClick={() => void commit()}
        >
          <Save size={16} />
          {saving ? "Saving…" : "Save & apply project"}
        </button>
      </div>
    </div>
  );
}
