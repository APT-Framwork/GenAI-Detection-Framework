"use client"

import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import {
  Server,
  Database,
  Shield,
  Key,
  ChevronRight,
  Plus,
} from "lucide-react"
import { toast } from "@/lib/toast"
import { randomKey } from "@/lib/download"

// Persisted settings live in localStorage under this key. The page
// hydrates from localStorage on mount and writes back on Synchronize.
const SETTINGS_LS_KEY = "strix:settings:v1"

interface PersistedSettings {
  highVisibility: boolean
  animateTransitions: boolean
  compactGrid: boolean
  density: string
  anomalySensitivity: number
  falsePositiveAggression: number
  retentionDays: number
  apiKeys: { id: string; label: string; preview: string }[]
}

const DEFAULTS: PersistedSettings = {
  highVisibility: true,
  animateTransitions: false,
  compactGrid: true,
  density: "Loose",
  anomalySensitivity: 0.65,
  falsePositiveAggression: 0.3,
  retentionDays: 90,
  apiKeys: [
    { id: "k1", label: "st_pk_default", preview: "st_pk_••••8x2k" },
    { id: "k2", label: "st_sk_default", preview: "st_sk_••••4m9p" },
  ],
}

function loadSettings(): PersistedSettings {
  if (typeof window === "undefined") return DEFAULTS
  try {
    const raw = window.localStorage.getItem(SETTINGS_LS_KEY)
    if (!raw) return DEFAULTS
    return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {
    return DEFAULTS
  }
}

/* ------------------------------------------------------------------ */
/*  Toggle                                                            */
/* ------------------------------------------------------------------ */
function Toggle({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-[20px] w-[40px] shrink-0 cursor-pointer rounded-[9999px] transition-colors",
        checked
          ? "bg-[#00666d] dark:bg-[#00666d]"
          : "bg-[rgba(128,182,195,0.3)]"
      )}
    >
      <span
        className={cn(
          "pointer-events-none inline-block h-[16px] w-[16px] rounded-full shadow transition-transform translate-y-[2px]",
          checked
            ? "translate-x-[22px] bg-[#cffbff]"
            : "translate-x-[2px] bg-white"
        )}
      />
    </button>
  )
}

/* ------------------------------------------------------------------ */
/*  Slider                                                            */
/* ------------------------------------------------------------------ */
function Slider({
  value,
  onChange,
  min = 0,
  max = 1,
  step = 0.01,
}: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
}) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div className="relative w-full h-[6px] rounded-full bg-[#baf1ff] dark:bg-[rgba(186,241,255,0.2)]">
      {/* fill */}
      <div
        className="absolute inset-y-0 left-0 rounded-full bg-[#00666d]"
        style={{ width: `${pct}%` }}
      />
      {/* thumb */}
      <div
        className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-[18px] w-[18px] rounded-full bg-[#00666d] border-4 border-[#cffbff] shadow cursor-pointer"
        style={{ left: `${pct}%` }}
      />
      {/* invisible range input for interaction */}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Pill Selector                                                     */
/* ------------------------------------------------------------------ */
function PillSelector({
  options,
  value,
  onChange,
}: {
  options: string[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="inline-flex items-center gap-[2px] bg-[#baf1ff] dark:bg-[rgba(186,241,255,0.15)] rounded-[9999px] p-[4px]">
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className={cn(
            "px-[14px] py-[4px] rounded-[9999px] text-[12px] font-medium transition-all",
            value === opt
              ? "bg-white dark:bg-[var(--strix-bg-card)] shadow text-[#00343d] dark:text-[var(--strix-text)]"
              : "text-[#2b636f] dark:text-[var(--strix-text-muted)] hover:text-[#00343d]"
          )}
        >
          {opt}
        </button>
      ))}
    </div>
  )
}

