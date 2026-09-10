/** Динамика видимости: доля запросов с упоминанием бренда по дням.
 *
 * Линия «Все сервисы» намеренно янтарная и толще остальных — это главный
 * показатель, а сервисы вокруг него объясняют, за счёт чего он изменился.
 */

import { useMemo, useState } from "react"
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { cn } from "cn"

import { EmptyState } from "@/components/bits"
import { longDate, shortDate } from "@/lib/format"
import type { Overview } from "@/lib/types"
import { useApp } from "@/store/app-store"

const TOTAL = "_all"

export function VisibilityChart({ overview }: { overview: Overview }) {
  const { services } = useApp()
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const shown = services.filter((s) => overview.services.includes(s.id))

  const data = useMemo(
    () =>
      overview.dates.map((d) => {
        const row: Record<string, string | number | null> = { date: d }
        row[TOTAL] = overview.stats[d]?.[TOTAL]?.pct ?? null
        for (const s of shown) row[s.id] = overview.stats[d]?.[s.id]?.pct ?? null
        return row
      }),
    [overview, shown],
  )

  const lines = [
    { id: TOTAL, name: "Все сервисы", color: "var(--c-total)", width: 2.5 },
    ...shown.map((s) => ({ id: s.id, name: s.name, color: `var(${s.color})`, width: 1.5 })),
  ]

  if (overview.dates.length < 2) {
    return (
      <EmptyState
        icon={<span className="text-lg">◔</span>}
        title="График появится после второго скана"
        text="Чтобы показать динамику, нужны минимум две даты проверок."
      />
    )
  }

  function toggle(id: string) {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="p-4">
      <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1.5">
        {lines.map((l) => {
          const off = hidden.has(l.id)
          return (
            <button
              key={l.id}
              type="button"
              onClick={() => toggle(l.id)}
              aria-pressed={!off}
              className={cn(
                "flex cursor-pointer items-center gap-1.5 rounded-md px-1.5 py-1 text-xs transition-opacity",
                "hover:bg-muted focus-visible:ring-ring focus-visible:ring-3 focus-visible:outline-none",
                off && "opacity-40",
              )}
            >
              <span
                aria-hidden="true"
                className="block h-0.5 w-3.5 rounded-full"
                style={{ background: l.color, height: l.id === TOTAL ? 3 : 2 }}
              />
              {l.name}
              <span className="sr-only">{off ? " — скрыт, показать" : " — показан, скрыть"}</span>
            </button>
          )
        })}
      </div>

      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={shortDate}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              minTickGap={16}
            />
            <YAxis
              domain={[0, 100]}
              unit="%"
              width={52}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={(props) => (
                <ChartTip {...(props as unknown as TipProps)} lines={lines} hidden={hidden} />
              )}
            />
            {lines
              .filter((l) => !hidden.has(l.id))
              .map((l) => (
                <Line
                  key={l.id}
                  type="monotone"
                  dataKey={l.id}
                  name={l.name}
                  stroke={l.color}
                  strokeWidth={l.width}
                  dot={false}
                  activeDot={{ r: 3.5, strokeWidth: 0 }}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/** Recharts отдаёт содержимому подсказки нетипизированный набор полей,
 *  поэтому описываем ровно то, что читаем. */
interface TipProps {
  active?: boolean
  label?: string | number
  payload?: readonly { dataKey?: string | number; value?: number | null }[]
}

function ChartTip({
  active,
  label,
  payload,
  lines,
  hidden,
}: TipProps & {
  lines: { id: string; name: string; color: string }[]
  hidden: Set<string>
}) {
  if (!active || !payload?.length) return null
  const byKey = new Map(payload.map((p) => [String(p.dataKey), p.value]))
  return (
    <div className="bg-popover text-popover-foreground rounded-lg border px-2.5 py-2 text-xs shadow-md">
      <div className="mb-1.5 font-semibold">{longDate(String(label))}</div>
      <div className="space-y-0.5">
        {lines
          .filter((l) => !hidden.has(l.id))
          .map((l) => {
            const v = byKey.get(l.id)
            return (
              <div key={l.id} className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="size-1.5 rounded-full"
                  style={{ background: l.color }}
                />
                <span className="text-muted-foreground mr-3">{l.name}</span>
                <span className="tnum ml-auto font-medium">
                  {v === null || v === undefined ? "—" : `${v}%`}
                </span>
              </div>
            )
          })}
      </div>
    </div>
  )
}
