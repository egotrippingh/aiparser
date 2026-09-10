/** Дашборд: сводка за свежий срез, динамика по дням и таблица «как в Топвизоре». */

import { useMemo, useState, type ReactNode } from "react"
import { motion, useReducedMotion } from "motion/react"
import { AlertTriangle, LineChart, Radar } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Delta, EmptyState, Panel, PanelHead } from "@/components/bits"
import { OverviewTable } from "@/components/overview-table"
import { QuerySheet, type QueryTarget } from "@/components/query-sheet"
import { ServiceCards } from "@/components/service-cards"
import { VisibilityChart } from "@/components/visibility-chart"
import { useResource } from "@/hooks/use-resource"
import { api } from "@/lib/api"
import { totalChanges } from "@/lib/changes"
import { longDate, pct, plural } from "@/lib/format"
import type { Overview } from "@/lib/types"
import { useApp } from "@/store/app-store"
import type { View } from "@/hooks/use-hash-route"

const PERIODS = [
  { days: 7, label: "7 дней" },
  { days: 14, label: "14 дней" },
  { days: 30, label: "30 дней" },
  { days: 90, label: "90 дней" },
]

export function DashboardScreen({ onView }: { onView: (v: View) => void }) {
  const { projectId, dataVersion } = useApp()
  const [days, setDays] = useState(30)
  const [target, setTarget] = useState<QueryTarget | null>(null)
  const reduce = useReducedMotion()

  const { data, error, loading } = useResource<Overview>(
    projectId
      ? () => api.get<Overview>(`/api/projects/${projectId}/overview?days=${days}`)
      : null,
    [projectId, days, dataVersion],
  )

  const changes = useMemo(() => (data ? totalChanges(data) : null), [data])

  if (error) {
    return (
      <Panel>
        <EmptyState
          icon={<AlertTriangle />}
          title="Не удалось загрузить данные"
          text={error}
        />
      </Panel>
    )
  }

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-72 rounded-xl" />
      </div>
    )
  }

  if (!data || !data.summary) {
    return (
      <Panel>
        <EmptyState
          icon={<Radar />}
          title="По проекту ещё не было ни одного скана"
          text="Добавьте запросы и запустите первую проверку — после неё здесь появятся видимость бренда, динамика по дням и таблица по срезам."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button onClick={() => onView("queries")}>Добавить запросы</Button>
              <Button variant="outline" onClick={() => onView("scan")}>
                Перейти к скану
              </Button>
            </div>
          }
        />
      </Panel>
    )
  }

  const s = data.summary
  const problems = s.errors + s.not_checked

  const cards: { key: string; label: string; value: ReactNode; unit: string; foot: ReactNode }[] = [
    {
      key: "vis",
      label: "Видимость бренда",
      value: pct(s.total.pct),
      unit: "%",
      foot: (
        <>
          <Delta value={s.total.delta} />
          <span className="text-muted-foreground">
            {s.prev_date ? `к ${longDate(s.prev_date)}` : "первый срез"}
          </span>
        </>
      ),
    },
    {
      key: "found",
      label: "Найдено упоминаний",
      value: String(s.total.found),
      unit: ` / ${s.total.checked}`,
      foot: (
        <span className="text-muted-foreground">
          {s.queries} {plural(s.queries, "запрос", "запроса", "запросов")} в срезе
        </span>
      ),
    },
    {
      // Как дельты в Топвизоре: сколько упоминаний появилось и сколько
      // пропало к прошлому срезу, по всем сервисам сразу.
      key: "changes",
      label: "Изменения к прошлому срезу",
      value: changes?.comparable ? (
        <span className="flex items-baseline gap-3">
          <span style={{ color: "var(--ok)" }} title="упоминание появилось">
            ▲{changes.gained}
          </span>
          <span style={{ color: "var(--bad)" }} title="упоминание пропало">
            ▼{changes.lost}
          </span>
        </span>
      ) : (
        "—"
      ),
      unit: "",
      foot: (
        <span className="text-muted-foreground">
          {changes?.comparable && s.prev_date
            ? `появилось / пропало к ${longDate(s.prev_date)}`
            : "первый срез — сравнивать не с чем"}
        </span>
      ),
    },
    {
      key: "review",
      label: "Требуют проверки",
      value: String(s.needs_review),
      unit: "",
      foot: (
        <span className="text-muted-foreground">
          {problems
            ? `${s.errors} ${plural(s.errors, "сбой", "сбоя", "сбоев")}${s.not_checked ? ` · ${s.not_checked} не проверено` : ""}`
            : "сбоев нет"}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map((c, i) => (
          <motion.div
            key={c.key}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, delay: reduce ? 0 : i * 0.04, ease: "easeOut" }}
            className="bg-card rounded-xl border p-3.5 shadow-[0_1px_2px_rgb(15_23_42/0.04)]"
          >
            <div className="text-muted-foreground flex items-center gap-1.5 text-[11px] font-medium">
              {c.label}
            </div>
            <div className="tnum mt-1.5 text-2xl leading-none font-semibold tracking-tight">
              {c.value}
              <span className="text-muted-foreground text-sm font-normal">{c.unit}</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-1.5 text-xs">{c.foot}</div>
          </motion.div>
        ))}
      </div>

      <ServiceCards overview={data} />

      <Panel>
        <PanelHead
          title="Динамика видимости"
          hint="доля запросов, где бренд упомянут"
        >
          <div className="flex gap-1" role="group" aria-label="Период">
            {PERIODS.map((p) => (
              <Button
                key={p.days}
                size="xs"
                variant={days === p.days ? "secondary" : "ghost"}
                aria-pressed={days === p.days}
                onClick={() => setDays(p.days)}
              >
                {p.label}
              </Button>
            ))}
          </div>
        </PanelHead>
        {data.dates.length ? (
          <VisibilityChart overview={data} />
        ) : (
          <EmptyState icon={<LineChart />} title="За период нет проверок" />
        )}
      </Panel>

      <Panel>
        <OverviewTable overview={data} onOpen={setTarget} />
      </Panel>

      <QuerySheet target={target} onClose={() => setTarget(null)} />
    </div>
  )
}
