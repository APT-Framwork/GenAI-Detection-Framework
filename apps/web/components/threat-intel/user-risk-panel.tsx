// -----------------------------------------------------------------------------
// user-risk-panel.tsx — UEBA top-N risky users.
//
// Visual: ranked list, each row = avatar (3-letter initials) · username
// (mono) · risk bar (0..1) · "N chains · M hosts" chip. Click row →
// /hunt?q=user:<name>. Empty state collapses to a single line, never an
// 8-row skeleton (per the plan).
// -----------------------------------------------------------------------------

"use client";

import Link from "next/link";
import { Users } from "lucide-react";
import { useUserRisk, type UserRiskItem } from "@/lib/api/ueba";
import { severityFromRisk, severityColors } from "@/lib/design-tokens";

function initials(user: string): string {
  const cleaned = user.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
  if (cleaned.length <= 3) return cleaned.padEnd(3, "·");
  return cleaned.slice(0, 3);
}

function fmtAgo(iso: string | null): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return iso;
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86_400)}d`;
}

export function UserRiskPanel() {
  const q = useUserRisk({ limit: 8 });
  const items = q.data?.items ?? [];

  return (
    <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
      <div className="flex items-center gap-2 mb-1">
        <Users className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
        <h3 className="text-sm font-bold text-[var(--strix-text)]">
          Top Risky Users (UEBA)
        </h3>
        <span className="ml-auto text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)] font-mono">
          src: {q.data?.source ?? "—"}
        </span>
      </div>
      <p className="text-[10px] text-[var(--strix-text-muted)] mb-4">
        Top 8 users by composite risk in the last 24 h · click to hunt
      </p>

      {q.isLoading && items.length === 0 ? (
        <SingleLine>Computing user risk…</SingleLine>
      ) : items.length === 0 ? (
        <SingleLine>
          No user-risk signals in window — full_log carries no audit-ID patterns yet.
        </SingleLine>
      ) : (
        <ul className="space-y-1">
          {items.map((u) => (
            <UserRow key={u.user} u={u} />
          ))}
        </ul>
      )}
    </div>
  );
}

function SingleLine({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] italic text-[var(--strix-text-muted)] py-2">
      {children}
    </p>
  );
}

function UserRow({ u }: { u: UserRiskItem }) {
  const sev = severityFromRisk(u.riskScore);
  const sevColor = severityColors[sev];
  const pct = Math.round(u.riskScore * 100);

  return (
    <li>
      <Link
        href={`/hunt?q=${encodeURIComponent(`user:${u.user}`)}`}
        className="group flex items-center gap-3 px-2 py-1.5 rounded hover:bg-[var(--strix-bg-surface)]/50"
        title={`${u.user} · risk ${u.riskScore.toFixed(3)} · max CKC ${u.maxCkcStage} · last ${fmtAgo(u.lastSeen)}`}
      >
        {/* Avatar */}
        <span
          className="h-7 w-7 rounded-full flex items-center justify-center text-[8px] font-bold tabular-nums"
          style={{
            backgroundColor: sevColor.bg,
            color: sevColor.fg,
            border: `1px solid ${sevColor.border}`,
          }}
        >
          {initials(u.user)}
        </span>

        {/* Identity + risk bar */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <span className="font-mono text-[12px] text-[var(--strix-text)] truncate">
              {u.user}
            </span>
            <span
              className="text-[10px] tabular-nums font-bold"
              style={{ color: sevColor.fg }}
            >
              {pct}%
            </span>
          </div>
          <div className="h-1 rounded-full bg-[rgba(128,182,195,0.12)] dark:bg-[var(--strix-border)] overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${pct}%`, background: sevColor.fg }}
            />
          </div>
          <p className="text-[9px] text-[var(--strix-text-muted)] mt-1 flex items-center gap-2">
            <span className="tabular-nums">{u.alertCount} alerts</span>
            <span>·</span>
            <span className="tabular-nums">{u.chainCount} chains</span>
            <span>·</span>
            <span className="tabular-nums">{u.hostsTouched} hosts</span>
            <span>·</span>
            <span>CKC {u.maxCkcStage}</span>
            <span className="ml-auto opacity-70">{fmtAgo(u.lastSeen)} ago</span>
          </p>
        </div>
      </Link>
    </li>
  );
}
