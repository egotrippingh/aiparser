import {expect, it} from "vitest"
import {restoreEmailProof} from "./registration"

it("restores an unexpired email ticket after reloading without storing password or code", () => {
  const proof = {email: "test@example.test", ticket: "a".repeat(43), expiresAt: 600_000, resendAt: 60_000}
  expect(restoreEmailProof(JSON.stringify(proof), 59_000)).toEqual(proof)
  expect(restoreEmailProof(JSON.stringify(proof), 600_000)).toBeNull()
  for (const raw of [null, "broken", "{}", JSON.stringify({...proof, ticket: "bad"}), JSON.stringify({...proof, resendAt: null})]) {
    expect(restoreEmailProof(raw, 0)).toBeNull()
  }
})
