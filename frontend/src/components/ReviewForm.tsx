import { useState } from 'react'

const PRESETS = ['答案錯誤', '亂填', '錯字']
export const MAX_REASON_LENGTH = 100

interface Props {
  action: 'invalid' | 'valid'
  /** 理由輸入即為確認步驟：按「確認」後立即送出 */
  onSubmit: (reason: string) => Promise<void> | void
  onCancel: () => void
  busy?: boolean
}

/** 駁回／恢復的理由輸入：常用理由快速選取＋自行輸入（≤100 字元），理由為空不可送出。 */
export default function ReviewForm({ action, onSubmit, onCancel, busy }: Props) {
  const [reason, setReason] = useState('')
  const label = action === 'invalid' ? '確認駁回' : '確認恢復'
  const empty = reason.trim() === ''
  return (
    <form
      className="mt-2 space-y-2 rounded border border-slate-200 bg-slate-50 p-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (!empty && !busy) void onSubmit(reason.trim())
      }}
    >
      <div className="flex flex-wrap gap-1">
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setReason(p)}
            className="rounded border border-slate-300 bg-white px-2 py-0.5 text-xs hover:bg-slate-100"
          >
            {p}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <input
          value={reason}
          maxLength={MAX_REASON_LENGTH}
          onChange={(e) => setReason(e.target.value)}
          placeholder="請填寫理由"
          aria-label="理由"
          className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
        />
        <span className="shrink-0 text-xs text-slate-400">
          {reason.length}/{MAX_REASON_LENGTH}
        </span>
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={empty || busy}
          className={`rounded px-3 py-1 text-sm font-semibold text-white disabled:opacity-50 ${
            action === 'invalid' ? 'bg-red-600 hover:bg-red-700' : 'bg-emerald-600 hover:bg-emerald-700'
          }`}
        >
          {busy ? '處理中…' : label}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="rounded border border-slate-300 px-3 py-1 text-sm disabled:opacity-50"
        >
          取消
        </button>
      </div>
    </form>
  )
}
