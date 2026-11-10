import { useCallback, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import QuestionFields from '../components/QuestionFields'
import {
  clearStudentJoin,
  loadStudentJoin,
  saveStudentJoin,
  type QuestionItem,
  type RoomPhase,
} from '../lib/api'
import { clearDraft, loadDraft, saveDraft } from '../lib/drafts'
import { useReconnectingSocket } from '../hooks/useReconnectingSocket'

type View = 'form' | 'joining' | 'joined' | 'closed'

// 自動重新加入時遇到「該組目前在線」（舊連線尚未被判定離線）的重試設定
const RETRY_INTERVAL_MS = 2000
const MAX_AUTO_RETRIES = 12 // 約 24 秒，涵蓋心跳偵測異常斷線的時間

export default function StudentJoin() {
  const saved = useRef(loadStudentJoin())
  const [code, setCode] = useState(saved.current?.code ?? '')
  const [name, setName] = useState(saved.current?.name ?? '')
  const [active, setActive] = useState<{ code: string; name: string } | null>(saved.current)
  const [phase, setPhase] = useState<View>(saved.current ? 'joining' : 'form')
  const [error, setError] = useState('')
  const [joinedName, setJoinedName] = useState('')
  const [joinedCode, setJoinedCode] = useState('')
  const [notice, setNotice] = useState('')
  const [connectKey, setConnectKey] = useState(0)
  const [roomPhase, setRoomPhase] = useState<RoomPhase>('Waiting')
  const [questions, setQuestions] = useState<QuestionItem[]>([])
  const [values, setValues] = useState<Record<string, string>>({})
  const [texts, setTexts] = useState<Record<string, string>>({}) // 題目文字：僅搶答中才有
  const lastRound = useRef(0)
  const roomCodeRef = useRef('')
  const auto = useRef(!!saved.current) // 是否為自動重新加入
  const retries = useRef(0)
  const activeRef = useRef(active)
  activeRef.current = active

  const onOpen = useCallback((send: (d: unknown) => void) => {
    const a = activeRef.current
    if (a) send({ type: 'join', code: a.code, name: a.name })
  }, [])

  // 離開房間、房間結束或改加入別的房間時，清除本機草稿與狀態（FR-013）
  const resetLocal = useCallback(() => {
    if (roomCodeRef.current) clearDraft(roomCodeRef.current)
    lastRound.current = 0
    setValues({})
  }, [])

  // 後端階段為唯一事實來源；round 增加（新一輪開始）才清空填空格與草稿，同輪重連不清空
  const applyPhase = useCallback((phase: RoomPhase, round: number) => {
    setRoomPhase(phase)
    if (round > lastRound.current) {
      lastRound.current = round
      setValues({})
      if (roomCodeRef.current) clearDraft(roomCodeRef.current)
    }
  }, [])

  const onChangeAnswer = useCallback((id: string, text: string) => {
    setValues((prev) => {
      const next = { ...prev, [id]: text }
      if (roomCodeRef.current) saveDraft(roomCodeRef.current, { round: lastRound.current, values: next })
      return next
    })
  }, [])

  const onMessage = useCallback((msg: Record<string, unknown>) => {
    if (msg.type === 'phase_changed') {
      applyPhase(msg.phase as RoomPhase, msg.round as number)
      if (msg.phase !== 'Answering') setTexts({}) // 結束搶答後隱藏題目文字
    } else if (msg.type === 'question_texts') {
      setTexts((msg.texts as Record<string, string>) ?? {})
    } else if (msg.type === 'joined') {
      const a = activeRef.current
      const group = msg.group as { name: string }
      const room = msg.room as { code: string }
      const round = msg.round as number
      // 順序很重要（避免重新整理時誤清草稿）：先讀草稿 → 以草稿輪次初始化 lastRound →
      // 同一輪才還原 → 最後才 applyPhase（輪次較大才清空）
      if (roomCodeRef.current && roomCodeRef.current !== room.code) resetLocal()
      roomCodeRef.current = room.code
      const draft = loadDraft(room.code)
      if (draft) lastRound.current = draft.round
      if (draft && draft.round === round) setValues(draft.values)
      setQuestions((msg.questions as QuestionItem[]) ?? [])
      setTexts((msg.texts as Record<string, string>) ?? {}) // 搶答中以外一律為空
      applyPhase(msg.phase as RoomPhase, round)
      setJoinedName(group.name)
      setJoinedCode(room.code)
      if (a) saveStudentJoin({ code: room.code, name: group.name })
      auto.current = true
      retries.current = 0
      setNotice('')
      setError('')
      setPhase('joined')
    } else if (msg.type === 'room_closed') {
      setRoomPhase('Ended')
      setTexts({})
      resetLocal()
      clearStudentJoin()
      setActive(null)
      setPhase('closed')
    } else if (msg.type === 'error') {
      const errCode = msg.code as string
      if (errCode === 'GROUP_ONLINE' && auto.current && retries.current < MAX_AUTO_RETRIES) {
        retries.current += 1
        setNotice('正在重新連線…')
        setPhase('joining')
        setTimeout(() => setConnectKey((k) => k + 1), RETRY_INTERVAL_MS)
        return
      }
      if (errCode === 'ROOM_CLOSED' || errCode === 'ROOM_NOT_FOUND') clearStudentJoin()
      auto.current = false
      setNotice('')
      setActive(null)
      setError(msg.message as string)
      setPhase(errCode === 'ROOM_CLOSED' ? 'closed' : 'form')
    }
  }, [applyPhase, resetLocal])

  const { status } = useReconnectingSocket({
    path: active ? '/ws/student' : null,
    onOpen,
    onMessage,
    connectKey,
    noReconnectCodes: [1008],
  })

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setError('請填寫組名')
      return
    }
    setError('')
    auto.current = false
    retries.current = 0
    resetLocal()
    setQuestions([])
    setTexts({})
    setRoomPhase('Waiting')
    setPhase('joining')
    setActive({ code: code.trim(), name: name.trim() })
    setConnectKey((k) => k + 1)
  }

  function onLeave() {
    clearStudentJoin()
    auto.current = false
    resetLocal()
    setQuestions([])
    setTexts({})
    setRoomPhase('Waiting')
    setActive(null)
    setPhase('form')
  }

  // 連線中斷時一律視為鎖定，重新收到 joined 後才依後端階段解鎖
  const unlocked = roomPhase === 'Answering' && status === 'open'

  if (phase === 'joined') {
    return (
      <div className="space-y-4 rounded-xl bg-white p-6 text-center shadow-sm">
        <p className="text-emerald-600">✓ 已加入</p>
        <p className="text-slate-500">房間 {joinedCode}</p>
        <p className="break-all text-4xl font-bold">{joinedName}</p>
        <p
          role="status"
          className={`rounded p-3 text-lg font-semibold ${
            unlocked ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'
          }`}
        >
          {roomPhase === 'Answering' ? '搶答中' : roomPhase === 'Ended' ? '搶答已結束' : '等待搶答'}
          {status !== 'open' && '（重新連線中…）'}
        </p>
        {questions.length > 0 && (
          <QuestionFields
            questions={questions}
            values={values}
            disabled={!unlocked}
            texts={unlocked ? texts : undefined}
            onChange={onChangeAnswer}
          />
        )}
        <button onClick={onLeave} className="text-sm text-slate-400 underline">
          離開房間
        </button>
      </div>
    )
  }

  if (phase === 'closed') {
    return (
      <div className="space-y-4 text-center">
        <p role="alert" className="rounded bg-slate-200 p-4 font-semibold">
          該房間已結束
        </p>
        <Link to="/" className="text-indigo-600 underline">
          回首頁
        </Link>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded-xl bg-white p-6 shadow-sm">
      <h1 className="text-2xl font-bold">加入房間</h1>
      <div>
        <label htmlFor="code" className="mb-1 block font-medium">
          房間代碼
        </label>
        <input
          id="code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          autoCapitalize="characters"
          className="w-full rounded border border-slate-300 px-3 py-2 font-mono text-lg uppercase"
        />
      </div>
      <div>
        <label htmlFor="name" className="mb-1 block font-medium">
          組名
        </label>
        <input
          id="name"
          value={name}
          maxLength={20}
          onChange={(e) => setName(e.target.value)}
          placeholder="例如：第 1 組"
          className="w-full rounded border border-slate-300 px-3 py-2 text-lg"
        />
      </div>
      {notice && <p className="text-amber-600">{notice}</p>}
      {error && (
        <p role="alert" className="rounded bg-red-50 p-3 text-red-700">
          {error}
        </p>
      )}
      <button
        disabled={phase === 'joining'}
        className="w-full rounded-lg bg-emerald-600 py-3 text-lg font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        {phase === 'joining' ? '加入中…' : '加入'}
      </button>
      <Link to="/" className="block text-center text-sm text-slate-400 underline">
        回首頁
      </Link>
    </form>
  )
}
