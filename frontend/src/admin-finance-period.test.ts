import { expect, it } from "vitest"
import {
  defaultFinancePeriod,
  financePresetRange,
  inclusiveDaySpan,
  isValidFinanceRange,
  matchFinancePreset,
  moscowToday,
  seriesGranularity,
  seriesQueryPath,
} from "./admin-finance-period"

it("builds Moscow calendar day as YYYY-MM-DD", () => {
  expect(moscowToday(new Date("2026-11-22T01:30:00+03:00"))).toBe("2026-11-22")
  expect(moscowToday(new Date("2026-11-21T23:30:00+03:00"))).toBe("2026-11-21")
  // Late evening UTC is already the next calendar day in Moscow.
  expect(moscowToday(new Date("2026-11-21T22:30:00Z"))).toBe("2026-11-22")
})

it("resolves inclusive presets and matches them back", () => {
  const today = "2026-11-22"
  expect(financePresetRange("7", today)).toEqual({ from: "2026-11-16", to: today })
  expect(financePresetRange("30", today)).toEqual({ from: "2026-10-24", to: today })
  expect(financePresetRange("90", today)).toEqual({ from: "2026-08-25", to: today })
  expect(financePresetRange("month", today)).toEqual({ from: "2026-11-01", to: today })
  expect(defaultFinancePeriod(today)).toEqual({ from: "2026-10-24", to: today, preset: "30" })
  expect(matchFinancePreset("2026-11-16", today, today)).toBe("7")
  expect(matchFinancePreset("2026-11-01", today, today)).toBe("month")
  expect(matchFinancePreset("2026-09-01", "2026-09-15", today)).toBe("custom")
})

it("rejects inverted or overlong ranges and picks week granularity after 90 days", () => {
  expect(inclusiveDaySpan("2026-01-01", "2026-01-01")).toBe(1)
  expect(inclusiveDaySpan("2026-01-01", "2026-01-07")).toBe(7)
  expect(isValidFinanceRange("2026-01-01", "2026-12-31")).toBe(true)
  expect(isValidFinanceRange("2026-01-01", "2027-01-01")).toBe(true)
  expect(isValidFinanceRange("2026-01-01", "2027-01-02")).toBe(false)
  expect(isValidFinanceRange("2026-02-01", "2026-01-01")).toBe(false)
  expect(isValidFinanceRange("2026-02-30", "2026-03-01")).toBe(false)
  expect(seriesGranularity("2026-10-24", "2026-11-22")).toBe("day")
  expect(seriesGranularity("2026-08-24", "2026-11-22")).toBe("week")
})

it("builds the series path with rates and automatic granularity", () => {
  expect(seriesQueryPath({ from: "2026-11-01", to: "2026-11-22" })).toBe(
    "/admin/dashboard/series?from=2026-11-01&to=2026-11-22&granularity=day",
  )
  expect(seriesQueryPath({ from: "2026-08-01", to: "2026-11-22" }, "analysis=12&usd_rub_kopeks=9000")).toBe(
    "/admin/dashboard/series?from=2026-08-01&to=2026-11-22&granularity=week&analysis=12&usd_rub_kopeks=9000",
  )
})
