/** Календарь обязан выбирать те же проверки, что и сервер (select_dates в
 *  app/api/results.py): иначе «в отчёт: N проверок» в календаре разойдётся
 *  с таблицей. Случаи повторяют tests/test_overview.py. */

import { describe, expect, it } from "vitest"

import { calendarLabel, calendarParams, selectedChecks, type CalendarValue } from "./calendar"

const ALL = ["2026-07-10", "2026-07-25", "2026-08-05", "2026-08-30", "2026-09-02"]
const v = (p: Partial<CalendarValue>): CalendarValue => ({ mode: "period", from: null, to: null, picked: [], ...p })

describe("selectedChecks", () => {
  it("период — все проверки диапазона", () => {
    expect(selectedChecks(v({ from: "2026-08-01", to: "2026-08-31" }), ALL)).toEqual([
      "2026-08-05",
      "2026-08-30",
    ])
  })

  it("две даты — первая и последняя проверка диапазона", () => {
    expect(selectedChecks(v({ mode: "two", from: "2026-07-01", to: "2026-09-30" }), ALL)).toEqual([
      "2026-07-10",
      "2026-09-02",
    ])
  })

  it("последний день месяца — по одной проверке на месяц", () => {
    expect(selectedChecks(v({ mode: "monthly" }), ALL)).toEqual([
      "2026-07-25",
      "2026-08-30",
      "2026-09-02",
    ])
  })

  it("выбранные даты — только существующие проверки", () => {
    expect(selectedChecks(v({ mode: "custom", picked: ["2026-07-10", "2099-01-01"] }), ALL)).toEqual([
      "2026-07-10",
    ])
  })

  it("без диапазона — последние 30 проверок", () => {
    const many = Array.from({ length: 40 }, (_, i) => `2026-01-${String(i + 1).padStart(2, "0")}`)
    expect(selectedChecks(v({}), many)).toHaveLength(30)
  })

  it("сравнение без диапазона — первая проверка за всё время против последней", () => {
    const many = Array.from({ length: 40 }, (_, i) => `2026-01-${String(i + 1).padStart(2, "0")}`)
    expect(selectedChecks(v({ mode: "two" }), many)).toEqual(["2026-01-01", "2026-01-40"])
  })
})

describe("calendarParams и подпись", () => {
  it("режим и границы уходят в запрос, выбранные даты — списком", () => {
    expect(calendarParams(v({ mode: "two", from: "2026-07-01", to: "2026-09-30" })).toString()).toBe(
      "mode=two&date_from=2026-07-01&date_to=2026-09-30",
    )
    expect(calendarParams(v({ mode: "custom", picked: ["2026-07-10", "2026-08-30"] })).get("dates")).toBe(
      "2026-07-10,2026-08-30",
    )
  })

  it("подпись понятна без открытия календаря", () => {
    expect(calendarLabel(v({}))).toBe("Последние 30 проверок")
    expect(calendarLabel(v({ from: "2026-08-01", to: "2026-08-31" }))).toBe("01.08.2026 – 31.08.2026")
    expect(calendarLabel(v({ mode: "custom", picked: ["2026-07-10", "2026-08-30"] }))).toBe(
      "Выбранные даты: 2 даты",
    )
  })
})
