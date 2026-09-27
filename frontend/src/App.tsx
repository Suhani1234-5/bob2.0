import { useEffect, useState } from 'react'
import { ShieldCheck, Activity, CheckCircle2, AlertCircle } from 'lucide-react'

interface HealthResponse {
  status: string
  service: string
  version: string
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`)
        }
        return res.json()
      })
      .then((data: HealthResponse) => {
        setHealth(data)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  return (
    <div className="min-h-screen bg-[#09090B] text-zinc-100 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-md bg-[#111113] border border-[#27272A] rounded-xl p-8 shadow-2xl space-y-6">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">ProofPR</h1>
            <p className="text-xs text-zinc-400">Evidence-Backed Multi-Agent PR Verification</p>
          </div>
        </div>

        <div className="pt-2 border-t border-[#27272A]">
          <div className="text-xs font-medium uppercase tracking-wider text-zinc-400 mb-3 flex items-center space-x-2">
            <Activity className="w-3.5 h-3.5" />
            <span>Backend Health Check (`/api/health`)</span>
          </div>

          {loading && (
            <div className="flex items-center space-x-2 text-sm text-zinc-400">
              <div className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
              <span>Checking backend connection...</span>
            </div>
          )}

          {error && (
            <div className="flex items-start space-x-2 text-sm text-red-400 bg-red-950/30 border border-red-800/40 p-3 rounded-lg">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>Failed to reach backend: {error}</span>
            </div>
          )}

          {health && (
            <div className="space-y-2">
              <div className="flex items-center space-x-2 text-emerald-400 bg-emerald-950/30 border border-emerald-800/40 p-3 rounded-lg text-sm">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span className="font-mono">Status: {health.status}</span>
              </div>
              <div className="text-xs text-zinc-400 font-mono bg-zinc-900/80 p-2.5 rounded border border-zinc-800">
                Service: {health.service} v{health.version}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
