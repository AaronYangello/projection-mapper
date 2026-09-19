import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { UploadPanel } from "./UploadPanel";
import type { Capabilities, Job, Project, Status } from "./types";
type DeploymentState = {
  active: string | null;
  previous: string | null;
  deployments: {
    id: string;
    built_at: number;
    source_project: { name: string };
    profile: { name: string };
    encoder_backend: string;
  }[];
};
const descriptions: Record<string, string> = {
  video_recompile:
    "Video encoding required: source content, clip timing, layout or profile changed.",
  audio_remux: "Audio remux required. Encoded video will be reused.",
  manifest_only:
    "Metadata update only: opacity, lighting or loop settings changed. No video encoding.",
  current:
    "Build current. Destination mapping changes do not require a rebuild.",
};
export function BuildDeploy({
  project,
  status,
  revision,
  capabilities,
  dirty,
}: {
  project: Project;
  status: Status;
  revision: number;
  capabilities: Capabilities | null;
  dirty: boolean;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [latest, setLatest] = useState<any>(null);
  const [error, setError] = useState("");
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [staleness, setStaleness] = useState(
    "Check build inputs to compare source hashes and saved settings.",
  );
  const [target, setTarget] = useState({ url: "", token_saved: false });
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState("");
  const [token, setTokenValue] = useState("");
  const [connection, setConnection] = useState<any>(null);
  const [deployments, setDeployments] = useState<DeploymentState>({
    active: null,
    previous: null,
    deployments: [],
  });
  const [confirmation, setConfirmation] = useState<{
    kind: "remote" | "activate" | "rollback" | "unload";
    id: string;
    active: string | null;
  } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const buildProfile =
    project.canvas.width === 3840 && project.canvas.height === 2160
      ? "pi5-4k30"
      : "pi4-1080p";
  const active = !!job && ["queued", "running"].includes(job.state);
  const stopped = status.transport === "READY" && !status.calibration;
  useEffect(() => {
    if (confirmation && !dialog.current?.open) dialog.current?.showModal();
  }, [confirmation]);
  async function refresh() {
    try {
      setLatest(await request("builds/latest"));
      setDeployments(await request("deployments"));
      if (capabilities?.role === "authoring") {
        const t = await request<typeof target>("target");
        setTarget(t);
        setUrl(t.url);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void refresh();
  }, [capabilities?.role]);
  useEffect(() => {
    setStaleness(
      "Saved configuration changed. Check build inputs for the exact work required.",
    );
  }, [revision]);
  async function follow(initial: Job) {
    let current = initial;
    setJob(current);
    while (["queued", "running"].includes(current.state)) {
      await new Promise((r) => setTimeout(r, 400));
      current = await request<Job>(`builds/${current.id}`);
      setJob(current);
    }
    if (current.state !== "complete")
      throw new Error(current.error ?? "Job cancelled");
    return current.result!;
  }
  async function run(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function build(andDeploy = false) {
    const result = await follow(
      await request<Job>("builds", {
        method: "POST",
        body: JSON.stringify({ revision, profile: buildProfile }),
      }),
    );
    setLatest(result);
    setStaleness(
      "Build current. Destination mapping changes do not require a rebuild.",
    );
    if (andDeploy) {
      const connected = await follow(
        await request<Job>("target/test", { method: "POST" }),
      );
      setConnection(connected);
      setConfirmation({
        kind: "remote",
        id: result.manifest.id,
        active: connected.active,
      });
    }
  }
  async function confirm() {
    if (!confirmation) return;
    const current = confirmation;
    setConfirmation(null);
    dialog.current?.close();
    if (current.kind === "remote")
      await follow(
        await request<Job>("target/deploy", {
          method: "POST",
          body: JSON.stringify({
            confirmed: true,
            expected_active: current.active,
            bundle_id: current.id,
            target_url: target.url,
          }),
        }),
      );
    else
      await request(
        current.kind === "rollback" || current.kind === "unload"
          ? `deployments/${current.kind}`
          : `deployments/${current.id}/activate`,
        {
          method: "POST",
          body: JSON.stringify({
            confirmed: true,
            expected_active: current.active,
          }),
        },
      );
    await refresh();
  }
  async function exportBundle() {
    const result = await request<{ url: string }>("builds/latest/download", {
      method: "POST",
    });
    const link = document.createElement("a");
    link.href = result.url;
    link.download = `${project.id}.pshow`;
    link.click();
  }
  return (
    <div className="build-deploy">
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {capabilities?.role === "authoring" && (
        <section className="panel form-panel">
          <h2>Build on this Mac</h2>
          <p>
            {buildProfile} · one 1920×1080 H.264 atlas at 30 fps, up to four
            concurrent media surfaces, sixteen lights, and one stereo audio
            program. The Pi 5 profile preserves the configured 3840×2160 canvas
            and its projector viewports.
          </p>
          {!capabilities.compiler && (
            <p className="notice">{capabilities.compiler_reason}</p>
          )}
          {dirty && (
            <p className="notice warning">
              Save or discard your timeline draft before building. Builds use
              the saved project.
            </p>
          )}
          <p role="status">{staleness}</p>
          <div className="button-row">
            <button
              disabled={active || !capabilities.compiler || dirty}
              onClick={() =>
                void run(async () => {
                  const result = await follow(
                    await request<Job>("builds/inspect", {
                      method: "POST",
                      body: JSON.stringify({ revision }),
                    }),
                  );
                  setStaleness(descriptions[result.change]);
                })
              }
            >
              Check build inputs
            </button>
            <button
              className="primary"
              disabled={active || dirty || !capabilities.compiler}
              onClick={() => void run(() => build())}
            >
              Build
            </button>
            <button
              disabled={!latest || active}
              onClick={() => void run(exportBundle)}
            >
              Export bundle
            </button>
            <button
              disabled={!latest || active || !stopped || loadingPreview}
              onClick={() =>
                void run(async () => {
                  setLoadingPreview(true);
                  try {
                    await request("builds/latest/preview", { method: "POST" });
                  } finally {
                    setLoadingPreview(false);
                  }
                })
              }
            >
              {loadingPreview ? "Validating preview…" : "Preview built show"}
            </button>
            {status.deployment_kind === "preview" && (
              <button
                disabled={!stopped}
                onClick={() =>
                  void run(() =>
                    request("builds/preview/unload", { method: "POST" }),
                  )
                }
              >
                Unload preview
              </button>
            )}
            <button
              disabled={
                active || dirty || !capabilities.compiler || !target.url
              }
              onClick={() => void run(() => build(true))}
            >
              Build & Deploy
            </button>
          </div>
          {latest && (
            <dl className="build-details">
              <dt>Latest bundle</dt>
              <dd>{latest.manifest.id}</dd>
              <dt>Built</dt>
              <dd>
                {new Date(latest.manifest.built_at * 1000).toLocaleString()}
              </dd>
              <dt>Encoder</dt>
              <dd>
                {latest.manifest.encoder_backend} · {latest.elapsed_seconds}s
                build
              </dd>
              <dt>Reused work</dt>
              <dd>
                Video {latest.reused_video ? "reused" : "encoded"} · audio{" "}
                {latest.reused_audio ? "reused" : "muxed"}
              </dd>
            </dl>
          )}
        </section>
      )}
      {job && (
        <section className="panel form-panel" aria-label="Job progress">
          <h3>
            {job.kind} · {job.state}
          </h3>
          <progress max={1} value={job.progress} />
          <p role="status">
            {job.message} · {Math.round(job.progress * 100)}%
          </p>
          {job.error && <p role="alert">{job.error}</p>}
          {active && (
            <button
              disabled={job.progress >= 0.98 && job.kind === "deploy"}
              onClick={() =>
                void run(async () => {
                  await request(`builds/${job.id}`, { method: "DELETE" });
                })
              }
            >
              Cancel {job.kind}
            </button>
          )}
          {job.result?.activation_confirmed && (
            <p className="notice success">
              Target confirmed active deployment: {job.result.active}
            </p>
          )}
        </section>
      )}
      {capabilities?.role === "authoring" && (
        <section className="panel form-panel">
          <h2>Private deployment target</h2>
          <p>
            Use your Pi's Tailscale Serve HTTPS address or deliberate private
            LAN address. A connection test does not deploy. Settings stay on
            this machine, outside project YAML and bundles.
          </p>
          {!editing ? (
            <>
              <p>
                {target.url || "No target configured"} · Token{" "}
                {target.token_saved ? "•••••••• saved" : "not saved"}
              </p>
              <button
                onClick={() => {
                  setEditing(true);
                  setTokenValue("");
                }}
              >
                Edit target
              </button>
            </>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void run(async () => {
                  const t = await request<typeof target>("target", {
                    method: "PUT",
                    body: JSON.stringify({ url, token: token || null }),
                  });
                  setTarget(t);
                  setEditing(false);
                  setTokenValue("");
                  setConnection(null);
                });
              }}
            >
              <label>
                Pi URL
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  required
                  placeholder="https://your-pi.your-tailnet.ts.net"
                />
              </label>
              <label>
                Bearer token
                <input
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setTokenValue(e.target.value)}
                  placeholder={
                    target.token_saved
                      ? "Leave blank to keep saved token"
                      : "Application token"
                  }
                />
              </label>
              <button>Save target</button>
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setTokenValue("");
                  setUrl(target.url);
                }}
              >
                Cancel
              </button>
            </form>
          )}
          <button
            disabled={active || !target.url || editing}
            onClick={() =>
              void run(async () =>
                setConnection(
                  await follow(
                    await request<Job>("target/test", { method: "POST" }),
                  ),
                ),
              )
            }
          >
            Test connection
          </button>
          {connection && (
            <p role="status">
              Connected · {connection.capabilities.role} · active{" "}
              {connection.active ?? "none"}
            </p>
          )}
        </section>
      )}
      <section className="panel form-panel">
        <h2>Deployments on this machine</h2>
        {!capabilities?.deployment_write && (
          <p className="notice">{capabilities?.deployment_reason}</p>
        )}
        <p>
          Current:{" "}
          <strong>{deployments.active ?? "No installed bundle"}</strong>
        </p>
        <p>Previous: {deployments.previous ?? "None"}</p>
        <p className="subtle">
          Activation preserves local projector mapping. It replaces the show
          program and leaves transport stopped. Start explicitly after checking
          the output.
        </p>
        <UploadPanel
          bundle
          enabled={!active && !!capabilities?.deployment_write}
          onComplete={() => void refresh()}
        />
        <button disabled={active} onClick={() => void refresh()}>
          Refresh deployments
        </button>
        <button
          disabled={
            !deployments.active ||
            !stopped ||
            active ||
            !capabilities?.deployment_write
          }
          onClick={() =>
            setConfirmation({
              kind: "unload",
              id: deployments.active!,
              active: deployments.active,
            })
          }
        >
          Unload bundle
        </button>
        <button
          disabled={
            !deployments.previous ||
            !stopped ||
            active ||
            !capabilities?.deployment_write
          }
          onClick={() =>
            setConfirmation({
              kind: "rollback",
              id: deployments.previous!,
              active: deployments.active,
            })
          }
        >
          Roll back
        </button>
        {deployments.deployments.map((d) => (
          <div className="deployment-row" key={d.id}>
            <strong>{d.source_project.name}</strong>
            <span>
              {d.id.slice(0, 12)} · {d.profile.name} ·{" "}
              {new Date(d.built_at * 1000).toLocaleString()}
            </span>
            <button
              disabled={
                d.id === deployments.active ||
                !stopped ||
                active ||
                !capabilities?.deployment_write
              }
              onClick={() =>
                setConfirmation({
                  kind: "activate",
                  id: d.id,
                  active: deployments.active,
                })
              }
            >
              {d.id === deployments.active ? "Active" : "Activate"}
            </button>
          </div>
        ))}
      </section>
      {confirmation && (
        <dialog
          ref={dialog}
          onCancel={() => setConfirmation(null)}
          aria-labelledby="deploy-title"
        >
          <h2 id="deploy-title">
            {confirmation.kind === "rollback"
              ? "Restore previous deployment?"
              : confirmation.kind === "unload"
                ? "Unload the active bundle?"
                : "Replace active deployment?"}
          </h2>
          <p>
            Target:{" "}
            {confirmation.kind === "remote" ? target.url : "this machine"}
          </p>
          <p>
            {confirmation.kind === "unload" ? "Unload" : "Activate"}{" "}
            <code>{confirmation.id}</code>
          </p>
          <p>
            {confirmation.kind === "unload" ? (
              "Return to the local project. The bundle stays available for rollback."
            ) : (
              <>
                Replace{" "}
                <code>{confirmation.active ?? "no current bundle"}</code>.
              </>
            )}
            The target must be stopped. Its physical mapping will be preserved.
          </p>
          <div className="button-row">
            <button
              autoFocus
              onClick={() => {
                setConfirmation(null);
                dialog.current?.close();
              }}
            >
              Keep current show
            </button>
            <button className="primary" onClick={() => void run(confirm)}>
              {confirmation.kind === "unload"
                ? "Confirm unload"
                : "Confirm activation"}
            </button>
          </div>
        </dialog>
      )}
    </div>
  );
}
