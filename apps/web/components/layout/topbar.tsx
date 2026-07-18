"use client"

import { usePathname, useRouter } from "next/navigation"
import { cn } from "@/lib/utils"
import { useSidebarStore } from "@/stores/sidebar-store"
import { useTheme } from "next-themes"
import {
  Search,
  Bell,
  Settings,
  Moon,
  Sun,
  User,
  ChevronRight,
  HelpCircle,
} from "lucide-react"
import { useTourStore } from "@/stores/tour-store"
import { useEffect, useState } from "react"
import Link from "next/link"
import { ConnectionStatusBar } from "@/components/layout/connection-status-bar"
import { useNotifications } from "@/lib/api/analysis"

const routeLabels: Record<string, string> = {
  "/": "Dashboard",
  "/attack-analysis": "Attack Analysis",
  "/vigilance-feed": "Vigilance Feed",
  "/topology": "System Topology",
  "/threat-intel": "Threat Intelligence",
  "/ai-engine": "AI Engine Performance",
  "/notifications": "Notification Center",
  "/settings": "Settings",
  "/profile": "Profile",
  "/support": "Support & Documentation",
}

function getBreadcrumb(pathname: string): { parent?: string; current: string } {
  if (pathname === "/") return { current: "Dashboard" }

  const segments = pathname.split("/").filter(Boolean)
  const base = `/${segments[0]}`
  const current = routeLabels[base] || segments[0]

  return {
    parent: "CAVIX",
    current,
  }
}

// Searchable destinations — keeps the topbar search useful without a
// dedicated search index/backend. Match keywords are matched
// case-insensitively as substrings against the user's query.
const SEARCH_TARGETS: { label: string; href: string; keywords: string[] }[] = [
  { label: "Dashboard", href: "/", keywords: ["dashboard", "live", "home", "overview"] },
  // Attack Analysis and Vigilance Feed hidden from the platform for the demo.
  { label: "Topology", href: "/topology", keywords: ["topology", "network", "graph", "map"] },
  { label: "Threat Intel", href: "/threat-intel", keywords: ["threat", "intel", "ioc", "reputation", "compromised"] },
  { label: "AI Engine", href: "/ai-engine", keywords: ["ai", "model", "engine", "monitoring", "drift", "performance"] },
  { label: "Notifications", href: "/notifications", keywords: ["notifications", "alerts", "intervention"] },
  { label: "Settings", href: "/settings", keywords: ["settings", "config", "mfa", "api key", "retention"] },
  { label: "Profile", href: "/profile", keywords: ["profile", "operator", "account"] },
  { label: "Support", href: "/support", keywords: ["support", "help", "docs", "documentation"] },
]

