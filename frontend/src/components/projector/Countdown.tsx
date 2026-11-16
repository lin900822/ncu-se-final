import { useEffect, useState } from 'react'

const STEPS = ['3', '2', '1', '開始！']

/** 搶答倒數動畫（純視覺）：3、2、1、開始！各約 0.75 秒；減少動態效果時由 CSS 關閉動畫，仍逐秒顯示。 */
export default function Countdown({ onDone }: { onDone: () => void }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => (i + 1 < STEPS.length ? setI(i + 1) : onDone()), 750)
    return () => clearTimeout(t)
  }, [i, onDone])
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90"
    >
      <span key={i} className="projector-count text-[22vw] font-black leading-none text-amber-300">
        {STEPS[i]}
      </span>
    </div>
  )
}
