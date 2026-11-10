import type { QuestionItem } from '../lib/api'
import { MAX_ANSWER_LENGTH } from '../lib/drafts'
import { groupByNumber } from '../lib/questions'

/** 題號清單（預覽、老師端使用）：只列題號，不含任何題目敘述。 */
export function QuestionList({
  questions,
  texts,
}: {
  questions: QuestionItem[]
  texts?: Record<string, string>
}) {
  // 老師端：有題目文字時改以垂直清單顯示「題號：題目文字」，方便核對
  if (texts && Object.keys(texts).length > 0) {
    return (
      <ul className="space-y-2">
        {[...questions]
          .sort((a, b) => a.number - b.number || (a.sub ?? 0) - (b.sub ?? 0))
          .map((q) => (
            <li key={q.id} className="rounded border border-slate-200 px-3 py-2 text-sm">
              <span className="font-semibold">{q.label}</span>
              <span className="ml-2 whitespace-pre-wrap text-slate-600">{texts[q.id]}</span>
            </li>
          ))}
      </ul>
    )
  }
  return (
    <ul className="flex flex-wrap gap-2">
      {groupByNumber(questions).map((g) => (
        <li key={g.number} className="rounded border border-slate-200 px-3 py-1 text-sm">
          {g.items.map((q) => q.label).join('、')}
        </li>
      ))}
    </ul>
  )
}

interface Props {
  questions: QuestionItem[]
  values: Record<string, string>
  disabled: boolean
  /** 題目文字：僅搶答中才會有值（由伺服器在開始搶答後才送出） */
  texts?: Record<string, string>
  onChange: (id: string, text: string) => void
}

/** 依題目動態生成填空格：只顯示題號與輸入框；React 預設跳脫文字輸出。 */
export default function QuestionFields({ questions, values, disabled, texts, onChange }: Props) {
  return (
    <div className="space-y-4 text-left">
      {groupByNumber(questions).map((g) => (
        <fieldset key={g.number} className="space-y-2 rounded-lg border border-slate-200 p-3">
          {g.items.map((q) => {
            const text = values[q.id] ?? ''
            return (
              <div key={q.id}>
                <label htmlFor={`q-${q.id}`} className="mb-1 block font-semibold">
                  {q.label}
                </label>
                {texts?.[q.id] && (
                  <p className="mb-2 whitespace-pre-wrap text-slate-700">{texts[q.id]}</p>
                )}
                <input
                  id={`q-${q.id}`}
                  value={text}
                  maxLength={MAX_ANSWER_LENGTH}
                  disabled={disabled}
                  onChange={(e) => onChange(q.id, e.target.value)}
                  className="w-full rounded border border-slate-300 px-3 py-2 text-lg disabled:cursor-not-allowed disabled:bg-slate-100"
                />
                {text.length >= MAX_ANSWER_LENGTH && (
                  <p className="mt-1 text-sm text-amber-600">已達 {MAX_ANSWER_LENGTH} 字上限</p>
                )}
              </div>
            )
          })}
        </fieldset>
      ))}
    </div>
  )
}
