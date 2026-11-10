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

/** 不帶參數＝不使用試算表；帶參數時後端會重新讀取並比對指紋 */
export async function createRoom(opts?: {
  sheetUrl: string
  fingerprint: string
}): Promise<TeacherSession> {
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
  return (e as Error).message
}

export async function recoverRoom(recoveryCode: string): Promise<TeacherSession> {
  return request<TeacherSession>('/api/rooms/recover', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recoveryCode }),
  })
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
