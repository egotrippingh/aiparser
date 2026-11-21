import { expect, test } from "vitest"
import { clientReport } from "./client-report"
import type { Report, Trend } from "./report-view"

const settings = { compare: false, group: "*", search: "", cards: true, external: true, dateMode: "Выбранные даты" }
const stats = (found: number, checked = 2) => ({
  found, checked, total: 2, skipped: 0, issues: 0, visibility_pct: checked ? found * 50 : null,
})
const trend = (from: number, to: number, coverage = 2): Trend => ({
  previous: stats(from), current: stats(to, coverage), delta: (to - from) * 50,
  relative: null, baseline_complete: true, baseline_from: "2026-11-04", baseline_to: "2026-11-04",
})
const row = (text: string, period_trend: Trend, comparison = period_trend): Report["rows"][number] => ({
  id: text, text, group_tag: "", period_trend, trend: comparison, cells: {}, latest: {},
})

const report: Parameters<typeof clientReport>[1] = {
  date_from: "2026-11-01", date_to: "2026-11-20", dates: ["2026-11-04", "2026-11-19"],
  period_from: "2026-11-04", period_to: "2026-11-19",
  services: ["chatgpt", "gemini"], service_stats: { chatgpt: trend(1, 1), gemini: trend(2, 0) },
  summary: { total: 16, checked: 13, found: 6, skipped: 2, issues: 1, visibility_pct: 37.5 },
  rows: [
    row("Малый рост", trend(0, 1)),
    row("Снижение", trend(2, 1)),
    { ...row("Большой рост", trend(0, 2), trend(1, 0)), group_tag: "Бренд" },
    row("Ровно", trend(1, 1)),
    row("Пропущена система", trend(2, 0, 1)),
  ],
}

test("client report uses actual selected scans and includes all comparable movers in order", () => {
  const doc = clientReport("Демо", report, settings)
  expect(doc).toMatchObject({
    period: "01.11.2026 — 20.11.2026", dates: ["04.11.2026", "19.11.2026"],
    tableHeaders: ["Группа", "Запрос", "04.11.2026", "19.11.2026", "Изм., %"],
    changeSummary: "Рост — 2 · Снижение — 1 · Без изменений — 1 · Недостаточно данных — 1",
  })
  expect(doc.metrics[0].value).toBe("37,5%")
  expect(doc.outcomes.map(item => item.value)).toEqual([6, 5, 2, 1, 2])
  expect(doc.services.map(item => item.value)).toEqual([50, 0])
  expect(doc.services.map(item => item.icon)).toEqual(["/assets/services/chatgpt.svg?v=20261012", "/assets/services/gemini.png"])
  expect(doc.tables.map(table => table.color)).toEqual(["#207657", "#BE483F"])
  expect(doc.tables[0].rows).toEqual([
    ["Бренд", "Большой рост", "0%", "100%", "+100%"],
    ["Без группы", "Малый рост", "0%", "50%", "+50%"],
  ])
  expect(doc.tables[1].rows).toEqual([["Без группы", "Снижение", "100%", "50%", "-50%"]])
})

test("two-date comparisons use calendar edges and the matching trend", () => {
  const doc = clientReport("Демо", report, { ...settings, compare: true, group: "", search: "тест", cards: false, external: false })
  expect(doc.comparison).toEqual(["01.11.2026", "20.11.2026"])
  expect(doc.mode).toContain("Сводка за 20.11.2026")
  expect(doc.filterNotes).toBe("Группа: Без группы · Поиск: «тест» · Карточки товаров исключены · Учитываются упоминания со ссылкой на домен бренда")
  expect(doc.tables[1].rows.map(row => row[1])).toEqual(["Снижение", "Большой рост"])
})

test("one date or no data does not create false movements", () => {
  const doc = clientReport("Демо", { ...report, period_from: "2026-11-04", period_to: "2026-11-04" }, settings)
  expect(doc.comparison).toBeNull()
  expect(doc.tables.every(table => table.rows.length === 0)).toBe(true)
  const empty = clientReport("Демо", { ...report, rows: [], dates: [], period_from: null, period_to: null, summary: {
    total: 0, checked: 0, found: 0, skipped: 0, issues: 0, visibility_pct: null,
  } }, settings)
  expect(empty.changeSummary).toBe("В выбранном периоде нет запросов.")
  expect(empty.metrics[0].value).toBe("—")
  expect(empty.outcomes.every(item => item.value === 0)).toBe(true)
})
