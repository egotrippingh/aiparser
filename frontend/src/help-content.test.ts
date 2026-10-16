import { describe, expect, it } from "vitest"
import { HELP_ARTICLES, helpHref, helpSearchContent } from "./help-content"
import { renderHelpHead, renderHelpPage } from "./help-render"
import { parseQueryImport } from "./query-import"

describe("help content", () => {
  it("has public articles with searchable body text and email-safe support guidance", () => {
    expect(HELP_ARTICLES.map(article => article.slug)).toEqual(["quick-start", "projects-and-queries", "scans", "schedule", "reports", "answers-and-sources", "billing", "troubleshooting"])
    expect(HELP_ARTICLES.find(article => article.slug === "projects-and-queries")?.sections.flatMap(section => section.body).join(" ")).toContain("CSV UTF-8")
    expect(helpSearchContent(HELP_ARTICLES.find(article => article.slug === "troubleshooting")!)).toContain("Не сообщайте")
  })

  it.each(HELP_ARTICLES)("renders complete article and section links for $slug without a session", article => {
    const html = renderHelpPage(article)
    expect(new Set(article.sections.map(section => section.id)).size).toBe(article.sections.length)
    expect(html).toContain(`href="${helpHref(article)}"`)
    expect(helpHref(article)).toBe(`/docs/${article.slug}/`)
    for (const section of article.sections) {
      expect(html).toContain(`id="${section.id}"`)
      expect(html).toContain(`href="#${section.id}"`)
    }
    expect(html).toContain("Не нашли ответ?")
    expect(html).toContain('href="mailto:support@airate.tech"')
    expect(html).not.toContain("Меню аккаунта")
    expect(html.includes("<video")).toBe(article.slug === "quick-start")
    if (article.slug === "quick-start") {
      expect(html).toMatch(/id="project".*?<\/h2><div class="help-video"/)
      expect(html).toContain('aria-label="Воспроизвести видео о создании проекта"')
      expect(html).toMatch(/<video[^>]*src="\/assets\/help\/create-project.mp4"[^>]*preload="metadata"/)
      expect(html).not.toMatch(/<video[^>]*(?:controls|autoplay)=/i)
      expect(html).toContain('aria-label="Перемотка видео о создании проекта"')
      expect(html).toContain('type="range"')
    }
  })

  it("indexes steps and CSV examples as well as paragraphs", () => {
    const billing = HELP_ARTICLES.find(article => article.slug === "billing")!
    expect(helpSearchContent(billing)).toContain("Выберите доступный способ: СБП")
    const imports = HELP_ARTICLES.find(article => article.slug === "projects-and-queries")!
    const example = imports.sections.find(section => section.code)!.code!
    expect(parseQueryImport(example)).toHaveLength(2)
    expect(helpSearchContent(imports)).toContain(example)
  })

  it("escapes punctuation in static metadata and preserves one canonical", () => {
    const article = { ...HELP_ARTICLES[0], title: 'Бренд <test> & ответ', summary: 'Описание с "кавычками" <тегом>' }
    const html = renderHelpHead(article)
    expect(html).toContain("Бренд &lt;test&gt; &amp; ответ")
    expect(html).toContain("&quot;кавычками&quot; &lt;тегом&gt;")
    expect(html.match(/rel="canonical"/g)).toHaveLength(1)
    expect(html).toContain(`href="https://airate.tech${helpHref(article)}"`)
  })
})
