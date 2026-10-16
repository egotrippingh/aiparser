import { expect, it } from "vitest"
import { renderLandingPage } from "./landing-render"

it("renders the actual homepage without browser globals or private account data", () => {
  const html = renderLandingPage()
  expect(html.match(/<h1\b/g)).toHaveLength(1)
  expect(html).toContain("Смотрите, где ИИ упоминает")
  expect(html).toContain("Какие ИИ-системы доступны?")
  expect(html).toContain("Gemini")
  expect(html).toContain('href="/cabinet/"')
  expect(html).not.toContain("Меню аккаунта")
  expect(html).not.toContain("Выбрать проект")
  expect(html).not.toContain("<canvas")
})
