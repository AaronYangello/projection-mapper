import { useEffect, useRef, useState } from "react";
import { getToken, request } from "./api";
import type { Surface } from "./types";

export type Corners = Surface["mapping"];
export const cornerNames = [
  "top_left",
  "top_right",
  "bottom_right",
  "bottom_left",
] as const;
type Session = {
  id: string;
  mapping: Corners;
  revision: number;
  sequence: number;
  dirty: boolean;
};
type Update = {
  mapping: Corners;
  pattern: string;
  black_others: boolean;
  sequence: number;
};

export function validCorners(mapping: Corners): boolean {
  const p = cornerNames.map((k) => mapping[k]);
  return (
    p.every(
      ([x, y]) =>
        Number.isFinite(x) &&
        Number.isFinite(y) &&
        x >= 0 &&
        x <= 1 &&
        y >= 0 &&
        y <= 1,
    ) &&
    p.every((a, i) => {
      const b = p[(i + 1) % 4],
        c = p[(i + 2) % 4];
      return (
        (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) > 1e-6
      );
    })
  );
}

export function useMapping(reload: () => Promise<unknown>) {
  const [session, setSession] = useState<Session | null>(null);
  const [mapping, setMapping] = useState<Corners | null>(null);
  const [saved, setSaved] = useState<Corners | null>(null);
  const [pattern, setPattern] = useState("grid");
  const [blackOthers, setBlackOthers] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [ack, setAck] = useState(-1);
  const owner = useRef<Session | null>(null);
  const mounted = useRef(true);
  const nextSequence = useRef(0);
  const pending = useRef<Update | null>(null);
  const working = useRef<Promise<void> | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const failure = useRef("");

  async function flush() {
    clearTimeout(timer.current);
    timer.current = undefined;
    if (working.current) await working.current;
    if (pending.current && owner.current) {
      const run = async () => {
        while (pending.current && owner.current) {
          const update = pending.current;
          pending.current = null;
          try {
            const response = await request<Session>(
              `mapping/${owner.current.id}`,
              { method: "PUT", body: JSON.stringify(update) },
            );
            setAck(response.sequence);
            failure.current = "";
            setError("");
          } catch (e) {
            failure.current = e instanceof Error ? e.message : String(e);
            setError(failure.current);
            pending.current = null;
            break;
          }
        }
      };
      working.current = run();
      await working.current;
      working.current = null;
    }
  }
  function preview(
    next: Corners,
    nextPattern = pattern,
    nextBlack = blackOthers,
  ) {
    if (!validCorners(next)) {
      setError(
        "Keep the four corners convex, clockwise, and inside the projector.",
      );
      return false;
    }
    setMessage("");
    setMapping(next);
    setError("");
    pending.current = {
      mapping: next,
      pattern: nextPattern,
      black_others: nextBlack,
      sequence: nextSequence.current++,
    };
    if (!timer.current) timer.current = setTimeout(() => void flush(), 35);
    return true;
  }
  async function begin(surfaceId: string, revision: number) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await request<Session>("mapping", {
        method: "POST",
        body: JSON.stringify({ surface_id: surfaceId, revision }),
      });
      if (!mounted.current) {
        await request(`mapping/${result.id}`, { method: "DELETE" });
        return;
      }
      owner.current = result;
      setSession(result);
      setMapping(result.mapping);
      setSaved(result.mapping);
      nextSequence.current = 0;
      setPattern("grid");
      setBlackOthers(true);
      setAck(-1);
      failure.current = "";
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    try {
      await flush();
      if (failure.current) throw new Error(failure.current);
      const result = await request<Session>(
        `mapping/${owner.current?.id}/save`,
        { method: "POST" },
      );
      owner.current = result;
      setSession(result);
      setSaved(result.mapping);
      setMessage("Mapping saved");
      setError("");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function end() {
    setBusy(true);
    try {
      pending.current = null;
      clearTimeout(timer.current);
      timer.current = undefined;
      await working.current;
      await request(`mapping/${owner.current?.id}`, { method: "DELETE" });
      owner.current = null;
      setSession(null);
      setMapping(null);
      setError("");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      owner.current = null;
      setSession(null);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    mounted.current = true;
    const heartbeat = setInterval(() => {
      if (owner.current)
        void request(`mapping/${owner.current.id}/heartbeat`, {
          method: "POST",
        }).catch((e) => setError(e.message));
    }, 10000);
    return () => {
      mounted.current = false;
      clearInterval(heartbeat);
      clearTimeout(timer.current);
      pending.current = null;
      const id = owner.current?.id;
      owner.current = null;
      if (id)
        void fetch(`/api/mapping/${id}`, {
          method: "DELETE",
          keepalive: true,
          headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
        }).catch(() => {});
    };
  }, []);
  return {
    session,
    mapping,
    saved,
    pattern,
    blackOthers,
    error,
    message,
    busy,
    ack,
    begin,
    preview,
    save,
    end,
    dirty: JSON.stringify(mapping) !== JSON.stringify(saved),
    setPattern: (p: string) => {
      setPattern(p);
      if (mapping) preview(mapping, p, blackOthers);
    },
    setBlackOthers: (b: boolean) => {
      setBlackOthers(b);
      if (mapping) preview(mapping, pattern, b);
    },
  };
}
