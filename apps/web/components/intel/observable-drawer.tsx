"use client";

// observable-drawer.tsx — right-slide enrichment drawer for a single
// observable (IP / hash / domain / email).
//
// The user-facing pivot move of the platform: paste/click any value
// and immediately see (1) the indicator record from intel_indicators,
// (2) the chains it appears in, (3) the actors and campaigns those
// chains are attributed to, (4) one click into /hunt or the chain.

import { useEffect } from "react";
import Link from "next/link";
import {
  X,
  Crosshair,
  Activity,
  Users,
  Target,
  Globe,
  Hash,
  Server,
  Mail,
  AlertTriangle,
  CheckCircle,
  Eye,
  HelpCircle,
  ExternalLink,
  ShieldAlert,
  Clock,
} from "lucide-react";

import { closeObservable, useObservableDrawer } from "@/lib/observable-store";
import { useObservableLookup } from "@/lib/api/intel";
import { cn } from "@/lib/utils";

const TYPE_ICONS: Record<string, typeof Globe> = {
  ip: Server,
  domain: Globe,
  url: Globe,
  email: Mail,
  hash: Hash,
};

const REP_CFG: Record<string, { color: string; bg: string; icon: typeof CheckCircle }> = {
  malicious:  { color: "text-rose-400",    bg: "bg-rose-500/10",    icon: AlertTriangle },
  suspicious: { color: "text-amber-400",   bg: "bg-amber-500/10",   icon: Eye },
  clean:      { color: "text-emerald-400", bg: "bg-emerald-500/10", icon: CheckCircle },
  unknown:    { color: "text-gray-400",    bg: "bg-gray-500/10",    icon: HelpCircle },
};

