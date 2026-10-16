import { useEffect, useRef } from "react"
import { FrameworkProvider } from "fumadocs-core/framework"
import { useDocsSearch } from "fumadocs-core/search/client"
import { staticClient } from "fumadocs-core/search/client/orama-static"
import { SearchDialog, SearchDialogClose, SearchDialogContent, SearchDialogHeader, SearchDialogIcon, SearchDialogInput, SearchDialogList, SearchDialogOverlay } from "fumadocs-ui/components/dialog/search"
import type { SharedProps } from "fumadocs-ui/contexts/search"
import { DocsLayout } from "fumadocs-ui/layouts/docs"
import { DocsBody, DocsDescription, DocsPage, DocsTitle } from "fumadocs-ui/page"
import { RootProvider } from "fumadocs-ui/provider/base"
import { PublicSiteHeader } from "./site-header"
import { SiteFooter, SUPPORT_EMAIL } from "./site-footer"
import { HELP_ARTICLES, helpHref, type HelpArticle } from "./help-content"
import { ProjectVideo } from "./help-video"

const tree = { name: "Документация AIRate", children: HELP_ARTICLES.map(article => ({ type: "page" as const, name: article.label, url: helpHref(article) })) }
const searchLinks = HELP_ARTICLES.map(article => ({ type: "page" as const, id: article.slug, content: article.label, url: helpHref(article) }))

function HelpSearchDialog(props: SharedProps) {
  const previousFocus = useRef<HTMLElement | null>(null)
  const search = useDocsSearch({ client: staticClient({ from: "/assets/help-search.json", locale: "ru" }) })
  return <SearchDialog {...search} {...props}>
    <SearchDialogOverlay />
    <SearchDialogContent onOpenAutoFocus={() => { previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null }} onCloseAutoFocus={event => {
      event.preventDefault()
      previousFocus.current?.focus()
    }}>
      <SearchDialogHeader><SearchDialogIcon /><SearchDialogInput /><SearchDialogClose /></SearchDialogHeader>
      <SearchDialogList defaultItems={searchLinks} />
    </SearchDialogContent>
  </SearchDialog>
}

const translations = {
  "Search(search trigger)": "Поиск по документации",
  "Search(search dialog)": "Поиск по документации",
  "Open Search(search trigger)(aria-label)": "Открыть поиск",
  "Close Search(search dialog)(aria-label)": "Закрыть поиск",
  "No results found(search dialog)": "Ничего не найдено. Измените запрос.",
  "Search failed(search dialog)": "Не удалось загрузить поиск. Попробуйте снова.",
  "On this page(table of contents)": "На странице",
  "No Headings(table of contents)": "Нет разделов",
  "Collapse Sidebar(sidebar)(aria-label)": "Свернуть меню",
  "Open Sidebar(sidebar)(aria-label)": "Открыть меню",
  "Close Sidebar(sidebar)(aria-label)": "Закрыть меню",
  "Close Sidebar(aria-label)": "Закрыть меню",
  "Show Sidebar(sidebar)": "Показать меню",
  "Hide Sidebar(sidebar)": "Скрыть меню",
  "Toggle Menu(mobile menu)(aria-label)": "Разделы документации",
  "Next Page(pagination)": "Следующая статья",
  "Previous Page(pagination)": "Предыдущая статья",
}

export function HelpPage({ article }: { article: HelpArticle }) {
  const header = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const element = header.current
    if (!element) return
    const measure = () => document.documentElement.style.setProperty("--fd-banner-height", `${element.getBoundingClientRect().height}px`)
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    measure()
    return () => observer.disconnect()
  }, [])
  const framework = {
    usePathname: () => helpHref(article),
    useParams: () => ({}),
    useRouter: () => ({ push: (url: string) => { location.assign(url) }, refresh: () => location.reload() }),
  }
  const toc = article.sections.map(section => ({ title: section.title, url: `#${section.id}`, depth: 2 }))
  return <>
    <a className="help-skip" href="#help-content">К статье</a>
    <div ref={header} className="help-site-header"><PublicSiteHeader /></div>
    <FrameworkProvider {...framework}>
      <RootProvider theme={{ enabled: false }} i18n={{ locale: "ru", translations }} search={{ SearchDialog: HelpSearchDialog }}>
        <DocsLayout tree={tree} nav={{ title: "Документация AIRate", url: "/docs/" }} tabs={false} themeSwitch={{ enabled: false }}>
          <DocsPage toc={toc} id="help-content" tabIndex={-1}>
            <DocsTitle>{article.title}</DocsTitle>
            <DocsDescription>{article.summary}</DocsDescription>
            <DocsBody>
              {article.sections.map(section => <section key={section.id}>
                <h2 id={section.id}><a href={`#${section.id}`}>{section.title}</a></h2>
                {article.slug === "quick-start" && section.id === "project" && <ProjectVideo />}
                {section.body.map(paragraph => <p key={paragraph}>{paragraph}</p>)}
                {section.steps && <ol>{section.steps.map(step => <li key={step}>{step}</li>)}</ol>}
                {section.code && <pre><code>{section.code}</code></pre>}
              </section>)}
              <section className="help-support">
                <h2>Не нашли ответ?</h2>
                <p>Напишите на <a href={SUPPORT_EMAIL}>support@airate.tech</a>. Укажите проект, запрос и время проверки; при необходимости приложите скриншот ошибки.</p>
              </section>
            </DocsBody>
          </DocsPage>
        </DocsLayout>
      </RootProvider>
    </FrameworkProvider>
    <SiteFooter />
  </>
}
