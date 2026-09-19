import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Box,
  ChevronRight,
  Circle,
  CircleStop,
  Columns3,
  Layers,
  Monitor,
  Moon,
  Pause,
  Play,
  Radio,
  RotateCcw,
  Settings2,
  SkipForward,
  Sun,
  Waves,
  X,
} from "lucide-react";
import { DiscardDialog } from "./editing";
import { setToken } from "./api";
import { ShowPage, TimelinePlayback } from "./ShowPage";
import { AudioSettings } from "./AudioSettings";
import { MediaPage } from "./MediaPage";
import { MappingPage } from "./MappingPage";
import { ProjectEditor } from "./ProjectEditor";
import { useEngine, usePreview } from "./useEngine";
import type { Project, Status } from "./types";

const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;
const words = (text: string) =>
  ({ FOREGROUND: "Playing", IDLE: "Stopped", GAP: "Between cues" })[text] ??
  text.toLowerCase().replaceAll("_", " ");

function Output({
  project,
  status,
  connected,
  visible,
}: {
  project: Project;
  status: Status;
  connected: boolean;
  visible: boolean;
}) {
  const live = visible && connected && status.renderer.status === "LIVE";
  const previewEnabled = live && project.canvas.preview_fps > 0;
  const preview = usePreview(previewEnabled, project.canvas.preview_fps || 1);
  return (
    <section className="panel output-panel">
      <div className="panel-heading">
        <div>
          <Monitor size={16} />
          <h2>Projected output</h2>
        </div>
        <span className="subtle">
          {project.canvas.width} × {project.canvas.height}
        </span>
      </div>
      <div
        className="output-image"
        style={{ aspectRatio: project.canvas.width / project.canvas.height }}
      >
        {preview ? (
          <img src={preview} alt="Live native GPU render of mapped surfaces" />
        ) : (
          <div className="output-empty">
            <Monitor size={32} />
            <strong>
              {previewEnabled
                ? "Receiving GPU preview…"
                : live
                  ? "Live preview disabled"
                  : "Native output unavailable"}
            </strong>
            <span>The scheduler and controls remain accessible.</span>
          </div>
        )}
        {status.blackout && (
          <div className="blackout-overlay">
            <Moon size={22} />
            <span>Output blacked out</span>
          </div>
        )}
      </div>
      <div className="output-caption">
        <span>
          <i className={`dot ${live ? "green" : "amber"}`} />
          {live ? "Native GPU output" : "Renderer offline"}
        </span>
        <span>
          {project.canvas.preview_fps > 0
            ? `Preview at ${project.canvas.preview_fps} fps · ${project.canvas.preview_width}px wide`
            : "Preview disabled"}{" "}
          · output {status.renderer.fps.toFixed(1)} fps
        </span>
      </div>
    </section>
  );
}

function CurrentCue({ project, status }: { project: Project; status: Status }) {
  const active = status.current && status.transport !== "READY";
  const surface = project.surfaces.find(
    (s) => s.id === status.current?.surface_id,
  );
  const scene = project.scenes.find((s) => s.id === status.current?.scene_id);
  const total = status.current
    ? status.current.fade_in + status.current.hold + status.current.fade_out
    : 1;
  return (
    <section className="panel current-panel">
      <div className="eyebrow">
        <span className="small-dot" />
        CURRENT CUE
        <span className="phase">
          {status.blackout
            ? "Blackout"
            : active
              ? words(status.phase)
              : "Show stopped"}
        </span>
      </div>
      <div className="current-body">
        <div
          className="scene-swatch"
          style={{
            background: active ? (scene?.color ?? "#506d63") : "#26302e",
          }}
        >
          {active && scene?.type === "video" ? (
            <Play size={22} />
          ) : (
            <Waves size={22} />
          )}
        </div>
        <div>
          <h2>{active ? scene?.name : "Show stopped"}</h2>
          <p>
            {active
              ? `${surface?.name} · ${scene?.type === "color" ? "Solid color" : scene?.type === "video" ? "Video" : "Image"}`
              : "Ambient content remains on. Start show plays the queue; Blackout hides all output."}
          </p>
        </div>
        <div className="remaining">
          <strong>{clock(active ? status.remaining : 0)}</strong>
          <span>{status.phase === "GAP" ? "until next cue" : "remaining"}</span>
        </div>
      </div>
      <div className="progress-track">
        <span
          style={{
            width: active
              ? `${Math.min(100, (status.elapsed / total) * 100)}%`
              : "0%",
          }}
        />
      </div>
      <div className="current-meta">
        <span>
          Fade in{" "}
          {Number(
            (status.current?.fade_in ?? project.show.fade_in_seconds).toFixed(
              2,
            ),
          )}
          s <ChevronRight size={12} /> Hold <ChevronRight size={12} /> Fade out{" "}
          {Number(
            (status.current?.fade_out ?? project.show.fade_out_seconds).toFixed(
              2,
            ),
          )}
          s
        </span>
        <span>
          {status.current?.manual
            ? "Manual cue · returns to queue"
            : "Automatic cue"}{" "}
          · {Math.round(status.opacity * 100)}% opacity
        </span>
      </div>
    </section>
  );
}

