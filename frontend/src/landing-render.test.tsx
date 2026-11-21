import { expect, it } from "vitest"
import { renderLandingPage } from "./landing-render"

it("renders the actual homepage without browser globals or private account data", () => {
  const html = renderLandingPage()
  expect(html.match(/<h1\b/g)).toHaveLength(1)
  expect(html).toContain("Узнайте, что ИИ говорит<br/> о вашем бренде<span>.</span>")
  expect(html).toContain("Подключите Аирейт к своему агенту")
  expect(html).toContain("Gemini")
  expect(html).toContain('href="/cabinet/"')
  expect(html).not.toContain("Меню аккаунта")
  expect(html).not.toContain("Выбрать проект")
  expect(html).not.toContain("<canvas")
  expect(html).toContain('src="/assets/landing/hero-lavender-desktop.webp"')
  expect(html).toContain('srcSet="/assets/landing/hero-lavender-mobile.webp"')
  expect(html).not.toContain('/src/assets/')
  expect(html).not.toContain('hero-playback')
  expect(html).not.toContain('Приостановить анимацию')
})
