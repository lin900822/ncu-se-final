import type { BundleItem, QuestionItem } from './api'

function byOrder(a: QuestionItem, b: QuestionItem): number {
  return a.number - b.number || (a.sub ?? 0) - (b.sub ?? 0)
}

/** 依題號分組（題組的多個小題歸在同一題號下）；依題號、小題編號排序。 */
export function groupByNumber(questions: QuestionItem[]): { number: number; items: QuestionItem[] }[] {
  const map = new Map<number, QuestionItem[]>()
  for (const q of questions) {
    const list = map.get(q.number) ?? []
    list.push(q)
    map.set(q.number, list)
  }
  return [...map.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([number, items]) => ({ number, items: items.sort((x, y) => (x.sub ?? 0) - (y.sub ?? 0)) }))
}

/** 搶答單位：一張卡片。老師綁定的題組整組一張；其餘題目沿用「同題號一框」。 */
export type AnswerUnit =
  | { kind: 'bundle'; bundle: BundleItem; items: QuestionItem[] }
  | { kind: 'single'; number: number; items: QuestionItem[] }

/** 依題目順序產生卡片：題組放在第一個成員的位置，成員依題目順序。 */
export function groupByUnit(questions: QuestionItem[], bundles: BundleItem[]): AnswerUnit[] {
  const sorted = [...questions].sort(byOrder)
  const bundleOf = new Map<string, BundleItem>()
  for (const b of bundles) for (const id of b.questionIds) bundleOf.set(id, b)
  const units: AnswerUnit[] = []
  const seenBundles = new Set<string>()
  let pendingSingles: QuestionItem[] = []
  const flushSingles = () => {
    for (const g of groupByNumber(pendingSingles)) units.push({ kind: 'single', ...g })
    pendingSingles = []
  }
  for (const q of sorted) {
    const b = bundleOf.get(q.id)
    if (!b) {
      pendingSingles.push(q)
      continue
    }
    if (seenBundles.has(b.id)) continue
    flushSingles()
    seenBundles.add(b.id)
    units.push({ kind: 'bundle', bundle: b, items: sorted.filter((x) => b.questionIds.includes(x.id)) })
  }
  flushSingles()
  return units
}

/** 題組標題，例如「題組：Q3、Q4」 */
export function bundleTitle(items: QuestionItem[]): string {
  return `題組：${items.map((q) => q.label).join('、')}`
}

/** 這些題目在題目清單中是否連續相鄰（依題號、小題編號排序） */
export function isAdjacent(questions: QuestionItem[], ids: string[]): boolean {
  const order = [...questions].sort(byOrder).map((q) => q.id)
  const positions = ids.map((id) => order.indexOf(id)).sort((a, b) => a - b)
  if (positions.length === 0 || positions[0] < 0) return false
  return positions[positions.length - 1] - positions[0] + 1 === positions.length
}
