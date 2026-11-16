import type { BundleItem, QuestionItem } from '../lib/api'
import { MAX_ANSWER_LENGTH } from '../lib/drafts'
import { bundleTitle, groupByUnit } from '../lib/questions'

/** 題號清單（預覽、老師端使用）：只列題號，不含任何題目敘述。 */
export function QuestionList({
  questions,
  texts,
  bundles,
}: {
  questions: QuestionItem[]
  texts?: Record<string, string>
  /** 題組（Step 7）：同一題組框在一起並標示「題組：Q3、Q4」 */
  bundles?: BundleItem[]
}) {
  const units = groupByUnit(questions, bundles ?? [])
  // 老師端：有題目文字時改以垂直清單顯示「題號：題目文字」，方便核對；題組成員框在一起
  if (texts && Object.keys(texts).length > 0) {
    const row = (q: QuestionItem) => (
      <div key={q.id} className="text-sm">
        <span className="font-semibold">{q.label}</span>
        <span className="ml-2 whitespace-pre-wrap text-slate-600">{texts[q.id]}</span>
      </div>
    )
    return (
      <ul className="space-y-2">
        {units.map((u) =>
          u.kind === 'bundle' ? (
            <li key={u.bundle.id} className="space-y-1 rounded border-2 border-indigo-300 px-3 py-2">
              <p className="text-xs font-semibold text-indigo-700">{bundleTitle(u.items)}</p>
              {u.items.map(row)}
            </li>
          ) : (
            u.items.map((q) => (
              <li key={q.id} className="rounded border border-slate-200 px-3 py-2">
                {row(q)}
              </li>
            ))
          ),
        )}
      </ul>
    )
  }
  return (
    <ul className="flex flex-wrap gap-2">
      {units.map((u) =>
        u.kind === 'bundle' ? (
          <li key={u.bundle.id} className="rounded border-2 border-indigo-300 px-3 py-1 text-sm font-semibold text-indigo-700">
            {bundleTitle(u.items)}
          </li>
        ) : (
          <li key={u.number} className="rounded border border-slate-200 px-3 py-1 text-sm">
            {u.items.map((q) => q.label).join('、')}
          </li>
        ),
      )}
    </ul>
  )
}

interface Props {
  questions: QuestionItem[]
  values: Record<string, string>
  disabled: boolean
  /** 題目文字：僅搶答中才會有值（由伺服器在開始搶答後才送出） */
  texts?: Record<string, string>
  /** 本組本輪已送出的 {題目識別碼: 答案}（由伺服器還原／同步，唯讀） */
  submitted?: Record<string, string>
  /** 本輪有其他組送出的題目識別碼（匿名提示，不含組名、內容、數量） */
  othersSubmitted?: string[]
  /** 每題的錯誤訊息（例如答案為空） */
  errors?: Record<string, string>
  /** 題組（Step 7）：同一題組框在同一張卡片、只有一顆送出鈕 */
  bundles?: BundleItem[]
  /** 每個題組的錯誤訊息 */
  bundleErrors?: Record<string, string>
  onSubmit?: (id: string) => void
  onSubmitBundle?: (bundleId: string) => void
  onChange: (id: string, text: string) => void
}

/** 依題目動態生成填空格：只顯示題號與輸入框；React 預設跳脫文字輸出。 */
export default function QuestionFields({
  questions,
  values,
  disabled,
  texts,
  submitted,
  othersSubmitted,
  errors,
  bundles,
  bundleErrors,
  onSubmit,
  onSubmitBundle,
  onChange,
}: Props) {
  const isSubmitted = (id: string) => submitted?.[id] !== undefined
  const textOf = (id: string) => (isSubmitted(id) ? (submitted?.[id] ?? '') : (values[id] ?? ''))

  // 單一作答格；inBundle 時不顯示各自的送出鈕與他組提示（由題組卡片統一處理）
  function field(q: QuestionItem, inBundle: boolean) {
    const done = isSubmitted(q.id)
    const text = textOf(q.id)
    const othersDone = !inBundle && !done && !!othersSubmitted?.includes(q.id)
    return (
      <div key={q.id}>
        <label htmlFor={`q-${q.id}`} className="mb-1 block font-semibold">
          {q.label}
        </label>
        {texts?.[q.id] && <p className="mb-2 whitespace-pre-wrap text-slate-700">{texts[q.id]}</p>}
        <div className="flex gap-2">
          <input
            id={`q-${q.id}`}
            value={text}
            maxLength={MAX_ANSWER_LENGTH}
            disabled={disabled || done}
            onChange={(e) => onChange(q.id, e.target.value)}
            className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-2 text-lg disabled:cursor-not-allowed disabled:bg-slate-100"
          />
          {!inBundle &&
            (done ? (
              <span className="shrink-0 self-center rounded bg-emerald-100 px-3 py-2 font-semibold text-emerald-700">
                已送出
              </span>
            ) : (
              <button
                type="button"
                onClick={() => onSubmit?.(q.id)}
                disabled={disabled || !text.trim()}
                className="shrink-0 rounded bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                送出
              </button>
            ))}
        </div>
        {text.length >= MAX_ANSWER_LENGTH && !done && (
          <p className="mt-1 text-sm text-amber-600">已達 {MAX_ANSWER_LENGTH} 字上限</p>
        )}
        {othersDone && <p className="mt-1 text-sm text-slate-500">本題已有組別送出</p>}
        {errors?.[q.id] && (
          <p role="alert" className="mt-1 text-sm text-red-600">
            {errors[q.id]}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4 text-left">
      {groupByUnit(questions, bundles ?? []).map((u) => {
        if (u.kind === 'single') {
          return (
            <fieldset key={`n-${u.number}`} className="space-y-2 rounded-lg border border-slate-200 p-3">
              {u.items.map((q) => field(q, false))}
            </fieldset>
          )
        }
        // 題組卡片：整組一顆送出鈕；任一格空白不可送；送出後整卡鎖定
        const ids = u.items.map((q) => q.id)
        const allDone = ids.every(isSubmitted)
        const incomplete = ids.some((id) => !textOf(id).trim())
        const othersDone = !allDone && ids.some((id) => othersSubmitted?.includes(id))
        return (
          <fieldset
            key={u.bundle.id}
            className="space-y-3 rounded-lg border-2 border-indigo-300 bg-indigo-50/40 p-3"
          >
            <legend className="px-1 text-sm font-semibold text-indigo-700">{bundleTitle(u.items)}</legend>
            {u.items.map((q) => field(q, true))}
            <div className="flex items-center justify-end gap-3">
              {!allDone && incomplete && !disabled && (
                <p className="text-sm text-slate-500">請填完題組內所有題目</p>
              )}
              {allDone ? (
                <span className="rounded bg-emerald-100 px-3 py-2 font-semibold text-emerald-700">
                  已送出
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => onSubmitBundle?.(u.bundle.id)}
                  disabled={disabled || incomplete}
                  className="rounded bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  送出
                </button>
              )}
            </div>
            {othersDone && <p className="text-sm text-slate-500">本題組已有組別送出</p>}
            {bundleErrors?.[u.bundle.id] && (
              <p role="alert" className="text-sm text-red-600">
                {bundleErrors[u.bundle.id]}
              </p>
            )}
          </fieldset>
        )
      })}
    </div>
  )
}
