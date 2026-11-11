import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { QuestionList } from '../components/QuestionFields'
import BundleEditor from '../components/BundleEditor'
import FairnessEditor, { EMPTY_FAIRNESS, parseFairness, type FairnessInput } from '../components/FairnessEditor'
import {
  ApiError,
  createRoom,
  describeError,
  loadTeacherSession,
  previewSheet,
  recoverRoom,
  saveTeacherSession,
  type SheetPreview,
} from '../lib/api'

const btn =
  'rounded-lg px-5 py-3 text-lg font-semibold transition disabled:opacity-50'

export default function Home() {
  const nav = useNavigate()
  // 同一瀏覽器已有老師身分時自動回到原房間（FR-012）
  const [hasSession] = useState(() => loadTeacherSession() !== null)
  useEffect(() => {
    if (hasSession) nav('/teacher', { replace: true })
  }, [hasSession, nav])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [recovery, setRecovery] = useState('')
  const [sheetUrl, setSheetUrl] = useState('')
  const [preview, setPreview] = useState<SheetPreview | null>(null)
  const [previewedUrl, setPreviewedUrl] = useState('')
  // 題組（Step 7）：只在預覽中暫存，確認建立時才送出；重新讀取或改連結即清除
  const [bundles, setBundles] = useState<string[][]>([])
  // 公平規則（Step 11）：只在預覽中暫存，確認建立時才送出；重新讀取或改連結即清除
  const [fairness, setFairness] = useState<FairnessInput>(EMPTY_FAIRNESS)

  async function onCreate() {
    setBusy(true)
    setError('')
    try {
      saveTeacherSession(await createRoom())
      nav('/teacher')
    } catch (e) {
      setError(describeError(e))
    } finally {
      setBusy(false)
    }
  }

  async function onPreview(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setPreview(null)
    setBundles([])
    setFairness(EMPTY_FAIRNESS)
    try {
      const url = sheetUrl.trim()
      setPreview(await previewSheet(url))
      setPreviewedUrl(url)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  // 老師確認預覽後才建立房間；後端會重新讀取並比對指紋
  async function onConfirm() {
    if (!preview) return
    const parsed = parseFairness(fairness, preview.questions.length)
    if (!parsed.ok) return // 無效時按鈕已禁用，這裡只是保險
    setBusy(true)
    setError('')
    try {
      saveTeacherSession(
        await createRoom({
          sheetUrl: previewedUrl,
          fingerprint: preview.fingerprint,
          bundles,
          fairness: parsed.rule,
        }),
      )
      nav('/teacher')
    } catch (err) {
      // 題組設定有誤時保留預覽讓老師修改；其他錯誤（例如試算表已變動）要求重新讀取
      if (!(err instanceof ApiError && (err.code === 'BUNDLES_INVALID' || err.code === 'FAIRNESS_INVALID'))) {
        setPreview(null)
        setBundles([])
        setFairness(EMPTY_FAIRNESS)
      }
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  async function onRecover(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      saveTeacherSession(await recoverRoom(recovery))
      nav('/teacher')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (hasSession) return null

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-bold">課堂搶答數位化系統</h1>

      <div className="grid gap-4 sm:grid-cols-2">
        <button
          onClick={onCreate}
          disabled={busy}
          className={`${btn} bg-indigo-600 text-white hover:bg-indigo-700`}
        >
          我是老師 — 直接建立房間（不使用試算表）
        </button>
        <Link
          to="/join"
          className={`${btn} bg-emerald-600 text-center text-white hover:bg-emerald-700`}
        >
          我是學生 — 加入房間
        </Link>
      </div>

      <form onSubmit={onPreview} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
        <label htmlFor="sheet" className="block font-medium">
          用 Google Sheet 學習單建立房間
        </label>
        <div className="flex gap-2">
          <input
            id="sheet"
            value={sheetUrl}
            onChange={(e) => {
              setSheetUrl(e.target.value)
              setPreview(null) // 改連結即清除預覽
              setBundles([])
              setFairness(EMPTY_FAIRNESS)
            }}
            placeholder="貼上 Google Sheet 連結"
            className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-2"
          />
          <button
            disabled={busy || !sheetUrl.trim()}
            className="rounded bg-slate-800 px-4 py-2 text-white disabled:opacity-50"
          >
            {busy && !preview ? '讀取中…' : preview ? '重新讀取' : '讀取題目'}
          </button>
        </div>
        {preview && (
          <div className="space-y-3 rounded bg-slate-50 p-3">
            <p className="text-sm text-slate-600">
              分頁「{preview.sheetTitle}」，共 {preview.questions.length} 題，請確認題號是否正確：
            </p>
            <QuestionList questions={preview.questions} />
            <BundleEditor
              questions={preview.questions}
              bundles={bundles}
              onChange={setBundles}
              disabled={busy}
            />
            <FairnessEditor
              questionCount={preview.questions.length}
              value={fairness}
              onChange={setFairness}
              disabled={busy}
            />
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy || !parseFairness(fairness, preview.questions.length).ok}
              className={`${btn} w-full bg-indigo-600 text-white hover:bg-indigo-700`}
            >
              確認建立房間
            </button>
          </div>
        )}
      </form>

      <form onSubmit={onRecover} className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
        <label htmlFor="recovery" className="block font-medium">
          換裝置了？用恢復碼回到老師端
        </label>
        <div className="flex gap-2">
          <input
            id="recovery"
            value={recovery}
            onChange={(e) => setRecovery(e.target.value)}
            placeholder="恢復碼"
            className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-2 uppercase"
          />
          <button
            disabled={busy || !recovery.trim()}
            className="rounded bg-slate-800 px-4 py-2 text-white disabled:opacity-50"
          >
            回復
          </button>
        </div>
      </form>

      {error && (
        <p role="alert" className="rounded bg-red-50 p-3 text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}
