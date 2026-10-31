/**
 * UI Zustand store — sidebar collapse, active route, global loading states.
 */
import { create } from 'zustand'

interface UIState {
  sidebarCollapsed: boolean
  mobileMenuOpen: boolean
  globalLoading: boolean
  alertPanelOpen: boolean
  isDark: boolean

  toggleTheme: () => void
  toggleSidebar: () => void
  setSidebarCollapsed: (v: boolean) => void
  toggleMobileMenu: () => void
  setGlobalLoading: (v: boolean) => void
  toggleAlertPanel: () => void
}

const THEME_KEY = 'crimeai-theme'

export const useUIStore = create<UIState>()((set) => ({
  sidebarCollapsed: false,
  mobileMenuOpen: false,
  globalLoading: false,
  alertPanelOpen: false,
  // public/theme-init.js applies the saved choice before first paint; the class is the source of truth.
  isDark: document.documentElement.classList.contains('dark'),

  toggleTheme: () => set((s) => {
    const next = !s.isDark
    document.documentElement.classList.toggle('dark', next)
    try {
      localStorage.setItem(THEME_KEY, next ? 'dark' : 'light')
    } catch {
      // Private mode or blocked storage: the choice lasts for this tab only.
    }
    return { isDark: next }
  }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  toggleMobileMenu: () => set((s) => ({ mobileMenuOpen: !s.mobileMenuOpen })),
  setGlobalLoading: (v) => set({ globalLoading: v }),
  toggleAlertPanel: () => set((s) => ({ alertPanelOpen: !s.alertPanelOpen })),
}))