/* ================================================================== */
/*  Settings Page                                                     */
/* ================================================================== */
export default function SettingsPage() {
  /* Toggles */
  const [highVisibility, setHighVisibility] = useState(DEFAULTS.highVisibility)
  const [animateTransitions, setAnimateTransitions] = useState(DEFAULTS.animateTransitions)
  const [compactGrid, setCompactGrid] = useState(DEFAULTS.compactGrid)

  /* Display density */
  const [density, setDensity] = useState(DEFAULTS.density)

  /* Sliders */
  const [anomalySensitivity, setAnomalySensitivity] = useState(DEFAULTS.anomalySensitivity)
  const [falsePositiveAggression, setFalsePositiveAggression] = useState(DEFAULTS.falsePositiveAggression)

  /* Data retention + API keys */
  const [retentionDays, setRetentionDays] = useState(DEFAULTS.retentionDays)
  const [apiKeys, setApiKeys] = useState(DEFAULTS.apiKeys)
  // Last-saved snapshot so "Discard Changes" restores it.
  const savedRef = useRef<PersistedSettings>(DEFAULTS)

  useEffect(() => {
    const s = loadSettings()
    savedRef.current = s
    setHighVisibility(s.highVisibility)
    setAnimateTransitions(s.animateTransitions)
    setCompactGrid(s.compactGrid)
    setDensity(s.density)
    setAnomalySensitivity(s.anomalySensitivity)
    setFalsePositiveAggression(s.falsePositiveAggression)
    setRetentionDays(s.retentionDays)
    setApiKeys(s.apiKeys)
  }, [])

  const onConfigureMfa = () => {
    toast.info(
      "MFA enrolment requires a TOTP authenticator app. Provisioning flow not enabled in this build.",
      5000,
    )
  }

  const onGenerateKey = () => {
    const raw = `st_sk_${randomKey(24)}`
    const preview = `${raw.slice(0, 6)}••••${raw.slice(-4)}`
    setApiKeys((prev) => [...prev, { id: `k${Date.now()}`, label: raw, preview }])
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(raw).catch(() => undefined)
      toast.success("New API key generated. Full key copied to clipboard — store it now, it won't be shown again.", 6000)
    } else {
      toast.success(`New API key generated: ${raw}`, 8000)
    }
  }

  const onEditRetention = () => {
    if (typeof window === "undefined") return
    const v = window.prompt("Data retention (days):", String(retentionDays))
    if (v == null) return
    const n = parseInt(v, 10)
    if (!Number.isFinite(n) || n <= 0 || n > 3650) {
      toast.error("Retention must be a positive integer (≤ 3650 days).")
      return
    }
    setRetentionDays(n)
    toast.success(`Retention staged at ${n} days. Press Synchronize to persist.`)
  }

  const onDiscard = () => {
    const s = savedRef.current
    setHighVisibility(s.highVisibility)
    setAnimateTransitions(s.animateTransitions)
    setCompactGrid(s.compactGrid)
    setDensity(s.density)
    setAnomalySensitivity(s.anomalySensitivity)
    setFalsePositiveAggression(s.falsePositiveAggression)
    setRetentionDays(s.retentionDays)
    setApiKeys(s.apiKeys)
    toast.info("Pending changes discarded.")
  }

  const onSynchronize = () => {
    const next: PersistedSettings = {
      highVisibility,
      animateTransitions,
      compactGrid,
      density,
      anomalySensitivity,
      falsePositiveAggression,
      retentionDays,
      apiKeys,
    }
    try {
      window.localStorage.setItem(SETTINGS_LS_KEY, JSON.stringify(next))
      savedRef.current = next
      toast.success("Configuration synchronized.")
    } catch {
      toast.error("Failed to persist settings (localStorage unavailable).")
    }
  }

  return (
    <div className="space-y-[24px]">
      {/* ============================================================ */}
      {/*  12-col Grid                                                 */}
      {/* ============================================================ */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-[24px]">
        {/* ========================================================== */}
        {/*  LEFT COLUMN — cols 1-4                                    */}
        {/* ========================================================== */}
        <div className="lg:col-span-4 space-y-[24px]">
          {/* ------ Platform Configuration Card ------ */}
          <div className="bg-[#d6f6ff] dark:bg-[var(--strix-bg-card)] rounded-[48px] p-[32px]">
            <h2 className="text-[18px] font-bold text-[#00343d] dark:text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif] mb-[20px]">
              Platform Configuration
            </h2>

            {/* Cluster Node Alpha */}
            <div className="bg-white dark:bg-[var(--strix-bg-surface,#1a2e33)] rounded-[32px] p-[16px] border-b-2 border-[rgba(0,102,109,0.1)] mb-[12px]">
              <div className="flex items-center gap-[12px]">
                <div className="flex items-center justify-center h-[36px] w-[36px] rounded-[12px] bg-[#e7faff] dark:bg-[rgba(135,237,246,0.1)]">
                  <Server className="h-[18px] w-[18px] text-[#00666d] dark:text-[#87edf6]" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[14px] font-semibold text-[#00343d] dark:text-[var(--strix-text)]">
                    Cluster Node Alpha
                  </p>
                  <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    Active Region: US-East-1
                  </p>
                </div>
                <ChevronRight className="h-[16px] w-[16px] text-[#497f8b] dark:text-[var(--strix-text-muted)]" />
              </div>
            </div>

            {/* Data Retention */}
            <div className="bg-white dark:bg-[var(--strix-bg-surface,#1a2e33)] rounded-[32px] p-[16px]">
              <div className="flex items-center gap-[12px]">
                <div className="flex items-center justify-center h-[36px] w-[36px] rounded-[12px] bg-[#e7faff] dark:bg-[rgba(135,237,246,0.1)]">
                  <Database className="h-[18px] w-[18px] text-[#00666d] dark:text-[#87edf6]" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[14px] font-semibold text-[#00343d] dark:text-[var(--strix-text)]">
                    Data Retention
                  </p>
                  <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    Policy: {retentionDays} Days
                  </p>
                </div>
                <button
                  onClick={onEditRetention}
                  className="text-[12px] font-semibold text-[#00666d] dark:text-[#87edf6] hover:underline"
                >
                  Edit
                </button>
              </div>
            </div>
          </div>

          {/* ------ Interface Preferences Card ------ */}
          <div className="bg-[#d6f6ff] dark:bg-[var(--strix-bg-card)] rounded-[48px] p-[32px]">
            <h2 className="text-[18px] font-bold text-[#00343d] dark:text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif] mb-[20px]">
              Interface Preferences
            </h2>

            <div className="space-y-[14px]">
              {/* High Visibility Mode */}
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-[#00343d] dark:text-[var(--strix-text)]">
                  High Visibility Mode
                </span>
                <Toggle checked={highVisibility} onChange={setHighVisibility} />
              </div>

              {/* Animate Transitions */}
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-[#00343d] dark:text-[var(--strix-text)]">
                  Animate Transitions
                </span>
                <Toggle
                  checked={animateTransitions}
                  onChange={setAnimateTransitions}
                />
              </div>

              {/* Compact Grid View */}
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-[#00343d] dark:text-[var(--strix-text)]">
                  Compact Grid View
                </span>
                <Toggle checked={compactGrid} onChange={setCompactGrid} />
              </div>
            </div>

            {/* Display Density */}
            <div className="mt-[20px]">
              <span className="block text-[12px] font-medium text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-[8px]">
                Display Density
              </span>
              <PillSelector
                options={["Loose", "Mid", "Tight"]}
                value={density}
                onChange={setDensity}
              />
            </div>
          </div>
        </div>

        {/* ========================================================== */}
        {/*  RIGHT COLUMN — cols 5-12                                  */}
        {/* ========================================================== */}
        <div className="lg:col-span-8 space-y-[24px]">
          {/* ------ Security Bento (2-col) ------ */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-[24px] h-auto md:h-[333px]">
            {/* MFA Card */}
            <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] shadow p-[32px] flex flex-col">
              <div className="flex items-start gap-[12px] mb-[16px]">
                <div className="flex items-center justify-center h-[40px] w-[40px] rounded-[14px] bg-[#e7faff] dark:bg-[rgba(135,237,246,0.1)]">
                  <Shield className="h-[20px] w-[20px] text-[#00666d] dark:text-[#87edf6]" />
                </div>
                <span className="inline-flex items-center px-[10px] py-[3px] rounded-[9999px] bg-[rgba(0,94,160,0.1)] text-[#005ea0] text-[10px] font-semibold">
                  Encrypted
                </span>
              </div>
              <h3 className="text-[20px] font-bold text-[#00343d] dark:text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif] mb-[8px]">
                Multi-Factor Auth
              </h3>
              <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] leading-relaxed flex-1">
                Biometric + TOTP verification required for all critical
                operations. Enforces layered identity checks on every session.
              </p>
              <button
                onClick={onConfigureMfa}
                className="mt-[16px] self-start bg-[#d6f6ff] dark:bg-[rgba(0,102,109,0.2)] text-[#00666d] dark:text-[#87edf6] text-[13px] font-semibold rounded-[32px] px-[24px] py-[10px] hover:opacity-90 transition-opacity"
              >
                Configure MFA
              </button>
            </div>

            {/* API Key Registry Card */}
            <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] shadow p-[32px] flex flex-col">
              <div className="flex items-center justify-between mb-[16px]">
                <div className="flex items-center justify-center h-[40px] w-[40px] rounded-[14px] bg-[#e7faff] dark:bg-[rgba(135,237,246,0.1)]">
                  <Key className="h-[20px] w-[20px] text-[#00666d] dark:text-[#87edf6]" />
                </div>
                <button
                  onClick={onGenerateKey}
                  className="flex items-center gap-[4px] text-[12px] font-semibold text-[#00666d] dark:text-[#87edf6] hover:underline"
                >
                  <Plus className="h-[14px] w-[14px]" />
                  Generate
                </button>
              </div>
              <h3 className="text-[20px] font-bold text-[#00343d] dark:text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif] mb-[16px]">
                API Key Registry
              </h3>
              <div className="space-y-[8px] flex-1 max-h-[140px] overflow-y-auto">
                {apiKeys.map((k) => (
                  <div key={k.id} className="bg-[#e7faff] dark:bg-[rgba(135,237,246,0.05)] rounded-[32px] p-[12px] px-[18px] flex items-center justify-between gap-2">
                    <span className="text-[13px] font-mono text-[#00343d] dark:text-[var(--strix-text)] truncate">
                      {k.preview}
                    </span>
                    <button
                      onClick={() => {
                        setApiKeys((prev) => prev.filter((p) => p.id !== k.id))
                        toast.info("Key revoked locally — Synchronize to persist.")
                      }}
                      className="text-[11px] text-rose-500 hover:underline shrink-0"
                    >
                      revoke
                    </button>
                  </div>
                ))}
                {apiKeys.length === 0 && (
                  <div className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] italic">
                    No API keys yet — click Generate.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ------ AI Alert Thresholds ------ */}
          <div className="bg-[#d6f6ff] dark:bg-[var(--strix-bg-card)] rounded-[48px] p-[32px]">
            {/* Header row */}
            <div className="flex items-start justify-between mb-[28px]">
              <div>
                <h2 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif]">
                  AI Alert Thresholds
                </h2>
                <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-[4px]">
                  Fine-tune detection sensitivity and response escalation
                </p>
              </div>
              <div className="text-right">
                <p className="text-[30px] font-bold text-[#00666d] dark:text-[#87edf6] leading-none font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif]">
                  82%
                </p>
                <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-[2px]">
                  Global Accuracy
                </p>
              </div>
            </div>

            {/* Anomaly Detection Sensitivity */}
            <div className="mb-[24px]">
              <div className="flex items-center justify-between mb-[4px]">
                <div>
                  <p className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    Anomaly Detection Sensitivity
                  </p>
                  <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-[2px]">
                    Triggers behavioral analysis on deviation score
                  </p>
                </div>
                <span className="text-[14px] font-mono text-[#00343d] dark:text-[var(--strix-text)] font-semibold">
                  {anomalySensitivity.toFixed(2)}&lambda;
                </span>
              </div>
              <div className="mt-[12px]">
                <Slider
                  value={anomalySensitivity}
                  onChange={setAnomalySensitivity}
                  min={0}
                  max={1}
                  step={0.01}
                />
              </div>
            </div>

            {/* False Positive Aggression */}
            <div className="mb-[28px]">
              <div className="flex items-center justify-between mb-[4px]">
                <div>
                  <p className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    False Positive Aggression
                  </p>
                  <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-[2px]">
                    Filters noise from low-confidence detections
                  </p>
                </div>
                <span className="text-[14px] font-mono text-[#00343d] dark:text-[var(--strix-text)] font-semibold">
                  Low Filter
                </span>
              </div>
              <div className="mt-[12px]">
                <Slider
                  value={falsePositiveAggression}
                  onChange={setFalsePositiveAggression}
                  min={0}
                  max={1}
                  step={0.01}
                />
              </div>
            </div>

            {/* Alert Priority Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-[12px]">
              {/* Standard */}
              <div className="bg-white dark:bg-[var(--strix-bg-surface,#1a2e33)] rounded-[32px] p-[16px] border-l-4 border-[#00666d]">
                <p className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                  Standard
                </p>
                <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-[2px]">
                  Log Only
                </p>
              </div>
              {/* Unusual */}
              <div className="bg-white dark:bg-[var(--strix-bg-surface,#1a2e33)] rounded-[32px] p-[16px] border-l-4 border-[#005ea0]">
                <p className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                  Unusual
                </p>
                <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-[2px]">
                  Email
                </p>
              </div>
              {/* Critical */}
              <div className="bg-white dark:bg-[var(--strix-bg-surface,#1a2e33)] rounded-[32px] p-[16px] border-l-4 border-[#b31b25]">
                <p className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                  Critical
                </p>
                <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-[2px]">
                  SMS + Pager
                </p>
              </div>
            </div>
          </div>

          {/* ------ Action Bar ------ */}
          <div className="flex justify-end gap-[16px]">
            <button
              onClick={onDiscard}
              className="text-[14px] font-medium text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00343d] dark:hover:text-[var(--strix-text)] transition-colors"
            >
              Discard Changes
            </button>
            <button
              onClick={onSynchronize}
              className="bg-[#00666d] text-[#cffbff] text-[14px] font-semibold rounded-[32px] px-[40px] py-[12px] shadow hover:opacity-90 transition-opacity"
            >
              Synchronize Configuration
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
