export interface FairnessInput {
  winCap: string
  cooldown: string
}

export const EMPTY_FAIRNESS: FairnessInput = { winCap: '', cooldown: '' }
export const MAX_COOLDOWN = 600

export type ParsedFairness =
  | { ok: true; rule: { winCap: number | null; cooldownSeconds: number } }
  | { ok: false; winCapError: string; cooldownError: string }

const INTEGER = /^\d+$/

/** 解析並檢查輸入：上限須為 1..題目數的整數（空＝不限制）、冷卻須為 0..600 的整數（空＝不套用）。 */
export function parseFairness(value: FairnessInput, questionCount: number): ParsedFairness {
  const cap = value.winCap.trim()
  const cool = value.cooldown.trim()
  let winCapError = ''
  let cooldownError = ''
  let winCap: number | null = null
  let cooldownSeconds = 0
  if (cap !== '') {
    const n = INTEGER.test(cap) ? Number(cap) : NaN
    if (!Number.isInteger(n) || n < 1 || n > questionCount) {
      winCapError = `上限須為 1 到 ${questionCount} 的整數`
    } else {
      winCap = n
    }
  }
  if (cool !== '') {
    const n = INTEGER.test(cool) ? Number(cool) : NaN
    if (!Number.isInteger(n) || n < 0 || n > MAX_COOLDOWN) {
      cooldownError = `冷卻須為 0 到 ${MAX_COOLDOWN} 的整數`
    } else {
      cooldownSeconds = n
    }
  }
  if (winCapError || cooldownError) return { ok: false, winCapError, cooldownError }
  return { ok: true, rule: { winCap, cooldownSeconds } }
}

interface Props {
  questionCount: number
  value: FairnessInput
  onChange: (v: FairnessInput) => void
  disabled?: boolean
}

/** 預覽頁的公平規則設定（選填）：每組最多搶得 N 題、搶得後冷卻秒數；建立房間後固定，學生活動前可見。 */
export default function FairnessEditor({ questionCount, value, onChange, disabled }: Props) {
  const parsed = parseFairness(value, questionCount)
  const winCapError = parsed.ok ? '' : parsed.winCapError
  const cooldownError = parsed.ok ? '' : parsed.cooldownError
  const input = 'w-24 rounded border border-slate-300 px-2 py-1 text-sm disabled:opacity-50'
  return (
    <div className="space-y-2 rounded border border-slate-200 bg-white p-3">
      <p className="text-sm text-slate-600">
        避免單一組別包辦所有題目（選填）；建立房間後規則固定，學生在活動開始前就看得到：
      </p>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <label className="flex items-center gap-2">
          每組最多搶得
          <input
            inputMode="numeric"
            aria-label="每組最多搶得題數"
            value={value.winCap}
            disabled={disabled}
            onChange={(e) => onChange({ ...value, winCap: e.target.value })}
            placeholder="不限制"
            className={input}
          />
          題
        </label>
        <label className="flex items-center gap-2">
          搶得後冷卻
          <input
            inputMode="numeric"
            aria-label="冷卻秒數"
            value={value.cooldown}
            disabled={disabled}
            onChange={(e) => onChange({ ...value, cooldown: e.target.value })}
            placeholder="0"
            className={input}
          />
          秒
        </label>
      </div>
      {(winCapError || cooldownError) && (
        <p role="alert" className="text-sm text-red-600">
          {[winCapError, cooldownError].filter(Boolean).join('；')}
        </p>
      )}
    </div>
  )
}
