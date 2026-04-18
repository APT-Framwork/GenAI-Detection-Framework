/**
 * Server-Sent Events for mobile.
 *
 * React Native has no native `EventSource`. We use `react-native-sse`
 * which also lets us attach custom headers — required because we authenticate
 * with a Bearer token, not an httpOnly cookie.
 *
 * Both hooks below:
 *   - refresh the token lazily on every (re)connect
 *   - exponential backoff up to 30s on disconnect
 *   - cap the in-memory event buffer so a quiet observer doesn't leak
 *   - clean up their subscription on component unmount
 */

import { useEffect, useRef, useState } from "react";
import EventSource from "react-native-sse";

import { API_BASE_URL, API_PREFIX } from "./config";
import { getAccessToken } from "./storage";

export type LiveFeedEvent = {
  alertId: string;
  agentId: string | null;
  occurredAt: string;
  chainId?: string | null;
  ckcStage: number;
  ckcStageName: string;
  vaeMaliciousProb: number | null;
  aeAnomalyScore: number | null;
  gnnNodeRisk: number | null;
  dqnAction: number | null;
  dqnActionName: string | null;
  mitreTechniques: string[];
};

export type ChainLogEvent = {
  alertId: string;
  ts: string;
  agentName: string | null;
  rawLog: string | null;
  decoder: string | null;
  ruleDescription: string | null;
};

type Status = "idle" | "connecting" | "open" | "closed" | "error";

const MAX_BUFFER = 200;

interface UseSseOpts<T> {
  path: string;          // begins with "/"; joined to API_PREFIX
  enabled?: boolean;     // disable entirely (e.g. user not logged in)
  onEvent?: (event: T) => void;
  bufferSize?: number;
}

function useSseStream<T>({
  path,
  enabled = true,
  onEvent,
  bufferSize = MAX_BUFFER,
}: UseSseOpts<T>) {
  const [events, setEvents] = useState<T[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const attemptsRef = useRef(0);
  const onEventRef = useRef(onEvent);
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  useEffect(() => {
    if (!enabled) {
      setStatus("idle");
      return;
    }

    let es: EventSource | null = null;
    let cancelled = false;
    let retryHandle: ReturnType<typeof setTimeout> | null = null;

    const connect = async () => {
      if (cancelled) return;
      setStatus("connecting");
      const token = await getAccessToken();
      if (!token) {
        // No creds yet; retry soon (bootstrap may still be running).
        retryHandle = setTimeout(connect, 2_000);
        return;
      }

      const url = `${API_BASE_URL}${API_PREFIX}${path}`;
      es = new EventSource(url, {
        headers: {
          Authorization: { toString: () => `Bearer ${token}` },
          Accept: "text/event-stream",
          "X-Client-Type": "mobile",
        },
        // react-native-sse exposes a custom pollingInterval; keep default
      });

      es.addEventListener("open", () => {
        if (cancelled) return;
        attemptsRef.current = 0;
        setStatus("open");
      });

      es.addEventListener("message", (evt) => {
        if (cancelled) return;
        // react-native-sse uses (evt as MessageEvent).data — untyped
        const raw = (evt as { data?: string | null }).data;
        if (!raw) return;
        try {
          const parsed = JSON.parse(raw) as T;
          setEvents((prev) => {
            const next = [parsed, ...prev];
            return next.length > bufferSize ? next.slice(0, bufferSize) : next;
          });
          onEventRef.current?.(parsed);
        } catch {
          // non-JSON heartbeats/comments — ignore silently
        }
      });

      const onFailure = () => {
        if (cancelled) return;
        setStatus("error");
        es?.close();
        es = null;
        const attempt = ++attemptsRef.current;
        const delay = Math.min(30_000, 500 * 2 ** Math.min(attempt, 6));
        retryHandle = setTimeout(connect, delay);
      };
      es.addEventListener("error", onFailure);
    };

    void connect();

    return () => {
      cancelled = true;
      if (retryHandle) clearTimeout(retryHandle);
      if (es) {
        setStatus("closed");
        es.close();
      }
    };
  }, [path, enabled, bufferSize]);

  return { events, status };
}

// ---- public hooks -----------------------------------------------------

export function useLiveFeed(
  opts: { enabled?: boolean; onEvent?: (e: LiveFeedEvent) => void } = {},
) {
  return useSseStream<LiveFeedEvent>({
    path: "/streams/live-feed",
    enabled: opts.enabled,
    onEvent: opts.onEvent,
  });
}

export function useChainLogStream(chainId: string | null) {
  return useSseStream<ChainLogEvent>({
    path: chainId ? `/streams/chains/${chainId}/logs` : "/streams/live-feed",
    enabled: chainId !== null,
  });
}

export function useJobResult(jobId: string | null) {
  return useSseStream<{ status: string; result?: unknown }>({
    path: jobId ? `/streams/jobs/${jobId}` : "/streams/live-feed",
    enabled: jobId !== null,
    bufferSize: 10,
  });
}
