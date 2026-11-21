import { useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent } from "react"
import { ServiceMark, serviceColors, serviceName } from "./service-mark"
import { shortDate } from "./report-calendar"

const chartColor = (id: string) => `var(--report-series-${id}, ${serviceColors[id]})`

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

export function chartTooltipPosition(x: number, y: number, width: number, height: number, tipWidth: number, tipHeight: number) {
  const inset = 8, gap = 12
  const clamp = (value: number, available: number) => Math.max(inset, Math.min(value, available - inset))
  const left = x + gap + tipWidth <= width - inset ? x + gap : x - gap - tipWidth
  const top = y - tipHeight / 2
  return { left: clamp(left, width - tipWidth), top: clamp(top, height - tipHeight) }
}

export function ReportChart({ days, services, available, choose }: {
  days: ChartDay[];
  services: string[]; available: string[]; choose: (services: string[]) => void
}) {
  // Timeline also contains calendar placeholders. Keep every real scan, including
  // absent AI blocks (0%) and failures (no percentage), but not an invented date.
  const chart = useMemo(() => chartDays(days), [days])
  const box = useRef<HTMLDivElement>(null)
  const plot = useRef<SVGSVGElement>(null), tooltip = useRef<HTMLDivElement>(null)
  const [viewportWidth, setViewportWidth] = useState(800)
  const [active, setActive] = useState<{ index: number; service?: string } | null>(null)
  const width = Math.max(300, viewportWidth)
  useEffect(() => {
    const observer = new ResizeObserver(entries => setViewportWidth(entries[0].contentRect.width))
    if (box.current) observer.observe(box.current)
    return () => observer.disconnect()
  }, [])
  const dateKey = chart.map(day => day.date).join(",")
  useEffect(() => setActive(null), [dateKey])
  const left = 42, right = width - 20, top = 17, bottom = 205
  const x = (i: number) => left + (chart.length === 1 ? (right - left) / 2 : i * (right - left) / Math.max(1, chart.length - 1))
  const y = (value: number) => bottom - value * (bottom - top) / 100
  const point = active && chart[active.index]
  const selectedService = active?.service && services.includes(active.service)
    ? active.service
    : services.find(service => point?.services[service]?.visibility_pct != null)
  const value = selectedService && point ? point.services[selectedService]?.visibility_pct : null
  const anchorX = active ? x(active.index) : 0
  const anchorY = value == null ? (top + bottom) / 2 : y(value)
  useLayoutEffect(() => {
    const svg = plot.current, tip = tooltip.current, wrapper = box.current
    const matrix = svg?.getScreenCTM()
    if (!svg || !tip || !wrapper || !matrix) return
    const bounds = svg.getBoundingClientRect(), origin = wrapper.getBoundingClientRect()
    const anchor = new DOMPoint(anchorX, anchorY).matrixTransform(matrix)
    tip.style.maxWidth = `${Math.max(0, bounds.width - 16)}px`
    const pos = chartTooltipPosition(anchor.x - bounds.left, anchor.y - bounds.top,
      bounds.width, bounds.height, tip.offsetWidth, tip.offsetHeight)
    tip.style.transform = `translate(${bounds.left - origin.left + pos.left}px, ${bounds.top - origin.top + pos.top}px)`
  }, [anchorX, anchorY, point, services, viewportWidth])

  function followPointer(event: MouseEvent<SVGSVGElement>) {
    if (!chart.length) return
    const matrix = event.currentTarget.getScreenCTM()
    if (!matrix) return
    const cursor = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    const index = Math.max(0, Math.min(chart.length - 1, Math.round((cursor.x - left) / (right - left) * (chart.length - 1))))
    let service: string | undefined, distance = Infinity
    for (const id of services) {
      const value = chart[index].services[id]?.visibility_pct
      if (value == null) continue
      const next = Math.abs(cursor.y - y(value))
      if (next < distance) { service = id; distance = next }
    }
    setActive(current => current?.index === index && current.service === service ? current : { index, service })
  }
  const indexes = [...new Set([0, Math.floor((chart.length - 1) / 2), chart.length - 1])].filter(i => chart[i])
  return <section className="panel"><div className="panel-head"><h2>Динамика упоминаемости</h2><span className="note">Доля возможных упоминаний, %</span></div>
    <div className="legend">{available.map(id => <button type="button" key={id} style={{color:chartColor(id)}} aria-pressed={services.includes(id)} disabled={services.length === 1 && services.includes(id)} title={services.length === 1 && services.includes(id) ? "В отчёте должна оставаться хотя бы одна система" : undefined} aria-label={`Показывать ${serviceName(id)}`} onClick={() => choose(services.includes(id) ? services.filter(s => s !== id) : [...services,id])}><ServiceMark id={id}/>{serviceName(id)}</button>)}</div>
    <div ref={box} className="chart-wrap"><svg ref={plot} className="line-chart" viewBox={`0 0 ${width} 240`} tabIndex={0} role="img" aria-label="Динамика по ИИ-системам. Стрелки выбирают день, Home и End — крайние даты, Escape скрывает значения."
      onMouseMove={followPointer}
      onMouseLeave={() => setActive(null)} onFocus={() => setActive(chart.length ? { index: chart.length - 1 } : null)} onBlur={() => setActive(null)}
      onKeyDown={e => { if (["ArrowLeft","ArrowRight","Home","End","Escape"].includes(e.key)) { e.preventDefault(); const key = e.key; setActive(current => { const index = chartIndex(current?.index ?? null,key,chart.length); return index === null ? null : { index } }) } }}>
      {[0,25,50,75,100].map(value => <g key={value}><line x1={left} y1={y(value)} x2={right} y2={y(value)} stroke="#e9edf3" strokeDasharray="3 3"/><text x={left-9} y={y(value)+3} textAnchor="end" fill="#748093" fontSize={10}>{value}%</text></g>)}
      {services.map(id => {
        const values = chart.map(day => day.services[id]?.visibility_pct ?? null)
        return <g key={id} fill="none" stroke={chartColor(id)} strokeWidth={id === "chatgpt" ? 2.8 : 2.2} strokeLinecap="round">
          <path d={linePath(values,x,y)}/>
        </g>
      })}
      {indexes.map(i => <text key={i} x={x(i)} y={230} textAnchor="middle" fill="#748093" fontSize={10}>{shortDate(chart[i].date)}</text>)}
      {point && <g><line className="chart-crosshair" x1={anchorX} x2={anchorX} y1={top} y2={bottom}/>{services.map(id => point.services[id]?.visibility_pct == null ? null : <circle key={id} cx={anchorX} cy={y(point.services[id].visibility_pct!)} r={4} fill={chartColor(id)} stroke="white" strokeWidth={2}/>)}</g>}
      {services.flatMap(id => chart.map((day, i) => {
        const value = day.services[id]?.visibility_pct
        return value != null
          ? <circle key={`${id}-${i}`} cx={x(i)} cy={y(value)} r={3} fill={chartColor(id)} stroke="white" strokeWidth={1}/> : null
      }))}
      {!chart.length && <text x={width/2} y={115} textAnchor="middle" fill="#748093" fontSize={12}>В этом периоде нет проверок</text>}
    </svg>{point && <div ref={tooltip} className="chart-tooltip" aria-live="polite"><strong>{shortDate(point.date)}.{point.date.slice(0,4)}</strong>{services.map(id => <div className="tooltip-service" key={id}><ServiceMark id={id}/><span>{serviceName(id)}</span><b>{point.services[id]?.visibility_pct == null ? "нет данных" : `${point.services[id].visibility_pct}%`}</b></div>)}</div>}</div><div className="chart-note">Точки — дни с проверками. Наведите на график для значений; ← → для выбора дня с клавиатуры.</div>
  </section>
}
