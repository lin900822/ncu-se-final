import { useState } from 'react'
import type { QuestionItem } from '../lib/api'
import ReviewForm from './ReviewForm'

export interface BoardRank {
  rank: number
  group: string
  submittedAt: string
  /** 該題答案（僅老師看板） */
  answer: string
  /** 審核狀態（Step 9）：被駁回者標示已駁回 */
  status: 'Valid' | 'Invalid'
  /** 遞補後名次；被駁回者為 null */
  successionRank: number | null
  /** 最近一次審核理由；未審核為 null */
  reason: string | null
}

export interface BoardQuestion {
  questionId: string
  /** 有效第一名（被駁回者略過）；沒有有效答案為 null */
  leader: string | null
  submittedCount: number
  ranking: BoardRank[]
  /** 題組（Step 7）：同題組各題名次清單相同；未綁定為 null */
  bundleId?: string | null
}

export interface Board {
  round: number
  questions: BoardQuestion[]
  leadTally: { group: string; leadCount: number }[]
}

export interface ReviewRequest {
  round: number
  unitId: string
  group: string
  action: 'invalid' | 'valid'
  reason: string
}

interface Props {
  board: Board | null
  questions: QuestionItem[]
  /** 搶答結束後才能審核（Step 9）；為假時不顯示任何審核按鈕 */
  canReview?: boolean
  round?: number
  onReview?: (r: ReviewRequest) => Promise<void>
  /** 無法審核時的說明（例如「搶答結束後才能審核答案」） */
  reviewHint?: string
}

/** 老師端進度板與審核面板：每個搶答單位的名次清單、有效第一名、各組領先題數（僅老師可見）。 */
export default function RankingBoard({ board, questions, canReview, round, onReview, reviewHint }: Props) {
  const [open, setOpen] = useState<{ key: string; action: 'invalid' | 'valid' } | null>(null)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState('')

  if (!board || board.questions.length === 0) {
    return <p className="text-slate-500">尚無組別送出</p>
  }
  const labelOf = (id: string) => questions.find((q) => q.id === id)?.label ?? id
  // 題組整組一張卡片、只顯示一份名次清單（取第一個成員；同題組各題名次相同），各題答案並列
  const cards: { key: string; unitId: string; title: string; q: BoardQuestion; members: BoardQuestion[]; bundle: boolean }[] = []
  const seen = new Set<string>()
  for (const q of board.questions) {
    if (!q.bundleId) {
      cards.push({ key: q.questionId, unitId: q.questionId, title: labelOf(q.questionId), q, members: [q], bundle: false })
      continue
    }
    if (seen.has(q.bundleId)) continue
    seen.add(q.bundleId)
    const members = board.questions.filter((x) => x.bundleId === q.bundleId)
    const title = `題組：${members.map((x) => labelOf(x.questionId)).join('、')}`
    cards.push({ key: q.bundleId, unitId: q.bundleId, title, q, members, bundle: true })
  }

  async function submit(unitId: string, group: string, action: 'invalid' | 'valid', reason: string) {
    if (!onReview || round === undefined) return
    setBusy(true)
    setFormError('')
    try {
      await onReview({ round, unitId, group, action, reason })
      setOpen(null)
    } catch (e) {
      setFormError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {reviewHint && <p className="text-sm text-slate-500">{reviewHint}</p>}
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
        {cards.map(({ key, unitId, title, q, members, bundle }) => (
          <li
            key={key}
            className={`rounded p-3 ${bundle ? 'border-2 border-indigo-300' : 'border border-slate-200'}`}
          >
            <div className="flex items-baseline justify-between">
              <span className="font-semibold">{title}</span>
              <span className="text-xs text-slate-500">已送出 {q.submittedCount} 組</span>
            </div>
            {q.leader === null ? (
              <p className="mt-1 text-slate-400">
                {q.submittedCount === 0 ? '尚無組別送出' : bundle ? '本題組無有效答案' : '本題無有效答案'}
              </p>
            ) : (
              <p className="mt-1 text-lg font-bold text-emerald-700">第一名：{q.leader}</p>
            )}
            <ol className="mt-1 space-y-2 text-sm">
              {q.ranking.map((r) => {
                const invalid = r.status === 'Invalid'
                const isOpen = open?.key === `${unitId}|${r.group}`
                const answers = members.map((m) => ({
                  label: labelOf(m.questionId),
                  answer: m.ranking.find((x) => x.group === r.group)?.answer ?? '',
                }))
                return (
                  <li key={r.group} className={invalid ? 'text-slate-400' : ''}>
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="inline-block w-8 font-mono">#{r.rank}</span>
                      <span className={invalid ? 'line-through' : 'font-medium'}>{r.group}</span>
                      <span className="text-xs text-slate-400">{new Date(r.submittedAt).toLocaleTimeString()}</span>
                      {invalid ? (
                        <span className="rounded bg-red-100 px-1.5 text-xs font-semibold text-red-700">已駁回</span>
                      ) : (
                        r.successionRank !== null &&
                        r.successionRank !== r.rank && (
                          <span className="rounded bg-emerald-100 px-1.5 text-xs font-semibold text-emerald-700">
                            遞補後第 {r.successionRank}
                          </span>
                        )
                      )}
                      {canReview && onReview && (
                        <button
                          type="button"
                          onClick={() => {
                            setFormError('')
                            setOpen(isOpen ? null : { key: `${unitId}|${r.group}`, action: invalid ? 'valid' : 'invalid' })
                          }}
                          className="ml-auto text-xs text-indigo-700 hover:underline"
                        >
                          {invalid ? '恢復有效' : '駁回/無效'}
                        </button>
                      )}
                    </div>
                    <div className="ml-8 whitespace-pre-wrap break-words">
                      {answers.map((a) => (
                        <div key={a.label}>
                          {members.length > 1 && <span className="mr-1 font-semibold">{a.label}</span>}
                          {a.answer}
                        </div>
                      ))}
                    </div>
                    {invalid && r.reason && <p className="ml-8 text-xs">理由：{r.reason}</p>}
                    {isOpen && open && (
                      <div className="ml-8">
                        <ReviewForm
                          action={open.action}
                          busy={busy}
                          onCancel={() => setOpen(null)}
                          onSubmit={(reason) => submit(unitId, r.group, open.action, reason)}
                        />
                        {formError && (
                          <p role="alert" className="mt-1 text-xs text-red-600">
                            {formError}
                          </p>
                        )}
                      </div>
                    )}
                  </li>
                )
              })}
            </ol>
          </li>
        ))}
      </ul>
    </div>
  )
}
