/**
 * Live alert stream.
 *
 * Each (re)connection first obtains a single-use, 30-second ticket over HTTPS,
 * so no long-lived credential is ever placed in a URL. Reconnects back off
 * exponentially with jitter; a policy-violation close (revoked session) stops
 * reconnecting until the user signs in again.
 */
import { useCallback, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { authApi } from '@/services/auth'
import { isAuthenticated, useAuthStore } from '@/store/auth'
import { useAlertsStore } from '@/store/alerts'
import type { WSMessage } from '@/types'

const WS_BASE =
  import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
const MAX_DELAY_MS = 30_000
const POLICY_VIOLATION = 1008

export function useWebSocket() {
  const socketRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  const delayRef = useRef(1_000)
  const activeRef = useRef(true)

  const authenticated = useAuthStore(isAuthenticated)
  const { setWsConnected, setWsError, incrementUnread } = useAlertsStore()
  const queryClient = useQueryClient()

  const scheduleReconnect = useCallback((connect: () => void) => {
    const jitter = Math.random() * 0.3 * delayRef.current
    timerRef.current = setTimeout(connect, delayRef.current + jitter)
    delayRef.current = Math.min(delayRef.current * 2, MAX_DELAY_MS)
  }, [])

  const connect = useCallback(async () => {
    if (!activeRef.current || !authenticated) return
    if (socketRef.current && socketRef.current.readyState <= WebSocket.OPEN) return

    let ticket: string
    try {
      ticket = await authApi.wsTicket()
    } catch {
      setWsError('Could not authorise the alert stream')
      scheduleReconnect(connect)
      return
    }

    const ws = new WebSocket(`${WS_BASE}/api/v1/ws/alerts?ticket=${encodeURIComponent(ticket)}`)
    socketRef.current = ws

    ws.onopen = () => {
      setWsConnected(true)
      setWsError(null)
      delayRef.current = 1_000
    }

    ws.onmessage = (event) => {
      let msg: WSMessage
      try {
        msg = JSON.parse(event.data) as WSMessage
      } catch {
        return
      }
      if (msg.type === 'ping') {
        ws.send(JSON.stringify({ type: 'pong' }))
      } else if (msg.type === 'new_alert') {
        incrementUnread()
        queryClient.invalidateQueries({ queryKey: ['alerts'] })
        if (msg.severity === 'critical' || msg.severity === 'high') {
          toast.error(msg.title, { duration: 8000 })
        }
      }
    }

    ws.onerror = () => setWsError('Alert stream connection error')

    ws.onclose = (event) => {
      setWsConnected(false)
      socketRef.current = null
      if (!activeRef.current || event.code === 1000) return
      if (event.code === POLICY_VIOLATION) {
        setWsError('Session expired; sign in again for live alerts')
        return
      }
      scheduleReconnect(connect)
    }
  }, [authenticated, incrementUnread, queryClient, scheduleReconnect, setWsConnected, setWsError])

  useEffect(() => {
    activeRef.current = true
    connect()
    return () => {
      activeRef.current = false
      clearTimeout(timerRef.current)
      socketRef.current?.close(1000, 'unmounted')
    }
  }, [connect])
}
