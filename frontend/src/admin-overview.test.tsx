import { expect, it } from "vitest"
import { balanceLabel } from "./admin-overview"
import { SCAN_SERVICES } from "./lib/scan-preferences"

it("distinguishes an unavailable supplier balance from zero", () => {
  expect(balanceLabel(null, "USD")).toBe("Недоступен")
  expect(balanceLabel("0", "USD")).not.toBe("Недоступен")
  expect(balanceLabel("3.705", "USD")).toContain("3,705")
  expect(balanceLabel("3.705", "CREDITS")).toBe("3,705 credits")
  expect(balanceLabel("10", "CREDITS")).not.toContain("$")
})
it("offers the five distinct server systems without retiring historical IDs", () => {
  expect(SCAN_SERVICES.map(s => s.id).sort()).toEqual(["chatgpt", "gemini", "google_aio", "perplexity", "yandex_neuro"])
  expect(SCAN_SERVICES.find(s => s.id === "yandex_neuro")?.label).toBe("Яндекс Поиск с Алисой")
  expect(SCAN_SERVICES.find(s => s.id === "google_aio")?.label).toBe("Google AI Overview")
})
