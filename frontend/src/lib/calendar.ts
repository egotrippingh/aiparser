/** Логика календаря периода — по образцу Топвизора.
 *
 * Выбирается не просто диапазон, а набор проверок, которые попадут в таблицу
 * и графики:
 *   «Период»                — все проверки за диапазон;
 *   «Две даты»              — первая и последняя проверка диапазона, сравнение;
 *   «Последний день месяца» — по одной проверке на месяц, динамика месяц к месяцу;
 *   «Выбранные даты»        — отмеченные вручную проверки.
 * selectedChecks повторяет select_dates из app/api/results.py: календарь
 * заранее говорит, сколько проверок попадёт в отчёт, и цифра обязана
 * совпасть с таблицей.
 */

import { dmy } from "./dates"
import { plural } from "./format"
import type { CalendarMode } from "./types"

export interface CalendarValue {
  mode: CalendarMode
  /** null — без границы: без диапазона берутся последние 30 проверок. */
  from: string | null
  to: string | null
  /** Для режима «Выбранные даты». */
  picked: string[]
}

export const DEFAULT_CALENDAR: CalendarValue = { mode: "period", from: null, to: null, picked: [] }

/** Больше столбцов дат таблица не показывает — как и Топвизор. */
export const MAX_DATES = 30

export const CALENDAR_MODES: { id: CalendarMode; label: string; hint: string }[] = [
  { id: "period", label: "Период", hint: "все проверки за диапазон" },
  { id: "two", label: "Две даты", hint: "первая и последняя проверка диапазона — сравнение" },
  { id: "monthly", label: "Последний день месяца", hint: "по одной проверке на месяц" },
  { id: "custom", label: "Выбранные даты", hint: "отметьте проверки в календаре" },
]

export function selectedChecks(v: CalendarValue, all: string[]): string[] {
  if (v.mode === "custom") return all.filter((d) => v.picked.includes(d))
  // Без диапазона «Период» — последние 30 проверок, а сравнение и помесячная
  // динамика — за всё время: первая против последней, по проверке на месяц.
  const inRange =
    v.from || v.to
      ? all.filter((d) => (!v.from || d >= v.from) && (!v.to || d <= v.to))
      : v.mode === "period"
        ? all.slice(-MAX_DATES)
        : all
  if (v.mode === "two") return inRange.length > 2 ? [inRange[0], inRange[inRange.length - 1]] : inRange
  if (v.mode === "monthly") {
    const last = new Map<string, string>()
    for (const d of inRange) last.set(d.slice(0, 7), d)
    return [...last.values()]
  }
  return inRange
}

export function calendarLabel(v: CalendarValue): string {
  const mode = CALENDAR_MODES.find((m) => m.id === v.mode)?.label ?? ""
  if (v.mode === "custom") {
    const n = v.picked.length
    return `${mode}: ${n} ${plural(n, "дата", "даты", "дат")}`
  }
  if (!v.from && !v.to) {
    if (v.mode === "two") return "Две даты: первая и последняя проверка"
    if (v.mode === "monthly") return `${mode} · всё время`
    return "Последние 30 проверок"
  }
  const range = `${v.from ? dmy(v.from) : "…"} – ${v.to ? dmy(v.to) : "…"}`
  return v.mode === "period" ? range : `${mode} · ${range}`
}

/** Параметры запроса к /overview. */
export function calendarParams(v: CalendarValue): URLSearchParams {
  const p = new URLSearchParams({ mode: v.mode })
  if (v.mode === "custom") {
    p.set("dates", v.picked.join(","))
  } else {
    if (v.from) p.set("date_from", v.from)
    if (v.to) p.set("date_to", v.to)
  }
  return p
}
