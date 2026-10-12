import { useEffect, useRef, useState } from "react"
import { ServiceMark, serviceColors, serviceName } from "./service-mark"
import { shortDate } from "./report-calendar"

export function chartIndex(current: number | null, key: string, length: number) {
  if (!length || key === "Escape") return null
  if (key === "Home") return 0
  if (key === "End") return length - 1
  return Math.max(0, Math.min(length - 1, (current ?? (key === "ArrowLeft" ? length : -1)) + (key === "ArrowLeft" ? -1 : 1)))
}
export function linePath(values: (number | null)[], x: (i: number) => number, y: (v: number) => number, connectGaps = false) {
  let continuous = false
  return values.map((value, index) => {
    if (value === null) { if (!connectGaps) continuous = false; return "" }
    const part = `${continuous ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`
    continuous = true; return part
  }).join(" ")
}
export function ReportChart({ days, services, available, choose }: {
  days: { date: string; services: Record<string, { visibility_pct: number | null }> }[];
  services: string[]; available: string[]; choose: (services: string[]) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(800), [active, setActive] = useState<number | null>(null)
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(Math.max(300, entries[0].contentRect.width)))
    if (box.current) observer.observe(box.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => setActive(null), [days])
  const left = 42, right = width - 20, top = 17, bottom = 205
  const x = (i: number) => left + (days.length === 1 ? (right - left) / 2 : i * (right - left) / Math.max(1, days.length - 1))
  const y = (value: number) => bottom - value * (bottom - top) / 100
  const point = active === null ? null : days[active]
  const indexes = [...new Set([0, Math.floor((days.length - 1) / 2), days.length - 1])].filter(i => days[i])
  return <section className="panel"><div className="panel-head"><h2>Динамика упоминаемости</h2><span className="note">Доля ответов с брендом, %</span></div>
    <div className="legend">{available.map(id => <label key={id} style={{color:serviceColors[id]}}><input type="checkbox" checked={services.includes(id)} disabled={services.length === 1 && services.includes(id)} aria-label={`Показывать ${serviceName(id)}`} onChange={e => choose(e.target.checked ? [...services,id] : services.filter(s => s !== id))}/><ServiceMark id={id}/>{serviceName(id)}</label>)}</div>
    <div ref={box} className="chart-wrap"><svg className="line-chart" viewBox={`0 0 ${width} 240`} tabIndex={0} role="img" aria-label="Динамика по ИИ-системам. Стрелки выбирают день, Home и End — крайние даты, Escape скрывает значения."
      onMouseMove={e => { const rect = e.currentTarget.getBoundingClientRect(); const position = (e.clientX - rect.left) * width / rect.width; setActive(days.length ? Math.max(0,Math.min(days.length-1,Math.round((position-left)/(right-left)*(days.length-1)))) : null) }}
      onMouseLeave={() => setActive(null)} onFocus={() => setActive(days.length ? days.length - 1 : null)} onBlur={() => setActive(null)}
      onKeyDown={e => { if (["ArrowLeft","ArrowRight","Home","End","Escape"].includes(e.key)) { e.preventDefault(); setActive(index => chartIndex(index,e.key,days.length)) } }}>
      {[0,25,50,75,100].map(value => <g key={value}><line x1={left} y1={y(value)} x2={right} y2={y(value)} stroke="#e9edf3" strokeDasharray="3 3"/><text x={left-9} y={y(value)+3} textAnchor="end" fill="#748093" fontSize={10}>{value}%</text></g>)}
      {services.map(id => {
        const values = days.map(day => day.services[id]?.visibility_pct ?? null)
        return <g key={id} fill="none" stroke={serviceColors[id]} strokeWidth={id === "chatgpt" ? 2.8 : 2.2} strokeLinecap="round">
          <path d={linePath(values,x,y,true)} strokeDasharray="4 4" opacity={0.75}/>
          <path d={linePath(values,x,y)}/>
        </g>
      })}
      {indexes.map(i => <text key={i} x={x(i)} y={230} textAnchor="middle" fill="#748093" fontSize={10}>{shortDate(days[i].date)}</text>)}
      {point && active !== null && <g><line className="chart-crosshair" x1={x(active)} x2={x(active)} y1={top} y2={bottom}/>{services.map(id => point.services[id]?.visibility_pct == null ? null : <circle key={id} cx={x(active)} cy={y(point.services[id].visibility_pct!)} r={4} fill={serviceColors[id]} stroke="white" strokeWidth={2}/>)}</g>}
      {services.flatMap(id => days.map((day, i) => {
        const value = day.services[id]?.visibility_pct
        return value != null
          ? <circle key={`${id}-${i}`} cx={x(i)} cy={y(value)} r={3} fill={serviceColors[id]} stroke="white" strokeWidth={1}/> : null
      }))}
      {!days.some(day => services.some(id => day.services[id]?.visibility_pct != null)) && <text x={width/2} y={115} textAnchor="middle" fill="#748093" fontSize={12}>В этом периоде нет проверок</text>}
    </svg>{point && <div className="chart-tooltip" style={{display:"block",left:Math.max(8,Math.min(x(active!),width-250)),top:20}} aria-live="polite"><strong>{shortDate(point.date)}.{point.date.slice(0,4)}</strong>{services.map(id => <div className="tooltip-service" key={id}><ServiceMark id={id}/><span>{serviceName(id)}</span><b>{point.services[id]?.visibility_pct == null ? "нет данных" : `${point.services[id].visibility_pct}%`}</b></div>)}</div>}</div><div className="chart-note">Точки — дни с проверками, пунктир — промежутки без проверок. Наведите на график для значений; ← → для выбора дня с клавиатуры.</div>
  </section>
}
