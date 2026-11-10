import type { BundleItem, QuestionItem } from '../lib/api'

export interface ResultItem {
  questionId: string
  winnerGroup: string | null
  answer: string | null
}

export interface ResultData {
  round: number
  results: ResultItem[]
}

/** 學生結果頁：逐題列出第一名組別與答案（只含第一名，其餘組別不公布）；題組整組一張卡片。 */
export default function ResultBoard({
  result,
  questions,
  myGroup,
  bundles,
}: {
  result: ResultData
  questions: QuestionItem[]
  myGroup: string
  bundles?: BundleItem[]
}) {
  const labelOf = (id: string) => questions.find((q) => q.id === id)?.label ?? id
  const bundleOf = new Map<string, BundleItem>()
  for (const b of bundles ?? []) for (const id of b.questionIds) bundleOf.set(id, b)
  const seen = new Set<string>()
  return (
    <section className="space-y-3 text-left">
      <h2 className="text-center text-xl font-bold">搶答結果</h2>
      <ul className="space-y-2">
        {result.results.map((r) => {
          const b = bundleOf.get(r.questionId)
          if (b) {
            if (seen.has(b.id)) return null
            seen.add(b.id)
            // 題組各題同一個搶下組別（同題組名次相同）；逐題列出答案
            const items = result.results.filter((x) => b.questionIds.includes(x.questionId))
            const winner = items[0]?.winnerGroup ?? null
            const mine = winner !== null && winner === myGroup
            return (
              <li
                key={b.id}
                className={`rounded border-2 p-3 ${
                  mine ? 'border-emerald-400 bg-emerald-50' : 'border-indigo-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold">
                    題組：{items.map((x) => labelOf(x.questionId)).join('、')}
                  </span>
                  {mine && (
                    <span className="rounded bg-emerald-600 px-2 py-0.5 text-xs font-semibold text-white">
                      本組搶下
                    </span>
                  )}
                </div>
                {winner === null ? (
                  <p className="mt-1 text-slate-400">本題組無人搶答</p>
                ) : (
                  <>
                    <p className="mt-1 text-lg font-bold text-emerald-700">{winner}</p>
                    <dl className="mt-1 space-y-1">
                      {items.map((x) => (
                        <div key={x.questionId} className="flex gap-2">
                          <dt className="shrink-0 font-semibold">{labelOf(x.questionId)}</dt>
                          <dd className="whitespace-pre-wrap break-words">{x.answer}</dd>
                        </div>
                      ))}
                    </dl>
                  </>
                )}
              </li>
            )
          }
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
