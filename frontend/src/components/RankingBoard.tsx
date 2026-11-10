import type { QuestionItem } from '../lib/api'

export interface BoardRank {
  rank: number
  group: string
  submittedAt: string
}

export interface BoardQuestion {
  questionId: string
  leader: string | null
  submittedCount: number
  ranking: BoardRank[]
}

export interface Board {
  round: number
  questions: BoardQuestion[]
  leadTally: { group: string; leadCount: number }[]
}

/** 老師端即時進度板：每題最快組別、名次清單、各組領先題數（僅老師可見）。 */
export default function RankingBoard({
  board,
  questions,
}: {
  board: Board | null
  questions: QuestionItem[]
}) {
  if (!board || board.questions.length === 0) {
    return <p className="text-slate-500">尚無組別送出</p>
  }
  const labelOf = (id: string) => questions.find((q) => q.id === id)?.label ?? id
  return (
    <div className="space-y-4">
      <div className="rounded bg-indigo-50 p-3 text-sm">
        <span className="font-semibold">各組領先題數：</span>
        {board.leadTally.length === 0 ? (
          <span className="text-slate-500">尚無領先組別</span>
        ) : (
          board.leadTally.map((t) => (
            <span key={t.group} className="mr-3 inline-block">
              {t.group} <span className="font-bold">{t.leadCount}</span>
            </span>
          ))
        )}
      </div>
      <ul className="grid gap-3 sm:grid-cols-2">
        {board.questions.map((q) => (
          <li key={q.questionId} className="rounded border border-slate-200 p-3">
            <div className="flex items-baseline justify-between">
              <span className="font-semibold">{labelOf(q.questionId)}</span>
              <span className="text-xs text-slate-500">已送出 {q.submittedCount} 組</span>
            </div>
            {q.leader === null ? (
              <p className="mt-1 text-slate-400">尚無組別送出</p>
            ) : (
              <>
                <p className="mt-1 text-lg font-bold text-emerald-700">最快：{q.leader}</p>
                <ol className="mt-1 space-y-0.5 text-sm">
                  {q.ranking.map((r) => (
                    <li key={r.group}>
                      <span className="inline-block w-8 font-mono">#{r.rank}</span>
                      {r.group}
                      <span className="ml-2 text-xs text-slate-400">
                        {new Date(r.submittedAt).toLocaleTimeString()}
                      </span>
                    </li>
                  ))}
                </ol>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
