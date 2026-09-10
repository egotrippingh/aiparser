import { describe, expect, it } from "vitest"

import { cellChange, rowChanges, totalChanges } from "./changes"
import type { Cell, Overview, OverviewRow, Status } from "./types"

const cell = (status: Status): Cell => ({ status, needs_review: false, result_id: 1 })

function row(cells: OverviewRow["cells"]): OverviewRow {
  return { query_id: 1, text: "запрос", group_tag: null, is_active: true, cells }
}

describe("cellChange", () => {
  it("находит появление и пропажу упоминания", () => {
    expect(cellChange(cell("not_found"), cell("found"))).toBe("gained")
    expect(cellChange(cell("found"), cell("not_found"))).toBe("lost")
  })

  it("не считает изменением сбои и лимиты — это отсутствие данных", () => {
    expect(cellChange(cell("found"), cell("error"))).toBeNull()
    expect(cellChange(cell("limit_reached"), cell("found"))).toBeNull()
    expect(cellChange(cell("captcha"), cell("not_found"))).toBeNull()
  })

  it("без одной из ячеек сравнивать не с чем", () => {
    expect(cellChange(undefined, cell("found"))).toBeNull()
    expect(cellChange(cell("found"), undefined)).toBeNull()
    expect(cellChange(cell("found"), cell("found"))).toBeNull()
  })
})

describe("rowChanges", () => {
  const r = row({
    "2026-09-01": { chatgpt: cell("not_found"), perplexity: cell("found"), alice: cell("found") },
    "2026-09-02": { chatgpt: cell("found"), perplexity: cell("not_found"), alice: cell("error") },
  })

  it("считает по выбранным сервисам", () => {
    const all = rowChanges(r, "2026-09-02", "2026-09-01", ["chatgpt", "perplexity", "alice"])
    expect(all.gained).toBe(1)
    expect(all.lost).toBe(1)
    expect(all.detail).toEqual([
      { service: "chatgpt", change: "gained" },
      { service: "perplexity", change: "lost" },
    ])

    const onlyGpt = rowChanges(r, "2026-09-02", "2026-09-01", ["chatgpt"])
    expect(onlyGpt).toMatchObject({ gained: 1, lost: 0 })
  })

  it("без прошлого среза изменений нет", () => {
    expect(rowChanges(r, "2026-09-02", null, ["chatgpt"])).toMatchObject({ gained: 0, lost: 0 })
  })
})

describe("totalChanges", () => {
  const base: Omit<Overview, "rows" | "summary"> = {
    project: {
      id: 1,
      name: "p",
      brand_name: "b",
      brand_aliases: [],
      brand_domains: [],
      region_code: null,
      deep_check_depth: 0,
      notes: null,
    },
    dates: ["2026-09-01", "2026-09-02"],
    services: ["chatgpt"],
    stats: {},
  }
  const summary = (prev: string | null) => ({
    date: "2026-09-02",
    prev_date: prev,
    total: { found: 0, checked: 0, pct: null, delta: null },
    by_service: [],
    queries: 0,
    needs_review: 0,
    errors: 0,
    not_checked: 0,
  })
  const rows = [
    row({ "2026-09-01": { chatgpt: cell("not_found") }, "2026-09-02": { chatgpt: cell("found") } }),
    row({ "2026-09-01": { chatgpt: cell("found") }, "2026-09-02": { chatgpt: cell("found") } }),
  ]

  it("суммирует по всем запросам", () => {
    expect(totalChanges({ ...base, rows, summary: summary("2026-09-01") })).toEqual({
      gained: 1,
      lost: 0,
      comparable: true,
    })
  })

  it("на первом срезе сравнивать не с чем", () => {
    expect(totalChanges({ ...base, rows, summary: summary(null) }).comparable).toBe(false)
    expect(totalChanges({ ...base, rows, summary: null }).comparable).toBe(false)
  })
})
