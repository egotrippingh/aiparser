import { expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { SiteHeader } from "./site-header"

it("keeps guest entry links separate from account data", () => {
  const html = renderToStaticMarkup(<SiteHeader/>)
  expect(html).toContain('href="/cabinet/?register=1"')
  expect(html).toContain('href="/cabinet/"')
  expect(html).not.toContain("Меню аккаунта")
  expect(html).not.toContain("Выбрать проект")
  expect(html).toContain('href="/docs/"')
  expect(html).toContain(">Документация</a>")
  expect(html).toContain('href="https://t.me/egotrippintg"')
  expect(html).toContain("lucide-send")
})

it("links projects from the homepage to the cabinet and preserves the active cabinet tab", () => {
  const props = {email: "test@example.test", projects: [{id: "one", name: "Project", config: {brand_domains: ["example.test"]}}], selectedId: "one"}
  const publicHtml = renderToStaticMarkup(<SiteHeader {...props}/>)
  expect(publicHtml).toContain('href="/cabinet/#/project/one/report"')
  expect(publicHtml).toContain('href="/cabinet/#/topup"')
  expect(publicHtml).toContain('href="/docs/"')
  expect(publicHtml).toContain('aria-label="Документация"')
  expect(publicHtml).toContain(">Документация</span>")
  expect(publicHtml.split('href="https://t.me/egotrippintg"')).toHaveLength(3)
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

it("uses an account portrait without a referrer and falls back to initials", () => {
  const email = "owner@example.test"
  const avatar = "https://avatars.yandex.net/get-yapic/123/portrait/islands-68"
  const withPortrait = renderToStaticMarkup(<SiteHeader cabinet email={email} avatarUrl={avatar}/>)
  expect(withPortrait.match(/<img[^>]*referrerPolicy="no-referrer"/gi)).toHaveLength(2)
  expect(withPortrait).toContain(avatar)
  const withoutPortrait = renderToStaticMarkup(<SiteHeader cabinet email={email}/>)
  expect(withoutPortrait.match(/class="sh-avatar"[^>]*>OW<\/span>/g)).toHaveLength(2)
})


it("separates the all-projects link from the searchable project trigger", () => {
  const html = renderToStaticMarkup(<SiteHeader email="test@example.test" cabinet/>)
  const link = html.match(/<a[^>]*aria-label="Все проекты"[^>]*>/)![0]
  expect(link).toContain('href="#/projects"')
  expect(html).toMatch(/<button[^>]*aria-label="Выбрать проект"/)
  expect(html).not.toContain('title="Все проекты"')
})

it("keeps account metadata and project searches out of Webvisor", () => {
  const html = renderToStaticMarkup(<SiteHeader email="test@example.test" projects={[{id: "one", name: "Private project", config: {brand_domains: ["example.test"]}}]}/>)
  expect(html).toContain('<header class="sh-header ym-hide-content ym-disable-clickmap ym-disable-tracklink">')
  expect(html).toMatch(/<input[^>]*class="ym-disable-keys"/)
})
