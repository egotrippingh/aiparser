import type { Report } from "./report-view"
import { serviceIconUrl, serviceName } from "./service-mark"

export const reportInk = "#242E3D"
export const reportNavy = "#153D75"
export const reportMuted = "#586578"
export const reportLine = "#E4E8ED"
export const reportTint = "#F5F7FA"
export const reportWarm = "#FFF0E9"
export const reportAccent = "#F25C37"
const green = "#207657"
const red = "#BE483F"
const percent = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 })
export const reportPercent = (value: number | null) => value === null ? "—" : `${percent.format(value)}%`
const reportDate = (iso: string) => iso.split("-").reverse().join(".")
const clean = (value: string) => value.replace(/[\s\p{Cc}\p{Cs}\uFFFE\uFFFF]+/gu, " ").trim()

type ReportFilters = { compare: boolean; group: string; search: string; cards: boolean; external: boolean; dateMode: string }
type Input = Pick<Report, "date_from" | "date_to" | "dates" | "period_from" | "period_to" | "services" | "summary" | "rows" | "service_stats">

export function clientReport(project: string, report: Input, filters: ReportFilters) {
  const from = filters.compare ? report.date_from : report.period_from
  const to = filters.compare ? report.date_to : report.period_to
  const comparison = from && to && from !== to ? [reportDate(from), reportDate(to)] as const : null
  const { checked, found, skipped, issues, total, visibility_pct } = report.summary
  const outcomes = [
    { label: "С упоминанием", value: found, color: reportAccent },
    { label: "Без упоминания", value: checked - found - skipped, color: "#8390A0" },
    { label: "Без ИИ-блока", value: skipped, color: "#BECADA" },
    { label: "Ошибки", value: issues, color: red },
    { label: "Без результата", value: total - checked - issues, color: reportLine },
  ]
  const services = report.services.map(id => ({
    label: serviceName(id), value: report.service_stats[id].current.visibility_pct, icon: serviceIconUrl(id),
  }))
  let unchanged = 0, unavailable = 0
  const changes = report.rows.flatMap(row => {
    const { current, previous, delta } = filters.compare ? row.trend : row.period_trend
    if (!comparison || delta === null || !current.total || !previous.total ||
      current.checked !== current.total || previous.checked !== previous.total) {
      unavailable++
      return []
    }
    if (delta === 0) {
      unchanged++
      return []
    }
    return [{ query: clean(row.text), group: clean(row.group_tag), from: previous.visibility_pct, to: current.visibility_pct, delta }]
  })
  const increased = changes.filter(row => row.delta > 0).sort((a, b) => b.delta - a.delta)
  const decreased = changes.filter(row => row.delta < 0).sort((a, b) => a.delta - b.delta)
  const period = report.date_from === report.date_to ? reportDate(report.date_from) :
    `${reportDate(report.date_from)} — ${reportDate(report.date_to)}`
  const filterNotes = [
    filters.group !== "*" && `Группа: ${clean(filters.group) || "Без группы"}`,
    filters.search.trim() && `Поиск: «${clean(filters.search)}»`,
    !filters.cards && "Карточки товаров исключены",
    !filters.external && "Учитываются упоминания со ссылкой на домен бренда",
  ].filter(Boolean).join(" · ")
  const mode = filters.compare ? `Сравнение двух дат. Сводка за ${reportDate(report.date_to)}` : filters.dateMode
  return {
    project: clean(project), period, mode, filterNotes, comparison, outcomes, services, total,
    dates: report.dates.map(reportDate),
    metrics: [
      { label: "Упоминаемость", value: reportPercent(visibility_pct) },
      { label: "Ответы с упоминанием", value: `${found} / ${total}` },
      { label: "Запросов в отчёте", value: String(report.rows.length) },
    ],
    changeSummary: comparison
      ? `Рост — ${increased.length} · Снижение — ${decreased.length} · Без изменений — ${unchanged} · Недостаточно данных — ${unavailable}`
      : report.rows.length ? "Для сравнения нужны проверки за две разные даты." : "В выбранном периоде нет запросов.",
    tableHeaders: ["Группа", "Запрос", comparison?.[0] ?? "Было", comparison?.[1] ?? "Стало", "Изм., %"],
    tables: [
      { title: "Рост упоминаемости", empty: "Запросов с ростом нет.", color: green, rows: increased },
      { title: "Снижение упоминаемости", empty: "Запросов со снижением нет.", color: red, rows: decreased },
    ].map(table => ({
      ...table,
      rows: table.rows.map(row => [
        row.group || "Без группы", row.query, reportPercent(row.from), reportPercent(row.to),
        `${row.delta > 0 ? "+" : ""}${reportPercent(row.delta)}`,
      ]),
    })),
  }
}

export type ClientReport = ReturnType<typeof clientReport>
export const reportTitle = "Отчёт об упоминаемости в ИИ"
export const reportMethod = "Упоминаемость — доля ответов с упоминанием от всех возможных проверок в выбранных датах и ИИ-системах. В столбце «Изм., %» показана разница между значениями за две даты. Запросы сравниваются при наличии результатов по всем выбранным ИИ-системам на обе даты. Отсутствие ИИ-блока учитывается как результат без упоминания."
