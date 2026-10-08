import { describe, expect, it } from "vitest"
import { parseRubles } from "./payment"
describe("Payment amount input", () => {
  it("preserves kopeks without rounding money", () => {
    expect(parseRubles("300,01")).toBe(30001)
    expect(parseRubles(" 1000.1 ")).toBe(100010)
    expect(parseRubles("100000")).toBe(10000000)
  })
  it("rejects exponent, negatives, excessive precision and out-of-range amounts", () => {
    for (const amount of ["", "0", "-300", "3e2", "NaN", "300.001", "100000.01", "300 000", ".5"]) expect(parseRubles(amount)).toBeNull()
  })
})
