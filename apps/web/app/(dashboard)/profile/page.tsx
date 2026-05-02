"use client"

import { useEffect, useState } from "react"
import { useAuthStore } from "@/stores/auth-store"
import { cn } from "@/lib/utils"
import {
  User,
  Fingerprint,
  KeyRound,
  Smartphone,
  Check,
  AlertTriangle,
  Pencil,
  Download,
  X,
} from "lucide-react"
import { toast } from "@/lib/toast"
import { downloadJson } from "@/lib/download"

const PROFILE_LS_KEY = "strix:profile:v1"

interface EditableProfile {
  name: string
  role: string
  site: string
}

const activityLogEntries = [
  {
    time: "14:22:01",
    type: "AUTH_SUCCESS",
    message: "Biometric validation confirmed at Terminal_Node_4.",
    color: "#00666d",
  },
  {
    time: "14:35:12",
    type: "SEC_AUDIT",
    message: "Deep packet inspection initiated on inbound segment 0x3F.",
    color: "#005ea0",
  },
  {
    time: "15:01:44",
    type: "SYS_CHECK",
    message: "Kernel heartbeat stable. Sentinel_Core_01 active status updated.",
    color: "#006574",
  },
  {
    time: "15:12:09",
    type: "ALERT_MITIGATED",
    message: "Unauthorized script execution blocked on DB_Cluster_7.",
    color: "#b31b25",
  },
  {
    time: "15:45:30",
    type: "SYSLOG_EXPORT",
    message: "Metadata archive compressed and sent to Vault_B.",
    color: "#00666d",
  },
  {
    time: "16:00:00",
    type: "SHIFT_SYNC",
    message: "Handover protocols initiated for Sector 7G.",
    color: "#006574",
  },
]

