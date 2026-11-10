/** 學生作答草稿：只存在該學生自己的瀏覽器，不送後端（FR-013）。所有存取皆 try/catch。 */
export const MAX_ANSWER_LENGTH = 500

export interface Draft {
  round: number
  values: Record<string, string>
}

const key = (roomCode: string) => `draft:${roomCode}`

export function loadDraft(roomCode: string): Draft | null {
  try {
    const raw = localStorage.getItem(key(roomCode))
    if (!raw) return null
    const d = JSON.parse(raw) as Draft
    if (typeof d?.round !== 'number' || typeof d?.values !== 'object' || d.values === null) {
      return null
    }
    return d
  } catch {
    return null
  }
}

export function saveDraft(roomCode: string, draft: Draft): void {
  try {
    const values: Record<string, string> = {}
    for (const [id, text] of Object.entries(draft.values)) {
      values[id] = String(text).slice(0, MAX_ANSWER_LENGTH)
    }
    localStorage.setItem(key(roomCode), JSON.stringify({ round: draft.round, values }))
  } catch {
    /* 隱私模式或儲存被封鎖：只影響還原，不影響輸入 */
  }
}

export function clearDraft(roomCode: string): void {
  try {
    localStorage.removeItem(key(roomCode))
  } catch {
    /* ignore */
  }
}
