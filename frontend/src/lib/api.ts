export interface TeacherSession {
  code: string
  teacherToken: string
  recoveryCode: string
}

export class ApiError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
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
    throw new ApiError(e?.code ?? 'UNKNOWN', e?.message ?? '發生未知錯誤')
  }
  return data as T
}

export async function createRoom(): Promise<TeacherSession> {
  const r = await request<{ code: string; teacherToken: string; recoveryCode: string }>('/api/rooms', {
    method: 'POST',
  })
  return r
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