const threatBars = [
  { day: "Mon", height: 60 },
  { day: "Tue", height: 85 },
  { day: "Wed", height: 45 },
  { day: "Thu", height: 95 },
  { day: "Fri", height: 70 },
  { day: "Sat", height: 30 },
  { day: "Sun", height: 50 },
]

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user)
  const [overrides, setOverrides] = useState<Partial<EditableProfile>>({})
  const [editing, setEditing] = useState(false)

  // Hydrate user-edited overrides from localStorage on mount.
  useEffect(() => {
    if (typeof window === "undefined") return
    try {
      const raw = window.localStorage.getItem(PROFILE_LS_KEY)
      if (raw) setOverrides(JSON.parse(raw))
    } catch { /* ignore */ }
  }, [])

  const baseProfile = user || {
    name: "SENTINEL_CORE_01",
    role: "Senior Security Operations Analyst",
    site: "Site Alpha",
    level: 4,
    tags: ["INCIDENT_RESPONSE", "THREAT_HUNTING", "CRYPTOGRAPHY"],
  }
  const profile = { ...baseProfile, ...overrides }

  const onExportLogs = () => {
    const payload = {
      exportedAt: new Date().toISOString(),
      operator: profile.name,
      role: profile.role,
      site: profile.site,
      activity: activityLogEntries,
    }
    const stamp = new Date().toISOString().replace(/[:.]/g, "-")
    downloadJson(`strix-profile-${profile.name}-${stamp}.json`, payload)
    toast.success("Profile activity log exported.")
  }

  const onSaveProfile = (next: EditableProfile) => {
    setOverrides(next)
    try {
      window.localStorage.setItem(PROFILE_LS_KEY, JSON.stringify(next))
    } catch { /* ignore */ }
    setEditing(false)
    toast.success("Profile updated.")
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <p className="text-[10px] text-[#00666d] dark:text-[#87edf6] uppercase tracking-widest font-semibold mb-1">
          OPERATOR PROFILE
        </p>
        <h1 className="text-3xl font-black text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif]">
          Sentinel Profile
        </h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* ========== LEFT COLUMN (col 1-8) ========== */}
        <div className="lg:col-span-8 space-y-6">
          {/* --- User Identity Card --- */}
          <div
            className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] h-auto min-h-[214px] shadow-md border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] p-8 flex flex-col sm:flex-row items-center gap-8"
          >
            {/* Avatar */}
            <div className="relative flex-shrink-0">
              <div className="h-[128px] w-[128px] rounded-[48px] border-4 border-[rgba(0,102,109,0.2)] dark:border-[rgba(135,237,246,0.2)] bg-[#e7faff] dark:bg-[var(--strix-bg-surface)] flex items-center justify-center">
                <User className="h-14 w-14 text-[#00666d] dark:text-[#87edf6]" />
              </div>
              {/* LVL Badge */}
              <div className="absolute bottom-0 right-0 bg-[#00666d] dark:bg-[#87edf6] text-[#cffbff] dark:text-[#00343d] rounded-[32px] p-[8px] text-[12px] font-bold leading-none">
                LVL 4
              </div>
            </div>

            {/* Info */}
            <div className="flex-1 flex flex-col items-center sm:items-start gap-3">
              <div>
                <h2 className="text-[36px] font-bold uppercase tracking-[-0.9px] text-[#00343d] dark:text-[var(--strix-text)] leading-tight font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif]">
                  {profile.name}
                </h2>
                <p className="text-[12px] uppercase tracking-[1.2px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-1">
                  {profile.role} &bull; {profile.site}
                </p>
              </div>

              {/* Tags */}
              <div className="flex flex-wrap gap-2">
                {(profile.tags || ["INCIDENT_RESPONSE", "THREAT_HUNTING", "CRYPTOGRAPHY"]).map(
                  (tag: string, i: number) => (
                    <span
                      key={i}
                      className="bg-[#baf1ff] dark:bg-[rgba(135,237,246,0.15)] text-[#00666d] dark:text-[#87edf6] rounded-[9999px] px-[12px] py-[4px] text-[12px] font-bold"
                    >
                      {tag}
                    </span>
                  )
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row gap-2 mt-1">
                <button
                  onClick={() => setEditing(true)}
                  className="bg-[#00666d] dark:bg-[#87edf6] text-[#cffbff] dark:text-[#00343d] rounded-[9999px] px-[24px] py-[12px] text-[12px] font-bold uppercase tracking-wider flex items-center gap-2 hover:opacity-90 transition-opacity"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit Profile
                </button>
                <button
                  onClick={onExportLogs}
                  className="bg-[#87edf6] dark:bg-[rgba(135,237,246,0.15)] text-[#00575d] dark:text-[#87edf6] rounded-[9999px] px-[24px] py-[12px] text-[12px] font-bold uppercase tracking-wider flex items-center gap-2 hover:opacity-90 transition-opacity"
                >
                  <Download className="h-3.5 w-3.5" />
                  Export Logs
                </button>
              </div>
            </div>
          </div>

          {/* --- Performance Metrics --- */}
          <div className="grid grid-cols-3 gap-6">
            {[
              {
                value: "94%",
                title: "Efficiency",
                subtitle: "System Optimization Rating",
                borderColor: "#00666d",
                darkBorderColor: "#87edf6",
              },
              {
                value: "99.8%",
                title: "Accuracy",
                subtitle: "False Positive Mitigation",
                borderColor: "#005ea0",
                darkBorderColor: "#5eb8ff",
              },
              {
                value: "12m",
                title: "Response Time",
                subtitle: "Mean Time To Resolution",
                borderColor: "#006574",
                darkBorderColor: "#00c4d6",
              },
            ].map((metric, i) => (
              <div
                key={i}
                className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] h-[190px] flex flex-col items-center justify-center gap-3 p-6"
              >
                <div
                  className="h-[64px] w-[64px] rounded-full border-4 flex items-center justify-center"
                  style={{
                    borderColor: metric.borderColor,
                  }}
                >
                  <span className="text-[16px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    {metric.value}
                  </span>
                </div>
                <div className="text-center">
                  <p className="text-[16px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    {metric.title}
                  </p>
                  <p className="text-[12px] uppercase text-[#497f8b] dark:text-[var(--strix-text-muted)] tracking-wider">
                    {metric.subtitle}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* --- Activity Log Terminal --- */}
          <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] shadow-md border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] overflow-clip p-[5px]">
            {/* Terminal Header */}
            <div className="bg-[#d6f6ff] dark:bg-[var(--strix-bg-surface)] rounded-t-[44px] px-6 py-3 flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <div className="h-[10px] w-[10px] rounded-full bg-[#b31b25]" />
                <div className="h-[10px] w-[10px] rounded-full bg-[#006574] opacity-40" />
                <div className="h-[10px] w-[10px] rounded-full bg-[#006574] opacity-40" />
              </div>
              <span className="text-[10px] uppercase tracking-widest text-[#497f8b] dark:text-[var(--strix-text-muted)] font-semibold">
                System_Activity_Log.sys
              </span>
            </div>

            {/* Terminal Body */}
            <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-b-[44px] p-6 font-mono text-[13px] leading-relaxed space-y-1" style={{ fontFamily: "'Liberation Mono', 'Courier New', monospace" }}>
              {activityLogEntries.map((entry, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)] flex-shrink-0">
                    [{entry.time}]
                  </span>
                  <span
                    className="font-bold flex-shrink-0"
                    style={{ color: entry.color }}
                  >
                    {entry.type}
                  </span>
                  <span className="text-[#00343d] dark:text-[var(--strix-text)]">
                    {entry.message}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ========== RIGHT COLUMN (col 9-12) ========== */}
        <div className="lg:col-span-4 space-y-6">
          {/* --- Security Credentials --- */}
          <div className="bg-[#d6f6ff] dark:bg-[var(--strix-bg-surface)] rounded-[48px] p-[32px]">
            <h3 className="text-[20px] font-bold text-[#00343d] dark:text-[var(--strix-text)] pb-4 mb-4 border-b border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif]">
              Security Credentials
            </h3>

            <div className="space-y-3">
              {/* Biometric ID */}
              <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] p-[16px] flex items-center gap-3">
                <div className="h-[40px] w-[40px] rounded-[32px] bg-[rgba(0,102,109,0.1)] dark:bg-[rgba(135,237,246,0.1)] flex items-center justify-center flex-shrink-0">
                  <Fingerprint className="h-5 w-5 text-[#00666d] dark:text-[#87edf6]" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    Biometric ID
                  </p>
                  <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    Verified 2h ago
                  </p>
                </div>
                <div className="h-[24px] w-[24px] rounded-full bg-[rgba(0,102,109,0.1)] dark:bg-[rgba(135,237,246,0.1)] flex items-center justify-center flex-shrink-0">
                  <Check className="h-3.5 w-3.5 text-[#00666d] dark:text-[#87edf6]" />
                </div>
              </div>

              {/* Hardware Key */}
              <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] p-[16px] flex items-center gap-3">
                <div className="h-[40px] w-[40px] rounded-[32px] bg-[rgba(0,94,160,0.1)] dark:bg-[rgba(94,184,255,0.1)] flex items-center justify-center flex-shrink-0">
                  <KeyRound className="h-5 w-5 text-[#005ea0] dark:text-[#5eb8ff]" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    Hardware Key
                  </p>
                  <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    YubiKey 5C Active
                  </p>
                </div>
                <div className="h-[24px] w-[24px] rounded-full bg-[rgba(0,94,160,0.1)] dark:bg-[rgba(94,184,255,0.1)] flex items-center justify-center flex-shrink-0">
                  <Check className="h-3.5 w-3.5 text-[#005ea0] dark:text-[#5eb8ff]" />
                </div>
              </div>

              {/* Mobile Auth */}
              <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] p-[16px] flex items-center gap-3 border-l-4 border-[#b31b25]">
                <div className="h-[40px] w-[40px] rounded-[32px] bg-[rgba(179,27,37,0.1)] flex items-center justify-center flex-shrink-0">
                  <Smartphone className="h-5 w-5 text-[#b31b25]" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    Mobile Auth
                  </p>
                  <p className="text-[11px] text-[#b31b25] font-semibold">
                    Re-auth required
                  </p>
                </div>
                <div className="h-[24px] w-[24px] rounded-full bg-[rgba(179,27,37,0.1)] flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="h-3.5 w-3.5 text-[#b31b25]" />
                </div>
              </div>
            </div>
          </div>

          {/* --- Threat Resolution History --- */}
          <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] p-[33px] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] shadow-md">
            <h3 className="text-[20px] font-bold text-[#00343d] dark:text-[var(--strix-text)] mb-6 font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif]">
              Threat Resolution History
            </h3>

            {/* Bar Chart */}
            <div className="flex items-end justify-between gap-2 h-[140px]">
              {threatBars.map((bar, i) => (
                <div key={i} className="flex flex-col items-center gap-2 flex-1">
                  <div
                    className="w-full bg-[rgba(0,102,109,0.2)] dark:bg-[rgba(135,237,246,0.2)] rounded-tl-[32px] rounded-tr-[32px] transition-all"
                    style={{ height: `${bar.height}%` }}
                  />
                </div>
              ))}
            </div>
            {/* Day Labels */}
            <div className="flex justify-between mt-3">
              {threatBars.map((bar, i) => (
                <span
                  key={i}
                  className="text-[10px] uppercase font-bold text-[#497f8b] dark:text-[var(--strix-text-muted)] flex-1 text-center"
                >
                  {bar.day}
                </span>
              ))}
            </div>
          </div>

          {/* --- Assigned Assets --- */}
          <div className="h-[192px] rounded-[48px] overflow-clip relative">
            {/* Background gradient as map placeholder */}
            <div className="absolute inset-0 bg-gradient-to-br from-[#006574] via-[#00666d] to-[#005ea0] dark:from-[#0a2a30] dark:via-[#0d3339] dark:to-[#0a2540]">
              {/* Subtle grid pattern to suggest a map */}
              <div
                className="absolute inset-0 opacity-10"
                style={{
                  backgroundImage:
                    "linear-gradient(rgba(255,255,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.3) 1px, transparent 1px)",
                  backgroundSize: "40px 40px",
                }}
              />
              {/* Scattered dots to suggest endpoints */}
              <div className="absolute top-[30%] left-[20%] h-2 w-2 rounded-full bg-[#87edf6] opacity-60 animate-pulse" />
              <div className="absolute top-[50%] left-[45%] h-1.5 w-1.5 rounded-full bg-[#87edf6] opacity-40" />
              <div className="absolute top-[25%] left-[65%] h-2 w-2 rounded-full bg-[#87edf6] opacity-50 animate-pulse" />
              <div className="absolute top-[60%] left-[75%] h-1.5 w-1.5 rounded-full bg-[#87edf6] opacity-60" />
              <div className="absolute top-[40%] left-[35%] h-1 w-1 rounded-full bg-[#87edf6] opacity-30" />
            </div>
            {/* Gradient overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-[rgba(0,102,109,0.8)] to-transparent" />
            {/* Text content */}
            <div className="absolute bottom-0 left-0 right-0 p-8">
              <h3 className="text-[18px] font-bold text-white font-[family-name:var(--font-space-grotesk),_'Space_Grotesk',_sans-serif]">
                Assigned Assets
              </h3>
              <p className="text-[12px] uppercase tracking-wider text-[rgba(207,251,255,0.8)]">
                124 Global Endpoints Monitored
              </p>
            </div>
          </div>
        </div>
      </div>

      {editing && (
        <EditProfileModal
          initial={{ name: profile.name, role: profile.role, site: profile.site }}
          onCancel={() => setEditing(false)}
          onSave={onSaveProfile}
        />
      )}
    </div>
  )
}

