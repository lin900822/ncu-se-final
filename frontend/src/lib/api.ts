export interface TeacherSession {
  code: string
  teacherToken: string
  recoveryCode: string
}

export class ApiError extends Error {
  code: string
  details?: Record<string, unknown>
  constructor(code: string, message: string, details?: Record<string, unknown>) {
    super(message)
    this.code = code
    this.details = details
  }
}

/** 題目（不含試算表位置；位置只存在伺服器） */
export interface QuestionItem {
  id: string
  number: number
  sub: number | null
  label: string
}

/** 公平規則（Step 11）：建立房間時確定、之後不可修改；null 表示不限制 */
export interface FairnessRule {
  winCap: number | null
  cooldownSeconds: number
}

/** 審核紀錄（僅老師可見） */
export interface ReviewItem {
  round: number
  unitId: string
  group: string
  action: 'invalid' | 'valid'
  reason: string
  by: string
  reviewedAt: string
}

/** 老師審核：駁回／恢復某組在某搶答單位的送出（憑證只放標頭） */
export async function reviewSubmission(
  code: string,
  token: string,
  body: { round: number; unitId: string; group: string; action: 'invalid' | 'valid'; reason: string },
): Promise<{ changed: boolean }> {
  return request<{ changed: boolean }>(`/api/rooms/${encodeURIComponent(code)}/reviews`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  })
}

/** 回填至 Google Sheet（Step 10）：確認摘要的各類格數 */
export interface BackfillCounts {
  write: number
  skip: number
  clear: number
  keep: number
  overwrite?: number
}

export interface BackfillItem {
  questionId: string
  label: string
  action: 'write' | 'clear' | 'keep' | 'skip'
  overwrite: boolean
  answer: string | null
}

export interface BackfillPreview {
  round: number
  sheetTitle: string
  sheetUrl: string
  canBackfill: boolean
  counts: BackfillCounts
  items: BackfillItem[]
}

/** 回填紀錄（公開格式：只含格數與結果，不含儲存格位置與答案內容） */
export interface BackfillRecordItem {
  round: number
  at: string
  written: number
  skipped: number
  cleared: number
  kept: number
  result: 'Success' | 'Failed'
  reason: string | null
  message: string | null
}

export interface BackfillResult {
  round: number
  sheetUrl: string
  counts: BackfillCounts
  record: BackfillRecordItem
}

/** 預覽（唯讀，不寫入）：憑證只放標頭 */
export async function backfillPreview(code: string, token: string, round: number): Promise<BackfillPreview> {
  return request<BackfillPreview>(`/api/rooms/${encodeURIComponent(code)}/backfill/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ round }),
  })
}

/** 確認回填：伺服器以確認當下的結果重新計算後寫入（全有或全無） */
export async function backfillConfirm(code: string, token: string, round: number): Promise<BackfillResult> {
  return request<BackfillResult>(`/api/rooms/${encodeURIComponent(code)}/backfill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ round }),
  })
}

/** 題組：老師綁定、須一起送出的相鄰題目（不含作答內容） */
export interface BundleItem {
  id: string
  questionIds: string[]
}

export interface SheetPreview {
  sheetTitle: string
  questions: QuestionItem[]
  fingerprint: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError('NETWORK', '無法連線到伺服器，請稍後再試')
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const e = data?.error
    throw new ApiError(e?.code ?? 'UNKNOWN', e?.message ?? '發生未知錯誤', e?.details)
  }
  return data as T
}

export async function previewSheet(url: string): Promise<SheetPreview> {
  return request<SheetPreview>('/api/sheets/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
}

/** 不帶參數＝不使用試算表；帶參數時後端會重新讀取並比對指紋；bundles 為題組（每組為相鄰題目的 id） */
export async function createRoom(opts?: {
  sheetUrl: string
  fingerprint: string
  bundles?: string[][]
  fairness?: { winCap?: number | null; cooldownSeconds?: number }
}): Promise<TeacherSession & { bundles?: BundleItem[]; fairness?: FairnessRule | null; projectorKey?: string }> {
  return request<TeacherSession>('/api/rooms', {
    method: 'POST',
    ...(opts
      ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opts) }
      : {}),
  })
}

/** 投影視圖（Step 12）的整份唯讀狀態：全班公開內容；搶答中只有匿名進度，不含組名與答案。 */
export interface ProjectorState {
  type: 'projector_state'
  code: string
  status: 'Open' | 'Closed'
  phase: 'Waiting' | 'Answering' | 'Ended'
  round: number
  groups: string[]
  questions: { id: string; number: number; sub: number | null; label: string }[]
  bundles: { id: string; questionIds: string[] }[]
  progress: { answered: number; total: number } | null
  submitted: Record<string, boolean> | null
  result: {
    round: number
    results: { questionId: string; winnerGroup: string | null; answer: string | null; noValid?: boolean }[]
  } | null
  scoreboard: { group: string; score: number; rank: number }[]
}