function relTime(iso: string | null): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "—";
  const sec = Math.max(0, (Date.now() - t) / 1000);
  if (sec < 60) return `${Math.floor(sec)}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function tlpBadge(tlp: string): { label: string; cls: string } {
  switch (tlp) {
    case "red":          return { label: "TLP:RED",         cls: "bg-red-500/15 text-red-400 border border-red-500/30" };
    case "amber+strict": return { label: "TLP:AMBER+STRICT", cls: "bg-amber-500/15 text-amber-400 border border-amber-500/30" };
    case "amber":        return { label: "TLP:AMBER",       cls: "bg-amber-500/10 text-amber-400 border border-amber-500/20" };
    case "green":        return { label: "TLP:GREEN",       cls: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" };
    default:             return { label: `TLP:${tlp.toUpperCase()}`, cls: "bg-strix-cyan/10 text-strix-cyan border border-strix-cyan/20" };
  }
}

function inferReputation(sourceLabel: string | undefined, tags: string[] | undefined): string {
  if (!sourceLabel) return "unknown";
  if (sourceLabel === "urlhaus" || sourceLabel === "feodotracker") return "malicious";
  if (sourceLabel === "internal_observation") {
    // Internal observation is suspicious-by-default — STRIX saw it but
    // hasn't tied it to a feed-classified malicious record yet.
    return tags?.includes("malicious") ? "malicious" : "suspicious";
  }
  return "unknown";
}

export function ObservableDrawer() {
  const { open, value } = useObservableDrawer();
  const lookup = useObservableLookup(open ? value : null);

  // Lock scroll under the drawer + Esc to close.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeObservable();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!open || !value) return null;

  const data = lookup.data;
  const indicator = data?.indicator ?? null;
  const indType = data?.indicatorType ?? indicator?.indicatorType ?? null;
  const TypeIcon = (indType && TYPE_ICONS[indType]) || Crosshair;
  const reputation = inferReputation(indicator?.sourceLabel, indicator?.tags);
  const rep = REP_CFG[reputation] ?? REP_CFG.unknown;
  const RepIcon = rep.icon;
  const tlp = indicator ? tlpBadge(indicator.tlp) : null;

  return (
    <>
      {/* Scrim */}
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm animate-fade-in"
        onClick={closeObservable}
        aria-hidden
      />
      {/* Panel */}
      <aside
        className="fixed right-0 top-0 z-50 h-full w-full max-w-[440px] bg-[var(--strix-bg-card)] border-l border-[var(--strix-border)] shadow-2xl flex flex-col animate-slide-in-right"
        role="dialog"
        aria-label="Observable enrichment"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 p-5 border-b border-[var(--strix-border)]">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1.5">
              <TypeIcon className="h-4 w-4 text-strix-cyan" />
              <span className="text-[9px] font-bold uppercase tracking-wider text-[var(--strix-text-muted)]">
                {indType ?? "observable"}
              </span>
              {tlp && (
                <span className={cn("text-[8px] font-mono uppercase px-1.5 py-0.5 rounded", tlp.cls)}>
                  {tlp.label}
                </span>
              )}
            </div>
            <p className="font-mono text-[14px] font-bold text-[var(--strix-text)] break-all leading-snug">
              {value}
            </p>
          </div>
          <button
            onClick={closeObservable}
            className="shrink-0 p-1 rounded hover:bg-[var(--strix-bg-surface)] text-[var(--strix-text-muted)]"
            aria-label="Close drawer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {lookup.isLoading && (
            <p className="text-xs text-[var(--strix-text-muted)] italic">Looking up…</p>
          )}

          {!lookup.isLoading && data && (
            <>
              {/* Reputation pill + summary stats */}
              <div className="grid grid-cols-2 gap-3">
                <div className={cn("p-3 rounded-xl border", rep.bg, "border-[var(--strix-border)]")}>
                  <div className="flex items-center gap-1.5 mb-1">
                    <RepIcon className={cn("h-3 w-3", rep.color)} />
                    <span className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)]">
                      reputation
                    </span>
                  </div>
                  <p className={cn("text-sm font-bold uppercase", rep.color)}>{reputation}</p>
                </div>
                <div className="p-3 rounded-xl border border-[var(--strix-border)] bg-[var(--strix-bg-surface)]">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Activity className="h-3 w-3 text-strix-cyan" />
                    <span className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)]">
                      chain hits
                    </span>
                  </div>
                  <p className="text-sm font-bold text-[var(--strix-text)]">
                    {data.totalChainHits}
                  </p>
                </div>
              </div>

              {/* First / last seen + source */}
              <div className="rounded-xl border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] p-3 space-y-1.5">
                <KV label="Source" value={indicator?.sourceLabel ?? "—"} mono />
                <KV
                  label="First seen"
                  value={data.firstSeen ? `${relTime(data.firstSeen)} · ${new Date(data.firstSeen).toLocaleString()}` : "—"}
                />
                <KV
                  label="Last seen"
                  value={data.lastSeen ? `${relTime(data.lastSeen)} · ${new Date(data.lastSeen).toLocaleString()}` : "—"}
                />
                {indicator?.internalHitCount != null && indicator.internalHitCount > 0 && (
                  <KV label="Internal hits" value={String(indicator.internalHitCount)} mono />
                )}
                {indicator?.tags && indicator.tags.length > 0 && (
                  <div className="pt-1.5 border-t border-[var(--strix-border)] flex flex-wrap gap-1">
                    {indicator.tags.map((t) => (
                      <span
                        key={t}
                        className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-strix-cyan/10 text-strix-cyan"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Actors */}
              {data.actors.length > 0 && (
                <Section icon={ShieldAlert} title="Linked actors">
                  <div className="space-y-1.5">
                    {data.actors.map((a) => (
                      <Link
                        key={a.actorId}
                        href={`/intel/actors/${a.actorId}`}
                        onClick={closeObservable}
                        className="flex items-center justify-between gap-2 p-2.5 rounded-lg border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] hover:border-strix-cyan/40 hover:bg-strix-cyan/5 transition-colors"
                      >
                        <div className="min-w-0">
                          <p className="text-xs font-bold text-[var(--strix-text)] truncate">{a.name}</p>
                          <p className="text-[10px] text-[var(--strix-text-muted)] font-mono">
                            {a.mitreGroupId ?? "—"}
                          </p>
                        </div>
                        <span className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)] shrink-0">
                          {a.chainCount} chain{a.chainCount === 1 ? "" : "s"}
                        </span>
                      </Link>
                    ))}
                  </div>
                </Section>
              )}

              {/* Campaigns */}
              {data.campaigns.length > 0 && (
                <Section icon={Target} title="Linked campaigns">
                  <div className="space-y-1.5">
                    {data.campaigns.map((c) => (
                      <Link
                        key={c.campaignId}
                        href={`/intel/campaigns/${c.campaignId}`}
                        onClick={closeObservable}
                        className="flex items-center justify-between gap-2 p-2.5 rounded-lg border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] hover:border-strix-cyan/40 hover:bg-strix-cyan/5 transition-colors"
                      >
                        <div className="min-w-0">
                          <p className="text-xs font-bold text-[var(--strix-text)] truncate">{c.name}</p>
                          <p className="text-[10px] text-[var(--strix-text-muted)] truncate">
                            {c.actorName ?? "—"}
                          </p>
                        </div>
                        <span className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)] shrink-0">
                          {c.chainCount} chain{c.chainCount === 1 ? "" : "s"}
                        </span>
                      </Link>
                    ))}
                  </div>
                </Section>
              )}

              {/* Chains */}
              <Section icon={Users} title={`Chains (${data.chains.length}${data.totalChainHits > data.chains.length ? ` of ${data.totalChainHits}` : ""})`}>
                {data.chains.length === 0 ? (
                  <p className="text-[10px] text-[var(--strix-text-muted)] italic">
                    No attack chains in the current alert window reference this observable.
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {data.chains.map((c) => (
                      <Link
                        key={c.chainId}
                        href={`/attack-analysis/${c.chainId}`}
                        onClick={closeObservable}
                        className="block p-2.5 rounded-lg border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] hover:border-strix-cyan/40 hover:bg-strix-cyan/5 transition-colors"
                      >
                        <div className="flex items-center justify-between gap-2 mb-0.5">
                          <p className="font-mono text-[11px] text-[var(--strix-text)] truncate">
                            {c.hostName ?? c.hostId ?? c.chainId.slice(0, 8)}
                          </p>
                          {c.ckcStage != null && (
                            <span className="shrink-0 text-[9px] font-bold uppercase tracking-wider text-amber-400">
                              stage {c.ckcStage} · {c.ckcStageName}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center justify-between text-[10px] text-[var(--strix-text-muted)]">
                          <span className="flex items-center gap-1">
                            <Clock className="h-2.5 w-2.5" />
                            {relTime(c.occurredAt)}
                          </span>
                          {c.triageStatus && (
                            <span className="font-mono uppercase">{c.triageStatus}</span>
                          )}
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </Section>
            </>
          )}
        </div>

        {/* Footer — pivot action */}
        <div className="p-4 border-t border-[var(--strix-border)] flex items-center gap-2">
          <Link
            href={`/hunt?q=${encodeURIComponent(value)}`}
            onClick={closeObservable}
            className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-strix-cyan text-strix-bg-deep dark:text-[#0b1416] text-[10px] font-bold uppercase tracking-wider hover:opacity-90 transition-opacity"
          >
            Pivot to Hunt
            <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
      </aside>
    </>
  );
}

function KV({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 text-[10px]">
      <span className="uppercase tracking-wider text-[var(--strix-text-muted)] shrink-0">{label}</span>
      <span className={cn("text-[var(--strix-text)] truncate text-right", mono && "font-mono")}>
        {value}
      </span>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Globe;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <Icon className="h-3 w-3 text-[var(--strix-text-muted)]" />
        <h4 className="text-[10px] font-bold uppercase tracking-wider text-[var(--strix-text-muted)]">
          {title}
        </h4>
      </div>
      {children}
    </div>
  );
}

// -----------------------------------------------------------------------------
// ObservableLink — wraps a value in a button that opens the drawer.
// Convenient where the rendered string is already the indicator.
// -----------------------------------------------------------------------------

import { openObservable } from "@/lib/observable-store";

export function ObservableLink({
  value,
  children,
  className,
}: {
  value: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        openObservable(value);
      }}
      className={cn(
        "font-mono text-strix-cyan hover:underline cursor-pointer text-left",
        className,
      )}
      title="Open enrichment drawer"
    >
      {children ?? value}
    </button>
  );
}
