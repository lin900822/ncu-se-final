import { useState } from 'react'
import type { QuestionItem } from '../lib/api'
import { isAdjacent } from '../lib/questions'

interface Props {
  questions: QuestionItem[]
  /** 已設定的題組（每組為相鄰題目的 id，依題目順序） */
  bundles: string[][]
  onChange: (bundles: string[][]) => void
  disabled?: boolean
}

function byOrder(a: QuestionItem, b: QuestionItem): number {
  return a.number - b.number || (a.sub ?? 0) - (b.sub ?? 0)
}

/** 預覽中設定題組：勾選相鄰題目後「設為題組」；已設定的題組可取消。伺服器建立時會再驗證一次。 */
export default function BundleEditor({ questions, bundles, onChange, disabled }: Props) {
  const [selected, setSelected] = useState<string[]>([])
  const [hint, setHint] = useState('')
  const sorted = [...questions].sort(byOrder)
  const label = (id: string) => sorted.find((q) => q.id === id)?.label ?? id
  const bundled = new Set(bundles.flat())

  function toggle(id: string) {
    setHint('')
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  function addBundle() {
    if (selected.length < 2) return setHint('題組至少需要 2 題')
    if (selected.some((id) => bundled.has(id))) return setHint('一題只能屬於一個題組')
    if (!isAdjacent(questions, selected)) return setHint('題組只能包含相鄰的題目')
    const order = sorted.map((q) => q.id)
    const members = [...selected].sort((a, b) => order.indexOf(a) - order.indexOf(b))
    const next = [...bundles, members].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))
    onChange(next)
    setSelected([])
    setHint('')
  }

  return (
    <div className="space-y-2 rounded border border-slate-200 bg-white p-3">
      <p className="text-sm text-slate-600">
        需要多題一起搶答時，勾選相鄰的題目後按「設為題組」（選填）：
      </p>
      <ul className="flex flex-wrap gap-2">
        {sorted.map((q) => {
          const inBundle = bundled.has(q.id)
          return (
            <li key={q.id}>
              <label
                className={`flex items-center gap-1 rounded border px-2 py-1 text-sm ${
                  inBundle ? 'border-slate-200 bg-slate-100 text-slate-400' : 'border-slate-300'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.includes(q.id)}
                  disabled={disabled || inBundle}
                  onChange={() => toggle(q.id)}
                />
                {q.label}
              </label>
            </li>
          )
        })}
      </ul>
      <button
        type="button"
        onClick={addBundle}
        disabled={disabled || selected.length === 0}
        className="rounded bg-slate-700 px-3 py-1 text-sm text-white disabled:opacity-50"
      >
        設為題組
      </button>
      {hint && (
        <p role="alert" className="text-sm text-red-600">
          {hint}
        </p>
      )}
      {bundles.length > 0 && (
        <ul className="space-y-1">
          {bundles.map((b) => (
            <li
              key={b.join(',')}
              className="flex items-center justify-between rounded border-2 border-indigo-300 px-3 py-1 text-sm"
            >
              <span className="font-semibold">題組：{b.map(label).join('、')}</span>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange(bundles.filter((x) => x !== b))}
                className="text-indigo-700 hover:underline disabled:opacity-50"
              >
                取消
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
