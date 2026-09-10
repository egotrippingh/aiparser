/** Календарь периода — по образцу Топвизора. Логика выбора — в lib/calendar.ts.
 *
 * Дни с проверками подсвечены. Правка идёт в черновике и применяется кнопкой —
 * иначе каждый клик по дню перезагружал бы дашборд.
 */

import { useMemo, useState } from "react"
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react"
import { cn } from "cn"

import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
  CALENDAR_MODES,
  MAX_DATES,
  calendarLabel,
  selectedChecks,
  type CalendarValue,
} from "@/lib/calendar"
import { addDays, dmy, monthGrid, monthStart, monthTitle, parse, today } from "@/lib/dates"
import { plural } from "@/lib/format"
import type { ScanDate } from "@/lib/types"

const WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

function presets(first: string | null): { label: string; from: string | null; to: string | null }[] {
  const t = today()
  const prevMonthDay = addDays(monthStart(t), -1)
  return [
    { label: "Неделя", from: addDays(t, -6), to: t },
    { label: "Месяц", from: addDays(t, -29), to: t },
    { label: "Этот месяц", from: monthStart(t), to: t },
    { label: "Прошлый месяц", from: monthStart(prevMonthDay), to: prevMonthDay },
    { label: "Квартал", from: addDays(t, -89), to: t },
    { label: "Год", from: addDays(t, -364), to: t },
    { label: "Всё время", from: first, to: t },
  ]
}

