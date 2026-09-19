import { useEffect, useState } from "react";
import {
  Film,
  Image as ImageIcon,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Copy,
  Music2,
} from "lucide-react";
import { UploadPanel } from "./UploadPanel";
import { getToken, request } from "./api";
import { DiscardDialog, useUnsavedWarning } from "./editing";
import type { MediaAsset, Project, Status } from "./types";

type Scene = Project["scenes"][number];
function Thumbnail({ asset }: { asset: MediaAsset }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let disposed = false,
      blobUrl = "";
    const controller = new AbortController();
    if (asset.thumbnail)
      void fetch(`/api/media/${asset.id}/thumbnail`, {
        signal: controller.signal,
        headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
      })
        .then(async (r) => {
          if (!r.ok) return;
          const blob = await r.blob();
          if (disposed) return;
          blobUrl = URL.createObjectURL(blob);
          setUrl(blobUrl);
        })
        .catch(() => {});
    return () => {
      disposed = true;
      controller.abort();
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [asset.id, asset.thumbnail]);
  return url ? (
    <img src={url} alt="" />
  ) : (
    <div className="media-placeholder">
      {asset.type === "video" ? (
        <Film size={28} />
      ) : asset.type === "audio" ? (
        <Music2 size={28} />
      ) : (
        <ImageIcon size={28} />
      )}
    </div>
  );
}

