/** Период графиков админ-финансов: даты и пресеты в Europe/Moscow. */

import { addDays, iso, monthStart, parse } from "./lib/dates"

export const MOSCOW_TZ = "Europe/Moscow"
export const MAX_SERIES_DAYS = 366

export type FinancePresetId = "7" | "30" | "90" | "month" | "custom"
export type SeriesGranularity = "day" | "week"

export type FinancePeriod = { from: string; to: string; preset: FinancePresetId }

const moscowParts = new Intl.DateTimeFormat("en-CA", {
  timeZone: MOSCOW_TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
})

/** Календарный день МСК в виде YYYY-MM-DD. */
export function moscowToday(now = new Date()): string {
  return moscowParts.format(now)
}

export function inclusiveDaySpan(from: string, to: string): number {
  return Math.round((parse(to).getTime() - parse(from).getTime()) / 86_400_000) + 1
}

export function isValidFinanceRange(from: string, to: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return false
  if (iso(parse(from)) !== from || iso(parse(to)) !== to) return false
  return from <= to && inclusiveDaySpan(from, to) <= MAX_SERIES_DAYS
}

export function financePresetRange(preset: Exclude<FinancePresetId, "custom">, today = moscowToday()): { from: string; to: string } {
  if (preset === "month") return { from: monthStart(today), to: today }
  const days = Number(preset)
  return { from: addDays(today, 1 - days), to: today }
}

export function defaultFinancePeriod(today = moscowToday()): FinancePeriod {
  const range = financePresetRange("30", today)
  return { ...range, preset: "30" }
}

export function matchFinancePreset(from: string, to: string, today = moscowToday()): FinancePresetId {
  for (const preset of ["7", "30", "90", "month"] as const) {
    const range = financePresetRange(preset, today)
    if (range.from === from && range.to === to) return preset
  }
  return "custom"
}

/** Для длинных периодов недельные точки читаемее дневных. */
export function seriesGranularity(from: string, to: string): SeriesGranularity {
  return inclusiveDaySpan(from, to) > 90 ? "week" : "day"
}

export function seriesQueryPath(period: Pick<FinancePeriod, "from" | "to">, rates = ""): string {
  const params = new URLSearchParams({
    from: period.from,
    to: period.to,
    granularity: seriesGranularity(period.from, period.to),
  })
  if (rates) {
    const extra = new URLSearchParams(rates)
    for (const [key, value] of extra) params.set(key, value)
  }
  return `/admin/dashboard/series?${params}`
}

export function shortFinanceDate(value: string): string {
  const [year, month, day] = value.split("-")
  return `${day}.${month}.${year.slice(2)}`
}

export function financeRangeLabel(from: string, to: string): string {
  return `${shortFinanceDate(from)} — ${shortFinanceDate(to)}`
}
