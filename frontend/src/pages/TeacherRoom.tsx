import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  clearTeacherSession,
  closeRoom,
  endAnswering,
  loadTeacherSession,
  startAnswering,
  type BundleItem,
  type QuestionItem,
  type RoomPhase,
  type TeacherSession,
} from '../lib/api'
import { QuestionList } from '../components/QuestionFields'
import ResultBoard, { type ResultData } from '../components/ResultBoard'
import RankingBoard, { type Board } from '../components/RankingBoard'
import { useReconnectingSocket } from '../hooks/useReconnectingSocket'

interface SubmissionItem {
  group: string
  questionId: string
  answer: string
  round: number
  submittedAt: string
  rank: number
  bundleId?: string | null
}

interface GroupItem {
  name: string
  online: boolean
  joinedAt: string
}

export default function TeacherRoom() {
  const nav = useNavigate()
  const [session] = useState<TeacherSession | null>(() => loadTeacherSession())
  const [groups, setGroups] = useState<GroupItem[]>([])
  const [closed, setClosed] = useState(false)
  const [roomPhase, setRoomPhase] = useState<RoomPhase>('Waiting')
  const [questions, setQuestions] = useState<QuestionItem[]>([])
  const [bundles, setBundles] = useState<BundleItem[]>([])
  const [sheetTitle, setSheetTitle] = useState<string | null>(null)
  const [texts, setTexts] = useState<Record<string, string>>({})
  const [round, setRound] = useState(0)
  const [submissions, setSubmissions] = useState<SubmissionItem[]>([])
  const [result, setResult] = useState<ResultData | null>(null)
  const [board, setBoard] = useState<Board | null>(null)
  const [revoked, setRevoked] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!session) nav('/', { replace: true })
  }, [session, nav])

  const onMessage = useCallback((msg: Record<string, unknown>) => {
    switch (msg.type) {
      case 'snapshot':
        // 後端為事實來源：以快照整份覆蓋
        setGroups(msg.groups as GroupItem[])
        {
          const room = msg.room as {
            phase: RoomPhase
            questions?: QuestionItem[]
            bundles?: BundleItem[]
            sheetTitle?: string | null
            texts?: Record<string, string>
            round?: number
            submissions?: SubmissionItem[]
            board?: Board
            result?: ResultData | null
          }
          setRoomPhase(room.phase)
          setQuestions(room.questions ?? [])
          setBundles(room.bundles ?? [])
          setSheetTitle(room.sheetTitle ?? null)
          setTexts(room.texts ?? {})
          setRound(room.round ?? 0)
          setSubmissions(room.submissions ?? [])
          setBoard(room.board ?? null)
          setResult(room.result ?? null)
        }
        break
      case 'question_texts':
        setTexts((msg.texts as Record<string, string>) ?? {})
        break
      case 'submission': {
        // 每筆新送出即時追加（只在老師端顯示答案內容）
        const item: SubmissionItem = {
          group: msg.group as string,
          questionId: msg.questionId as string,
          answer: msg.answer as string,
          round: msg.round as number,
          submittedAt: msg.submittedAt as string,
          rank: msg.rank as number,
          bundleId: (msg.bundleId as string | null | undefined) ?? null,
        }
        setSubmissions((prev) => [...prev, item])
        break
      }
      case 'board':
        // 完整看板直接覆蓋（後端為事實來源）
        setBoard(msg as unknown as Board)
        break
      case 'round_result':
        setResult({ round: msg.round as number, results: msg.results as ResultData['results'] })
        break
      case 'phase_changed':
        if (msg.phase === 'Answering') setResult(null)
        setRound(msg.round as number)
        setRoomPhase(msg.phase as RoomPhase)
        break
      case 'group_joined':
        setGroups((prev) => {
          const g = msg.group as GroupItem
          return prev.some((x) => x.name === g.name) ? prev : [...prev, g]
        })
        break
      case 'group_status':
        setGroups((prev) =>
          prev.map((g) => (g.name === msg.name ? { ...g, online: msg.online as boolean } : g)),
        )
        break
      case 'room_closed':
        setClosed(true)
        break
      case 'token_revoked':
        clearTeacherSession()
        setRevoked(true)
        break
    }
  }, [])

  const path =
    session && !closed && !revoked
      ? `/ws/teacher?code=${encodeURIComponent(session.code)}&token=${encodeURIComponent(session.teacherToken)}`
      : null

  const { status } = useReconnectingSocket({
    path,
    onMessage,
    noReconnectCodes: [4401],
    onClose: (code) => {
      if (code === 4401) {
        clearTeacherSession()
        setRevoked(true)
      }
    },
  })

  async function onTogglePhase() {
    if (!session) return
    setError('')
    try {
      const r =
        roomPhase === 'Answering'
          ? await endAnswering(session.code, session.teacherToken)
          : await startAnswering(session.code, session.teacherToken)
      setRoomPhase(r.phase)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function onClose() {
    if (!session) return
    if (!window.confirm('確定要結束房間嗎？結束後學生將無法再加入。')) return
    try {
      await closeRoom(session.code, session.teacherToken)
      setClosed(true)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!session) return null

  // 只顯示目前這一輪；舊輪次的紀錄仍保留在後端
  const currentSubmissions = submissions.filter((x) => x.round === round)

  if (revoked) {
    return (
      <div className="space-y-4">
        <p role="alert" className="rounded bg-amber-50 p-4 text-amber-800">
          身分已失效，請以恢復碼回復。
        </p>
        <Link to="/" className="text-indigo-600 underline">
          回首頁
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl bg-white p-6 text-center shadow-sm">
        <p className="text-slate-500">房間代碼</p>
        <p className="my-2 font-mono text-6xl font-bold tracking-widest sm:text-7xl">
          {session.code}
        </p>
        <p className="text-sm text-slate-500">
          恢復碼：<span className="font-mono font-semibold">{session.recoveryCode}</span>
          （換裝置時需要，請妥善保存）
        </p>
      </section>

      {closed && (
        <div role="status" className="space-y-2 rounded bg-slate-200 p-3 text-center">
          <p className="font-semibold">房間已結束</p>
          <button
            onClick={() => {
              clearTeacherSession()
              nav('/', { replace: true })
            }}
            className="rounded bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700"
          >
            回首頁，建立新房間
          </button>
        </div>
      )}

      {!closed && (
        <section className="space-y-3 rounded-xl bg-white p-6 text-center shadow-sm">
          <p className="text-slate-500">目前階段</p>
          <p className="text-2xl font-bold">
            {roomPhase === 'Answering' ? '搶答中' : roomPhase === 'Ended' ? '已結束搶答' : '等待搶答'}
          </p>
          <button
            onClick={onTogglePhase}
            disabled={status !== 'open'}
            className={`w-full rounded-lg py-3 text-lg font-semibold text-white disabled:opacity-50 ${
              roomPhase === 'Answering'
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-emerald-600 hover:bg-emerald-700'
            }`}
          >
            {roomPhase === 'Answering' ? '結束搶答' : '開始搶答'}
          </button>
        </section>
      )}

      <section className="space-y-2 rounded-xl bg-white p-6 shadow-sm">
        <h2 className="text-xl font-bold">題目{questions.length > 0 && `（共 ${questions.length} 題）`}</h2>
        {questions.length === 0 ? (
          <p className="text-slate-500">本房間未設定題目</p>
        ) : (
          <>
            {sheetTitle && <p className="text-sm text-slate-500">來源分頁：{sheetTitle}</p>}
            <QuestionList questions={questions} texts={texts} bundles={bundles} />
          </>
        )}
      </section>

      <section className="space-y-2 rounded-xl bg-white p-6 shadow-sm">
        <h2 className="text-xl font-bold">{roomPhase === 'Ended' && result ? '最終結果' : '即時進度板'}</h2>
        {roomPhase === 'Ended' && result && (
          <ResultBoard result={result} questions={questions} myGroup="" bundles={bundles} />
        )}
        <RankingBoard board={board} questions={questions} />
      </section>

      <section className="space-y-2 rounded-xl bg-white p-6 shadow-sm">
        <h2 className="text-xl font-bold">本輪送出</h2>
        {currentSubmissions.length === 0 ? (
          <p className="text-slate-500">尚無組別送出</p>
        ) : (
          <ul className="space-y-2">
            {currentSubmissions.map((sub) => (
              <li
                key={`${sub.round}-${sub.group}-${sub.questionId}`}
                className="rounded border border-slate-200 px-3 py-2 text-sm"
              >
                <span className="font-semibold">{sub.group}</span>
                <span className="mx-2 text-slate-500">
                  {questions.find((q) => q.id === sub.questionId)?.label ?? sub.questionId}
                </span>
                <span className="whitespace-pre-wrap">{sub.answer}</span>
                <span className="ml-2 text-xs text-slate-400">
                  {new Date(sub.submittedAt).toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl bg-white p-6 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xl font-bold">目前 {groups.length} 組</h2>
          {!closed && status !== 'open' && (
            <span className="text-sm text-amber-600">連線中…</span>
          )}
        </div>
        {groups.length === 0 ? (
          <p className="text-slate-500">尚無組別加入</p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {groups.map((g) => (
              <li
                key={g.name}
                className="flex items-center justify-between gap-2 rounded border border-slate-200 px-3 py-2"
              >
                <span className="break-all font-medium">{g.name}</span>
                <span
                  className={`shrink-0 text-sm ${g.online ? 'text-emerald-600' : 'text-slate-400'}`}
                >
                  <span aria-hidden>●</span> {g.online ? '在線' : '離線'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {error && (
        <p role="alert" className="rounded bg-red-50 p-3 text-red-700">
          {error}
        </p>
      )}

      {!closed && (
        <button
          onClick={onClose}
          className="rounded border border-red-300 px-4 py-2 text-red-600 hover:bg-red-50"
        >
          結束房間
        </button>
      )}
    </div>
  )
}
