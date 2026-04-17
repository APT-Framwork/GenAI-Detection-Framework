"use client"

import { usePathname } from "next/navigation"
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
} from "lucide-react"
import { useState } from "react"
import Link from "next/link"

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
    parent: "STRIX",
    current,
  }
}

export function TopBar() {
  const pathname = usePathname()
  const { isCollapsed } = useSidebarStore()
  const { theme, setTheme } = useTheme()
  const [searchFocused, setSearchFocused] = useState(false)

  const breadcrumb = getBreadcrumb(pathname)

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
            STRIX
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

        {/* System status pills */}
        <div className="hidden md:flex items-center gap-3 ml-4">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            System Health
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            Threat Level: High
          </div>
        </div>
      </div>

      {/* Right: Search + Actions */}
      <div className="flex items-center gap-3">
        {/* Search */}
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
            className="bg-transparent text-xs outline-none placeholder:text-[var(--strix-text-muted)] text-[var(--strix-text)] w-full"
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
          />
        </div>

        {/* Theme Toggle */}
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)] transition-colors"
        >
          {theme === "dark" ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </button>

        {/* Notifications */}
        <Link
          href="/notifications"
          className="relative flex h-8 w-8 items-center justify-center rounded-lg text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)] transition-colors"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
            3
          </span>
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
