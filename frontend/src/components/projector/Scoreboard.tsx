import type { ProjectorState } from '../../lib/api'

/** 組別得分排行榜：已結算輪次取得題數累計，同分名次並列。 */
export default function Scoreboard({ rows }: { rows: ProjectorState['scoreboard'] }) {
  const size = rows.length <= 8 ? 'text-[2.4vw]' : rows.length <= 14 ? 'text-[1.8vw]' : 'text-[1.3vw]'
  return (
    <section aria-label="得分排行榜">
      <h2 className="mb-[0.8vw] text-[2.2vw] font-bold text-amber-300">得分排行榜</h2>
      <ol className={`space-y-[0.5vw] ${size}`}>
        {rows.map((r) => (
          <li
            key={r.group}
            className={`flex items-baseline gap-[1.2vw] rounded-lg px-[1vw] py-[0.4vw] ${
              r.rank === 1 && r.score > 0 ? 'bg-amber-400/20 font-black text-amber-200' : 'bg-slate-800/60'
            }`}
          >
            <span className="w-[4vw] font-mono">#{r.rank}</span>
            <span className="flex-1 break-words">{r.group}</span>
            <span className="font-bold">{r.score} 題</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