export function MediaPage({
  project,
  status,
  connected,
  reload,
  save,
}: {
  project: Project;
  status: Status;
  connected: boolean;
  reload: () => Promise<unknown>;
  save: (p: Project) => Promise<void>;
}) {
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [folder, setFolder] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState("");
  const [pendingSelection, setPendingSelection] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [scanRevision, setScanRevision] = useState(0);
  const [draft, setDraft] = useState<Scene | null>(null);
  const [base, setBase] = useState<Scene | null>(null);
  const eligible = project.surfaces.filter(
    (s) =>
      s.enabled &&
      s.foreground_enabled &&
      s.role === "media" &&
      project.projectors.some((p) => p.id === s.projector_id && p.enabled),
  );
  const [surfaceId, setSurfaceId] = useState(eligible[0]?.id ?? "");
  const asset = assets.find((a) => a.id === selected);
  const scene = project.scenes.find(
    (s) => s.path === asset?.path && s.type !== "color",
  );
  const dirty = JSON.stringify(draft) !== JSON.stringify(base);
  const conflict =
    dirty && !!base && JSON.stringify(scene) !== JSON.stringify(base);
  const canEdit =
    status.transport === "READY" && connected && !status.calibration;
  useUnsavedWarning(dirty);
  useEffect(() => {
    void request<{ assets: MediaAsset[]; folder?: string }>("media")
      .then((data) => {
        setAssets(data.assets);
        setFolder(data.folder ?? "");
        setSelected(data.assets[0]?.id ?? "");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (!dirty || JSON.stringify(draft) === JSON.stringify(scene)) {
      setDraft(scene ?? null);
      setBase(scene ?? null);
    }
  }, [scene]);
  useEffect(() => {
    if (!eligible.some((s) => s.id === surfaceId))
      setSurfaceId(eligible[0]?.id ?? "");
  }, [eligible, surfaceId]);
  const filtered = assets.filter((a) => {
    const source = project.scenes.find((s) => s.path === a.path);
    return (
      (kind === "all" ||
        a.type === kind ||
        (kind === "attention" && !!a.error)) &&
      `${a.name} ${source?.name ?? ""} ${a.path} ${source?.tags.join(" ") ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase())
    );
  });
  function select(id: string) {
    if (id === selected) return;
    if (dirty) {
      setPendingSelection(id);
      return;
    }
    setDraft(null);
    setBase(null);
    setSelected(id);
    setMessage("");
    setError("");
  }
  function update(change: Partial<Scene>) {
    if (draft) setDraft({ ...draft, ...change });
    setMessage("");
  }
  async function action(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="media-page">
      <UploadPanel enabled={canEdit && !dirty} />
      <div className="section-heading">
        <div>
          <h2>
            Media library <span className="count">{assets.length}</span>
          </h2>
          <p>Choosing a file here does not change the projected output.</p>
        </div>
        <button
          disabled={!canEdit || busy || dirty}
          onClick={() =>
            void action(async () => {
              const data = await request<{
                assets: MediaAsset[];
                folder?: string;
              }>("media/scan", { method: "POST" });
              setAssets(data.assets);
              if (data.folder) setFolder(data.folder);
              setScanRevision((v) => v + 1);
              if (!data.assets.some((a) => a.id === selected))
                setSelected(data.assets[0]?.id ?? "");
              setMessage(
                `Scan complete. ${data.assets.length} files, ${data.assets.filter((a) => a.error).length} need attention.`,
              );
            })
          }
        >
          <RefreshCw size={16} />
          {busy ? "Working…" : "Scan folder"}
        </button>
      </div>
      <details className="folder-help">
        <summary>Add files to this library</summary>
        <p>
          Copy videos or images into this project's media folder, then stop the
          show and scan. MP4, MOV, MKV, WebM, AVI, PNG, JPEG, and WebP are
          supported.
        </p>
        {folder ? (
          <div className="folder-path">
            <input
              aria-label="Media folder path"
              readOnly
              value={folder}
              onFocus={(e) => e.target.select()}
            />
            <button
              onClick={() =>
                void action(async () => {
                  if (!navigator.clipboard)
                    throw new Error(
                      "Select the folder path and copy it manually.",
                    );
                  await navigator.clipboard.writeText(folder);
                  setMessage("Media folder path copied.");
                })
              }
            >
              <Copy size={16} />
              Copy path
            </button>
          </div>
        ) : (
          <p>
            Folder: <code>media/</code> beside your project.yaml file.
          </p>
        )}
      </details>
      {!canEdit && (
        <p className="notice">
          {status.calibration
            ? "Finish mapping before changing media settings."
            : "Stop show to scan or save settings."}{" "}
          You can still browse and play saved sources.
        </p>
      )}
      {error && (
        <div role="alert" className="notice error">
          {error}
        </div>
      )}
      {message && (
        <div role="status" className="notice success">
          {message}
        </div>
      )}
      {loading ? (
        <p role="status" className="empty">
          Loading the media library…
        </p>
      ) : !assets.length ? (
        <div className="empty">
          <h3>No media files yet</h3>
          <p>
            Open “Add files to this library” above, copy your files, and scan
            the folder.
          </p>
        </div>
      ) : (
        <>
          <div className="library-tools">
            <label>
              <span>
                <Search size={14} /> Search files, names, or tags
              </span>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search media"
              />
            </label>
            <label>
              File type
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="all">All files</option>
                <option value="video">Videos</option>
                <option value="image">Images</option>
                <option value="audio">Audio</option>
                <option value="attention">Needs attention</option>
              </select>
            </label>
            <span className="subtle" role="status">
              {filtered.length} of {assets.length} files
            </span>
          </div>
          <div className="media-layout">
            <div className="media-grid">
              {filtered.map((item) => {
                const source = project.scenes.find((s) => s.path === item.path);
                return (
                  <button
                    className={`media-card ${item.id === selected ? "selected" : ""}`}
                    aria-pressed={item.id === selected}
                    key={item.id}
                    onClick={() => select(item.id)}
                  >
                    <Thumbnail
                      key={`${item.id}-${scanRevision}`}
                      asset={item}
                    />
                    <span className="media-card-name">
                      {source?.name ?? item.name}
                    </span>
                    <span>
                      {item.error
                        ? "Needs attention"
                        : item.type === "audio"
                          ? `Audio · ${item.duration_seconds?.toFixed(1)} s`
                          : `${item.width} × ${item.height}${item.type === "video" ? ` · ${item.duration_seconds?.toFixed(1)} s` : " · Image"}`}
                    </span>
                    <span className="media-membership">
                      {source
                        ? source.enabled
                          ? "In show"
                          : "Disabled in show"
                        : "Not in show"}
                    </span>
                  </button>
                );
              })}
              {!filtered.length && (
                <div className="empty">
                  <p>No files match these filters.</p>
                  <button
                    onClick={() => {
                      setQuery("");
                      setKind("all");
                    }}
                  >
                    Clear filters
                  </button>
                </div>
              )}
            </div>
            {asset && (
              <section
                className="panel form-panel media-details"
                aria-label="Selected media"
              >
                <h2>{scene?.name ?? asset.name}</h2>
                <p className="source-path">{asset.path}</p>
                {!asset.error && (
                  <div className="media-metadata">
                    <span>
                      {asset.type === "audio"
                        ? "Master audio source"
                        : asset.type === "video"
                          ? "Video · muted"
                          : "Image"}
                    </span>
                    <span>{asset.codec}</span>
                    <span>
                      {asset.fps ? `${asset.fps.toFixed(2)} fps` : "Still"}
                    </span>
                    <span>{((asset.bytes ?? 0) / 1048576).toFixed(1)} MB</span>
                  </div>
                )}
                {asset.error ? (
                  <div className="media-error">
                    <p className="notice error">
                      This file could not be read. Fix or replace the file, then
                      scan again.
                    </p>
                    <details>
                      <summary>Technical details</summary>
                      <p>{asset.error}</p>
                    </details>
                  </div>
                ) : !scene ? (
                  <>
                    <p>Add this file as a reusable scene before playing it.</p>
                    <button
                      className="primary"
                      disabled={busy || !canEdit}
                      onClick={() =>
                        void action(async () => {
                          await request(`media/${asset.id}/add`, {
                            method: "POST",
                          });
                          await reload();
                          setMessage(
                            asset.type === "audio" || status.mode === "timeline"
                              ? "Source added. Assign it in Show → Timeline."
                              : "Added to the show. Choose a surface to play it.",
                          );
                        })
                      }
                    >
                      <Plus size={16} />
                      Add to show
                    </button>
                  </>
                ) : (
                  <>
                    {scene.type === "audio" || status.mode === "timeline" ? (
                      <p className="hint">
                        Assign this source in Show → Timeline. Audio belongs in
                        the Master audio lane; media belongs on a surface track.
                      </p>
                    ) : (
                      <>
                        <div className="media-play">
                          <label>
                            Target surface
                            <select
                              value={surfaceId}
                              onChange={(e) => setSurfaceId(e.target.value)}
                            >
                              {eligible.map((s) => (
                                <option key={s.id} value={s.id}>
                                  {s.name}
                                </option>
                              ))}
                            </select>
                          </label>
                          <button
                            className="primary"
                            disabled={
                              busy ||
                              !connected ||
                              !surfaceId ||
                              status.mode === "timeline" ||
                              !scene.enabled ||
                              dirty
                            }
                            onClick={() =>
                              void action(async () => {
                                await request("manual/play", {
                                  method: "POST",
                                  body: JSON.stringify({
                                    surface_id: surfaceId,
                                    scene_id: scene.id,
                                  }),
                                });
                                setMessage(
                                  `Playing ${scene.name} on ${eligible.find((s) => s.id === surfaceId)?.name}.`,
                                );
                              })
                            }
                          >
                            <Play size={16} />
                            Play on surface
                          </button>
                        </div>
                        <p className="hint">
                          Replaces the current cue, then returns to the
                          automatic queue.{" "}
                          {dirty
                            ? "Save or discard edits before playing."
                            : status.blackout
                              ? "Blackout is active; restore output to see it."
                              : "Uses the saved settings below."}
                        </p>
                      </>
                    )}
                    {!eligible.length && (
                      <p className="notice">
                        Enable a foreground surface in Project before playing
                        media.
                      </p>
                    )}
                    {draft && (
                      <form
                        className="media-settings"
                        onSubmit={(e) => {
                          e.preventDefault();
                          if (!canEdit || conflict) return;
                          void action(async () => {
                            const normalized = {
                              ...draft,
                              tags: draft.tags
                                .map((tag) => tag.trim())
                                .filter(Boolean),
                            };
                            await save({
                              ...project,
                              scenes: project.scenes.map((s) =>
                                s.id === draft.id ? normalized : s,
                              ),
                            });
                            setDraft(normalized);
                            setBase(normalized);
                            setMessage("Playback settings saved.");
                          });
                        }}
                      >
                        <div className="section-heading">
                          <h3>Scene settings</h3>
                          <span className="badge">
                            {dirty ? "Unsaved edits" : "Saved"}
                          </span>
                        </div>
                        {conflict && (
                          <p role="alert" className="notice error">
                            This project changed while you were editing. Discard
                            edits to load the current settings.
                          </p>
                        )}
                        <fieldset
                          disabled={!canEdit || busy}
                          className="settings-fields"
                        >
                          <label>
                            Display name
                            <input
                              value={draft.name}
                              required
                              onChange={(e) => update({ name: e.target.value })}
                            />
                          </label>
                          <label className="check-label">
                            <input
                              type="checkbox"
                              checked={draft.enabled}
                              onChange={(e) =>
                                update({ enabled: e.target.checked })
                              }
                            />
                            Enabled in show
                          </label>
                          {draft.type !== "audio" && (
                            <label>
                              Fit to surface
                              <select
                                value={draft.fit}
                                onChange={(e) =>
                                  update({ fit: e.target.value })
                                }
                              >
                                <option value="cover">Fill · crop edges</option>
                                <option value="contain">
                                  Fit · show entire image
                                </option>
                                <option value="stretch">
                                  Stretch · may distort
                                </option>
                                <option value="native">
                                  Native · original pixel size
                                </option>
                              </select>
                            </label>
                          )}
                          {draft.type === "video" && (
                            <>
                              <label>
                                Playback length
                                <select
                                  value={draft.playback}
                                  onChange={(e) =>
                                    update({ playback: e.target.value })
                                  }
                                >
                                  <option value="full_clip">
                                    Full clip, including fades
                                  </option>
                                  <option value="timed">
                                    Use project hold time
                                  </option>
                                </select>
                              </label>
                              {draft.playback === "timed" && (
                                <label>
                                  When the clip ends
                                  <select
                                    value={draft.end_behavior}
                                    onChange={(e) =>
                                      update({ end_behavior: e.target.value })
                                    }
                                  >
                                    <option value="hold">
                                      Hold the last frame
                                    </option>
                                    <option value="loop">
                                      Loop until the cue ends
                                    </option>
                                  </select>
                                </label>
                              )}
                              <div className="trim-fields">
                                <label>
                                  Start at (seconds)
                                  <input
                                    type="number"
                                    min="0"
                                    step="any"
                                    max={asset.duration_seconds}
                                    value={draft.start_seconds ?? 0}
                                    onChange={(e) =>
                                      update({
                                        start_seconds: Number(e.target.value),
                                      })
                                    }
                                  />
                                </label>
                                <label>
                                  End at (seconds)
                                  <input
                                    type="number"
                                    min="0"
                                    step="any"
                                    max={asset.duration_seconds}
                                    value={draft.end_seconds ?? ""}
                                    placeholder={asset.duration_seconds?.toFixed(
                                      2,
                                    )}
                                    onChange={(e) =>
                                      update({
                                        end_seconds:
                                          e.target.value === ""
                                            ? null
                                            : Number(e.target.value),
                                      })
                                    }
                                  />
                                </label>
                              </div>
                              <p className="hint">
                                Leave End empty to use the full file. Fades are
                                included in full-clip duration.
                              </p>
                            </>
                          )}
                          <details>
                            <summary>
                              {draft.type === "audio"
                                ? "Tags"
                                : "Crop position & tags"}
                            </summary>
                            {draft.type !== "audio" && (
                              <>
                                <p className="hint">
                                  Crop center: 0 is left/top, 1 is right/bottom.
                                  Centered is 0.5. Applies to cropped content;
                                  letterboxing stays centered.
                                </p>
                                <div className="trim-fields">
                                  {(["X", "Y"] as const).map((axis, i) => (
                                    <label key={axis}>
                                      Crop center {axis}
                                      <input
                                        type="number"
                                        min="0"
                                        max="1"
                                        step="any"
                                        disabled={
                                          draft.fit === "stretch" ||
                                          draft.fit === "contain"
                                        }
                                        value={draft.focal_point?.[i] ?? 0.5}
                                        onChange={(e) => {
                                          const point: [number, number] = [
                                            ...(draft.focal_point ?? [
                                              0.5, 0.5,
                                            ]),
                                          ];
                                          point[i] = Number(e.target.value);
                                          update({ focal_point: point });
                                        }}
                                      />
                                    </label>
                                  ))}
                                </div>
                              </>
                            )}
                            <label>
                              Tags (comma separated)
                              <input
                                value={draft.tags.join(", ")}
                                onChange={(e) =>
                                  update({
                                    tags: e.target.value
                                      .split(",")
                                      .map((t) => t.trim()),
                                  })
                                }
                              />
                            </label>
                          </details>
                        </fieldset>
                        <div className="editor-actions">
                          <button
                            type="button"
                            disabled={!dirty || busy}
                            onClick={() => {
                              setDraft(scene);
                              setBase(scene);
                              setMessage("");
                              setError("");
                            }}
                          >
                            Discard edits
                          </button>
                          <button
                            type="submit"
                            className="primary"
                            disabled={!canEdit || busy || !dirty || conflict}
                          >
                            <Save size={16} />
                            {busy ? "Saving…" : "Save settings"}
                          </button>
                        </div>
                      </form>
                    )}
                  </>
                )}
              </section>
            )}
          </div>
        </>
      )}
      <details className="decoder-details">
        <summary>
          Decoder details · {status.renderer.decoder?.state ?? "IDLE"}
        </summary>
        <p>
          {status.renderer.decoder?.backend ?? "FFmpeg / PyAV"}
          {status.renderer.decoder?.pts != null
            ? ` · ${status.renderer.decoder.pts.toFixed(2)} s source position`
            : ""}
          . CPU decode; GPU composition. Audio muted.
        </p>
        {status.renderer.decoder?.error && (
          <p role="alert">{status.renderer.decoder.error}</p>
        )}
      </details>
      <DiscardDialog
        open={pendingSelection !== null}
        title="Discard these media edits?"
        description="The saved scene will stay unchanged. Keep editing to save these settings first."
        onKeep={() => setPendingSelection(null)}
        onDiscard={() => {
          setDraft(null);
          setBase(null);
          setSelected(pendingSelection ?? "");
          setPendingSelection(null);
          setMessage("");
        }}
      />
    </section>
  );
}
