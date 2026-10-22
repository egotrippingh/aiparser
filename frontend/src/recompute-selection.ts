import { calendarDates, type ReportDateSelection } from "./report-calendar"
import { dmy } from "./lib/dates"

export type RecomputeSelection = { from_date: string; to_date: string | null; dates: string[] | null }

export function recomputeSelection(from: string, to: string, available: string[], selection: ReportDateSelection): RecomputeSelection {
  return {
    from_date: from,
    to_date: selection.mode === "from" ? null : selection.mode === "day" ? from : to,
    dates: ["custom","two","monthly"].includes(selection.mode) ? calendarDates(from,to,available,selection) : null,
  }
}

export function selectionLabel(selection: RecomputeSelection) {
  if (selection.dates) return selection.dates.map(dmy).join(", ")
  if (!selection.to_date) return `С ${dmy(selection.from_date)} включительно`
  if (selection.from_date === selection.to_date) return dmy(selection.from_date)
  return `${dmy(selection.from_date)} — ${dmy(selection.to_date)} включительно`
}
