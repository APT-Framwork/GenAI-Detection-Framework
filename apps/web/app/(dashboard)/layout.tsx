"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { TopBar } from "@/components/layout/topbar"
import { Toaster } from "@/components/layout/toaster"
import { ObservableDrawer } from "@/components/intel/observable-drawer"
import { useSidebarStore } from "@/stores/sidebar-store"
import { cn } from "@/lib/utils"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { isCollapsed } = useSidebarStore()

  return (
    <div className="min-h-screen bg-[var(--strix-bg)]">
      <Sidebar />
      <div
        className={cn(
          "flex flex-col transition-all duration-300",
          isCollapsed ? "ml-[68px]" : "ml-[220px]"
        )}
      >
        <TopBar />
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </div>
      <Toaster />
      <ObservableDrawer />
    </div>
  )
}
