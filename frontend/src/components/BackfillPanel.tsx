import { useState } from 'react'
import {
  ApiError,
  backfillConfirm,
  backfillPreview,
  type BackfillPreview,
  type BackfillRecordItem,
  type BackfillResult,
} from '../lib/api'

interface Props {
  code: string
  token: string
  round: number
  /** 房間有綁定試算表且搶答已結束時才可回填 */
  canBackfill: boolean
  /** 不可回填時顯示的原因 */
  disabledReason?: string
  sheetUrl: string | null
  /** 回填紀錄（公開格式，不含儲存格位置與答案內容） */
  records: BackfillRecordItem[]
  onUnauthorized: () => void
}

/** 老師端「回填至 Google Sheet」：先預覽確認摘要，按「確認回填」才寫入（全有或全無）。 */
export default function BackfillPanel({
  code,
  token,
  round,
  canBackfill,
  disabledReason,
  sheetUrl,
  records,
  onUnauthorized,
}: Props) {
  const [preview, setPreview] = useState<BackfillPreview | null>(null)
  const [result, setResult] = useState<BackfillResult | null>(null)
  const [busy, setBusy] = useState<'preview' | 'confirm' | null>(null)
  const [error, setError] = useState('')
  // 針對特定錯誤的補充說明（需要編輯者時顯示機器人 email）
  const [showItems, setShowItems] = useState(false)
  const [hint, setHint] = useState<{ code: string; email: string } | null>(null)

  function fail(e: unknown) {
    if (e instanceof ApiError && e.code === 'UNAUTHORIZED') {
      onUnauthorized()
      return
    }
    setError((e as Error).message)
    const code = e instanceof ApiError ? e.code : ''
    const email = e instanceof ApiError ? String(e.details?.serviceAccountEmail ?? '') : ''
    setHint(code ? { code, email } : null)
  }

  async function onPreview() {
    setError('')
    setHint(null)
    setResult(null)
    setBusy('preview')
    try {
      setShowItems(false)
      setPreview(await backfillPreview(code, token, round))
    } catch (e) {
      setPreview(null)
      fail(e)
    } finally {
      setBusy(null)
    }
  }

  async function onConfirm() {
    setError('')
    setHint(null)
    setBusy('confirm')
    try {
      setResult(await backfillConfirm(code, token, round))
      setPreview(null)
    } catch (e) {
      setPreview(null)
      fail(e)
    } finally {
      setBusy(null)
    }
  }

  const c = preview?.counts
  return (
    <section className="space-y-3 rounded-xl bg-white p-6 shadow-sm">
      <h2 className="text-xl font-bold">回填至 Google Sheet</h2>
      <p className="text-sm text-slate-500">
        把各題獲勝組別的答案寫回原試算表（需將試算表共用給機器人並設為編輯者）。
      </p>
      <button
        onClick={onPreview}
        disabled={!canBackfill || busy !== null}
        className="rounded bg-emerald-700 px-4 py-2 font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
      >
        {busy === 'preview' ? '讀取中…' : '回填至 Google Sheet'}
      </button>
      {!canBackfill && disabledReason && <p className="text-sm text-slate-500">{disabledReason}</p>}

      {preview && c && (
        <div className="space-y-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm">
          {preview.canBackfill ? (
            <>
              <p className="font-semibold">
                將寫入 {c.write} 格、略過 {c.skip} 題
                {c.clear > 0 && `、清空 ${c.clear} 格`}
                {c.keep > 0 && `、保留 ${c.keep} 格`}。
              </p>
              {(c.overwrite ?? 0) > 0 && (
                <p className="font-semibold text-red-700">其中 {c.overwrite} 格原有內容將被覆寫。</p>
              )}
              {c.clear > 0 && (
                <p className="text-slate-700">清空的格先前由本系統寫入、現已無有效答案，將被清空回空白。</p>
              )}
              {c.keep > 0 && <p className="text-slate-700">保留的格已被您修改過，將保留不動。</p>}
              <button
                type="button"
                onClick={() => setShowItems((v) => !v)}
                className="text-indigo-700 underline"
              >
                {showItems ? '收合逐題清單' : '展開逐題清單'}
              </button>
              {showItems && (
                <ul className="space-y-1">
                  {preview.items.map((it) => (
                    <li key={it.questionId} className="rounded bg-white px-2 py-1">
                      <span className="font-semibold">{it.label}</span>{' '}
                      <span className="text-slate-600">
                        {{ write: '寫入', clear: '清空', keep: '保留', skip: '略過' }[it.action]}
                      </span>
                      {it.overwrite && <span className="ml-1 text-red-700">（將覆寫原有內容）</span>}
                      {it.answer !== null && (
                        <span className="ml-2 whitespace-pre-wrap break-words text-slate-800">{it.answer}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex gap-2">
                <button
                  onClick={onConfirm}
                  disabled={busy !== null}
                  className="rounded bg-red-600 px-3 py-1 font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {busy === 'confirm' ? '回填中…' : '確認回填'}
                </button>
                <button
                  onClick={() => setPreview(null)}
                  disabled={busy !== null}
                  className="rounded border border-slate-300 bg-white px-3 py-1 disabled:opacity-50"
                >
                  取消
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="font-semibold">沒有可回填的答案。</p>
              <button onClick={() => setPreview(null)} className="rounded border border-slate-300 bg-white px-3 py-1">
                關閉
              </button>
            </>
          )}
        </div>
      )}

      {result && (
        <div role="status" className="space-y-1 rounded border border-emerald-300 bg-emerald-50 p-3 text-sm">
          <p className="font-semibold text-emerald-800">
            回填完成：寫入 {result.counts.write} 格、略過 {result.counts.skip} 題
            {result.counts.clear > 0 && `、清空 ${result.counts.clear} 格`}
            {result.counts.keep > 0 && `、保留 ${result.counts.keep} 格`}（
            {new Date(result.record.at).toLocaleTimeString()}）
          </p>
          {(result.sheetUrl || sheetUrl) && (
            <a
              href={result.sheetUrl || sheetUrl || '#'}
              target="_blank"
              rel="noreferrer"
              className="text-indigo-700 underline"
            >
              開啟試算表
            </a>
          )}
        </div>
      )}

      <div className="space-y-1">
        <h3 className="text-sm font-semibold text-slate-700">回填紀錄</h3>
        {records.length === 0 ? (
          <p className="text-sm text-slate-500">尚無回填紀錄</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {records.map((rec, i) => (
              <li key={`${rec.at}-${i}`} className="rounded border border-slate-200 px-3 py-1">
                <span className="text-xs text-slate-400">
                  第 {rec.round} 輪 · {new Date(rec.at).toLocaleTimeString()}
                </span>{' '}
                {rec.result === 'Success' ? (
                  <span className="text-emerald-700">
                    成功：寫入 {rec.written} 格、略過 {rec.skipped} 題
                    {rec.cleared > 0 && `、清空 ${rec.cleared} 格`}
                    {rec.kept > 0 && `、保留 ${rec.kept} 格`}
                  </span>
                ) : (
                  <span className="text-red-600">失敗：{rec.message ?? rec.reason}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && (
        <div role="alert" className="space-y-1 rounded bg-red-50 p-3 text-sm text-red-700">
          <p>{error}</p>
          {hint?.code === 'SHEET_NOT_EDITABLE' && (
            <p>
              請在 Google 試算表的「共用」把機器人帳號設為「編輯者」後再試
              {hint.email && (
                <>
                  ：<span className="select-all font-mono">{hint.email}</span>
                </>
              )}
            </p>
          )}
          {hint?.code === 'SHEET_STRUCTURE_CHANGED' && <p>試算表在建立房間後被改動，為避免寫錯位置，請重新建立房間。</p>}
          {(hint?.code === 'SHEET_QUOTA' || hint?.code === 'SHEET_TIMEOUT') && <p>請稍後再試，可直接重新按「回填至 Google Sheet」。</p>}
        </div>
      )}
    </section>
  )
}
