import { useCallback, useState } from 'react'
import { useReconnectingSocket } from '../hooks/useReconnectingSocket'
import type { ProjectorState } from '../lib/api'
import Countdown from '../components/projector/Countdown'
import ProgressBoard from '../components/projector/ProgressBoard'
import Scoreboard from '../components/projector/Scoreboard'
import WinnersBoard from '../components/projector/WinnersBoard'

const PHASE_LABEL = { Waiting: '等待搶答', Answering: '搶答中', Ended: '已結束' } as const

/** 教室大螢幕投影視圖：唯讀、放大；沒有任何按鈕或輸入欄位。內容全部來自後端推送的整份狀態。 */
export default function Projector() {
  const params = new URLSearchParams(location.search)
  const code = params.get('code') ?? ''
  const key = params.get('key') ?? ''
  const [state, setState] = useState<ProjectorState | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [counting, setCounting] = useState(false)

  const { status } = useReconnectingSocket({
    path: code && key ? `/ws/projector?code=${encodeURIComponent(code)}&key=${encodeURIComponent(key)}` : null,
    noReconnectCodes: [1008, 1000],
    onMessage: (msg) => {
      if (msg.type === 'projector_unavailable') setUnavailable(true)
      else if (msg.type === 'projector_state') setState(msg as unknown as ProjectorState)
      else if (msg.type === 'countdown') setCounting(true) // 只有連線期間收到才播放；重新整理不補播
    },
  })
  const done = useCallback(() => setCounting(false), [])

  if (unavailable || !code || !key) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-[3vw] text-slate-300">
        無法顯示
      </main>
    )
  }
  if (!state) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-[3vw] text-slate-400">
        連線中…
      </main>
    )
  }

  const hasQuestions = state.questions.length > 0
  const showScores = state.scoreboard.some((r) => r.score > 0) || state.phase === 'Ended'
  const disconnected = status !== 'open' && state.status !== 'Closed'
  return (
    <main className="min-h-screen bg-slate-950 p-[2vw] text-white">
      {counting && <Countdown onDone={done} />}
      {disconnected && (
        <div role="alert" className="mb-[1vw] rounded-lg bg-red-600 px-[1.5vw] py-[0.8vw] text-[2vw] font-bold">
          連線中斷，重新連線中
        </div>
      )}
      {state.status === 'Closed' && (
        <div role="status" className="mb-[1vw] rounded-lg bg-slate-700 px-[1.5vw] py-[0.8vw] text-[2vw] font-bold">
          房間已結束
        </div>
      )}
      <header className="mb-[1.5vw] flex flex-wrap items-baseline gap-x-[3vw]">
        <div>
          <span className="text-[1.8vw] text-slate-400">房間代碼</span>
          <span className="ml-[1vw] font-mono text-[6vw] font-black tracking-widest">{state.code}</span>
        </div>
        <div className="text-[2.6vw] font-bold text-amber-300">
          {PHASE_LABEL[state.phase]}
          {state.round > 0 && `・第 ${state.round} 輪`}
        </div>
      </header>

      {state.phase === 'Waiting' && (
        <section className="mb-[2vw]">
          <h2 className="mb-[0.8vw] text-[2.2vw] font-bold">已加入的組別（{state.groups.length}）</h2>
          {state.groups.length === 0 ? (
            <p className="text-[2.2vw] text-slate-400">輸入房間代碼加入</p>
          ) : (
            <ul className="flex flex-wrap gap-[1vw]">
              {state.groups.map((g) => (
                <li key={g} className="rounded-xl bg-slate-800 px-[1.5vw] py-[0.6vw] text-[2.6vw] font-semibold">
                  {g}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <div className={showScores && hasQuestions ? 'grid gap-[2vw] lg:grid-cols-[2fr_1fr]' : ''}>
        {hasQuestions && state.phase === 'Answering' && <ProgressBoard state={state} />}
        {hasQuestions && state.phase === 'Ended' && <WinnersBoard state={state} />}
        {showScores && state.scoreboard.length > 0 && <Scoreboard rows={state.scoreboard} />}
      </div>
    </main>
  )
}