/** 投影網址：只含唯讀投影憑證，不含老師憑證。 */
export function projectorUrl(code: string, key: string): string {
  return `/projector?code=${encodeURIComponent(code)}&key=${encodeURIComponent(key)}`
}

/** 把 API 錯誤轉成給老師看的中文訊息（題號問題會列出重複與缺漏） */
export function describeError(e: unknown): string {
  if (e instanceof ApiError && e.code === 'SHEET_QUESTIONS_INVALID' && e.details) {
    const d = e.details as {
      duplicates?: number[]
      missing?: number[]
      invalidSubs?: number[]
      empty?: number[]
    }
    const parts: string[] = []
    if (d.duplicates?.length) parts.push(`重複的題號：${d.duplicates.join('、')}`)
    if (d.missing?.length) parts.push(`缺漏的題號：${d.missing.join('、')}`)
    if (d.invalidSubs?.length) parts.push(`小題編號不連續的題號：${d.invalidSubs.join('、')}`)
    if (d.empty?.length) parts.push(`沒有作答格的題號：${d.empty.join('、')}`)
    return `${e.message}（${parts.join('；')}）`
  }
  if (e instanceof ApiError && e.code === 'FAIRNESS_INVALID' && e.details) {
    const reasons: Record<string, string> = {
      WIN_CAP_RANGE: '每組上限須為 1 到題目數的整數',
      COOLDOWN_RANGE: '冷卻秒數須為 0 到 600 的整數',
      TYPE: '公平規則欄位格式錯誤',
      NO_QUESTIONS: '沒有題目時不能設定公平規則',
    }
    const reason = reasons[e.details.reason as string]
    return reason ? `${e.message}：${reason}` : e.message
  }
  if (e instanceof ApiError && e.code === 'BUNDLES_INVALID' && e.details) {
    const reasons: Record<string, string> = {
      TOO_FEW: '題組至少需要 2 題',
      NOT_ADJACENT: '題組只能包含相鄰的題目',
      OVERLAP: '一題只能屬於一個題組',
      UNKNOWN_QUESTION: '題組包含不存在的題目',
      NO_QUESTIONS: '沒有題目時不能設定題組',
    }
    const reason = reasons[e.details.reason as string]
    return reason ? `${e.message}：${reason}` : e.message
  }
  return (e as Error).message
}

export async function recoverRoom(recoveryCode: string): Promise<TeacherSession> {
  return request<TeacherSession>('/api/rooms/recover', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recoveryCode }),
  })
}

/** 匯出紀錄：憑證只放標頭（不進網址）；取得 Blob 後以本地日期命名並觸發下載。 */
export async function exportRecords(code: string, token: string): Promise<void> {
  let res: Response
  try {
    res = await fetch(`/api/rooms/${encodeURIComponent(code)}/records.csv`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  } catch {
    throw new ApiError('NETWORK', '無法連線到伺服器，請稍後再試')
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    const e = data?.error
    throw new ApiError(e?.code ?? 'UNKNOWN', e?.message ?? '發生未知錯誤', e?.details)
  }
  const blob = await res.blob()
  const d = new Date()
  const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `搶答紀錄_${code}_${ymd}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export async function closeRoom(code: string, token: string): Promise<void> {
  await request(`/api/rooms/${encodeURIComponent(code)}/close`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
}

const TEACHER_KEY = 'teacherSession'

export function loadTeacherSession(): TeacherSession | null {
  try {
    const raw = localStorage.getItem(TEACHER_KEY)
    return raw ? (JSON.parse(raw) as TeacherSession) : null
  } catch {
    return null
  }
}

export function saveTeacherSession(s: TeacherSession): void {
  try {
    localStorage.setItem(TEACHER_KEY, JSON.stringify(s))
  } catch {
    /* 儲存失敗時仍可正常運作 */
  }
}

export function clearTeacherSession(): void {
  try {
    localStorage.removeItem(TEACHER_KEY)
  } catch {
    /* ignore */
  }
}

const STUDENT_KEY = 'studentJoin'

export function loadStudentJoin(): { code: string; name: string } | null {
  try {
    const raw = sessionStorage.getItem(STUDENT_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function saveStudentJoin(v: { code: string; name: string }): void {
  try {
    sessionStorage.setItem(STUDENT_KEY, JSON.stringify(v))
  } catch {
    /* ignore */
  }
}

export function clearStudentJoin(): void {
  try {
    sessionStorage.removeItem(STUDENT_KEY)
  } catch {
    /* ignore */
  }
}

export type RoomPhase = 'Waiting' | 'Answering' | 'Ended'

export interface PhaseResult {
  phase: RoomPhase
  round: number
  changed: boolean
}

function phaseRequest(code: string, token: string, action: 'start' | 'end') {
  return request<PhaseResult>(`/api/rooms/${encodeURIComponent(code)}/phase/${action}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
}

export const startAnswering = (code: string, token: string) => phaseRequest(code, token, 'start')
export const endAnswering = (code: string, token: string) => phaseRequest(code, token, 'end')
