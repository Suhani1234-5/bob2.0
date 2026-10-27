import { useEffect, useState } from "react"

export function useVerificationStream(prId: string) {
  const [events, setEvents] = useState<any[]>([])
  const [agentStatus, setAgentStatus] = useState<Record<string, string>>({})

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/verification/${prId}/stream`)
    ws.onmessage = (msg) => {
      const data = JSON.parse(msg.data)
      setEvents((prev) => [...prev, { ...data, time: new Date().toLocaleTimeString() }])
      if (data.agent) setAgentStatus((prev) => ({ ...prev, [data.agent]: data.status }))
    }
    return () => ws.close()
  }, [prId])

  return { events, agentStatus }
}