import type { QuestionItem } from './api'

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
