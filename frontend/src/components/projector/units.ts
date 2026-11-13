import type { ProjectorState } from '../../lib/api'

export interface ProjectorUnit {
  id: string
  title: string
  members: { id: string; label: string }[]
  bundle: boolean
}

/** 搶答單位：題組整組一格（標題「題組：Q3、Q4」），未綁定的題目各一格；依題目順序。 */
export function buildUnits(state: Pick<ProjectorState, 'questions' | 'bundles'>): ProjectorUnit[] {
  const bundleOf = new Map<string, string>()
  for (const b of state.bundles) for (const q of b.questionIds) bundleOf.set(q, b.id)
  const label = new Map(state.questions.map((q) => [q.id, q.label]))
  const units: ProjectorUnit[] = []
  const seen = new Set<string>()
  for (const q of state.questions) {
    const bid = bundleOf.get(q.id)
    if (!bid) {
      units.push({ id: q.id, title: q.label, members: [{ id: q.id, label: q.label }], bundle: false })
      continue
    }
    if (seen.has(bid)) continue
    seen.add(bid)
    const ids = state.bundles.find((b) => b.id === bid)?.questionIds ?? []
    const members = ids.map((id) => ({ id, label: label.get(id) ?? id }))
    units.push({ id: bid, title: `題組：${members.map((m) => m.label).join('、')}`, members, bundle: true })
  }
  return units
}

/** 依格數決定字級與欄數，讓 30 題也能在一個畫面內呈現。 */
export function density(n: number): { cols: number; title: string; body: string } {
  if (n <= 4) return { cols: 2, title: 'text-[3.2vw]', body: 'text-[2.6vw]' }
  if (n <= 8) return { cols: 4, title: 'text-[2.4vw]', body: 'text-[1.9vw]' }
  if (n <= 15) return { cols: 5, title: 'text-[1.9vw]', body: 'text-[1.5vw]' }
  return { cols: 6, title: 'text-[1.5vw]', body: 'text-[1.15vw]' }
}
