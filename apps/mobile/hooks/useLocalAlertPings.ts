/**
 * Watches the live SSE feed and fires a local system notification for any
 * event the analyst should hear about. Works in Expo Go because local
 * notifications don't need an Expo push token or EAS projectId — they're
 * scheduled directly on-device.
 *
 *   - Permissions are requested lazily on the first qualifying event.
 *   - We dedupe by `alertId` so a noisy reconnect can't ring twice.
 *   - On cold start the SSE hook backfills its buffer; we capture those
 *     IDs into the seen-set without firing, so the user isn't flooded.
 *   - High severity = vaeMaliciousProb ≥ 0.7 OR CKC stage ≥ 4. Mirrors
 *     the bucket logic in feed.tsx.
 */

import { useEffect, useRef } from "react";

import { useLiveFeed, type LiveFeedEvent } from "../lib/api/sse";
import {
  IS_EXPO_GO,
  presentLocalAlert,
  tryGetNotifications,
} from "../services/notifications";
import { useUserStore } from "../stores/user-store";

function isHighSeverity(ev: LiveFeedEvent): boolean {
  const prob = ev.vaeMaliciousProb ?? 0;
  const stage = ev.ckcStage ?? 0;
  return prob >= 0.7 || stage >= 4;
}

async function ensurePermission(): Promise<boolean> {
  const N = tryGetNotifications();
  if (!N) return false;
  const existing = await N.getPermissionsAsync();
  if (existing.granted) return true;
  if (!existing.canAskAgain) return false;
  const next = await N.requestPermissionsAsync();
  return next.granted;
}

export function useLocalAlertPings() {
  const status = useUserStore((s) => s.status);
  // Disable entirely in Expo Go — the underlying expo-notifications module
  // is unavailable on Android and the iOS Expo Go renderer drops the
  // notification silently.
  const enabled = status === "authed" && !IS_EXPO_GO;

  // Track which alerts we've already pinged for + a "primed" flag so the
  // first batch (backfilled events) is silently ingested.
  const seenRef = useRef<Set<string>>(new Set());
  const primedRef = useRef<boolean>(false);
  // Whether the user granted permission. Resolved lazily on first ping
  // attempt; cached so we don't re-prompt every event.
  const permissionRef = useRef<boolean | null>(null);

  const { events } = useLiveFeed({
    enabled,
    onEvent: (ev) => {
      // First event ever — assume the buffer is a backfill, mark
      // everything currently in flight as seen.
      if (!primedRef.current) return; // gated via the events-effect below
      if (seenRef.current.has(ev.alertId)) return;
      seenRef.current.add(ev.alertId);
      if (!isHighSeverity(ev)) return;
      void fire(ev, permissionRef);
    },
  });

  // After the first events array arrives, mark all current ids as seen
  // without firing — they're the SSE hook's initial buffer / backfill.
  useEffect(() => {
    if (primedRef.current) return;
    if (!enabled) return;
    if (events.length === 0) return;
    for (const ev of events) seenRef.current.add(ev.alertId);
    primedRef.current = true;
  }, [events, enabled]);

  // Reset the dedupe set on logout so a re-login starts fresh.
  useEffect(() => {
    if (!enabled) {
      seenRef.current = new Set();
      primedRef.current = false;
      permissionRef.current = null;
    }
  }, [enabled]);
}

async function fire(
  ev: LiveFeedEvent,
  permissionRef: React.MutableRefObject<boolean | null>,
): Promise<void> {
  if (permissionRef.current === false) return;
  if (permissionRef.current === null) {
    permissionRef.current = await ensurePermission();
    if (!permissionRef.current) return;
  }

  const stage = ev.ckcStageName || `Stage ${ev.ckcStage ?? "?"}`;
  const prob = ev.vaeMaliciousProb;
  const probTxt = prob != null ? ` · VAE ${(prob * 100).toFixed(0)}%` : "";
  const techniques = (ev.mitreTechniques ?? []).slice(0, 2).join(", ");

  await presentLocalAlert({
    title: `New detection · ${stage}`,
    body: techniques
      ? `${techniques}${probTxt}`
      : `Live feed detection${probTxt}`,
    data: {
      type: "intervention",
      alertId: ev.alertId,
      chainId: ev.chainId ?? null,
    },
  });
}
