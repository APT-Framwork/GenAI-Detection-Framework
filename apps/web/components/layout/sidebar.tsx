"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { useSidebarStore } from "@/stores/sidebar-store"
import { CavixLogo, CavixMark } from "@/components/layout/cavix-logo"
import {
  LayoutDashboard,
  Shield,
  Brain,
  Activity,
  Settings,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Crosshair,
  Target,
} from "lucide-react"

const navItems = [
  { label: "DASHBOARD", href: "/", icon: LayoutDashboard, id: "dashboard" },
  { label: "CASES", href: "/cases", icon: Inbox, id: "cases" },
  { label: "HUNT", href: "/hunt", icon: Crosshair, id: "hunt" },
  // ANALYSIS and ACTIONS hidden from the platform for the demo.
  { label: "CTI", href: "/intel", icon: Target, id: "intel" },
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
        {isCollapsed ? (
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-strix-cyan/20 to-strix-cyan/5 border border-strix-cyan/30">
            <CavixMark size={20} color="#00F2FF" />
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <CavixLogo width={88} color="#00F2FF" />
            <span className="text-[10px] text-sidebar-text tracking-widest uppercase">
              Powered by STRIX RL
            </span>
          </div>
        )}
      </div>

      {/* Main Navigation */}
      <nav data-tour="sidebar-nav" className="flex-1 px-3 py-4 space-y-1 overflow-y-auto scrollbar-thin">
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

      {/* ACTIVE VIGILANCE button hidden from the platform for the demo. */}

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
