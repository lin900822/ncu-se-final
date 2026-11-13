import type { ProjectorState } from '../../lib/api'
import { buildUnits, density } from './units'

/** 搶答中的匿名進度：只顯示各格「尚無／已有組別送出」與總進度，不含組名與答案。 */
export default function ProgressBoard({ state }: { state: ProjectorState }) {
  const units = buildUnits(state)
  const d = density(units.length)
  const p = state.progress
  return (
    <section>
      {p && (
        <p className="mb-[1.2vw] text-[2.6vw] font-bold text-amber-300">
          已有答案的題目 {p.answered}／{p.total}
        </p>
      )}
      <ul className="grid gap-[1vw]" style={{ gridTemplateColumns: `repeat(${d.cols}, minmax(0, 1fr))` }}>
        {units.map((u) => {
          const done = state.submitted?.[u.id] === true
          return (
            <li
              key={u.id}
              className={`rounded-xl border-2 p-[1vw] ${
                done ? 'border-emerald-400 bg-emerald-500/20' : 'border-slate-700 bg-slate-800/60'
              }`}
            >
              <div className={`${d.title} font-bold`}>{u.title}</div>
              <div className={`${d.body} ${done ? 'font-semibold text-emerald-300' : 'text-slate-400'}`}>
                {done ? '已有組別送出' : '尚無組別送出'}
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