export function CalendarPicker({
  value,
  onChange,
  scanDates,
}: {
  value: CalendarValue
  onChange: (v: CalendarValue) => void
  scanDates: ScanDate[]
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<CalendarValue>(value)
  // Первый клик ставит начало диапазона, второй — конец.
  const [anchor, setAnchor] = useState<string | null>(null)
  const all = useMemo(() => scanDates.map((d) => d.date), [scanDates])
  const checksOn = useMemo(() => new Map(scanDates.map((d) => [d.date, d.checks])), [scanDates])

  const lastScan = all.at(-1) ?? today()
  const [view, setView] = useState(() => {
    const d = parse(value.to ?? lastScan)
    return { y: d.getFullYear(), m: d.getMonth() }
  })

  function openChange(next: boolean) {
    if (next) {
      setDraft(value)
      setAnchor(null)
      // Правый месяц — месяц конца периода, левый — предыдущий.
      const d = parse(value.to ?? lastScan)
      setView({ y: d.getFullYear(), m: d.getMonth() })
    }
    setOpen(next)
  }

  function shift(n: number) {
    setView((v) => {
      const d = new Date(v.y, v.m + n, 1)
      return { y: d.getFullYear(), m: d.getMonth() }
    })
  }

  function clickDay(d: string) {
    if (draft.mode === "custom") {
      if (!checksOn.has(d)) return
      setDraft((v) => ({
        ...v,
        picked: v.picked.includes(d) ? v.picked.filter((x) => x !== d) : [...v.picked, d].sort(),
      }))
      return
    }
    if (!anchor) {
      setAnchor(d)
      setDraft((v) => ({ ...v, from: d, to: d }))
    } else {
      const [a, b] = anchor <= d ? [anchor, d] : [d, anchor]
      setAnchor(null)
      setDraft((v) => ({ ...v, from: a, to: b }))
    }
  }

  const chosen = selectedChecks(draft, all)
  const chosenSet = new Set(chosen)
  const months = [new Date(view.y, view.m - 1, 1), new Date(view.y, view.m, 1)]
  const canApply = draft.mode === "custom" ? draft.picked.length > 0 : true

  return (
    <Popover open={open} onOpenChange={openChange}>
      <PopoverTrigger
        render={
          <Button variant="outline" size="sm" className="tnum gap-1.5 font-normal">
            <CalendarDays />
            {calendarLabel(value)}
          </Button>
        }
      />
      <PopoverContent align="start" className="w-[min(40rem,calc(100vw-2rem))] gap-0 p-0">
        <div className="flex flex-wrap gap-1 border-b p-2" role="radiogroup" aria-label="Какие проверки показывать">
          {CALENDAR_MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={draft.mode === m.id}
              title={m.hint}
              onClick={() => setDraft((v) => ({ ...v, mode: m.id }))}
              className={cn(
                "h-7 cursor-pointer rounded border px-2.5 text-xs transition-colors",
                "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
                draft.mode === m.id
                  ? "border-foreground bg-foreground text-background"
                  : "hover:bg-muted text-foreground",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>

        {draft.mode !== "custom" ? (
          <div className="flex flex-wrap gap-x-3 gap-y-1 border-b px-3 py-2 text-xs">
            {presets(all[0] ?? null).map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => {
                  setAnchor(null)
                  setDraft((v) => ({ ...v, from: p.from, to: p.to }))
                  if (p.to) {
                    const d = parse(p.to)
                    setView({ y: d.getFullYear(), m: d.getMonth() })
                  }
                }}
                className="text-primary cursor-pointer hover:underline"
              >
                {p.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => {
                setAnchor(null)
                setDraft((v) => ({ ...v, from: null, to: null }))
              }}
              className="text-primary cursor-pointer hover:underline"
            >
              Последние 30 проверок
            </button>
          </div>
        ) : null}

        <div className="flex items-start gap-3 p-3">
          <Button variant="ghost" size="icon-sm" aria-label="Предыдущий месяц" onClick={() => shift(-1)}>
            <ChevronLeft />
          </Button>
          <div className="grid flex-1 gap-4 sm:grid-cols-2">
            {months.map((md, i) => (
              <Month
                key={i}
                year={md.getFullYear()}
                month={md.getMonth()}
                draft={draft}
                chosen={chosenSet}
                checksOn={checksOn}
                onDay={clickDay}
                className={i === 0 ? "hidden sm:block" : undefined}
              />
            ))}
          </div>
          <Button variant="ghost" size="icon-sm" aria-label="Следующий месяц" onClick={() => shift(1)}>
            <ChevronRight />
          </Button>
        </div>

        <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-2 border-t px-3 py-2 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="bg-primary size-1.5 rounded-full" aria-hidden="true" />
            была проверка
          </span>
          <span className="flex items-center gap-1.5">
            <span className="bg-foreground size-2.5 rounded-sm" aria-hidden="true" />
            попадёт в отчёт
          </span>
          <span className="tnum">
            {draft.mode !== "custom"
              ? `${draft.from ? dmy(draft.from) : "…"} – ${draft.to ? dmy(draft.to) : "…"} · `
              : ""}
            в отчёт: {Math.min(chosen.length, MAX_DATES)}{" "}
            {plural(Math.min(chosen.length, MAX_DATES), "проверка", "проверки", "проверок")}
            {chosen.length > MAX_DATES ? ` (из ${chosen.length}, показываются последние ${MAX_DATES})` : ""}
          </span>
          <div className="ml-auto flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button
              size="sm"
              disabled={!canApply}
              onClick={() => {
                onChange(draft)
                setOpen(false)
              }}
            >
              Применить
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function Month({
  year,
  month,
  draft,
  chosen,
  checksOn,
  onDay,
  className,
}: {
  year: number
  month: number
  draft: CalendarValue
  chosen: Set<string>
  checksOn: Map<string, number>
  onDay: (d: string) => void
  className?: string
}) {
  const cells = monthGrid(year, month)
  const t = today()
  const from = draft.mode === "custom" ? null : draft.from
  const to = draft.mode === "custom" ? null : draft.to

  return (
    <div className={className}>
      <div className="mb-1.5 text-center text-xs font-semibold capitalize">{monthTitle(year, month)}</div>
      <div className="grid grid-cols-7 text-center text-[10px]">
        {WEEKDAYS.map((w) => (
          <div key={w} className="text-muted-foreground py-1">
            {w}
          </div>
        ))}
        {cells.map((d, i) => {
          if (!d) return <div key={`e${i}`} />
          const checks = checksOn.get(d)
          const inRange = Boolean(from && to && d >= from && d <= to)
          const edge = d === from || d === to
          const isChosen = chosen.has(d)
          const disabled = draft.mode === "custom" && !checks
          const label = `${dmy(d)}${checks ? `, проверок: ${checks}` : ", проверок не было"}${isChosen ? ", попадёт в отчёт" : ""}`
          return (
            <button
              key={d}
              type="button"
              disabled={disabled}
              onClick={() => onDay(d)}
              aria-label={label}
              aria-pressed={isChosen}
              title={label}
              className={cn(
                "tnum relative h-7 cursor-pointer text-[12px] transition-colors",
                "focus-visible:ring-ring focus-visible:z-10 focus-visible:ring-2 focus-visible:outline-none",
                "disabled:cursor-default disabled:opacity-35",
                inRange && !edge && "bg-muted",
                edge && "bg-muted font-semibold",
                isChosen && "bg-foreground text-background font-semibold",
                !isChosen && !disabled && "hover:bg-accent",
                d === t && !isChosen && "underline underline-offset-2",
              )}
            >
              {Number(d.slice(8))}
              {checks && !isChosen ? (
                <span
                  aria-hidden="true"
                  className="bg-primary absolute bottom-0.5 left-1/2 size-1 -translate-x-1/2 rounded-full"
                />
              ) : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}
