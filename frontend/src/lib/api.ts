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
}): Promise<TeacherSession & { bundles?: BundleItem[] }> {
  return request<TeacherSession>('/api/rooms', {
    method: 'POST',
    ...(opts
      ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opts) }
      : {}),
  })
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