function Queue({ project, status }: { project: Project; status: Status }) {
  return (
    <section className="panel queue-panel">
      <div className="panel-heading">
        <div>
          <Columns3 size={16} />
          <h2>Up next</h2>
        </div>
        <span className="badge">Automatic</span>
      </div>
      <p className="queue-intro">
        Planned order · one foreground cue at a time.
      </p>
      <ol className="queue">
        {status.queue.map((cue, index) => {
          const scene = project.scenes.find((s) => s.id === cue.scene_id);
          return (
            <li key={cue.id}>
              <span className="queue-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span
                className="color-chip"
                style={{ background: scene?.color ?? "#506d63" }}
              />
              <div>
                <strong>{scene?.name}</strong>
                <span>
                  {project.surfaces.find((s) => s.id === cue.surface_id)?.name}
                </span>
              </div>
              <span className="duration">
                {Math.round(cue.fade_in + cue.hold + cue.fade_out)}s
              </span>
            </li>
          );
        })}
      </ol>
      {!status.queue.length && (
        <p className="empty">
          Enable a surface and a scene to build the queue.
        </p>
      )}
      <div className="queue-foot">
        <RotateCcw size={14} />
        <span>
          Each eligible item plays once before reshuffling.
          <br />
          No immediate repeats when possible.
        </span>
      </div>
    </section>
  );
}