function EditProfileModal({
  initial,
  onCancel,
  onSave,
}: {
  initial: EditableProfile
  onCancel: () => void
  onSave: (next: EditableProfile) => void
}) {
  const [name, setName] = useState(initial.name)
  const [role, setRole] = useState(initial.role)
  const [site, setSite] = useState(initial.site)

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onCancel}>
      <div
        className="bg-white dark:bg-[var(--strix-bg-card)] rounded-2xl shadow-xl border border-[rgba(128,182,195,0.25)] dark:border-[var(--strix-border)] w-[420px] max-w-[90vw] p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[16px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">Edit Profile</h3>
          <button onClick={onCancel} className="text-[#497f8b] hover:text-[#00343d] dark:hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-3">
          <Field label="Name" value={name} onChange={setName} />
          <Field label="Role" value={role} onChange={setRole} />
          <Field label="Site" value={site} onChange={setSite} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] px-4 py-2 hover:text-[#00343d] dark:hover:text-white"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave({ name: name.trim() || initial.name, role: role.trim() || initial.role, site: site.trim() || initial.site })}
            className="bg-[#00666d] text-white text-[12px] font-semibold rounded-full px-5 py-2 hover:opacity-90"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="block text-[10px] uppercase tracking-wider text-[#497f8b] mb-1">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full text-[13px] bg-[#e7faff] dark:bg-[rgba(135,237,246,0.05)] border border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] rounded-lg px-3 py-2 text-[#00343d] dark:text-[var(--strix-text)] outline-none focus:border-[#00666d]"
      />
    </label>
  )
}
