import { expect, it } from "vitest"
import { agentStatus } from "./agent-status"

it("shows a paused remote run without resuming it", () => {
  expect(agentStatus(false, {state:"paused"}, {desired_state:"paused"})[0]).toBe("Проверка на паузе")
  expect(agentStatus(false, {state:"paused"}, {desired_state:"running"})[1]).toContain("Ожидается")
  expect(agentStatus(false, null, {desired_state:"paused"})[0]).toBe("Проверка на паузе")
})
