import { expect, it } from "vitest"
import { budgetBuffer, calibratedRate, forecastRates, recommendedRefill, runJournalLabel } from "./admin-data"

it("preserves free checks, leaves unknown rates unset and sends native collector rates separately from FX", () => {
  const query = forecastRates({ chatgpt: "0", google_aio: "0,0042", recompute: " ", usd_rub_kopeks: "99,87" })
  expect(Object.fromEntries(query ?? [])).toEqual({ chatgpt: "0", google_aio: "0.42", usd_rub_kopeks: "9987" })
  expect(forecastRates({ perplexity: "0.002501", usd_rub_kopeks: "80" })?.get("perplexity")).toBe("0.2501")
  expect(forecastRates({ perplexity: "0.002501", usd_rub_kopeks: "120" })?.get("perplexity")).toBe("0.2501")
  expect(forecastRates({ usd_rub_kopeks: "0" })).toBeNull()
  expect(forecastRates({ usd_rub_kopeks: "99.987" })).toBeNull()
  expect(forecastRates({ analysis: "-1" })).toBeNull()
})

it("distinguishes backoff and a requested stop from a manual pause", () => {
  const run = { state: "paused", desired_state: "running", phase: "cloud", retry_at: "2026-11-22T00:00:00Z" }
  expect(runJournalLabel(run)).toBe("Ожидает повтора")
  expect(runJournalLabel({ ...run, desired_state: "paused" })).toBe("На паузе")
  expect(runJournalLabel({ ...run, desired_state: "cancelled" })).toBe("Останавливается")
  expect(runJournalLabel({ ...run, state: "done" })).toBe("Завершён")
})

it("derives a collector's rate in the amount's own currency and rounds up a fractional cost", () => {
  expect(calibratedRate("1,01", 3, 4)).toBe("0.3367")
  expect(calibratedRate("2.10", 700, 6)).toBe("0.003")
  expect(calibratedRate("2.101111", 700, 6)).toBe("0.003002")
  expect(calibratedRate("0", 700, 6)).toBe("0")
  expect(calibratedRate("2.10", 0, 6)).toBeNull()
  expect(calibratedRate("", 10, 4)).toBeNull()
})

it("uses one currency for the balance and budget and preserves missing or sufficient funds", () => {
  expect(recommendedRefill(10, "6.125", 20)).toBe(5.88)
  expect(recommendedRefill(4, "10.1121", 10)).toBe(0)
  expect(recommendedRefill(0, "-0.31", 10)).toBe(0.31)
  expect(recommendedRefill(0.25, "0.03", 0)).toBe(0.22)
  expect(recommendedRefill(1, null, 10)).toBeNull()
  expect(recommendedRefill(null, "1", 10)).toBeNull()
  expect(budgetBuffer("10")).toBe(10)
  expect(budgetBuffer()).toBe(15)
  expect(budgetBuffer("0")).toBe(0)
  expect(budgetBuffer("101")).toBeNull()
})
