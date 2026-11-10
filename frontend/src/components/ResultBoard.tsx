import type { QuestionItem } from '../lib/api'

export interface ResultItem {
  questionId: string
  winnerGroup: string | null
  answer: string | null
}

export interface ResultData {
  round: number
  results: ResultItem[]
}

/** 學生結果頁：逐題列出第一名組別與答案（只含第一名，其餘組別不公布）。 */
export default function ResultBoard({
  result,
  questions,
  myGroup,
}: {
  result: ResultData
  questions: QuestionItem[]
  myGroup: string
}) {
  const labelOf = (id: string) => questions.find((q) => q.id === id)?.label ?? id
  return (
    <section className="space-y-3 text-left">
      <h2 className="text-center text-xl font-bold">搶答結果</h2>
      <ul className="space-y-2">
        {result.results.map((r) => {
          const mine = r.winnerGroup !== null && r.winnerGroup === myGroup
          return (
            <li
              key={r.questionId}
              className={`rounded border p-3 ${
                mine ? 'border-emerald-400 bg-emerald-50' : 'border-slate-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold">{labelOf(r.questionId)}</span>
                {mine && (
                  <span className="rounded bg-emerald-600 px-2 py-0.5 text-xs font-semibold text-white">
                    本組搶下
                  </span>
                )}
              </div>
              {r.winnerGroup === null ? (
                <p className="mt-1 text-slate-400">本題無人搶答</p>
              ) : (
                <>
                  <p className="mt-1 text-lg font-bold text-emerald-700">{r.winnerGroup}</p>
                  <p className="whitespace-pre-wrap break-words">{r.answer}</p>
                </>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