export default function App() {
  const engine = useEngine();
  const { project, status, connected, error, busy } = engine;
  const [page, setPage] = useState(
    () => sessionStorage.getItem("projection-page") || "Playback",
  );
  const [mappingDirty, setMappingDirty] = useState(false);
  const [mediaWarningsShown, setMediaWarningsShown] = useState<string[]>([]);
  const [destination, setDestination] = useState<string | null>(null);
  const [mappingSurface, setMappingSurface] = useState<string | undefined>();
  const needsCompiledPreview =
    status?.mode === "timeline" &&
    !!project?.show.timeline.audio &&
    !status?.deployment;
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [page]);
  function navigate(next: string) {
    if (page === "Mapping" && mappingDirty && next !== page)
      setDestination(next);
    else {
      setPage(next);
      sessionStorage.setItem("projection-page", next);
    }
  }
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (
        event.code !== "Space" ||
        event.repeat ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        !connected ||
        busy ||
        !status ||
        status.blackout ||
        needsCompiledPreview ||
        document.querySelector("dialog[open]") ||
        (event.target instanceof Element &&
          event.target.closest(
            "input,textarea,select,button,a,[contenteditable=true]",
          ))
      )
        return;
      event.preventDefault();
      void engine.command(
        status.transport === "RUNNING"
          ? "pause"
          : status.transport === "PAUSED"
            ? "resume"
            : "start",
      );
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [connected, busy, status, engine.command, needsCompiledPreview]);
  const [auth, setAuth] = useState("");
  const visibleWarnings =
    status?.warnings.filter(
      (w) =>
        !w.startsWith("Test pattern active:") &&
        !(page === "Media" && mediaWarningsShown.includes(w)),
    ) ?? [];
  const disabled = busy || !connected;
  const running = status?.transport === "RUNNING";
  const live =
    connected && status?.renderer.status === "LIVE" && !status.blackout;
  const nav = [
    { name: "Playback", icon: Radio },
    { name: "Show", icon: Columns3 },
    { name: "Mapping", icon: Layers },
    { name: "Media", icon: Monitor },
    { name: "Project", icon: Settings2 },
    { name: "Diagnostics", icon: Activity },
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("Playback");
          }}
        >
          <span className="brand-mark">
            <Box size={23} />
          </span>
          <span>
            Projection<span className="brand-sub">SHOW ENGINE</span>
          </span>
        </a>

        <nav aria-label="Primary navigation">
          {nav.map(({ name, icon: Icon }) => (
            <button
              key={name}
              aria-current={page === name ? "page" : undefined}
              className={page === name ? "nav-active" : ""}
              onClick={() => navigate(name)}
            >
              <Icon size={18} />
              {name}
              {page === name && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-project">
          <span className="eyebrow">ACTIVE PROJECT</span>
          <strong>{project?.name ?? "Connecting…"}</strong>
          <span>
            <i className={`dot ${connected ? "green" : "amber"}`} />
            {connected ? "Connected locally" : "Reconnecting"}
          </span>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumb">
            Project <ChevronRight size={14} />
            <span>{project?.name ?? "Projection Show Engine"}</span>
          </div>
          <span className="connection">
            <i className={`dot ${connected ? "green" : "amber"}`} />
            {connected ? "Engine connected" : "Connection lost"}
          </span>
        </header>
        <div className="page-content">
          <div className="page-heading">
            <div>
              <h1>{page}</h1>
              <p>
                {page === "Playback"
                  ? status?.mode === "timeline"
                    ? "Current show time, mapped output and surface brightness. Space to pause or resume."
                    : "Current output and automatic queue. Space to pause or resume."
                  : page === "Show"
                    ? "Author surface timing, opacity, audio, and deployment bundles."
                    : page === "Project"
                      ? "Outputs, surfaces, and automatic show settings."
                      : page === "Mapping"
                        ? "Align each surface with the projector output."
                        : page === "Media"
                          ? "Select a file to inspect it. Play on surface sends it to the output."
                          : "Output tests, decoder status, and recent activity."}
              </p>
            </div>
            <span
              className={`status-pill ${status?.blackout ? "danger" : live ? "healthy" : ""}`}
            >
              <i className="dot" />
              {!connected
                ? "OFFLINE"
                : status?.blackout
                  ? "BLACKOUT"
                  : status?.renderer.status !== "LIVE"
                    ? "NO OUTPUT"
                    : status?.transport === "READY"
                      ? "Show stopped"
                      : status?.transport === "PAUSED"
                        ? "Paused"
                        : "Playing"}
            </span>
          </div>
          {error && (
            <div className="notice error" role="alert">
              <span>{error}</span>
              <button
                aria-label="Dismiss error"
                onClick={() => engine.setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {!project && (
            <section className="panel form-panel">
              <h2>Connect to the engine</h2>
              <p>
                Start the local application. If access is protected, enter its
                token.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setToken(auth);
                  location.reload();
                }}
              >
                <label>
                  Access token
                  <input
                    type="password"
                    value={auth}
                    onChange={(e) => setAuth(e.target.value)}
                    autoComplete="off"
                  />
                </label>
                <button className="primary" type="submit">
                  Connect
                </button>
              </form>
            </section>
          )}
          {project && status && (
            <>
              {visibleWarnings.length > 0 && (
                <div className="notice warning" role="status">
                  <AlertTriangle size={18} aria-hidden="true" />
                  <div>
                    <strong>Needs attention</strong>
                    {visibleWarnings.map((warning) => (
                      <p key={warning}>{warning}</p>
                    ))}
                  </div>
                </div>
              )}
              <section className="transport" aria-label="Show controls">
                <span className="transport-state">
                  {status.blackout
                    ? "Output black"
                    : status.transport === "READY"
                      ? "Show stopped"
                      : status.transport === "PAUSED"
                        ? "Paused"
                        : "Playing"}
                </span>
                <div className="transport-primary">
                  <button
                    className="primary"
                    disabled={
                      disabled || status.blackout || needsCompiledPreview
                    }
                    title="Space: start, pause, or resume the show"
                    onClick={() =>
                      void engine.command(
                        running
                          ? "pause"
                          : status.transport === "PAUSED"
                            ? "resume"
                            : "start",
                      )
                    }
                  >
                    {running ? <Pause size={16} /> : <Play size={16} />}{" "}
                    {running
                      ? "Pause"
                      : status.transport === "PAUSED"
                        ? "Resume"
                        : "Start show"}
                  </button>
                  {status.mode !== "timeline" && (
                    <>
                      <button
                        disabled={
                          disabled ||
                          status.transport === "READY" ||
                          status.blackout
                        }
                        onClick={() => void engine.command("skip")}
                      >
                        <SkipForward size={16} />
                        Next
                      </button>
                      <button
                        disabled={
                          disabled ||
                          status.transport === "READY" ||
                          status.blackout
                        }
                        onClick={() => void engine.command("fade-out")}
                      >
                        <Waves size={16} />
                        Fade to next
                      </button>
                    </>
                  )}
                  <button
                    disabled={disabled || status.transport === "READY"}
                    title={
                      status.mode === "timeline"
                        ? "Reset time to zero and darken timeline surfaces."
                        : "Clear the cue and reset the queue. Ambient content remains visible."
                    }
                    onClick={() => void engine.command("stop")}
                  >
                    <CircleStop size={16} />
                    Stop show
                  </button>
                </div>
                <button
                  className={status.blackout ? "restore" : "blackout-button"}
                  disabled={disabled}
                  onClick={() =>
                    void engine.command(
                      status.blackout ? "restore" : "blackout",
                    )
                  }
                >
                  {status.blackout ? <Sun size={16} /> : <Moon size={16} />}{" "}
                  {status.blackout ? "Restore output" : "Blackout"}
                </button>
              </section>
              {needsCompiledPreview && (
                <p className="notice">
                  This timeline has audio. In Show → Build &amp; Deploy, build
                  and load Preview built show before starting synchronized
                  playback.
                </p>
              )}
              {status.blackout && (
                <div className="notice error" role="status">
                  <strong>Blackout active.</strong> All output is black and
                  playback is frozen. Restore output returns to{" "}
                  {status.transport === "READY"
                    ? "the stopped show"
                    : status.transport.toLowerCase() + " playback"}
                  .
                </div>
              )}
              {status.pattern !== "show" && (
                <div className="notice" role="status">
                  <span>
                    <strong>{words(status.pattern)} test pattern.</strong>{" "}
                    Replaces the show image while cues continue.
                  </span>
                  <button
                    disabled={disabled}
                    onClick={() => void engine.pattern("show")}
                  >
                    Return to content
                  </button>
                </div>
              )}
              {status.calibration && page !== "Mapping" && (
                <div className="notice" role="status">
                  Mapping is active in another session. Save or Revert there
                  before saving project settings.
                </div>
              )}
              <div hidden={page !== "Playback"}>
                <div
                  className={`runtime-layout ${status.mode === "timeline" ? "timeline-runtime" : ""}`}
                >
                  <div className="main-column">
                    {status.mode === "timeline" ? (
                      <TimelinePlayback project={project} status={status} />
                    ) : (
                      <CurrentCue project={project} status={status} />
                    )}
                    <Output
                      project={project}
                      status={status}
                      connected={connected}
                      visible={page === "Playback"}
                    />
                  </div>
                  {status.mode !== "timeline" && (
                    <Queue project={project} status={status} />
                  )}
                </div>
                <section className="surfaces-section">
                  <div className="section-heading">
                    <h2>
                      On the surfaces{" "}
                      <span className="count">{project.surfaces.length}</span>
                    </h2>
                    <span className="subtle">
                      {status.mode === "timeline"
                        ? "Surface opacity follows the show clock"
                        : status.blackout || status.transport === "PAUSED"
                          ? "Ambient paused"
                          : "Background content on enabled surfaces"}
                    </span>
                  </div>
                  <div className="surface-cards">
                    {project.surfaces.map((surface, index) => {
                      const enabled =
                        surface.enabled &&
                        project.projectors.some(
                          (p) => p.id === surface.projector_id && p.enabled,
                        );
                      const layer = status.timeline?.layers.find(
                        (l) => l.surface_id === surface.id,
                      );
                      const active =
                        status.mode === "timeline"
                          ? enabled &&
                            status.transport !== "READY" &&
                            !!layer &&
                            layer.opacity > 0 &&
                            (layer.role === "lighting" || !!layer.source_id)
                          : enabled &&
                            status.current?.surface_id === surface.id &&
                            status.transport !== "READY" &&
                            status.phase !== "GAP";
                      const ambient = project.ambient_profiles.find(
                        (a) => a.id === surface.ambient_profile,
                      );
                      return (
                        <button
                          title={`Map ${surface.name}`}
                          onClick={() => {
                            setMappingSurface(surface.id);
                            navigate("Mapping");
                          }}
                          className={`surface-card ${active ? "active" : ""}`}
                          key={surface.id}
                        >
                          <div>
                            <span className="surface-number">
                              {String(index + 1).padStart(2, "0")}
                            </span>
                            <span
                              className={`small-dot ${active ? "lit" : ""}`}
                            />
                          </div>
                          <strong>{surface.name}</strong>
                          <span>
                            {!enabled
                              ? "Disabled"
                              : status.blackout
                                ? "Blackout"
                                : status.pattern !== "show"
                                  ? "Test pattern"
                                  : active
                                    ? status.mode === "timeline"
                                      ? `${Math.round((layer?.opacity ?? 0) * 100)}% ${layer?.role === "lighting" ? "light" : "media"}`
                                      : words(status.phase)
                                    : status.mode === "timeline"
                                      ? "Dark"
                                      : ambient?.enabled
                                        ? ambient.name
                                        : "Black"}
                          </span>
                          <span className="surface-action">Map surface →</span>
                        </button>
                      );
                    })}
                  </div>
                </section>
              </div>
              <div hidden={page !== "Show"}>
                <ShowPage
                  project={project}
                  status={status}
                  revision={engine.revision}
                  save={engine.save}
                  reload={engine.load}
                />
              </div>
              {page === "Mapping" && (
                <MappingPage
                  project={project}
                  initialSurface={mappingSurface}
                  onDirtyChange={setMappingDirty}
                  revision={engine.revision}
                  reload={engine.load}
                  connected={connected}
                />
              )}
              <div hidden={page !== "Media"}>
                <MediaPage
                  onVisibleWarningsChange={setMediaWarningsShown}
                  project={project}
                  status={status}
                  connected={connected}
                  reload={engine.load}
                  save={engine.save}
                />
              </div>
              <div hidden={page !== "Project"}>
                <ProjectEditor
                  project={project}
                  canSave={
                    status.transport === "READY" &&
                    connected &&
                    !status.calibration
                  }
                  save={engine.save}
                />
              </div>
              <div hidden={page !== "Diagnostics"}>
                {status.renderer.performance && (
                  <section className="panel form-panel">
                    <h3>Renderer performance</h3>
                    <dl className="build-details">
                      <div className="diagnostic-item">
                        <dt>Frame time</dt>
                        <dd>
                          {status.renderer.performance.frame_avg_ms} ms average
                          · {status.renderer.performance.frame_max_ms} ms max
                        </dd>
                      </div>
                      <div className="diagnostic-item">
                        <dt>Render / present</dt>
                        <dd>
                          {status.renderer.performance.render_avg_ms} /{" "}
                          {status.renderer.performance.present_avg_ms} ms
                          average
                        </dd>
                      </div>
                      <div className="diagnostic-item">
                        <dt>Preview readback</dt>
                        <dd>
                          {status.renderer.performance.preview.enabled
                            ? `${status.renderer.performance.preview.readback_avg_ms} ms average at ${status.renderer.performance.preview.resolution?.join("×")}`
                            : "Disabled"}
                        </dd>
                      </div>
                      <div className="diagnostic-item">
                        <dt>Preview encoder</dt>
                        <dd>
                          {status.renderer.performance.preview.enabled
                            ? `${status.renderer.performance.preview.encoder.last_encode_ms} ms encode · ${status.renderer.performance.preview.encoder.last_age_ms} ms age · ${status.renderer.performance.preview.skipped_interval} skipped this interval`
                            : "No work scheduled"}
                        </dd>
                      </div>
                    </dl>
                    <p className="subtle">
                      Target {status.renderer.performance.target_fps} fps ·{" "}
                      {status.renderer.performance.frame_budget_ms} ms budget ·{" "}
                      {status.renderer.performance.late_frames_interval} late in
                      the latest sample
                    </p>
                  </section>
                )}
                {status.renderer.timeline_clock && (
                  <section className="panel form-panel">
                    <h3>Native playback pipeline</h3>
                    <dl className="build-details">
                      {Object.entries(status.renderer.timeline_clock).map(
                        ([key, value]) => (
                          <div className="diagnostic-item" key={key}>
                            <dt>{key.replaceAll("_", " ")}</dt>
                            <dd>
                              {value === null
                                ? "Unavailable"
                                : typeof value === "object"
                                  ? JSON.stringify(value)
                                  : String(value)}
                            </dd>
                          </div>
                        ),
                      )}
                    </dl>
                    <p className="subtle">
                      A/V skew is video PTS minus pipeline position, not
                      measured speaker/projector latency. A silent test sink
                      never verifies HDMI.
                    </p>
                  </section>
                )}
                {status.system && (
                  <section className="panel form-panel">
                    <h3>Host resources</h3>
                    <p>
                      Process CPU: {status.system.cpu_percent}% (100% = one
                      core) · RAM:{" "}
                      {(status.system.memory_bytes / 1024 ** 2).toFixed(1)} MiB
                      ({status.system.memory_measurement}) · Free disk:{" "}
                      {(status.system.free_disk_bytes / 1024 ** 3).toFixed(1)}{" "}
                      GiB
                    </p>
                    <p>
                      Temperature:{" "}
                      {status.system.temperature_c === null
                        ? "Unavailable"
                        : `${status.system.temperature_c} °C`}{" "}
                      · Throttling: {status.system.throttling ?? "Unavailable"}
                    </p>
                  </section>
                )}
                <AudioSettings stopped={status.transport === "READY"} />
                <div className="stat-grid">
                  <section className="panel stat">
                    <span>Native renderer</span>
                    <strong>
                      {status.renderer.fps.toFixed(1)} <small>fps</small>
                    </strong>
                    <small>Target {project.canvas.refresh_rate} fps</small>
                  </section>
                  <section className="panel stat">
                    <span>Late frames</span>
                    <strong>{status.renderer.late_frames}</strong>
                    <small>Frame work over 1.5× its budget</small>
                  </section>
                  <section className="panel stat">
                    <span>Web clients</span>
                    <strong>{status.clients}</strong>
                    <small>Live state at 10 updates / second</small>
                  </section>
                  <section className="panel stat">
                    <span>Application uptime</span>
                    <strong>{clock(status.uptime)}</strong>
                    <small>{status.renderer.gpu ?? "No GPU connected"}</small>
                  </section>
                </div>
                <section className="panel form-panel">
                  <h3>Test the mapping</h3>
                  <p>
                    These patterns replace all mapped content. Cues continue in
                    the background; pause first to hold your place.
                  </p>
                  <div className="patterns">
                    {["show", "grid", "white", "color", "border"].map(
                      (pattern) => (
                        <button
                          aria-pressed={status.pattern === pattern}
                          className={
                            status.pattern === pattern ? "selected" : ""
                          }
                          key={pattern}
                          disabled={disabled || !!status.calibration}
                          onClick={() => void engine.pattern(pattern)}
                        >
                          {pattern === "show" ? (
                            <Play size={15} />
                          ) : (
                            <Circle size={15} />
                          )}{" "}
                          {pattern === "show"
                            ? "Show content"
                            : pattern[0].toUpperCase() + pattern.slice(1)}
                        </button>
                      ),
                    )}
                  </div>
                  <p className="hint">
                    Output window:{" "}
                    {status.renderer.output_size?.join(" × ") ?? "unavailable"}{" "}
                    · Logical canvas: {project.canvas.width} ×{" "}
                    {project.canvas.height}. Windowed output preserves the
                    canvas aspect ratio.
                  </p>
                </section>
                <section className="panel form-panel">
                  <div className="section-heading">
                    <h3>Recent activity</h3>
                    <button
                      disabled={disabled || status.transport !== "READY"}
                      onClick={() => void engine.command("reload")}
                    >
                      <RotateCcw size={14} /> Reload saved project
                    </button>
                  </div>
                  <div className="events">
                    {status.events.map((event, i) => (
                      <div key={`${event.time}-${i}`}>
                        <time>
                          {new Date(event.time * 1000).toLocaleTimeString()}
                        </time>
                        <strong>{event.title}</strong>
                        <span>{event.detail}</span>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
              <DiscardDialog
                open={destination !== null}
                title="Leave unsaved mapping?"
                description="The projected preview will revert to the last saved corners. Stay here to save your mapping first."
                onKeep={() => setDestination(null)}
                onDiscard={() => {
                  if (destination) {
                    setPage(destination);
                    sessionStorage.setItem("projection-page", destination);
                  }
                  setMappingDirty(false);
                  setDestination(null);
                }}
              />
              <footer>
                <span>
                  <i className="dot green" />
                  Local engine · No cloud connection required
                </span>
                <span>
                  Projection Show Engine{" "}
                  <span className="footer-version">v0.3 / Local engine</span>
                </span>
              </footer>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
