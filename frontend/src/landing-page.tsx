import { useEffect, useId, useRef, useState, type PointerEvent } from "react"
import { Brand } from "./brand"
import { PublicSiteHeader } from "./site-header"
import { SUPPORT_URL } from "./site-footer"
import { LandingHeroAnimation } from "./components/landing-hero-animation"
import { LandingWorkflow } from "./components/landing-workflow"
import "./site-theme.scss"
import "./styles/landing.scss"

const registerUrl = `${import.meta.env.VITE_APP_URL || "/cabinet/"}?register=1`
const services = [["google.svg", "Google AI Overview"], ["alice.svg", "Яндекс с Алисой"], ["chatgpt.svg", "ChatGPT"], ["perplexity.svg", "Perplexity"], ["gemini.png", "Gemini"]] as const
const reportViews = [
  ["scan-text.svg", "Упоминания", "Сравните долю ответов, в которых появился ваш бренд.", ["По запросам", "По сервисам", "По датам"]],
  ["message-square.svg", "Ответы", "Откройте полный ответ и прочитайте, что именно ИИ написал о бренде.", []],
  ["link-2.svg", "Источники", "Откройте ссылку, которую привёл ИИ, или выгрузите список доменов.", []],
] as const

function ReportContent({ text, facets }: { text: string; facets: readonly string[] }) {
  return <div className="landing-report__content"><p>{text}</p>{facets.length > 0 && <ul>{facets.map(facet => <li key={facet}>{facet}</li>)}</ul>}</div>
}

function ReportIndex() {
  const container = useRef<HTMLDivElement>(null)
  const measure = useRef<HTMLDivElement>(null)
  const baseId = useId()
  const [active, setActive] = useState(0)

  useEffect(() => {
    const index = container.current
    const hidden = measure.current
    if (!index || !hidden || !window.ResizeObserver) return
    const rows = Array.from(index.querySelectorAll<HTMLElement>(".landing-report__row"))
    const summaries = Array.from(index.querySelectorAll<HTMLElement>(".landing-report__summary"))
    const borderHeight = (element: HTMLElement) => {
      const styles = getComputedStyle(element)
      return parseFloat(styles.borderBlockStartWidth) + parseFloat(styles.borderBlockEndWidth)
    }
    const sync = () => {
      const height = Math.ceil(hidden.getBoundingClientRect().height)
      const chrome = summaries.reduce((sum, summary) => sum + summary.getBoundingClientRect().height, borderHeight(index))
      const borders = rows.reduce((sum, row) => sum + borderHeight(row), 0)
      index.style.setProperty("--report-panel-size", `${height}px`)
      index.style.setProperty("--report-size", `${Math.ceil(height + chrome + borders)}px`)
      index.classList.add("landing-report__index--stable")
    }
    sync()
    const observer = new ResizeObserver(sync)
    observer.observe(hidden)
    summaries.forEach(summary => observer.observe(summary))
    return () => observer.disconnect()
  }, [])

  return <div className="landing-report__index" ref={container}>
    {reportViews.map(([icon, title, text, facets], index) => {
      const opened = active === index
      const id = `${baseId}-${index}`
      return <section className={opened ? "landing-report__row landing-report__row--open" : "landing-report__row"} key={title}>
        <button type="button" className="landing-report__summary" aria-expanded={opened} aria-controls={id} onClick={() => setActive(opened ? -1 : index)}>
          <img src={`/assets/ui/${icon}`} width="16" height="16" alt=""/><span>{title}</span><i aria-hidden="true"/>
        </button>
        <div className="landing-report__panel" id={id} inert={!opened}><ReportContent text={text} facets={facets}/></div>
      </section>
    })}
    <div className="landing-report__measure" ref={measure} aria-hidden="true" inert>
      {reportViews.map(([, title, text, facets]) => <ReportContent key={title} text={text} facets={facets}/>)}
    </div>
  </div>
}

function ServiceTicker() {
  const [enabled, setEnabled] = useState(false)
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)")
    const sync = () => setEnabled(!reduced.matches)
    sync()
    reduced.addEventListener("change", sync)
    return () => reduced.removeEventListener("change", sync)
  }, [])
  return <section className="landing-services" aria-label="Где Аирейт проверяет запросы"><div className="container"><div
    className={enabled ? "landing-services__window landing-services__window--animated" : "landing-services__window"}
    tabIndex={enabled ? 0 : undefined}
    role="region"
    aria-label="Лента ИИ-сервисов"
    aria-keyshortcuts={enabled ? "Space Enter" : undefined}
    title={enabled ? "Нажмите или используйте пробел, чтобы остановить или продолжить ленту" : undefined}
    onClick={() => { if (enabled) setPaused(value => !value) }}
    onKeyDown={event => {
      if (!enabled || event.repeat || (event.key !== " " && event.key !== "Enter")) return
      event.preventDefault()
      setPaused(value => !value)
    }}
  >
    <div className="landing-services__track" style={{ animationPlayState: paused ? "paused" : "running" }}>
      {[false, true].map(hidden => <ul className="landing-services__list" aria-hidden={hidden || undefined} key={String(hidden)}>{services.map(([icon, title]) => <li key={title}><img draggable="false" src={`/assets/services/${icon}`} width="16" height="16" alt=""/>{title}</li>)}</ul>)}
    </div>
  </div></div></section>
}

