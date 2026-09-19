import { useEffect, useState } from "react";
import { request } from "./api";
type Settings = {
  audio_sink: string;
  audio_device: string;
  volume: number | null;
  muted: boolean | null;
  sync_offset_ms: number | null;
};

export function AudioSettings({ stopped }: { stopped: boolean }) {
  const [saved, setSaved] = useState<Settings | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    void request<Settings>("runtime/audio")
      .then(setSaved)
      .catch((e) => setMessage(e.message));
  }, []);
  if (!saved) return message ? <p role="alert">{message}</p> : null;
  return (
    <section className="panel form-panel">
      <h3>Audio on this machine</h3>
      <p>
        Routing stays with this installation. Blank controls use the bundle's
        audio settings. Positive sync offset delays audio to match projector
        latency.
      </p>
      <form
        key={JSON.stringify(saved)}
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const optional = (key: string) =>
            f.get(key) === "" ? null : Number(f.get(key));
          try {
            setSaved(
              await request("runtime/audio", {
                method: "PUT",
                body: JSON.stringify({
                  audio_sink: stopped ? f.get("sink") : saved.audio_sink,
                  audio_device: stopped ? f.get("device") : saved.audio_device,
                  volume: optional("volume"),
                  sync_offset_ms: optional("offset"),
                  muted: f.get("mute") === "" ? null : f.get("mute") === "true",
                }),
              }),
            );
            setMessage("Audio settings applied.");
          } catch (e) {
            setMessage((e as Error).message);
          }
        }}
      >
        <div className="fields three">
          <label>
            Audio output
            <select
              name="sink"
              defaultValue={saved.audio_sink}
              disabled={!stopped}
            >
              <option value="auto">System audio output</option>
              <option value="alsa">ALSA / Pi HDMI</option>
              <option value="fake">Silent test sink</option>
            </select>
          </label>
          <label>
            ALSA device
            <input
              name="device"
              defaultValue={saved.audio_device}
              disabled={!stopped}
              placeholder="System default"
            />
          </label>
          <label>
            Mute
            <select
              name="mute"
              defaultValue={saved.muted === null ? "" : String(saved.muted)}
            >
              <option value="">Use bundle setting</option>
              <option value="true">Muted</option>
              <option value="false">Audible</option>
            </select>
          </label>
          <label>
            Volume override (0–1)
            <input
              name="volume"
              type="number"
              min="0"
              max="1"
              step="0.05"
              defaultValue={saved.volume ?? ""}
              placeholder="Use bundle setting"
            />
          </label>
          <label>
            Sync offset override (ms)
            <input
              name="offset"
              type="number"
              min="-1000"
              max="1000"
              step="1"
              defaultValue={saved.sync_offset_ms ?? ""}
              placeholder="Use bundle setting"
            />
          </label>
        </div>
        <button>Apply audio settings</button>
        <p className="subtle">
          Stop playback to change output routing. Volume, mute and offset apply
          immediately when you press Apply.
        </p>
      </form>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
