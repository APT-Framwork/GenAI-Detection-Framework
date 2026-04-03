import { create } from "zustand"

interface SidebarState {
  isCollapsed: boolean
  activeItem: string
  toggle: () => void
  setCollapsed: (collapsed: boolean) => void
  setActiveItem: (item: string) => void
}

export const useSidebarStore = create<SidebarState>((set) => ({
  isCollapsed: false,
  activeItem: "dashboard",
  toggle: () => set((state) => ({ isCollapsed: !state.isCollapsed })),
  setCollapsed: (collapsed) => set({ isCollapsed: collapsed }),
  setActiveItem: (item) => set({ activeItem: item }),
}))
