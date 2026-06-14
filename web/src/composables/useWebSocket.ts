import { ref, onMounted, onUnmounted } from 'vue'

export interface WSMessage {
  type: string
  content?: string
  session_id?: string
  source?: string
  sessions?: any[]
  [key: string]: any
}

export function useWebSocket() {
  const connected = ref(false)
  const messages = ref<WSMessage[]>([])
  const handlers = new Map<string, Set<(msg: WSMessage) => void>>()

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const token = localStorage.getItem('aisu_token')
    const url = token ? `${proto}//${location.host}/ws?token=${token}` : `${proto}//${location.host}/ws`
    console.log('[WS] connecting to', url.replace(token || '', '***'))

    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      console.log('[WS] connected, flushing', pending.length, 'pending messages')
      for (const d of pending) {
        ws!.send(JSON.stringify(d))
      }
      pending = []
    }

    ws.onclose = () => {
      connected.value = false
      console.log('[WS] disconnected, reconnecting in 2s')
      scheduleReconnect()
    }

    ws.onerror = () => {
      console.error('[WS] error')
    }

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data)
        messages.value.push(msg)
        if (messages.value.length > 500) messages.value.shift()

        const typeHandlers = handlers.get(msg.type)
        if (typeHandlers) {
          for (const fn of typeHandlers) fn(msg)
        }

        const allHandlers = handlers.get('*')
        if (allHandlers) {
          for (const fn of allHandlers) fn(msg)
        }
      } catch {}
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, 2000)
  }

  function on(type: string, fn: (msg: WSMessage) => void) {
    if (!handlers.has(type)) handlers.set(type, new Set())
    handlers.get(type)!.add(fn)
  }

  function off(type: string, fn: (msg: WSMessage) => void) {
    handlers.get(type)?.delete(fn)
  }

  let pending: Record<string, any>[] = []

  function send(data: Record<string, any>): boolean {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
      return true
    }
    pending.push(data)
    console.warn('[WS] not connected (state:', ws?.readyState, '), queued:', data.type)
    return false
  }

  onMounted(() => connect())
  onUnmounted(() => {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws?.close()
  })

  return { connected, messages, on, off, send }
}
