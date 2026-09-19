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
  finished?: boolean;
};
type Context = { surfaceId: string; revision: number; original: Corners };
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
  const [mapping, setMapping] = useState<Corners | null>(null);
  const [saved, setSaved] = useState<Corners | null>(null);
  const [pattern, setPattern] = useState("grid");
  const [blackOthers, setBlackOthers] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const owner = useRef<Session | null>(null);
  const mounted = useRef(true);
  const opening = useRef<Promise<void> | null>(null);
  const nextSequence = useRef(0);
  const pending = useRef<Update | null>(null);
  const working = useRef<Promise<void> | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const failure = useRef("");

  function clear() {
    owner.current = null;
    pending.current = null;
    setMapping(null);
    setSaved(null);
    failure.current = "";
  }
  function open(context: Context) {
    setSaved(structuredClone(context.original));
    failure.current = "";
    opening.current = (async () => {
      try {
        const result = await request<Session>("mapping", {
          method: "POST",
          body: JSON.stringify({
            surface_id: context.surfaceId,
            revision: context.revision,
          }),
        });
        if (!mounted.current) {
          await request(`mapping/${result.id}`, { method: "DELETE" });
          return;
        }
        owner.current = result;
        // Keep every movement made while the lease request was in flight.
        setSaved(result.mapping);
      } catch (e) {
        failure.current = e instanceof Error ? e.message : String(e);
        setError(failure.current);
        pending.current = null;
        setMapping(null);
        setSaved(null);
      } finally {
        opening.current = null;
      }
    })();
  }
  async function flush() {
    clearTimeout(timer.current);
    timer.current = undefined;
    await opening.current;
    if (working.current) await working.current;
    if (pending.current && owner.current) {
      working.current = (async () => {
        while (pending.current && owner.current) {
          const update = pending.current;
          pending.current = null;
          try {
            await request<Session>(`mapping/${owner.current.id}`, {
              method: "PUT",
              body: JSON.stringify(update),
            });
            failure.current = "";
            setError("");
          } catch (e) {
            failure.current = e instanceof Error ? e.message : String(e);
            setError(failure.current);
            pending.current = null;
            break;
          }
        }
      })();
      await working.current;
      working.current = null;
    }
  }
  function preview(
    next: Corners,
    context?: Context,
    nextPattern = pattern,
    nextBlack = blackOthers,
  ) {
    if (!validCorners(next)) {
      setError(
        "Keep the four corners convex, clockwise, and inside the projector.",
      );
      return false;
    }
    if (!owner.current && !opening.current) {
      if (!context) return false;
      open(context);
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
  async function save() {
    setBusy(true);
    try {
      await flush();
      if (failure.current) throw new Error(failure.current);
      if (!owner.current) throw new Error("Move a corner to begin editing.");
      const result = await request<Session>(
        `mapping/${owner.current.id}/save?finish=true`,
        {
          method: "POST",
        },
      );
      // A running older backend may serve newly rebuilt UI assets before restart.
      // Its save route ignores finish; release that lease explicitly.
      if (!result.finished)
        await request(`mapping/${owner.current.id}`, { method: "DELETE" });
      clear();
      setMessage("Mapping saved · show content restored");
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
      await opening.current;
      await working.current;
      if (owner.current)
        await request(`mapping/${owner.current.id}`, { method: "DELETE" });
      clear();
      setError("");
      setMessage("Mapping reverted · show content restored");
      await reload();
    } catch (e) {
      // Keep the lease/draft visible on failure so Revert can be retried.
      setError(e instanceof Error ? e.message : String(e));
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
    mapping,
    saved,
    pattern,
    blackOthers,
    error,
    message,
    busy,
    editing: mapping !== null,
    dirty:
      mapping !== null && JSON.stringify(mapping) !== JSON.stringify(saved),
    preview,
    save,
    end,
    setPattern: (p: string) => {
      setPattern(p);
      if (mapping) preview(mapping, undefined, p, blackOthers);
    },
    setBlackOthers: (b: boolean) => {
      setBlackOthers(b);
      if (mapping) preview(mapping, undefined, pattern, b);
    },
  };
}