export function TopBar() {
  const pathname = usePathname()
  const router = useRouter()
  const { isCollapsed } = useSidebarStore()
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const [searchFocused, setSearchFocused] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  // Live-ish notification count (refetches every 30s).
  const notifications = useNotifications(50)
  const notifCount = notifications.data?.items?.length ?? 0

  const breadcrumb = getBreadcrumb(pathname)

  const searchResults = (() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return [] as typeof SEARCH_TARGETS
    return SEARCH_TARGETS.filter(
      (t) =>
        t.label.toLowerCase().includes(q) ||
        t.keywords.some((k) => k.toLowerCase().includes(q)),
    ).slice(0, 6)
  })()

  return (
    <header
      className={cn(
        "sticky top-0 z-40 flex h-14 items-center justify-between border-b px-6 transition-all duration-300",
        "bg-[var(--strix-bg-card)]/80 backdrop-blur-md border-[var(--strix-border)]",
        isCollapsed ? "ml-[68px]" : "ml-[220px]"
      )}
    >
      {/* Left: Breadcrumb + Status */}
      <div className="flex items-center gap-4">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 text-sm">
          <span className="font-bold text-[var(--strix-text)] tracking-wider">
            CAVIX
          </span>
          {breadcrumb.parent && (
            <>
              <ChevronRight className="h-3 w-3 text-[var(--strix-text-muted)]" />
            </>
          )}
          <span className="text-[var(--strix-text-muted)]">
            {breadcrumb.current}
          </span>
        </div>

        {/* Connection + system status */}
        <div data-tour="topbar-status" className="hidden md:flex items-center gap-3 ml-4">
          <ConnectionStatusBar />
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            Threat Level: High
          </div>
        </div>
      </div>

      {/* Right: Search + Actions */}
      <div className="flex items-center gap-3">
        {/* Search */}
        <div data-tour="topbar-search" className="relative">
          <div
            className={cn(
              "flex items-center gap-2 rounded-lg border px-3 py-1.5 transition-all duration-200",
              searchFocused
                ? "border-strix-primary dark:border-strix-cyan w-64 bg-white dark:bg-strix-bg-dark-surface"
                : "border-[var(--strix-border)] w-48 bg-[var(--strix-bg-surface)]"
            )}
          >
            <Search className="h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
            <input
              placeholder="Search Intel..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && searchResults.length > 0) {
                  router.push(searchResults[0].href)
                  setSearchQuery("")
                  ;(e.target as HTMLInputElement).blur()
                } else if (e.key === "Escape") {
                  setSearchQuery("")
                  ;(e.target as HTMLInputElement).blur()
                }
              }}
              className="bg-transparent text-xs outline-none placeholder:text-[var(--strix-text-muted)] text-[var(--strix-text)] w-full"
              onFocus={() => setSearchFocused(true)}
              // Defer blur so a click on a dropdown item registers before
              // the dropdown unmounts.
              onBlur={() => setTimeout(() => setSearchFocused(false), 150)}
            />
          </div>
          {searchFocused && searchResults.length > 0 && (
            <div className="absolute top-full mt-1 left-0 right-0 z-50 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-lg shadow-xl overflow-hidden">
              {searchResults.map((r) => (
                <button
                  key={r.href}
                  onClick={() => {
                    router.push(r.href)
                    setSearchQuery("")
                  }}
                  className="block w-full text-left px-3 py-2 text-xs text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)]"
                >
                  {r.label}
                </button>
              ))}
            </div>
          )}
          {searchFocused && searchQuery && searchResults.length === 0 && (
            <div className="absolute top-full mt-1 left-0 right-0 z-50 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-lg shadow-xl px-3 py-2 text-xs text-[var(--strix-text-muted)] italic">
              No matches.
            </div>
          )}
        </div>

        {/* Tutorial launcher */}
        <button
          onClick={() => useTourStore.getState().start(0)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)] transition-colors"
          aria-label="Start platform tutorial"
          title="Platform tutorial"
        >
          <HelpCircle className="h-4 w-4" />
        </button>

        {/* Theme Toggle */}
        <button
          data-tour="topbar-theme"
          onClick={() => setTheme((resolvedTheme ?? theme) === "dark" ? "light" : "dark")}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)] transition-colors"
          suppressHydrationWarning
          aria-label="Toggle theme"
        >
          {mounted ? (
            (resolvedTheme ?? theme) === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )
          ) : (
            <span className="h-4 w-4" />
          )}
        </button>

        {/* Notifications */}
        <Link
          href="/notifications"
          data-tour="topbar-bell"
          className="relative flex h-8 w-8 items-center justify-center rounded-lg text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)] transition-colors"
        >
          <Bell className="h-4 w-4" />
          {notifCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex min-w-4 h-4 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">
              {notifCount > 99 ? "99+" : notifCount}
            </span>
          )}
        </Link>

        {/* Settings */}
        <Link
          href="/settings"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)] transition-colors"
        >
          <Settings className="h-4 w-4" />
        </Link>

        {/* User Avatar */}
        <Link
          href="/profile"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-strix-primary to-strix-tertiary text-white"
        >
          <User className="h-4 w-4" />
        </Link>
      </div>
    </header>
  )
}
