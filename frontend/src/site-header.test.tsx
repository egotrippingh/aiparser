import { expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { SiteHeader } from "./site-header"

it("keeps guest entry links separate from account data", () => {
  const html = renderToStaticMarkup(<SiteHeader/>)
  expect(html).toContain('href="/cabinet/?register=1"')
  expect(html).toContain('href="/cabinet/"')
  expect(html).not.toContain("Меню аккаунта")
  expect(html).not.toContain("Выбрать проект")
})

it("links projects from the homepage to the cabinet and preserves the active cabinet tab", () => {
  const props = {email: "test@example.test", projects: [{id: "one", name: "Project", config: {brand_domains: ["example.test"]}}], selectedId: "one"}
  const publicHtml = renderToStaticMarkup(<SiteHeader {...props}/>)
  expect(publicHtml).toContain('href="/cabinet/#/project/one/report"')
  expect(publicHtml).toContain('href="/cabinet/#/topup"')
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
