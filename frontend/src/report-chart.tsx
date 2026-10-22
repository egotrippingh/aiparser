import { useEffect, useMemo, useRef, useState } from "react"
import { ServiceMark, serviceColors, serviceName } from "./service-mark"
import { shortDate } from "./report-calendar"

export function chartIndex(current: number | null, key: string, length: number) {
  if (!length || key === "Escape") return null
  if (key === "Home") return 0
  if (key === "End") return length - 1
  return Math.max(0, Math.min(length - 1, (current ?? (key === "ArrowLeft" ? length : -1)) + (key === "ArrowLeft" ? -1 : 1)))
}
export function linePath(values: (number | null)[], x: (i: number) => number, y: (v: number) => number) {
  let continuous = false
  return values.map((value, index) => {
    if (value === null) { continuous = false; return "" }
    const part = `${continuous ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`
    continuous = true; return part
  }).join(" ")
}
type ChartDay = { date: string; checked: number; issues: number; skipped: number; services: Record<string, { visibility_pct: number | null }> }
export const chartDays = (days: ChartDay[]) => days.filter(day => day.checked || day.issues || day.skipped)
export function ReportChart({ days, services, available, choose }: {
  days: ChartDay[];
  services: string[]; available: string[]; choose: (services: string[]) => void
}) {
  // Timeline also contains calendar placeholders. Keep every real scan, including
  // absent AI blocks (0%) and failures (no percentage), but not an invented date.
  const chart = useMemo(() => chartDays(days), [days])
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(800), [active, setActive] = useState<number | null>(null)
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(Math.max(300, entries[0].contentRect.width)))
    if (box.current) observer.observe(box.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => setActive(null), [chart])
  const left = 42, right = width - 20, top = 17, bottom = 205
  const x = (i: number) => left + (chart.length === 1 ? (right - left) / 2 : i * (right - left) / Math.max(1, chart.length - 1))
  const y = (value: number) => bottom - value * (bottom - top) / 100
  const point = active === null ? null : chart[active]
  const indexes = [...new Set([0, Math.floor((chart.length - 1) / 2), chart.length - 1])].filter(i => chart[i])
  return <section className="panel"><div className="panel-head"><h2>Динамика упоминаемости</h2><span className="note">Доля возможных упоминаний, %</span></div>
    <div className="legend">{available.map(id => <button type="button" key={id} style={{color:serviceColors[id]}} aria-pressed={services.includes(id)} disabled={services.length === 1 && services.includes(id)} title={services.length === 1 && services.includes(id) ? "В отчёте должна оставаться хотя бы одна система" : undefined} aria-label={`Показывать ${serviceName(id)}`} onClick={() => choose(services.includes(id) ? services.filter(s => s !== id) : [...services,id])}><ServiceMark id={id}/>{serviceName(id)}</button>)}</div>
    <div ref={box} className="chart-wrap"><svg className="line-chart" viewBox={`0 0 ${width} 240`} tabIndex={0} role="img" aria-label="Динамика по ИИ-системам. Стрелки выбирают день, Home и End — крайние даты, Escape скрывает значения."
      onMouseMove={e => { const rect = e.currentTarget.getBoundingClientRect(); const position = (e.clientX - rect.left) * width / rect.width; setActive(chart.length ? Math.max(0,Math.min(chart.length-1,Math.round((position-left)/(right-left)*(chart.length-1)))) : null) }}
      onMouseLeave={() => setActive(null)} onFocus={() => setActive(chart.length ? chart.length - 1 : null)} onBlur={() => setActive(null)}
      onKeyDown={e => { if (["ArrowLeft","ArrowRight","Home","End","Escape"].includes(e.key)) { e.preventDefault(); setActive(index => chartIndex(index,e.key,chart.length)) } }}>
      {[0,25,50,75,100].map(value => <g key={value}><line x1={left} y1={y(value)} x2={right} y2={y(value)} stroke="#e9edf3" strokeDasharray="3 3"/><text x={left-9} y={y(value)+3} textAnchor="end" fill="#748093" fontSize={10}>{value}%</text></g>)}
      {services.map(id => {
        const values = chart.map(day => day.services[id]?.visibility_pct ?? null)
        return <g key={id} fill="none" stroke={serviceColors[id]} strokeWidth={id === "chatgpt" ? 2.8 : 2.2} strokeLinecap="round">
          <path d={linePath(values,x,y)}/>
        </g>
      })}
      {indexes.map(i => <text key={i} x={x(i)} y={230} textAnchor="middle" fill="#748093" fontSize={10}>{shortDate(chart[i].date)}</text>)}
      {point && active !== null && <g><line className="chart-crosshair" x1={x(active)} x2={x(active)} y1={top} y2={bottom}/>{services.map(id => point.services[id]?.visibility_pct == null ? null : <circle key={id} cx={x(active)} cy={y(point.services[id].visibility_pct!)} r={4} fill={serviceColors[id]} stroke="white" strokeWidth={2}/>)}</g>}
      {services.flatMap(id => chart.map((day, i) => {
        const value = day.services[id]?.visibility_pct
        return value != null
          ? <circle key={`${id}-${i}`} cx={x(i)} cy={y(value)} r={3} fill={serviceColors[id]} stroke="white" strokeWidth={1}/> : null
      }))}
      {!chart.length && <text x={width/2} y={115} textAnchor="middle" fill="#748093" fontSize={12}>В этом периоде нет проверок</text>}
    </svg>{point && <div className="chart-tooltip" style={{display:"block",left:Math.max(8,Math.min(x(active!),width-250)),top:20}} aria-live="polite"><strong>{shortDate(point.date)}.{point.date.slice(0,4)}</strong>{services.map(id => <div className="tooltip-service" key={id}><ServiceMark id={id}/><span>{serviceName(id)}</span><b>{point.services[id]?.visibility_pct == null ? "нет данных" : `${point.services[id].visibility_pct}%`}</b></div>)}</div>}</div><div className="chart-note">Точки — дни с проверками. Наведите на график для значений; ← → для выбора дня с клавиатуры.</div>
  </section>
}