function trackGlow(event: PointerEvent<HTMLAnchorElement>) {
  if (event.pointerType !== "mouse" || !window.matchMedia("(prefers-reduced-motion: no-preference)").matches) return
  const bounds = event.currentTarget.getBoundingClientRect()
  event.currentTarget.style.setProperty("--edge-x", `${event.clientX - bounds.left}px`)
  event.currentTarget.style.setProperty("--edge-y", `${event.clientY - bounds.top}px`)
}

function resetGlow(event: PointerEvent<HTMLAnchorElement>) {
  event.currentTarget.style.removeProperty("--edge-x")
  event.currentTarget.style.removeProperty("--edge-y")
}

export function LandingPage() {
  return <div className="landing-page landing-page--moonrow">
    <a href="#main" className="skip">К содержанию</a>
    <PublicSiteHeader landing/>
    <main id="main" tabIndex={-1}>
      <section className="landing-hero" aria-labelledby="hero-title"><div className="container landing-hero__grid">
        <h1 id="hero-title"><span>Упоминают ли нейросети</span>{" "}<span><strong>ваш бренд</strong>?</span></h1>
        <div className="landing-hero__lede"><p>Аирейт проверит запросы покупателей в пяти ИИ-сервисах, сохранит ответы и отметит ваш бренд.</p><a className="landing-primary" onPointerMove={trackGlow} onPointerLeave={resetGlow} href={registerUrl}>Начать проверку</a></div>
        <LandingHeroAnimation/>
      </div></section>

      <ServiceTicker/>

      <section className="landing-report" id="report" aria-labelledby="report-title"><div className="container landing-section-grid"><h2 id="report-title">Что видно <br/>в отчёте</h2><ReportIndex/></div></section>

      <section className="landing-audience" id="audience" aria-labelledby="audience-title"><div className="container landing-section-grid"><h2 id="audience-title">Для кого</h2>
        <ul className="landing-audience__list">
          <li><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 6a13 13 0 0 0 8.4-2.8A1 1 0 0 1 21 4v12a1 1 0 0 1-1.6.8A13 13 0 0 0 11 14H5a2 2 0 0 1-2-2V8a2 2 0 0 0 2-2zM6 14a12 12 0 0 0 2.4 7.2 2 2 0 0 0 3.2-2.4A8 8 0 0 1 10 14M8 6v8"/></svg><div><h3>Маркетинговые агентства</h3><p>Покажите клиенту, как изменилась доля ответов с его брендом.</p></div></li>
          <li><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m8.5 11 1.8 1.8 3.3-3.4M20.5 20.5l-4-4"/></svg><div><h3>SEO-агентства</h3><p>Найдите в семантике запросы без упоминаний бренда клиента.</p></div></li>
          <li><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M3 21h18M10 8h4m-4 4h4m-2 9v-5"/></svg><div><h3>Владельцы бизнеса</h3><p>Узнайте, кого ИИ советует покупателям в вашей категории.</p></div></li>
          <li><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="13" rx="2"/><path d="M2 20h20M10 17l-1 3m5-3 1 3"/></svg><div><h3>Фрилансеры</h3><p>Ведите бренды отдельно и делитесь с каждым клиентом его отчётом.</p></div></li>
        </ul>
      </div></section>

      <LandingWorkflow/>
      <section className="landing-integrations" aria-labelledby="integrations-title"><div className="container landing-integrations__grid"><h2 id="integrations-title">Интеграции</h2>
        <a className="landing-integration" id="api" onPointerMove={trackGlow} onPointerLeave={resetGlow} href="/docs/api/"><img src="/assets/ui/braces.svg" width="16" height="16" alt=""/><span><strong>REST API</strong><small>Забирайте ответы и источники в свои отчёты.</small></span></a>
        <a className="landing-integration" id="mcp" onPointerMove={trackGlow} onPointerLeave={resetGlow} href="/docs/mcp/"><img src="/assets/ui/cable.svg" width="16" height="16" alt=""/><span><strong>MCP</strong><small>Подключите Аирейт к своему ИИ-агенту.</small></span></a>
      </div></section>
      <section className="landing-closing" aria-labelledby="closing-title"><div className="container landing-closing__grid"><h2 id="closing-title">Проверьте свой бренд</h2><a className="landing-primary" onPointerMove={trackGlow} onPointerLeave={resetGlow} href={registerUrl}>Начать проверку</a></div></section>
    </main>
    <footer className="landing-footer"><div className="container landing-footer__inner"><Brand/><nav aria-label="Документы и поддержка"><a href="/terms/">Условия использования</a><a href="/privacy/">Конфиденциальность</a><a href={SUPPORT_URL}>Поддержка</a></nav></div></footer>
  </div>
}
