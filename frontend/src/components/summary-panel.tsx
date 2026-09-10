/** Сводка над таблицей — одна плоская панель, как в Топвизоре.
 *
 * Сверху строка показателей через разделители, под ней таблица по ИИ-системам:
 * прошлый срез → текущий → изменение и мини-график. В режиме «Две даты» это
 * и есть сравнение: прошлый срез — первая дата периода, текущий — последняя.
 */

import type { ReactNode } from "react"

import { Delta, ServiceDot } from "@/components/bits"
import { dmy } from "@/lib/dates"
import { pct, plural, shortDate } from "@/lib/format"
import type { Overview } from "@/lib/types"
import { useApp } from "@/store/app-store"

export function SummaryPanel({
  overview,
  changes,
}: {
  overview: Overview
  changes: { gained: number; lost: number; comparable: boolean }
}) {
  const { serviceById } = useApp()
  const s = overview.summary
  if (!s) return null
  const compare = overview.selection.mode === "two"

  return (
    <section className="bg-card rounded-md border">
      <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 border-b px-4 py-2 text-xs">
        {compare && s.prev_date ? (
          <span>
            Сравнение <b className="text-foreground tnum">{dmy(s.prev_date)}</b> →{" "}
            <b className="text-foreground tnum">{dmy(s.date)}</b>
          </span>
        ) : (
          <span>
            Срез <b className="text-foreground tnum">{dmy(s.date)}</b>
            {s.prev_date ? (
              <>
                {" "}
                · изменения к <span className="tnum">{dmy(s.prev_date)}</span>
              </>
            ) : (
              " · первый срез, сравнивать не с чем"
            )}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 divide-x divide-y md:grid-cols-4 md:divide-y-0">
        <Metric label="Видимость бренда">
          <span className="tnum text-[26px] leading-none font-semibold">
            {pct(s.total.pct)}
            <span className="text-muted-foreground text-base font-normal">%</span>
          </span>
          <Delta value={s.total.delta} />
        </Metric>
        <Metric label="Упоминаний">
          <span className="tnum text-[26px] leading-none font-semibold">{s.total.found}</span>
          <span className="text-muted-foreground tnum text-xs">
            из {s.total.checked} {plural(s.total.checked, "проверки", "проверок", "проверок")} ·{" "}
            {s.queries} {plural(s.queries, "запрос", "запроса", "запросов")}
          </span>
        </Metric>
        <Metric label="Изменения">
          {changes.comparable ? (
            <span className="tnum flex items-baseline gap-3 text-[22px] leading-none font-semibold">
              <span style={{ color: "var(--ok)" }} title="упоминание появилось">
                +{changes.gained}
              </span>
              <span style={{ color: "var(--bad)" }} title="упоминание пропало">
                −{changes.lost}
              </span>
            </span>
          ) : (
            <span className="text-muted-foreground text-[22px] leading-none">—</span>
          )}
          <span className="text-muted-foreground text-xs">появилось / пропало</span>
        </Metric>
        <Metric label="Требуют внимания">
          <span className="tnum text-[26px] leading-none font-semibold">
            {s.needs_review + s.errors}
          </span>
          <span className="text-muted-foreground tnum text-xs">
            {s.needs_review} на проверку · {s.errors} {plural(s.errors, "сбой", "сбоя", "сбоев")}
            {s.not_checked ? ` · ${s.not_checked} не проверено` : ""}
          </span>
        </Metric>
      </div>

      {s.by_service.length ? (
        <div className="overflow-x-auto border-t">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-muted-foreground bg-muted/60 text-[11px]">
                <th scope="col" className="px-4 py-1.5 text-left font-medium">
                  ИИ-система
                </th>
                {s.prev_date ? (
                  <th scope="col" className="tnum px-3 py-1.5 text-right font-medium">
                    {shortDate(s.prev_date)}
                  </th>
                ) : null}
                <th scope="col" className="tnum px-3 py-1.5 text-right font-medium">
                  {shortDate(s.date)}
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  Δ
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  Упоминаний
                </th>
                {!compare && overview.dates.length > 2 ? (
                  <th scope="col" className="px-4 py-1.5 text-right font-medium">
                    Динамика
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {s.by_service.map((svc) => {
                const meta = serviceById(svc.id)
                const before = s.prev_date ? overview.stats[s.prev_date]?.[svc.id]?.pct : null
                const series = overview.dates.map((d) => overview.stats[d]?.[svc.id]?.pct ?? null)
                return (
                  <tr key={svc.id} className="hover:bg-muted/40 border-t">
                    <th scope="row" className="px-4 py-1.5 text-left font-normal">
                      <span className="flex items-center gap-2">
                        <ServiceDot service={meta} />
                        {svc.name}
                      </span>
                    </th>
                    {s.prev_date ? (
                      <td className="tnum text-muted-foreground px-3 py-1.5 text-right">
                        {before === null || before === undefined ? "—" : `${pct(before)}%`}
                      </td>
                    ) : null}
                    <td className="tnum px-3 py-1.5 text-right font-semibold">
                      {svc.pct === null ? "—" : `${pct(svc.pct)}%`}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {svc.delta === null ? <span className="text-muted-foreground">—</span> : <Delta value={svc.delta} />}
                    </td>
                    <td className="tnum text-muted-foreground px-3 py-1.5 text-right">
                      <span className="text-foreground">{svc.found}</span> из {svc.checked}
                    </td>
                    {!compare && overview.dates.length > 2 ? (
                      <td className="px-4 py-1 text-right">
                        <Sparkline
                          values={series}
                          color={meta ? `var(${meta.color})` : "var(--muted-foreground)"}
                          label={svc.name}
                        />
                      </td>
                    ) : null}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}

function Metric({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 px-4 py-3">
      <span className="text-muted-foreground text-xs">{label}</span>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">{children}</div>
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
  if (values.filter((v) => v !== null).length < 2) {
    return <span className="text-muted-foreground text-xs">—</span>
  }
  const w = 96
  const h = 22
  const step = w / (values.length - 1)
  const y = (v: number) => h - 1 - (v / 100) * (h - 2)

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

  return (
    <svg
      width={w}
      height={h}
      viewBox={`-1 -1 ${w + 2} ${h + 2}`}
      className="ml-auto block"
      role="img"
      aria-label={`${label}: динамика видимости по срезам`}
    >
      {segments.map((pts, i) => (
        <polyline
          key={i}
          points={pts}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
    </svg>
  )
}
