import {expect, it} from "vitest"
import {needsRegistrationPassword, restoreEmailProof} from "./registration"

it("restores an unexpired email ticket after reloading without storing password or code", () => {
  const proof = {email: "test@example.test", ticket: "a".repeat(43), expiresAt: 600_000, resendAt: 60_000}
  expect(restoreEmailProof(JSON.stringify(proof), 59_000)).toEqual(proof)
  expect(restoreEmailProof(JSON.stringify(proof), 600_000)).toBeNull()
  for (const raw of [null, "broken", "{}", JSON.stringify({...proof, ticket: "bad"}), JSON.stringify({...proof, resendAt: null})]) {
    expect(restoreEmailProof(raw, 0)).toBeNull()
  }
})

it("recollects missing or changed credentials when returning to a pending registration", () => {
  const password = "long-test-password-123"
  expect(needsRegistrationPassword("", false, password, password)).toBe(true)
  expect(needsRegistrationPassword("ticket", false, password, password)).toBe(false)
  expect(needsRegistrationPassword("ticket", true, password, password)).toBe(true)
  expect(needsRegistrationPassword("ticket", false, "", "")).toBe(true)
  expect(needsRegistrationPassword("ticket", false, "short", "short")).toBe(true)
  expect(needsRegistrationPassword("ticket", false, password + "changed", password)).toBe(true)
})
