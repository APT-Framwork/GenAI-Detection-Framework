"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { useSidebarStore } from "@/stores/sidebar-store"
import {
  LayoutDashboard,
  Search,
  Shield,
  Brain,
  Activity,
  Settings,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
  Radar,
} from "lucide-react"

const navItems = [
  { label: "DASHBOARD", href: "/", icon: LayoutDashboard, id: "dashboard" },
  { label: "ANALYSIS", href: "/attack-analysis/latest", icon: Search, id: "analysis" },
  { label: "THREAT INTEL", href: "/threat-intel", icon: Shield, id: "threat-intel" },
  { label: "MODEL MONITORING", href: "/ai-engine", icon: Brain, id: "ai-engine" },
  { label: "SIMULATION", href: "/topology", icon: Activity, id: "simulation" },
]

const bottomItems = [
  { label: "SETTINGS", href: "/settings", icon: Settings, id: "settings" },
  { label: "SUPPORT", href: "/support", icon: HelpCircle, id: "support" },
]

export function Sidebar() {
  const pathname = usePathname()
  const { isCollapsed, toggle } = useSidebarStore()

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/" || pathname === ""
    return pathname?.startsWith(href)
  }

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-50 flex h-screen flex-col border-r transition-all duration-300",
        "bg-sidebar-bg border-[#1E293B]",
        isCollapsed ? "w-[68px]" : "w-[220px]"
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-[#1E293B]">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-strix-cyan/20 to-strix-cyan/5 border border-strix-cyan/30">
          <Shield className="h-5 w-5 text-strix-cyan" />
        </div>
        {!isCollapsed && (
          <div className="flex flex-col">
            <span className="text-sm font-bold text-white tracking-wider">
              STRIX
            </span>
            <span className="text-[10px] text-sidebar-text tracking-widest uppercase">
              Vigilant Sentinel
            </span>
          </div>
        )}
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto scrollbar-thin">
        {navItems.map((item) => {
          const active = isActive(item.href)
          return (
            <Link
              key={item.id}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-xs font-medium tracking-wide transition-all duration-200 group",
                active
                  ? "bg-strix-cyan/10 text-strix-cyan border border-strix-cyan/20"
                  : "text-sidebar-text hover:bg-sidebar-hover hover:text-white border border-transparent"
              )}
            >
              <item.icon
                className={cn(
                  "h-[18px] w-[18px] flex-shrink-0 transition-colors",
                  active ? "text-strix-cyan" : "text-sidebar-text group-hover:text-white"
                )}
              />
              {!isCollapsed && <span>{item.label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* Deploy Probe Button */}
      <div className="px-3 py-3">
        <button
          className={cn(
            "w-full flex items-center justify-center gap-2 rounded-lg py-2.5 text-xs font-semibold tracking-wide transition-all",
            "bg-strix-cyan/10 text-strix-cyan border border-strix-cyan/30 hover:bg-strix-cyan/20",
            isCollapsed && "px-2"
          )}
        >
          <Radar className="h-4 w-4" />
          {!isCollapsed && <span>ACTIVE VIGILANCE</span>}
        </button>
      </div>

      {/* Bottom Navigation */}
      <div className="px-3 py-2 border-t border-[#1E293B] space-y-1">
        {bottomItems.map((item) => {
          const active = isActive(item.href)
          return (
            <Link
              key={item.id}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-xs font-medium tracking-wide transition-all duration-200 group",
                active
                  ? "bg-strix-cyan/10 text-strix-cyan border border-strix-cyan/20"
                  : "text-sidebar-text hover:bg-sidebar-hover hover:text-white border border-transparent"
              )}
            >
              <item.icon
                className={cn(
                  "h-[18px] w-[18px] flex-shrink-0",
                  active ? "text-strix-cyan" : "text-sidebar-text group-hover:text-white"
                )}
              />
              {!isCollapsed && <span>{item.label}</span>}
            </Link>
          )
        })}
      </div>

      {/* Collapse Toggle */}
      <button
        onClick={toggle}
        className="absolute -right-3 top-20 flex h-6 w-6 items-center justify-center rounded-full bg-sidebar-bg border border-[#1E293B] text-sidebar-text hover:text-white transition-colors"
      >
        {isCollapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </button>
    </aside>
  )
}
