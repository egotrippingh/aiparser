/** Изменения между срезами — «появилось / пропало», как дельты в Топвизоре.
 *
 * Изменением считается только переход между «найдено» и «не найдено».
 * Ошибка, капча или лимит тарифа — это отсутствие данных, а не смена
 * видимости: иначе каждый сбой проверки выглядел бы как потеря упоминания.
 */

import type { Cell, Overview, OverviewRow } from "./types"

export type Change = "gained" | "lost"

export function cellChange(prev: Cell | undefined, cur: Cell | undefined): Change | null {
  if (!prev || !cur) return null
  if (prev.status === "not_found" && cur.status === "found") return "gained"
  if (prev.status === "found" && cur.status === "not_found") return "lost"
  return null
}

export interface RowChanges {
  gained: number
  lost: number
  detail: { service: string; change: Change }[]
}

export function rowChanges(
  row: OverviewRow,
  date: string | null | undefined,
  prevDate: string | null | undefined,
  services: readonly string[],
): RowChanges {
  const out: RowChanges = { gained: 0, lost: 0, detail: [] }
  if (!date || !prevDate) return out
  for (const service of services) {
    const change = cellChange(row.cells[prevDate]?.[service], row.cells[date]?.[service])
    if (!change) continue
    out.detail.push({ service, change })
    if (change === "gained") out.gained += 1
    else out.lost += 1
  }
  return out
}

/** Сумма изменений по всему проекту между свежим и прошлым срезом. */
export function totalChanges(ov: Overview): { gained: number; lost: number; comparable: boolean } {
  const s = ov.summary
  if (!s?.prev_date) return { gained: 0, lost: 0, comparable: false }
  let gained = 0
  let lost = 0
  for (const r of ov.rows) {
    const c = rowChanges(r, s.date, s.prev_date, ov.services)
    gained += c.gained
    lost += c.lost
  }
  return { gained, lost, comparable: true }
}
