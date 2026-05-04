// -----------------------------------------------------------------------------
// useSseStream — generic Server-Sent Events hook (P4-7).
//
// Subscribes to an SSE endpoint with auto-reconnect (capped exponential
// backoff). Cookies are sent automatically (browsers always include them on
// EventSource connections), so auth Just Works against the auth middleware.
//
// Usage:
//
//     const { events, status } = useSseStream<LiveFeedEvent>("/streams/live-feed");
//     // status: "connecting" | "open" | "closed" | "error"
//     // events: most-recent-first, capped at maxEvents (default 100)
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE: string =
  (process.env.NEXT_PUBLIC_STRIX_API_BASE ?? "/api/v1").replace(/\/$/, "");

export type SseStatus = "connecting" | "open" | "closed" | "error";

export interface SseStreamOptions<T = unknown> {
  /** Cap on retained events. Defaults to 100. */
  maxEvents?: number;
  /** Disable the hook (e.g. when user is unauthenticated). */
  enabled?: boolean;
  /** Filter to a single SSE event name. Defaults to all messages. */
  eventName?: string;
  /**
   * Optional async backfill called once on mount BEFORE the SSE connects.
   * Returned events are inserted as oldest-last (so newest-first ordering
   * is preserved when live frames arrive). Useful when the SSE channel is
   * future-only and the panel would otherwise show "Waiting…" on a fresh
   * page load. Errors are swallowed — backfill is best-effort.
   */
  backfill?: () => Promise<Array<{ id: string; data: T }>>;
}

export interface SseStreamResult<T> {
  events: Array<{ id: string; data: T; receivedAt: number }>;
  status: SseStatus;
  reconnect: () => void;
}

export function useSseStream<T = unknown>(
  path: string,
  options: SseStreamOptions<T> = {},
): SseStreamResult<T> {
  const { maxEvents = 100, enabled = true, eventName, backfill } = options;

  const [status, setStatus] = useState<SseStatus>("connecting");
  const [events, setEvents] = useState<SseStreamResult<T>["events"]>([]);
  const sourceRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const restartTokenRef = useRef(0);
  const backfillRef = useRef(backfill);
  backfillRef.current = backfill;

  useEffect(() => {
    if (!enabled) {
      setStatus("closed");
      return;
    }
    let cancelled = false;
    let backoffTimer: ReturnType<typeof setTimeout> | null = null;
    const url = path.startsWith("http") ? path : `${API_BASE}${path}`;

    // Best-effort historical backfill before the live connection opens.
    // Result is appended OLDEST-LAST (so subsequent live frames keep the
    // newest-first ordering on the front of the array).
    const fn = backfillRef.current;
    if (fn) {
      void (async () => {
        try {
          const seeded = await fn();
          if (cancelled || seeded.length === 0) return;
          setEvents((prev) => {
            const ids = new Set(prev.map((e) => e.id));
            const newOnes = seeded
              .filter((e) => !ids.has(e.id))
              .map((e) => ({
                id: e.id,
                data: e.data,
                receivedAt: Date.now(),
              }));
            // Backfill arrives oldest-first; reverse so the resulting
            // array remains newest-first like the live insert above.
            const merged = [...prev, ...newOnes.slice().reverse()];
            return merged.length > maxEvents ? merged.slice(0, maxEvents) : merged;
          });
        } catch {
          // Best-effort — silent.
        }
      })();
    }

    const open = () => {
      if (cancelled) return;
      setStatus("connecting");
      const src = new EventSource(url, { withCredentials: true });
      sourceRef.current = src;

      const handler = (ev: MessageEvent<string>) => {
        if (cancelled) return;
        let parsed: T;
        try {
          parsed = JSON.parse(ev.data) as T;
        } catch {
          // Non-JSON frame (e.g. heartbeat) — ignore.
          return;
        }
        setEvents((prev) => {
          const next = [
            { id: ev.lastEventId || crypto.randomUUID(), data: parsed, receivedAt: Date.now() },
            ...prev,
          ];
          return next.length > maxEvents ? next.slice(0, maxEvents) : next;
        });
      };

      if (eventName) {
        src.addEventListener(eventName, handler as EventListener);
      } else {
        src.onmessage = handler;
      }

      src.onopen = () => {
        retriesRef.current = 0;
        setStatus("open");
      };
      src.onerror = () => {
        src.close();
        if (cancelled) return;
        setStatus("error");
        // Exponential backoff capped at 30 s.
        const delay = Math.min(30_000, 500 * 2 ** retriesRef.current);
        retriesRef.current += 1;
        backoffTimer = setTimeout(open, delay);
      };
    };

    open();

    return () => {
      cancelled = true;
      if (backoffTimer) clearTimeout(backoffTimer);
      sourceRef.current?.close();
      sourceRef.current = null;
      setStatus("closed");
    };
  }, [path, enabled, eventName, maxEvents, restartTokenRef.current === restartTokenRef.current]);

  return {
    events,
    status,
    reconnect: () => {
      retriesRef.current = 0;
      restartTokenRef.current += 1;
      sourceRef.current?.close();
    },
  };
}
