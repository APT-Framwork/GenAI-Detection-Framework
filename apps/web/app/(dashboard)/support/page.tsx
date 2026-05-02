"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { toast } from "@/lib/toast"
import {
  BookOpen,
  Code,
  Shield,
  FlaskConical,
  Check,
  ArrowRight,
  Headphones,
  MessageCircle,
  ChevronDown,
  Send,
} from "lucide-react"

export default function SupportPage() {
  const [incidentLevel, setIncidentLevel] = useState("")
  const [subject, setSubject] = useState("")
  const [description, setDescription] = useState("")
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const incidentLevels = ["Low — Informational", "Medium — Operational", "High — Escalation", "Critical — Immediate"]

  return (
    <div className="space-y-12">
      {/* ──────────────── Hero Section ──────────────── */}
      <section className="flex flex-col md:flex-row items-start justify-between gap-8">
        <div className="max-w-2xl">
          <h1
            className="text-[60px] leading-[1.05] font-bold tracking-tight text-[#00343d] dark:text-[var(--strix-text)]"
            style={{ fontFamily: "var(--font-space-grotesk, 'Space Grotesk', sans-serif)" }}
          >
            VIGILANCE
            <br />
            HANDBOOK
          </h1>
          <p
            className="mt-5 text-[20px] leading-[1.6] text-[#2b636f] dark:text-[var(--strix-text-muted)]"
            style={{ fontFamily: "var(--font-inter, 'Inter', sans-serif)" }}
          >
            Master the clinical precision of the STRIX ecosystem. Complete
            documentation for the clinical sentinel, from initial deployment to
            advanced threat neutralization.
          </p>
        </div>

        <div className="flex-shrink-0 text-right">
          <span className="block text-[10px] uppercase tracking-[1px] text-[#497f8b] dark:text-[var(--strix-text-muted)] font-semibold mb-1">
            Documentation Version
          </span>
          <span
            className="text-[30px] font-bold text-[#00666d] dark:text-strix-cyan"
            style={{ fontFamily: "var(--font-space-grotesk, 'Space Grotesk', sans-serif)" }}
          >
            v2.0.44-STABLE
          </span>
        </div>
      </section>

      {/* ──────────────── Bento Grid ──────────────── */}
      <section className="grid grid-cols-12 gap-6">
        {/* Row 1 — Featured Deployment Card */}
        <div className="col-span-12 lg:col-span-8 bg-white dark:bg-[var(--strix-bg-card)] rounded-[48px] shadow-lg dark:shadow-none border border-transparent dark:border-[var(--strix-border)] p-[41px] flex flex-col justify-between">
          <div>
            <div className="w-12 h-12 rounded-2xl bg-[#e7faff] dark:bg-strix-cyan/10 flex items-center justify-center mb-5">
              <BookOpen className="h-6 w-6 text-[#00666d] dark:text-strix-cyan" />
            </div>
            <h2
              className="text-[30px] font-bold text-[#00343d] dark:text-[var(--strix-text)] mb-3"
              style={{ fontFamily: "var(--font-space-grotesk, 'Space Grotesk', sans-serif)" }}
            >
              Initial Deployment
            </h2>
            <p className="text-[15px] leading-relaxed text-[#497f8b] dark:text-[var(--strix-text-muted)] max-w-lg mb-8">
              Get started with STRIX Sentinel in under 15 minutes. This guide
              covers installation, initial configuration, and connecting your
              first data sources.
            </p>
          </div>
          <div className="flex items-center gap-4 flex-wrap">
            <button className="bg-[#00666d] hover:bg-[#005258] text-[#cffbff] rounded-[9999px] px-[24px] py-[12px] text-sm font-semibold transition-colors dark:bg-strix-cyan dark:text-[var(--strix-bg-dark)] dark:hover:opacity-90">
              Begin Onboarding
            </button>
            <button className="rounded-[9999px] px-[24px] py-[12px] text-sm font-semibold border border-[rgba(0,102,109,0.2)] dark:border-[var(--strix-border)] text-[#00666d] dark:text-[var(--strix-text)] hover:bg-[#e7faff] dark:hover:bg-[var(--strix-bg-surface)] transition-colors">
              Video Guide
            </button>
          </div>
        </div>

        {/* Row 1 — Night Owl Patch */}
        <div className="col-span-12 lg:col-span-4 bg-[#87edf6] dark:bg-strix-cyan/15 rounded-[48px] p-[32px] flex flex-col justify-between border border-transparent dark:border-[var(--strix-border)]">
          <div>
            <span className="inline-block text-[10px] uppercase tracking-[1px] font-semibold text-[#00575d] dark:text-strix-cyan mb-3">
              Latest Update
            </span>
            <h3
              className="text-[24px] font-bold text-[#00575d] dark:text-[var(--strix-text)] mb-5"
              style={{ fontFamily: "var(--font-space-grotesk, 'Space Grotesk', sans-serif)" }}
            >
              The &ldquo;Night Owl&rdquo;
              <br />
              Patch
            </h3>
            <ul className="space-y-3 mb-6">
              {[
                "Dark-mode analytics dashboard",
                "Automated threat report scheduling",
                "New MITRE ATT&CK v14 mappings",
              ].map((item, i) => (
                <li key={i} className="flex items-start gap-2 text-[13px] text-[#00575d] dark:text-[var(--strix-text-muted)]">
                  <Check className="h-4 w-4 mt-0.5 flex-shrink-0 text-[#00666d] dark:text-strix-cyan" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
          <a
            href="#"
            className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-[#00575d] dark:text-strix-cyan hover:underline"
          >
            Read full changelog <ArrowRight className="h-4 w-4" />
          </a>
        </div>

        {/* Row 2 — Three bottom cards */}
        {[
          {
            icon: Code,
            title: "API Reference",
            desc: "Complete REST API documentation for STRIX integration endpoints.",
            link: "Explore Endpoints",
            linkColor: "text-[#006574]",
          },
          {
            icon: Shield,
            title: "Security Policies",
            desc: "Operational security protocols, compliance frameworks, and audit procedures.",
            link: "Review Standards",
            linkColor: "text-[#005ea0]",
          },
          {
            icon: FlaskConical,
            title: "Threat Lab",
            desc: "Sandbox environments, attack simulations, and detection tuning guides.",
            link: "Read Analysis",
            linkColor: "text-[#00666d]",
          },
        ].map((card, i) => {
          const CardIcon = card.icon
          return (
            <div
              key={i}
              className="col-span-12 md:col-span-4 h-[265px] bg-[#d6f6ff] dark:bg-[var(--strix-bg-card)] rounded-[48px] p-[32px] flex flex-col justify-between border border-transparent dark:border-[var(--strix-border)]"
            >
              <div>
                <div className="w-10 h-10 rounded-xl bg-white/60 dark:bg-[var(--strix-bg-surface)] flex items-center justify-center mb-4">
                  <CardIcon className="h-5 w-5 text-[#00666d] dark:text-strix-cyan" />
                </div>
                <h3
                  className="text-[20px] font-bold text-[#00343d] dark:text-[var(--strix-text)] mb-2"
                  style={{ fontFamily: "var(--font-space-grotesk, 'Space Grotesk', sans-serif)" }}
                >
                  {card.title}
                </h3>
                <p className="text-[13px] leading-relaxed text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                  {card.desc}
                </p>
              </div>
              <a
                href="#"
                className={cn(
                  "text-[10px] uppercase font-bold tracking-[1px] hover:underline",
                  card.linkColor,
                  "dark:text-strix-cyan"
                )}
              >
                {card.link} &rarr;
              </a>
            </div>
          )
        })}
      </section>

      {/* ──────────────── Tactical Assistance Section ──────────────── */}
      <section className="bg-[rgba(154,233,252,0.3)] dark:bg-[var(--strix-bg-surface)] rounded-[48px] pt-[96px] pb-[32px] px-[48px]">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
          {/* Left Column */}
          <div>
            <h2
              className="text-[36px] font-bold text-[#00343d] dark:text-[var(--strix-text)] mb-4"
              style={{ fontFamily: "var(--font-space-grotesk, 'Space Grotesk', sans-serif)" }}
            >
              Tactical Assistance
            </h2>
            <p className="text-[15px] leading-relaxed text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-8 max-w-md">
              Connect directly with our engineering team or tap into the
              collective intelligence of the STRIX operator community.
            </p>

            <div className="space-y-4">
              {/* Direct Engineer Access Card */}
              <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[16px] shadow-md dark:shadow-none border border-transparent dark:border-[var(--strix-border)] p-5 flex items-center gap-4">
                <div className="w-12 h-12 rounded-[48px] bg-[#00666d] dark:bg-strix-cyan flex items-center justify-center flex-shrink-0">
                  <Headphones className="h-5 w-5 text-white dark:text-[var(--strix-bg-dark)]" />
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="text-[15px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    Direct Engineer Access
                  </h4>
                  <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    Real-time support from STRIX engineers
                  </p>
                </div>
                <button className="bg-[rgba(0,102,109,0.1)] dark:bg-strix-cyan/10 text-[#00666d] dark:text-strix-cyan rounded-[9999px] px-5 py-2 text-[13px] font-semibold hover:bg-[rgba(0,102,109,0.18)] dark:hover:bg-strix-cyan/20 transition-colors flex-shrink-0">
                  Connect
                </button>
              </div>

              {/* Community Intel Card */}
              <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-[16px] shadow-md dark:shadow-none border border-transparent dark:border-[var(--strix-border)] p-5 flex items-center gap-4">
                <div className="w-12 h-12 rounded-[48px] bg-[#00666d] dark:bg-strix-cyan flex items-center justify-center flex-shrink-0">
                  <MessageCircle className="h-5 w-5 text-white dark:text-[var(--strix-bg-dark)]" />
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="text-[15px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    Community Intel
                  </h4>
                  <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    Join the STRIX operator network on Discord
                  </p>
                </div>
                <button className="bg-[rgba(0,102,109,0.1)] dark:bg-strix-cyan/10 text-[#00666d] dark:text-strix-cyan rounded-[9999px] px-5 py-2 text-[13px] font-semibold hover:bg-[rgba(0,102,109,0.18)] dark:hover:bg-strix-cyan/20 transition-colors flex-shrink-0">
                  Join Discord
                </button>
              </div>
            </div>
          </div>

          {/* Right Column — Form */}
          <div className="bg-white dark:bg-[var(--strix-bg-card)] rounded-tl-[48px] rounded-tr-[48px] rounded-br-[48px] rounded-bl-none shadow-lg dark:shadow-none border border-transparent dark:border-[var(--strix-border)] p-[41px]">
            <h3
              className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] mb-2"
              style={{ fontFamily: "var(--font-space-grotesk, 'Space Grotesk', sans-serif)" }}
            >
              Request Deployment Support
            </h3>
            <p className="text-[13px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-8">
              Submit a detailed request and our team will respond within one
              operational cycle.
            </p>

            <div className="space-y-5">
              {/* Incident Level Dropdown */}
              <div className="relative">
                <label className="block text-[10px] uppercase tracking-[1px] font-semibold text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-2">
                  Operation Incident Level
                </label>
                <button
                  type="button"
                  onClick={() => setDropdownOpen(!dropdownOpen)}
                  className="w-full flex items-center justify-between bg-[#e7faff] dark:bg-[var(--strix-bg-surface)] rounded-[32px] px-6 py-3.5 text-[14px] text-left text-[#00343d] dark:text-[var(--strix-text)] border border-transparent dark:border-[var(--strix-border)] focus:outline-none focus:ring-2 focus:ring-[#00666d]/30 dark:focus:ring-strix-cyan/30"
                >
                  <span className={cn(!incidentLevel && "text-[#497f8b] dark:text-[var(--strix-text-muted)]")}>
                    {incidentLevel || "Select severity level"}
                  </span>
                  <ChevronDown className={cn("h-4 w-4 text-[#497f8b] dark:text-[var(--strix-text-muted)] transition-transform", dropdownOpen && "rotate-180")} />
                </button>
                {dropdownOpen && (
                  <div className="absolute z-20 mt-2 w-full bg-white dark:bg-[var(--strix-bg-card)] rounded-2xl shadow-lg border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] overflow-hidden">
                    {incidentLevels.map((level) => (
                      <button
                        key={level}
                        type="button"
                        onClick={() => {
                          setIncidentLevel(level)
                          setDropdownOpen(false)
                        }}
                        className="w-full text-left px-6 py-3 text-[14px] text-[#00343d] dark:text-[var(--strix-text)] hover:bg-[#e7faff] dark:hover:bg-[var(--strix-bg-surface)] transition-colors"
                      >
                        {level}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Subject */}
              <div>
                <label className="block text-[10px] uppercase tracking-[1px] font-semibold text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-2">
                  Subject Matter
                </label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Brief description of the issue"
                  className="w-full bg-[#e7faff] dark:bg-[var(--strix-bg-surface)] rounded-[32px] px-6 py-3.5 text-[14px] text-[#00343d] dark:text-[var(--strix-text)] placeholder:text-[#497f8b] dark:placeholder:text-[var(--strix-text-muted)] border border-transparent dark:border-[var(--strix-border)] focus:outline-none focus:ring-2 focus:ring-[#00666d]/30 dark:focus:ring-strix-cyan/30"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-[10px] uppercase tracking-[1px] font-semibold text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-2">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={4}
                  placeholder="Provide a detailed account of the deployment scenario or issue..."
                  className="w-full bg-[#e7faff] dark:bg-[var(--strix-bg-surface)] rounded-[32px] px-6 py-5 text-[14px] text-[#00343d] dark:text-[var(--strix-text)] placeholder:text-[#497f8b] dark:placeholder:text-[var(--strix-text-muted)] border border-transparent dark:border-[var(--strix-border)] focus:outline-none focus:ring-2 focus:ring-[#00666d]/30 dark:focus:ring-strix-cyan/30 resize-none"
                />
              </div>

              {/* Submit */}
              <button
                type="button"
                onClick={() => {
                  if (!subject.trim() || !description.trim()) {
                    toast.warning("Subject and description are required.")
                    return
                  }
                  if (!incidentLevel) {
                    toast.warning("Pick an incident level.")
                    return
                  }
                  // No backend ticketing endpoint exists. Open the user's
                  // mail client with a prefilled body — at least the
                  // request actually leaves the page.
                  const body = encodeURIComponent(
                    `Incident level: ${incidentLevel}\n\nSubject: ${subject}\n\nDescription:\n${description}\n\n— sent via STRIX support form`,
                  )
                  const subj = encodeURIComponent(`[STRIX Support] ${subject}`)
                  if (typeof window !== "undefined") {
                    window.location.href = `mailto:support@strix.dev?subject=${subj}&body=${body}`
                  }
                  toast.success("Opening your mail client with the request prefilled.")
                  setSubject("")
                  setDescription("")
                  setIncidentLevel("")
                }}
                className="w-full bg-[#00666d] dark:bg-strix-cyan text-[#cffbff] dark:text-[var(--strix-bg-dark)] rounded-[48px] py-[16px] text-[12px] uppercase tracking-[1.4px] font-bold hover:bg-[#005258] dark:hover:opacity-90 transition-opacity"
              >
                Transmit Request
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ──────────────── Footer ──────────────── */}
      <footer className="border-t border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] pt-8 pb-4 flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span
            className="text-[18px] font-bold text-[#00666d] dark:text-strix-cyan tracking-wider"
            style={{ fontFamily: "var(--font-space-grotesk, 'Space Grotesk', sans-serif)" }}
          >
            STRIX
          </span>
          <span className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            &copy; {new Date().getFullYear()} STRIX Sentinel. All rights reserved.
          </span>
        </div>
        <div className="flex items-center gap-6">
          {["Privacy Protocol", "Compliance Shield", "System Status"].map((link) => (
            <a
              key={link}
              href="#"
              className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00666d] dark:hover:text-strix-cyan transition-colors"
            >
              {link}
            </a>
          ))}
        </div>
      </footer>
    </div>
  )
}
