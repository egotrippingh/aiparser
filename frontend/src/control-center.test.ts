import { expect, it } from "vitest"
import { historyRecovery, needsAgent } from "./control-center"

it("restores stamped history entries by their actual traversal distance", () => {
  expect(historyRecovery("#/project/p/report", 4, 3, 3)).toEqual({ delta: 1 })
  expect(historyRecovery("#/project/p/report", 3, 4, 4)).toEqual({ delta: -1 })
})

it("pushes a fresh editor entry when a legacy target has no position", () => {
  expect(historyRecovery("#/project/p/settings", 4, null, 5)).toEqual({ hash: "#/project/p/settings", position: 6 })
})

it("requires a computer only when the project includes an agent service", () => {
  expect(needsAgent(["google_aio", "yandex_neuro"])).toBe(false)
  expect(needsAgent(["google_aio", "chatgpt"])).toBe(true)
  expect(needsAgent(["alice"])).toBe(true)
})
