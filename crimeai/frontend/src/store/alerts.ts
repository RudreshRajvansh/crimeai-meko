/**
 * Real-time alerts Zustand store — manages WebSocket connection
 * and incoming alert notifications.
 */
import { create } from 'zustand'
import type { Alert } from '@/types'

interface AlertsState {
  alerts: Alert[]
  unreadCount: number
  wsConnected: boolean
  wsError: string | null

  addAlert: (alert: Alert) => void
  setAlerts: (alerts: Alert[], unreadCount: number) => void
  markRead: (id: string) => void
  resolve: (id: string) => void
  setWsConnected: (v: boolean) => void
  setWsError: (e: string | null) => void
  incrementUnread: () => void
}

export const useAlertsStore = create<AlertsState>()((set) => ({
  alerts: [],
  unreadCount: 0,
  wsConnected: false,
  wsError: null,

  addAlert: (alert) =>
    set((s) => ({
      alerts: [alert, ...s.alerts].slice(0, 100),
      unreadCount: s.unreadCount + 1,
    })),

  setAlerts: (alerts, unreadCount) => set({ alerts, unreadCount }),

  markRead: (id) =>
    set((s) => ({
      alerts: s.alerts.map((a) => (a.id === id ? { ...a, is_read: true } : a)),
      unreadCount: Math.max(0, s.unreadCount - 1),
    })),

  resolve: (id) =>
    set((s) => ({
      alerts: s.alerts.map((a) =>
        a.id === id ? { ...a, is_resolved: true, is_read: true } : a
      ),
    })),

  setWsConnected: (v) => set({ wsConnected: v }),
  setWsError: (e) => set({ wsError: e }),
  incrementUnread: () => set((s) => ({ unreadCount: s.unreadCount + 1 })),
}))
