import { useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Box,
  ChevronRight,
  Circle,
  CircleStop,
  Columns3,
  Gauge,
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
import { setToken } from "./api";
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
const words = (text: string) => text.toLowerCase().replaceAll("_", " ");

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
  const preview = usePreview(live);
  return (
    <section className="panel output-panel">
      <div className="panel-heading">
        <div>
          <Monitor size={16} />
          <h2>Output canvas</h2>
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
              {live ? "Receiving GPU preview…" : "Native output unavailable"}
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
          Preview at 2 fps · output {status.renderer.fps.toFixed(1)} fps
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
              : "Ready"}
        </span>
      </div>
      <div className="current-body">
        <div
          className="scene-swatch"
          style={{
            background: active ? (scene?.color ?? "#506d63") : "#26302e",
          }}
        >
          <Waves size={28} />
        </div>
        <div>
          <h2>{active ? scene?.name : "Ready when you are"}</h2>
          <p>
            {active
              ? `${surface?.name} · ${scene?.type === "color" ? "Solid color" : scene?.type === "video" ? "Native video" : "Image"}`
              : "Start the show to play the planned queue."}
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
        <span>{Math.round(status.opacity * 100)}% opacity</span>
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
        <span className="badge">Shuffle bag</span>
      </div>
      <p className="queue-intro">The next places light will land.</p>
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
          Each eligible item once per bag.
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
  const [page, setPage] = useState("Runtime");
  const [auth, setAuth] = useState("");
  const disabled = busy || !connected;
  const running = status?.transport === "RUNNING";
  const live =
    connected && status?.renderer.status === "LIVE" && !status.blackout;
  const nav = [
    { name: "Dashboard", icon: Gauge },
    { name: "Runtime", icon: Radio },
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
            setPage("Dashboard");
          }}
        >
          <span className="brand-mark">
            <Box size={23} />
          </span>
          <span>
            Projection<span className="brand-sub">SHOW ENGINE</span>
          </span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav aria-label="Primary navigation">
          {nav.map(({ name, icon: Icon }) => (
            <button
              key={name}
              aria-current={page === name ? "page" : undefined}
              className={page === name ? "nav-active" : ""}
              onClick={() => setPage(name)}
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
        <div className="sidebar-bottom">
          <span className="prototype">DEV</span>
          <div>
            Mapping & media<span>Native output · Local control</span>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
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
              <div className="eyebrow">CONTROL ROOM</div>
              <h1>{page === "Project" ? "Your installation" : page}</h1>
              <p>
                {page === "Runtime"
                  ? "A little light. Exactly where it belongs."
                  : page === "Dashboard"
                    ? "Your installation, at a glance."
                    : page === "Project"
                      ? "Geometry, sources, and show behavior in one reusable definition."
                      : page === "Mapping"
                        ? "Place every corner. See the change on your output."
                        : page === "Media"
                          ? "Local sources, ready for the surfaces you choose."
                          : "Measured state from the running engine."}
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
                    : status?.state}
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
              {status.warnings.length > 0 && (
                <div className="notice warning" role="status">
                  {status.warnings.join(" · ")}
                </div>
              )}
              <section className="transport" aria-label="Show controls">
                <div className="transport-primary">
                  <button
                    className="primary"
                    disabled={disabled}
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
                  <button
                    disabled={disabled || status.transport === "READY"}
                    onClick={() => void engine.command("skip")}
                  >
                    <SkipForward size={16} />
                    Skip
                  </button>
                  <button
                    disabled={disabled || status.transport === "READY"}
                    onClick={() => void engine.command("fade-out")}
                  >
                    <Waves size={16} />
                    Fade out
                  </button>
                  <button
                    disabled={disabled || status.transport === "READY"}
                    onClick={() => void engine.command("stop")}
                  >
                    <CircleStop size={16} />
                    Stop
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
              <div hidden={page !== "Runtime"}>
                <div className="runtime-layout">
                  <div className="main-column">
                    <Output
                      project={project}
                      status={status}
                      connected={connected}
                      visible={page === "Runtime"}
                    />
                    <CurrentCue project={project} status={status} />
                  </div>
                  <Queue project={project} status={status} />
                </div>
                <section className="surfaces-section">
                  <div className="section-heading">
                    <h2>
                      On the surfaces{" "}
                      <span className="count">{project.surfaces.length}</span>
                    </h2>
                    <span className="subtle">
                      <span className="small-dot" /> Ambient stays in motion
                    </span>
                  </div>
                  <div className="surface-cards">
                    {project.surfaces.map((surface, index) => {
                      const enabled =
                        surface.enabled &&
                        project.projectors.some(
                          (p) => p.id === surface.projector_id && p.enabled,
                        );
                      const active =
                        enabled &&
                        status.current?.surface_id === surface.id &&
                        status.transport !== "READY" &&
                        status.phase !== "GAP";
                      const ambient = project.ambient_profiles.find(
                        (a) => a.id === surface.ambient_profile,
                      );
                      return (
                        <div
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
                                    ? words(status.phase)
                                    : ambient?.enabled
                                      ? ambient.name
                                      : "Black"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </section>
              </div>
              <div hidden={page !== "Dashboard"}>
                <div className="stat-grid">
                  {[
                    {
                      label: "Projectors",
                      value: project.projectors.length,
                      detail: "Configured viewports",
                    },
                    {
                      label: "Surfaces",
                      value: project.surfaces.filter((s) => s.enabled).length,
                      detail: "Enabled mapping planes",
                    },
                    {
                      label: "Scenes",
                      value: project.scenes.length,
                      detail: "Color, image & video sources",
                    },
                    {
                      label: "Show time",
                      value: clock(status.show_time),
                      detail: "Excludes pause and blackout",
                    },
                  ].map((stat) => (
                    <section className="panel stat" key={stat.label}>
                      <span>{stat.label}</span>
                      <strong>{stat.value}</strong>
                      <small>{stat.detail}</small>
                    </section>
                  ))}
                </div>
                <Output
                  project={project}
                  status={status}
                  connected={connected}
                  visible={page === "Dashboard"}
                />
                <div className="dashboard-links">
                  <button onClick={() => setPage("Runtime")}>
                    <Radio size={17} /> Open runtime <ArrowUpRight size={16} />
                  </button>
                  <button onClick={() => setPage("Project")}>
                    <Layers size={17} /> Configure project{" "}
                    <ArrowUpRight size={16} />
                  </button>
                </div>
              </div>
              {page === "Mapping" && (
                <MappingPage
                  project={project}
                  revision={engine.revision}
                  reload={engine.load}
                  connected={connected}
                />
              )}
              {page === "Media" && (
                <MediaPage
                  project={project}
                  status={status}
                  connected={connected}
                  reload={engine.load}
                  save={engine.save}
                />
              )}
              <div hidden={page !== "Project"}>
                <ProjectEditor
                  project={project}
                  canSave={status.transport === "READY" && connected}
                  save={engine.save}
                />
              </div>
              <div hidden={page !== "Diagnostics"}>
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
                    Patterns replace surface content; blackout always takes
                    priority. These controls affect the native output.
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
                          disabled={disabled}
                          onClick={() => void engine.pattern(pattern)}
                        >
                          {pattern === "show" ? (
                            <Play size={15} />
                          ) : (
                            <Circle size={15} />
                          )}{" "}
                          {pattern[0].toUpperCase() + pattern.slice(1)}
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
              <footer>
                <span>
                  <i className="dot green" />
                  All configuration stays on this device.
                </span>
                <span>
                  Projection Show Engine{" "}
                  <span className="footer-version">v0.2 / Desktop preview</span>
                </span>
              </footer>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
