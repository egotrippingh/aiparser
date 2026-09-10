/** Видимость по каждой ИИ-системе: сколько упоминаний, доля, изменение и
 *  мини-график по срезам — сравнить системы между собой одним взглядом. */

import { motion, useReducedMotion } from "motion/react"

import { Delta, ServiceDot } from "@/components/bits"
import { longDate, pct, plural } from "@/lib/format"
import type { Overview } from "@/lib/types"
import { useApp } from "@/store/app-store"

export function ServiceCards({ overview }: { overview: Overview }) {
  const { serviceById } = useApp()
  const reduce = useReducedMotion()
  const s = overview.summary
  if (!s || !s.by_service.length) return null

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {s.by_service.map((svc, i) => {
        const meta = serviceById(svc.id)
        const series = overview.dates.map((d) => overview.stats[d]?.[svc.id]?.pct ?? null)
        return (
          <motion.div
            key={svc.id}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, delay: reduce ? 0 : 0.12 + i * 0.05, ease: "easeOut" }}
            className="bg-card flex items-end gap-3 rounded-xl border p-3.5 shadow-[0_1px_2px_rgb(15_23_42/0.04)]"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 text-[12px] font-semibold">
                <ServiceDot service={meta} className="size-2.5" />
                {svc.name}
              </div>
              <div className="tnum mt-1.5 text-2xl leading-none font-semibold tracking-tight">
                {pct(svc.pct)}
                <span className="text-muted-foreground text-sm font-normal">%</span>
              </div>
              <div className="text-muted-foreground mt-2 text-xs">
                <b className="tnum text-foreground font-semibold">{svc.found}</b> из{" "}
                <span className="tnum">{svc.checked}</span>{" "}
                {plural(svc.found, "упоминание", "упоминания", "упоминаний")}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs">
                {s.prev_date ? (
                  <>
                    <Delta value={svc.delta} />
                    {svc.delta === null ? (
                      <span className="text-muted-foreground">нет данных за {longDate(s.prev_date)}</span>
                    ) : (
                      <span className="text-muted-foreground">к {longDate(s.prev_date)}</span>
                    )}
                  </>
                ) : (
                  <span className="text-muted-foreground">первый срез</span>
                )}
              </div>
            </div>
            <Sparkline values={series} color={meta ? `var(${meta.color})` : "var(--muted-foreground)"} label={svc.name} />
          </motion.div>
        )
      })}
    </div>
  )
}

/** Мини-график 0–100%. Пропуски (сервис в тот день не проверялся) разрывают
 *  линию, а не рисуются нулём — ноль означал бы «бренда нет». */
function Sparkline({
  values,
  color,
  label,
}: {
  values: (number | null)[]
  color: string
  label: string
}) {
  const points = values.filter((v) => v !== null).length
  if (points < 2) return null

  const w = 72
  const h = 32
  const step = values.length > 1 ? w / (values.length - 1) : 0
  const y = (v: number) => h - 2 - (v / 100) * (h - 4)

  const segments: string[] = []
  let current: string[] = []
  values.forEach((v, i) => {
    if (v === null) {
      if (current.length > 1) segments.push(current.join(" "))
      current = []
      return
    }
    current.push(`${(i * step).toFixed(1)},${y(v).toFixed(1)}`)
  })
  if (current.length > 1) segments.push(current.join(" "))

  const lastIdx = values.length - 1 - [...values].reverse().findIndex((v) => v !== null)
  const last = values[lastIdx] as number

  return (
    <svg
      width={w}
      height={h}
      viewBox={`-2 -2 ${w + 4} ${h + 4}`}
      className="shrink-0"
      role="img"
      aria-label={`${label}: динамика видимости по срезам`}
    >
      <line x1={0} x2={w} y1={y(0)} y2={y(0)} stroke="var(--border)" strokeWidth={1} />
      {segments.map((pts, i) => (
        <polyline
          key={i}
          points={pts}
          fill="none"
          stroke={color}
          strokeWidth={1.75}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
      <circle cx={lastIdx * step} cy={y(last)} r={2.5} fill={color} />
    </svg>
  )
}
