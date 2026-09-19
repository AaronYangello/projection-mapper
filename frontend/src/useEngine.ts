import { useCallback, useEffect, useState } from "react";
import { getToken, request } from "./api";
import type { Project, Status } from "./types";

export function useEngine() {
  const [project, setProject] = useState<Project | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const load = useCallback(async () => {
    const data = await request<{ project: Project; revision: number }>(
      "project",
    );
    setProject((previous) =>
      JSON.stringify(previous) === JSON.stringify(data.project)
        ? previous
        : data.project,
    );
    setRevision(data.revision);
    return data;
  }, []);
  useEffect(() => {
    if (status && status.revision !== revision)
      void load().catch((e) => setError(e.message));
  }, [status?.revision, revision, load]);
  useEffect(() => {
    let disposed = false,
      socket: WebSocket | undefined,
      retry: ReturnType<typeof setTimeout>;
    function connect() {
      if (disposed) return;
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/live`,
      );
      socket.onopen = () => {
        socket?.send(JSON.stringify({ token: getToken() }));
        load().catch((e) => setError(e.message));
      };
      socket.onmessage = (event) => {
        setStatus(JSON.parse(event.data));
        setConnected(true);
      };
      socket.onclose = () => {
        setConnected(false);
        if (!disposed) retry = setTimeout(connect, 2000);
      };
      socket.onerror = () => socket?.close();
    }
    load().catch((e) => setError(e.message));
    connect();
    return () => {
      disposed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, [load]);
  async function perform(operation: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await operation();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return {
    project,
    status,
    connected,
    error,
    setError,
    busy,
    revision,
    load,
    command: (action: string) =>
      perform(async () => {
        setStatus(
          await request<Status>(`runtime/${action}`, { method: "POST" }),
        );
        if (action === "reload") await load();
      }),
    pattern: (pattern: string) =>
      perform(async () => {
        setStatus(
          await request<Status>("pattern", {
            method: "PUT",
            body: JSON.stringify({ pattern }),
          }),
        );
      }),
    save: async (next: Project) => {
      const saved = await request<{ project: Project; revision: number }>(
        "project",
        {
          method: "PUT",
          body: JSON.stringify({ revision, project: next }),
        },
      );
      setProject(saved.project);
      setRevision(saved.revision);
    },
  };
}

export function usePreview(live: boolean, fps: number) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!live) {
      setUrl("");
      return;
    }
    let stopped = false,
      previous = "",
      timer: ReturnType<typeof setTimeout>;
    const abort = new AbortController();
    async function refresh() {
      try {
        const response = await fetch("/api/preview.jpg", {
          signal: abort.signal,
          headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
        });
        if (!response.ok) throw new Error("Preview unavailable");
        const blob = await response.blob();
        if (stopped) return;
        const next = URL.createObjectURL(blob);
        setUrl(next);
        if (previous) URL.revokeObjectURL(previous);
        previous = next;
      } catch {
        if (!stopped) setUrl("");
      }
      if (!stopped) timer = setTimeout(refresh, Math.max(250, 1000 / fps));
    }
    void refresh();
    return () => {
      stopped = true;
      abort.abort();
      clearTimeout(timer);
      if (previous) URL.revokeObjectURL(previous);
    };
  }, [fps, live]);
  return url;
}
