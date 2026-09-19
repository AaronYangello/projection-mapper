import { useRef, useState } from "react";
import { getToken, request } from "./api";

type Item = {
  id: string;
  name: string;
  progress: number;
  state: string;
  error?: string;
  serverId?: string;
};
export function uploadStream(
  url: string,
  file: File,
  progress: (n: number) => void,
  register: (xhr: XMLHttpRequest) => void,
): Promise<any> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    register(xhr);
    xhr.open("POST", url);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    if (getToken())
      xhr.setRequestHeader("Authorization", `Bearer ${getToken()}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) progress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = { detail: "Unexpected server response" };
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else
        reject(
          new Error(
            typeof body.detail === "string" ? body.detail : "Upload failed",
          ),
        );
    };
    xhr.onerror = () => reject(new Error("Connection lost during upload"));
    xhr.onabort = () => reject(new Error("Upload cancelled"));
    xhr.send(file);
  });
}
export function UploadPanel({
  enabled,
  bundle = false,
  onComplete,
}: {
  enabled: boolean;
  bundle?: boolean;
  onComplete?: () => void;
}) {
  const [items, setItems] = useState<Item[]>([]);
  const active = useRef(new Map<string, XMLHttpRequest>());
  const cancelled = useRef(new Set<string>());
  const [notice, setNotice] = useState("");
  const update = (id: string, patch: Partial<Item>) =>
    setItems((old) => old.map((i) => (i.id === id ? { ...i, ...patch } : i)));
  async function add(files: FileList | null) {
    if (!files || !enabled) return;
    if (files.length > 10) {
      setNotice("Choose up to 10 files at a time.");
      return;
    }
    for (const file of Array.from(files)) {
      const id = crypto.randomUUID();
      setItems((old) => [
        ...old,
        { id, name: file.name, progress: 0, state: "Preparing" },
      ]);
      try {
        const job = bundle
          ? null
          : await request<{ id: string }>("media/uploads", {
              method: "POST",
              body: JSON.stringify({ name: file.name, size: file.size }),
            });
        update(id, { serverId: job?.id, state: "Uploading" });
        if (cancelled.current.has(id)) {
          if (job)
            await request(`media/uploads/${job.id}`, { method: "DELETE" });
          throw new Error("Upload cancelled");
        }
        const result = await uploadStream(
          bundle
            ? "/api/deployments/upload"
            : `/api/media/upload?upload_id=${job!.id}`,
          file,
          (n) => update(id, { progress: n }),
          (xhr) => active.current.set(id, xhr),
        );
        if (bundle) {
          let validation = result;
          update(id, { serverId: result.id });
          while (["queued", "running"].includes(validation.state)) {
            if (cancelled.current.has(id)) {
              await request(`builds/${result.id}`, { method: "DELETE" });
              throw new Error("Validation cancelled");
            }
            update(id, { state: "Validating" });
            await new Promise((r) => setTimeout(r, 500));
            validation = await request(`builds/${result.id}`);
          }
          if (validation.state !== "complete")
            throw new Error(validation.error || "Bundle rejected");
          update(id, { state: "Validated · ready to activate", progress: 1 });
        } else
          update(id, {
            state:
              result.state === "duplicate"
                ? "Already in library"
                : "Uploaded · scan to index",
            progress: 1,
          });
        onComplete?.();
      } catch (e) {
        update(id, {
          state: cancelled.current.has(id) ? "Cancelled" : "Failed",
          error: (e as Error).message,
        });
      } finally {
        active.current.delete(id);
      }
    }
  }
  return (
    <section
      className="upload-panel"
      aria-label={bundle ? "Upload deployment bundle" : "Upload media"}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        void add(e.dataTransfer.files);
      }}
    >
      <label>
        {bundle ? "Upload a .pshow bundle" : "Drop media here or choose files"}
        <input
          type="file"
          multiple={!bundle}
          disabled={!enabled}
          accept={
            bundle
              ? ".pshow"
              : ".mp4,.mov,.mkv,.m4v,.webm,.avi,.png,.jpg,.jpeg,.webp,.wav,.mp3,.m4a,.aac,.flac,.ogg"
          }
          onChange={(e) => {
            void add(e.target.files);
            e.target.value = "";
          }}
        />
      </label>
      <p className="subtle">
        {bundle
          ? "Upload validates only. Review the result before activating."
          : "Stop playback to upload. Files are probed and installed without playing or adding them to the show. Then Scan folder and Add to show."}
      </p>
      {notice && <p role="alert">{notice}</p>}
      {items.map((i) => (
        <div key={i.id} className="upload-item">
          <strong>{i.name}</strong>
          <span role="status">
            {i.state} · {Math.round(i.progress * 100)}%
          </span>
          <progress max={1} value={i.progress} />
          {i.error && <span role="alert">{i.error}</span>}
          {["Uploading", "Preparing", "Validating"].includes(i.state) && (
            <button
              onClick={() => {
                cancelled.current.add(i.id);
                active.current.get(i.id)?.abort();
                if (i.serverId)
                  void request(
                    `${bundle ? "builds" : "media/uploads"}/${i.serverId}`,
                    {
                      method: "DELETE",
                    },
                  ).catch(() => {});
                update(i.id, { state: "Cancelled" });
              }}
            >
              Cancel upload
            </button>
          )}
        </div>
      ))}
    </section>
  );
}
