import { useCallback, useEffect, useRef, useState } from 'react'

export type SocketStatus = 'idle' | 'connecting' | 'open' | 'closed'

interface Options {
  /** 為 null 時不連線 */
  path: string | null
  onOpen?: (send: (data: unknown) => void) => void
  onMessage: (msg: Record<string, unknown>) => void
  onClose?: (code: number) => void
  /** 這些關閉碼代表伺服器主動拒絕/終止，不再自動重連 */
  noReconnectCodes?: number[]
  /** 變更此值會強制重新連線（例如重試加入） */
  connectKey?: number
}

function wsUrl(path: string) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}

/** 非預期斷線時以指數退避（1s、2s、4s…上限 10s）自動重連；每次連上都會呼叫 onOpen。 */
export function useReconnectingSocket({
  path,
  onOpen,
  onMessage,
  onClose,
  noReconnectCodes = [],
  connectKey = 0,
}: Options) {
  const [status, setStatus] = useState<SocketStatus>('idle')
  const wsRef = useRef<WebSocket | null>(null)
  const onOpenRef = useRef(onOpen)
  const onMessageRef = useRef(onMessage)
  const onCloseRef = useRef(onClose)
  const noReconnectRef = useRef(noReconnectCodes)
  onOpenRef.current = onOpen
  onMessageRef.current = onMessage
  onCloseRef.current = onClose
  noReconnectRef.current = noReconnectCodes

  useEffect(() => {
    if (!path) {
      setStatus('idle')
      return
    }
    let disposed = false
    let attempt = 0
    let timer: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      if (disposed) return
      setStatus('connecting')
      const ws = new WebSocket(wsUrl(path))
      wsRef.current = ws
      ws.onopen = () => {
        attempt = 0
        setStatus('open')
        onOpenRef.current?.((d) => ws.send(JSON.stringify(d)))
      }
      ws.onmessage = (ev) => {
        try {
          onMessageRef.current(JSON.parse(ev.data))
        } catch {
          /* 忽略非 JSON 訊息 */
        }
      }
      ws.onclose = (ev) => {
        if (disposed || wsRef.current !== ws) return
        setStatus('closed')
        onCloseRef.current?.(ev.code)
        if (noReconnectRef.current.includes(ev.code) || ev.code === 1000) return
        const delay = Math.min(1000 * 2 ** attempt, 10000)
        attempt += 1
        timer = setTimeout(connect, delay)
      }
    }
    connect()

    return () => {
      disposed = true
      if (timer) clearTimeout(timer)
      const ws = wsRef.current
      wsRef.current = null
      ws?.close()
    }
  }, [path, connectKey])

  const send = useCallback((data: unknown) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data))
  }, [])

  return { status, send }
}
