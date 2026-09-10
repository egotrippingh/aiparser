/** Дашборд: календарь периода, сводка, динамика по дням и таблица «как в Топвизоре». */

import { useMemo, useState } from "react"
import { AlertTriangle, Radar } from "lucide-react"
import { cn } from "cn"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, Panel, PanelHead } from "@/components/bits"
import { CalendarPicker } from "@/components/calendar-picker"
import { OverviewTable } from "@/components/overview-table"
import { QuerySheet, type QueryTarget } from "@/components/query-sheet"
import { SummaryPanel } from "@/components/summary-panel"
import { VisibilityChart } from "@/components/visibility-chart"
import { useResource } from "@/hooks/use-resource"
import { api } from "@/lib/api"
import { DEFAULT_CALENDAR, calendarParams, type CalendarValue } from "@/lib/calendar"
import { totalChanges } from "@/lib/changes"
import type { Overview, ScanDate } from "@/lib/types"
import { useApp } from "@/store/app-store"
import type { View } from "@/hooks/use-hash-route"

const CAL_KEY = "aimt.calendar."

/** Выбор календаря помнится по проекту: открыл завтра — тот же период. */
function loadCalendar(projectId: number): CalendarValue {
  try {
    const raw = localStorage.getItem(CAL_KEY + projectId)
    if (raw) return { ...DEFAULT_CALENDAR, ...(JSON.parse(raw) as Partial<CalendarValue>) }
  } catch {
    /* повреждённая запись — просто начинаем с умолчаний */
  }
  return DEFAULT_CALENDAR
}

export function DashboardScreen({ onView }: { onView: (v: View) => void }) {
  const { projectId, dataVersion } = useApp()
  const [target, setTarget] = useState<QueryTarget | null>(null)
  const [calendars, setCalendars] = useState<Record<number, CalendarValue>>({})

  const calendar = projectId ? (calendars[projectId] ?? loadCalendar(projectId)) : DEFAULT_CALENDAR
  const params = calendarParams(calendar).toString()

  function setCalendar(v: CalendarValue) {
    if (!projectId) return
    setCalendars((prev) => ({ ...prev, [projectId]: v }))
    try {
      localStorage.setItem(CAL_KEY + projectId, JSON.stringify(v))
    } catch {
      /* без localStorage период просто не запомнится */
    }
  }

  const { data: scanDates } = useResource<{ dates: ScanDate[] }>(
    projectId ? () => api.get(`/api/projects/${projectId}/scan-dates`) : null,
    [projectId, dataVersion],
  )
  const { data, error, loading } = useResource<Overview>(
    projectId ? () => api.get<Overview>(`/api/projects/${projectId}/overview?${params}`) : null,
    [projectId, params, dataVersion],
  )

  const changes = useMemo(() => (data ? totalChanges(data) : null), [data])

  if (error) {
    return (
      <Panel>
        <EmptyState icon={<AlertTriangle />} title="Не удалось загрузить данные" text={error} />
      </Panel>
    )
  }

  if (loading && !data) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-80" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    )
  }

  const hasScans = Boolean(data?.selection.last_scan)

  if (!data || !hasScans) {
    return (
      <Panel>
        <EmptyState
          icon={<Radar />}
          title="По проекту ещё не было ни одного скана"
          text="Добавьте запросы и запустите первую проверку."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button size="sm" onClick={() => onView("queries")}>
                Добавить запросы
              </Button>
              <Button size="sm" variant="outline" onClick={() => onView("scan")}>
                Перейти к скану
              </Button>
            </div>
          }
        />
      </Panel>
    )
  }

  const compare = calendar.mode === "two"
  const toolbar = (
    <div className="flex flex-wrap items-center gap-2">
      <CalendarPicker value={calendar} onChange={setCalendar} scanDates={scanDates?.dates ?? []} />
      <div className="flex rounded border" role="radiogroup" aria-label="Вид отчёта">
        {[
          { id: "dynamics", label: "Динамика", on: !compare },
          { id: "compare", label: "Сравнение", on: compare },
        ].map((b) => (
          <button
            key={b.id}
            type="button"
            role="radio"
            aria-checked={b.on}
            onClick={() =>
              setCalendar({
                ...calendar,
                mode: b.id === "compare" ? "two" : calendar.mode === "two" ? "period" : calendar.mode,
              })
            }
            className={cn(
              "h-7 cursor-pointer px-3 text-xs transition-colors first:rounded-l last:rounded-r",
              "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
              b.on ? "bg-foreground text-background" : "hover:bg-muted",
            )}
            title={
              b.id === "compare"
                ? "Сравнить первую и последнюю проверку выбранного периода"
                : "Все проверки периода"
            }
          >
            {b.label}
          </button>
        ))}
      </div>
      {data.selection.truncated ? (
        <span className="text-muted-foreground text-xs">
          Показаны последние {data.dates.length} из {data.selection.available} проверок — сузьте период
          или выберите «Последний день месяца»
        </span>
      ) : null}
      {loading ? <span className="text-muted-foreground text-xs">обновляется…</span> : null}
    </div>
  )

  if (!data.summary) {
    return (
      <div className="space-y-3">
        {toolbar}
        <Panel>
          <EmptyState
            icon={<Radar />}
            title="За выбранный период проверок нет"
            text="Выберите другие даты в календаре — дни с проверками в нём подсвечены."
            action={
              <Button size="sm" variant="outline" onClick={() => setCalendar(DEFAULT_CALENDAR)}>
                Показать последние 30 проверок
              </Button>
            }
          />
        </Panel>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {toolbar}

      <SummaryPanel overview={data} changes={changes ?? { gained: 0, lost: 0, comparable: false }} />

      {!compare ? (
        <Panel>
          <PanelHead title="Динамика видимости" hint="доля запросов, где бренд упомянут" />
          <VisibilityChart overview={data} />
        </Panel>
      ) : null}

      <Panel>
        <OverviewTable overview={data} onOpen={setTarget} />
      </Panel>

      <QuerySheet target={target} onClose={() => setTarget(null)} />
    </div>
  )
}
