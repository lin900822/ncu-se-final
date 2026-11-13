import type { ProjectorState } from '../../lib/api'
import { buildUnits, density } from './units'

/** 結算後各題得主：組名（大字）與答案；題組一格並列各小題；與學生端結果同一份資料。 */
export default function WinnersBoard({ state }: { state: ProjectorState }) {
  const units = buildUnits(state)
  const d = density(units.length)
  const byQ = new Map((state.result?.results ?? []).map((r) => [r.questionId, r]))
  return (
    <ul className="grid gap-[1vw]" style={{ gridTemplateColumns: `repeat(${Math.min(d.cols, 3)}, minmax(0, 1fr))` }}>
      {units.map((u) => {
        const first = byQ.get(u.members[0].id)
        const winner = first?.winnerGroup ?? null
        return (
          <li key={u.id} className="rounded-xl border-2 border-slate-700 bg-slate-800/60 p-[1vw]">
            <div className={`${d.body} text-slate-400`}>{u.title}</div>
            {winner ? (
              <div className={`${d.title} font-black text-amber-300`}>{winner}</div>
            ) : (
              <div className={`${d.title} font-semibold text-slate-500`}>
                {first?.noValid ? '無有效答案' : '無人搶答'}
              </div>
            )}
            {winner && (
              <div className={`${d.body} break-words text-slate-100`}>
                {u.members.map((m) => (
                  <div key={m.id}>
                    {u.bundle && <span className="mr-[0.5vw] font-semibold text-slate-400">{m.label}</span>}
                    {byQ.get(m.id)?.answer ?? ''}
                  </div>
                ))}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
