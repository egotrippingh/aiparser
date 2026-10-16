import { expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { SiteHeader } from "./site-header"

it("keeps guest entry links separate from account data", () => {
  const html = renderToStaticMarkup(<SiteHeader/>)
  expect(html).toContain('href="/cabinet/?register=1"')
  expect(html).toContain('href="/cabinet/"')
  expect(html).not.toContain("Меню аккаунта")
  expect(html).not.toContain("Выбрать проект")
  expect(html).toContain('href="/help/"')
  expect(html).toContain('href="mailto:support@airate.tech"')
  expect(html).toContain("lucide-mail")
  expect(html).not.toContain("t.me")
})

it("links projects from the homepage to the cabinet and preserves the active cabinet tab", () => {
  const props = {email: "test@example.test", projects: [{id: "one", name: "Project", config: {brand_domains: ["example.test"]}}], selectedId: "one"}
  const publicHtml = renderToStaticMarkup(<SiteHeader {...props}/>)
  expect(publicHtml).toContain('href="/cabinet/#/project/one/report"')
  expect(publicHtml).toContain('href="/cabinet/#/topup"')
  expect(publicHtml).toContain('href="/help/"')
  expect(publicHtml.match(/href="mailto:support@airate.tech"/g)).toHaveLength(2)
  expect(publicHtml).not.toContain("Регистрация")
  const cabinetHtml = renderToStaticMarkup(<SiteHeader {...props} cabinet projectTab="queries"/>)
  expect(cabinetHtml).toContain('href="#/project/one/queries" aria-current="true"')
  expect(cabinetHtml).not.toContain("Администрирование")
})

it("distinguishes project loading, failure and empty account states", () => {
  expect(renderToStaticMarkup(<SiteHeader email="test@example.test" loading/>)).toContain("Загрузка проектов")
  const failed = renderToStaticMarkup(<SiteHeader email="test@example.test" projectError/>)
  expect(failed).toContain("Не удалось загрузить проекты")
  expect(failed).not.toContain("У вас пока нет проектов")
  expect(renderToStaticMarkup(<SiteHeader email="test@example.test"/>)).toContain("У вас пока нет проектов")
})


it("separates the all-projects link from the searchable project trigger", () => {
  const html = renderToStaticMarkup(<SiteHeader email="test@example.test" cabinet/>)
  const link = html.match(/<a[^>]*aria-label="Все проекты"[^>]*>/)![0]
  expect(link).toContain('href="#/projects"')
  expect(html).toMatch(/<button[^>]*aria-label="Выбрать проект"/)
  expect(html).not.toContain('title="Все проекты"')
})
