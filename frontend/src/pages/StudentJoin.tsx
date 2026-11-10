import { useCallback, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import QuestionFields from '../components/QuestionFields'
import {
  clearStudentJoin,
  loadStudentJoin,
  saveStudentJoin,
  type BundleItem,
  type QuestionItem,
  type RoomPhase,
} from '../lib/api'
import { clearDraft, loadDraft, saveDraft } from '../lib/drafts'
import ResultBoard, { type ResultData } from '../components/ResultBoard'
import { useReconnectingSocket } from '../hooks/useReconnectingSocket'

type View = 'form' | 'joining' | 'joined' | 'closed'

export default function StudentJoin() {
  const saved = useRef(loadStudentJoin())
  const [code, setCode] = useState(saved.current?.code ?? '')
  const [name, setName] = useState(saved.current?.name ?? '')
  const [active, setActive] = useState<{ code: string; name: string } | null>(saved.current)
  const [phase, setPhase] = useState<View>(saved.current ? 'joining' : 'form')
  const [error, setError] = useState('')
  const [result, setResult] = useState<ResultData | null>(null)
  const [joinedName, setJoinedName] = useState('')
  const [joinedCode, setJoinedCode] = useState('')
  const [notice, setNotice] = useState('')
  const [connectKey, setConnectKey] = useState(0)
  const [roomPhase, setRoomPhase] = useState<RoomPhase>('Waiting')
  const [questions, setQuestions] = useState<QuestionItem[]>([])
  const [values, setValues] = useState<Record<string, string>>({})
  const [texts, setTexts] = useState<Record<string, string>>({}) // 題目文字：僅搶答中才有
  // 答案提交（Step 4）：一律以伺服器事件為準，不做樂觀更新
  const [submitted, setSubmitted] = useState<Record<string, string>>({})
  const [othersSubmitted, setOthersSubmitted] = useState<string[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  // 題組（Step 7）：設定由伺服器下發；錯誤依題組顯示
  const [bundles, setBundles] = useState<BundleItem[]>([])
  const bundlesRef = useRef<BundleItem[]>([])
  const [bundleErrors, setBundleErrors] = useState<Record<string, string>>({})
  const lastRound = useRef(0)
  const roomCodeRef = useRef('')
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
    setSubmitted({})
    setOthersSubmitted([])
    setErrors({})
    setBundleErrors({})
    setResult(null)
  }, [])

  // 後端階段為唯一事實來源；round 增加（新一輪開始）才清空填空格與草稿，同輪重連不清空
  const applyPhase = useCallback((phase: RoomPhase, round: number) => {
    setRoomPhase(phase)
    if (round > lastRound.current) {
      lastRound.current = round
      setValues({})
      setSubmitted({})
      setOthersSubmitted([])
      setErrors({})
      setBundleErrors({})
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
      if (msg.phase === 'Answering') setResult(null) // 新一輪開始：離開結果頁
      if (msg.phase !== 'Answering') setTexts({}) // 結束搶答後隱藏題目文字
    } else if (msg.type === 'round_result') {
      // 結算後公布：每題只有第一名的組別與答案
      setResult({ round: msg.round as number, results: msg.results as ResultData['results'] })
    } else if (msg.type === 'submitted') {
      // 同組任一視窗送出（含自己）：該題變「已送出」，內容以伺服器為準
      const qid = msg.questionId as string
      const answer = msg.answer as string
      setSubmitted((prev) => ({ ...prev, [qid]: answer }))
      setValues((prev) => ({ ...prev, [qid]: answer }))
      setErrors((prev) => {
        const { [qid]: _removed, ...rest } = prev
        return rest
      })
    } else if (msg.type === 'bundle_submitted') {
      // 同組任一視窗送出題組（含自己）：整張卡片一次變「已送出」，內容以伺服器為準
      const bid = msg.bundleId as string
      const answers = (msg.answers as Record<string, string>) ?? {}
      setSubmitted((prev) => ({ ...prev, ...answers }))
      setValues((prev) => ({ ...prev, ...answers }))
      setBundleErrors((prev) => {
        const { [bid]: _removed, ...rest } = prev
        return rest
      })
    } else if (msg.type === 'bundle_hint') {
      // 匿名提示：只知道「這個題組有組別送出」，以成員題目記錄（與重連時的 submittedByOthers 一致）
      if ((msg.round as number) >= lastRound.current) {
        const b = bundlesRef.current.find((x) => x.id === msg.bundleId)
        if (b) setOthersSubmitted((prev) => [...new Set([...prev, ...b.questionIds])])
      }
    } else if (msg.type === 'question_submitted') {
      // 匿名提示：只知道「這題有組別送出」，不含組名、內容、數量
      if ((msg.round as number) >= lastRound.current) {
        const qid = msg.questionId as string
        setOthersSubmitted((prev) => (prev.includes(qid) ? prev : [...prev, qid]))
      }
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
      bundlesRef.current = (msg.bundles as BundleItem[]) ?? []
      setBundles(bundlesRef.current)
      setTexts((msg.texts as Record<string, string>) ?? {}) // 搶答中以外一律為空
      applyPhase(msg.phase as RoomPhase, round)
      // 伺服器還原本組本輪已送出的內容與他組匿名提示（須在 applyPhase 之後，避免被輪次清空覆蓋）
      const mine = (msg.mySubmissions as Record<string, string>) ?? {}
      setSubmitted(mine)
      setValues((prev) => ({ ...prev, ...mine }))
      setOthersSubmitted((msg.submittedByOthers as string[]) ?? [])
      setResult((msg.result as ResultData | null) ?? null) // 後端還原（重連／晚加入）
      setJoinedName(group.name)
      setJoinedCode(room.code)
      if (a) saveStudentJoin({ code: room.code, name: group.name })
      setNotice('')
      setError('')
      setPhase('joined')
    } else if (msg.type === 'room_closed') {
      setRoomPhase('Ended')
      setTexts({})
      resetLocal()
      setResult(null)
      clearStudentJoin()
      setActive(null)
      setPhase('closed')
    } else if (msg.type === 'error') {
      const errCode = msg.code as string
      if (msg.bundleId !== undefined) {
        // 題組送出被拒絕（未填完、過長、非搶答中…）：顯示在該題組卡片，連線維持
        const bid = msg.bundleId as string
        setBundleErrors((prev) => ({ ...prev, [bid]: msg.message as string }))
        return
      }
      if (msg.questionId !== undefined) {
        // 送出被拒絕（空白、過長、非搶答中…）：只顯示在該題，連線維持
        const qid = msg.questionId as string
        setErrors((prev) => ({ ...prev, [qid]: msg.message as string }))
        return
      }
      if (errCode === 'ROOM_CLOSED' || errCode === 'ROOM_NOT_FOUND') clearStudentJoin()
      setNotice('')
      setActive(null)
      setError(msg.message as string)
      setPhase(errCode === 'ROOM_CLOSED' ? 'closed' : 'form')
    }
  }, [applyPhase, resetLocal])

  const { status, send } = useReconnectingSocket({
    path: active ? '/ws/student' : null,
    onOpen,
    onMessage,
    connectKey,
    noReconnectCodes: [1008],
  })

  // 送出某題：不做樂觀更新，等伺服器回 submitted 才顯示「已送出」
  function onSubmitAnswer(id: string) {
    setErrors((prev) => {
      const { [id]: _removed, ...rest } = prev
      return rest
    })
    send({ type: 'submit', questionId: id, answer: values[id] ?? '' })
  }

  // 送出題組：只送該題組成員的答案；不做樂觀更新，等伺服器回 bundle_submitted
  function onSubmitBundle(bundleId: string) {
    const b = bundles.find((x) => x.id === bundleId)
    if (!b) return
    setBundleErrors((prev) => {
      const { [bundleId]: _removed, ...rest } = prev
      return rest
    })
    const answers = Object.fromEntries(b.questionIds.map((id) => [id, values[id] ?? '']))
    send({ type: 'submit_bundle', bundleId, answers })
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setError('請填寫組名')
      return
    }
    setError('')
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
        {roomPhase === 'Ended' && result && (
          <ResultBoard result={result} questions={questions} myGroup={joinedName} bundles={bundles} />
        )}
        {!(roomPhase === 'Ended' && result) && questions.length > 0 && (
          <QuestionFields
            questions={questions}
            values={values}
            disabled={!unlocked}
            texts={unlocked ? texts : undefined}
            submitted={submitted}
            othersSubmitted={othersSubmitted}
            errors={errors}
            bundles={bundles}
            bundleErrors={bundleErrors}
            onSubmit={onSubmitAnswer}
            onSubmitBundle={onSubmitBundle}
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
