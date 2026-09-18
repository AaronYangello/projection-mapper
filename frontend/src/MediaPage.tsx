import { useEffect, useState } from "react";
import {
  Film,
  Image as ImageIcon,
  Play,
  Plus,
  RefreshCw,
  Save,
} from "lucide-react";
import { getToken, request } from "./api";
import type { MediaAsset, Project, Status } from "./types";

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
    <img src={url} alt={`${asset.name} thumbnail`} />
  ) : (
    <div className="media-placeholder">
      {asset.type === "video" ? <Film size={28} /> : <ImageIcon size={28} />}
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
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState("");
  const eligible = project.surfaces.filter(
    (s) =>
      s.enabled &&
      s.foreground_enabled &&
      project.projectors.some((p) => p.id === s.projector_id && p.enabled),
  );
  const [surfaceId, setSurfaceId] = useState(eligible[0]?.id ?? "");
  const [fit, setFit] = useState("cover");
  const [focal, setFocal] = useState<[number, number]>([0.5, 0.5]);
  const [scanRevision, setScanRevision] = useState(0);
  const [playback, setPlayback] = useState("full_clip");
  const [endBehavior, setEndBehavior] = useState("hold");
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState("");
  const asset = assets.find((a) => a.id === selected);
  const scene = project.scenes.find(
    (s) => s.path === asset?.path && s.type !== "color",
  );
  const stopped = status.transport === "READY";
  useEffect(() => {
    void request<{ assets: MediaAsset[] }>("media")
      .then((data) => {
        setAssets(data.assets);
        setSelected(data.assets[0]?.id ?? "");
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setFit(scene?.fit ?? "cover");
    setFocal(scene?.focal_point ?? [0.5, 0.5]);
    setPlayback(scene?.playback ?? "full_clip");
    setEndBehavior(scene?.end_behavior ?? "hold");
    setStart(scene?.start_seconds ?? 0);
    setEnd(scene?.end_seconds == null ? "" : String(scene.end_seconds));
  }, [scene]);
  async function action(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
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
      <div className="section-heading">
        <div>
          <h2>Local media</h2>
          <p>
            Add files to this project's <code>media/</code> folder, then scan.
          </p>
        </div>
        <button
          disabled={!stopped || busy || !connected}
          onClick={() =>
            void action(async () => {
              const data = await request<{ assets: MediaAsset[] }>(
                "media/scan",
                { method: "POST" },
              );
              setAssets(data.assets);
              setScanRevision((value) => value + 1);
              setSelected(data.assets[0]?.id ?? "");
            })
          }
        >
          <RefreshCw size={15} />
          {busy ? "Working…" : "Scan media"}
        </button>
      </div>
      {error && (
        <div role="alert" className="notice error">
          {error}
        </div>
      )}
      {!stopped && (
        <p className="notice">
          Stop the show to scan, add, or change media settings. Play now works
          while the show is running.
        </p>
      )}
      {!assets.length ? (
        <div className="panel form-panel">
          <h3>No local media yet</h3>
          <p>
            Copy an MP4, MOV, MKV, WebM, PNG, JPEG, or WebP into the project's
            media folder. Scanning reads metadata and makes a thumbnail.
          </p>
          <p className="hint">
            For the included example, run{" "}
            <code>.venv/bin/python scripts/download_sample.py</code> from the
            repository, then scan.
          </p>
        </div>
      ) : (
        <div className="media-layout">
          <div className="media-grid">
            {assets.map((item) => (
              <button
                className={`media-card ${item.id === selected ? "selected" : ""}`}
                aria-pressed={item.id === selected}
                key={item.id}
                onClick={() => setSelected(item.id)}
              >
                <Thumbnail key={`${item.id}-${scanRevision}`} asset={item} />
                <span className="media-card-name">{item.name}</span>
                <span>
                  {item.error
                    ? "Needs attention"
                    : `${item.width} × ${item.height} · ${item.type === "video" ? `${item.duration_seconds?.toFixed(1)}s` : item.type}`}
                </span>
              </button>
            ))}
          </div>
          {asset && (
            <section className="panel form-panel media-details">
              <div className="eyebrow">
                {asset.type === "video" ? "NATIVE VIDEO" : "IMAGE SOURCE"}
              </div>
              <h3>{asset.name}</h3>
              <p>{asset.path}</p>
              {asset.error ? (
                <div className="notice error">{asset.error}</div>
              ) : (
                <>
                  <div className="media-metadata">
                    <span>{asset.codec}</span>
                    <span>
                      {asset.fps
                        ? `${asset.fps.toFixed(2)} fps`
                        : "Still image"}
                    </span>
                    <span>{((asset.bytes ?? 0) / 1048576).toFixed(1)} MB</span>
                  </div>
                  {!scene ? (
                    <button
                      className="primary"
                      disabled={busy || !stopped || !connected}
                      onClick={() =>
                        void action(async () => {
                          await request(`media/${asset.id}/add`, {
                            method: "POST",
                          });
                          await reload();
                        })
                      }
                    >
                      <Plus size={15} />
                      Add to show
                    </button>
                  ) : (
                    <>
                      <div className="media-play">
                        <label>
                          Play on surface
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
                            busy || !connected || !surfaceId || !scene.enabled
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
                            })
                          }
                        >
                          <Play size={16} />
                          Play now
                        </button>
                      </div>
                      <p className="hint">
                        Plays one cue, then returns to the planned queue. Pause
                        and blackout preserve the video position. Audio is
                        muted.
                      </p>
                      <div className="media-settings">
                        <label>
                          Fit mode
                          <select
                            value={fit}
                            disabled={!stopped}
                            onChange={(e) => setFit(e.target.value)}
                          >
                            {["cover", "contain", "stretch", "native"].map(
                              (f) => (
                                <option key={f} value={f}>
                                  {f[0].toUpperCase() + f.slice(1)}
                                </option>
                              ),
                            )}
                          </select>
                        </label>
                        <div className="trim-fields">
                          {(["X", "Y"] as const).map((axis, index) => (
                            <label key={axis}>
                              Focal point {axis}
                              <input
                                type="number"
                                min="0"
                                max="1"
                                step="0.05"
                                disabled={!stopped || fit === "stretch"}
                                value={focal[index]}
                                onChange={(e) => {
                                  const next: [number, number] = [...focal];
                                  next[index] = Number(e.target.value);
                                  setFocal(next);
                                }}
                              />
                            </label>
                          ))}
                        </div>
                        {asset.type === "video" && (
                          <>
                            <label>
                              Playback length
                              <select
                                value={playback}
                                disabled={!stopped}
                                onChange={(e) => setPlayback(e.target.value)}
                              >
                                <option value="full_clip">
                                  Full clip, including fades
                                </option>
                                <option value="timed">
                                  Show's configured timing
                                </option>
                              </select>
                            </label>
                            <label>
                              At end of video
                              <select
                                value={endBehavior}
                                disabled={!stopped || playback === "full_clip"}
                                onChange={(e) => setEndBehavior(e.target.value)}
                              >
                                <option value="hold">Hold final frame</option>
                                <option value="loop">
                                  Loop during timed cue
                                </option>
                              </select>
                            </label>
                            <div className="trim-fields">
                              <label>
                                Clip start (s)
                                <input
                                  type="number"
                                  min="0"
                                  step="0.1"
                                  disabled={!stopped}
                                  value={start}
                                  onChange={(e) =>
                                    setStart(Number(e.target.value))
                                  }
                                />
                              </label>
                              <label>
                                Clip end (s)
                                <input
                                  type="number"
                                  min="0"
                                  step="0.1"
                                  disabled={!stopped}
                                  placeholder={asset.duration_seconds?.toFixed(
                                    2,
                                  )}
                                  value={end}
                                  onChange={(e) => setEnd(e.target.value)}
                                />
                              </label>
                            </div>
                          </>
                        )}
                        <button
                          disabled={!stopped || busy || !connected}
                          onClick={() =>
                            void action(async () => {
                              const next = {
                                ...scene,
                                fit,
                                focal_point: focal,
                                ...(scene.type === "video"
                                  ? {
                                      playback,
                                      end_behavior: endBehavior,
                                      start_seconds: start,
                                      end_seconds:
                                        end === "" ? null : Number(end),
                                    }
                                  : {}),
                              };
                              await save({
                                ...project,
                                scenes: project.scenes.map((s) =>
                                  s.id === scene.id ? next : s,
                                ),
                              });
                            })
                          }
                        >
                          <Save size={15} />
                          Save playback settings
                        </button>
                      </div>
                    </>
                  )}
                </>
              )}
            </section>
          )}
        </div>
      )}
      <section className="panel decoder-panel">
        <span>Native decoder</span>
        <strong>{status.renderer.decoder?.state ?? "IDLE"}</strong>
        <span>{status.renderer.decoder?.backend ?? "FFmpeg / PyAV"}</span>
        <span>
          {status.renderer.decoder?.pts != null
            ? `${status.renderer.decoder.pts.toFixed(2)}s source position`
            : ""}
        </span>
      </section>
    </section>
  );
}
