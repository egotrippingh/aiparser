import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { Brand } from "./brand"
import { SiteFooter, SUPPORT_URL } from "./site-footer"
import { privacy, terms } from "./legal-content"
import "./legal.css"

const documentContent = window.location.pathname.startsWith("/privacy") ? privacy : terms

function LegalPage() {
  return <>
    <header className="legal-header"><Brand /><a href="/cabinet/">Личный кабинет ↗</a></header>
    <main className="legal-page">
      <span className="legal-meta">Документы AIRate · Редакция от 28 сентября 2026 года</span>
      <h1>{documentContent.title}</h1>
      <p className="legal-lead">{documentContent.lead}</p>
      <nav className="legal-nav" aria-label="Содержание документа"><ol>{documentContent.sections.map(section =>
        <li key={section.id}><a href={`#${section.id}`}>{section.title.replace(/^\d+\. /, "")}</a></li>
      )}</ol></nav>
      {documentContent.sections.map(section => <section key={section.id} id={section.id}>
        <h2>{section.title}</h2>{section.content}
      </section>)}
      <p className="legal-contact">Вопросы по документу: <a href={SUPPORT_URL} target="_blank" rel="noopener noreferrer">поддержка AIRate в Telegram ↗</a></p>
    </main>
    <SiteFooter />
  </>
}

createRoot(document.getElementById("root")!).render(<StrictMode><LegalPage /></StrictMode>)
