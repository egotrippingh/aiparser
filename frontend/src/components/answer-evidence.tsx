import { createElement, Fragment, useRef, useState, type ReactNode } from "react"
import { ChevronLeft, ChevronRight, ImageOff } from "lucide-react"
import { sourcesOf } from "./answer-content"
import "./answer-evidence.css"

export type BrandHighlight = { names: string[]; domains: string[] }
export type AnswerNode = string | { tag: string; href?: string; children: AnswerNode[] }
export type AnswerEvidence = { content: AnswerNode[]; products: { title: string; url: string; image_url: string; price: string }[]; source_cards: { title: string; text: string; url: string }[] }

function brandPattern(brand?: BrandHighlight) {
  const forms = [...new Set(brand?.names.map(n => n.trim()).filter(Boolean) || [])].sort((a,b) => b.length-a.length)
  return forms.length ? new RegExp(`(?<![\\p{L}\\p{N}_])(${forms.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(?![\\p{L}\\p{N}_])`, "giu") : null
}

export function highlightedText(text: string, brand?: BrandHighlight): ReactNode {
  const pattern = brandPattern(brand)
  if (!pattern) return text
  return text.split(pattern).map((part,i) => i % 2 ? <mark className="answer-brand" key={i}>{part}</mark> : part)
}

export function brandLink(href: string, brand?: BrandHighlight) {
  try {
    const host = new URL(href).hostname.replace(/^www\./, "")
    return brand?.domains.some(domain => {
      try {
        const value = new URL(domain.includes("://") ? domain : `https://${domain}`).hostname.replace(/^www\./, "")
        return host === value || host.endsWith(`.${value}`)
      } catch { return false }
    }) || false
  } catch { return false }
}

function AnswerLink({ href, brand, children }: { href: string; brand?: BrandHighlight; children: ReactNode }) {
  const url = sourcesOf([href])[0]
  return url ? <a href={url} className={brandLink(url, brand) ? "answer-brand-link" : undefined} target="_blank" rel="noopener noreferrer">{children}</a> : <>{children}</>
}

const tags = new Set(["a","article","b","blockquote","br","code","dd","div","dl","dt","em","h1","h2","h3","h4","h5","h6","hr","i","li","ol","p","pre","s","section","small","span","strong","table","tbody","td","th","thead","tr","u","ul"])
function answerNodes(nodes: AnswerNode[], brand?: BrandHighlight, depth = 0): ReactNode {
  if (depth > 128) return null
  return nodes.map((node,i) => {
    if (typeof node === "string") return <Fragment key={i}>{highlightedText(node, brand)}</Fragment>
    if (!tags.has(node.tag)) return null
    const children = answerNodes(node.children, brand, depth+1)
    if (node.tag === "a") return <AnswerLink key={i} href={node.href || ""} brand={brand}>{children}</AnswerLink>
    if (node.tag === "table") return <div key={i} className="answer-table-scroll" role="region" aria-label="Таблица ответа" tabIndex={0}><table className="answer-table">{children}</table></div>
    return createElement(node.tag, {key:i}, ["br","hr"].includes(node.tag) ? undefined : children)
  })
}

export function safeProductImage(value: string) {
  try {
    const url = new URL(value), host = url.hostname.toLowerCase()
    return sourcesOf([value]).length && url.protocol === "https:" && host.includes(".") && !host.endsWith(".local") && !host.endsWith(".localhost") && !/^(?:127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(host) ? url.href : ""
  } catch { return "" }
}

function ProductPhoto({ url, title }: { url: string; title: string }) {
  const [failed, setFailed] = useState(false), src = safeProductImage(url)
  return src && !failed ? <img src={src} alt={title} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)}/> : <div className="answer-product-no-photo"><ImageOff size={24} aria-hidden="true"/><span>Фото недоступно</span></div>
}

export function AnswerEvidenceView({ evidence, brand }: { evidence: AnswerEvidence; brand?: BrandHighlight }) {
  const rail = useRef<HTMLUListElement>(null)
  const move = (direction: number) => {
    const el = rail.current
    if (el) el.scrollBy({left:direction * el.clientWidth * .85, behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"})
  }
  return <div className="answer-evidence"><p className="answer-note">Сохранённый ответ ИИ. Выделены название бренда и ссылки на его сайт.</p><div className="answer-content">{answerNodes(evidence.content, brand)}</div>
    {evidence.products.length > 0 && <section className="answer-products" aria-label="Товары из ответа"><div className="answer-products-heading"><h3>Товары из ответа <small>{evidence.products.length}</small></h3><div><button type="button" className="cc-button icon" aria-label="Предыдущие товары" onClick={() => move(-1)}><ChevronLeft size={18}/></button><button type="button" className="cc-button icon" aria-label="Следующие товары" onClick={() => move(1)}><ChevronRight size={18}/></button></div></div><ul ref={rail} className="answer-product-rail" tabIndex={0} aria-label="Карточки товаров; листайте стрелками" onKeyDown={e => { if (e.target === e.currentTarget && ["ArrowLeft","ArrowRight"].includes(e.key)) {e.preventDefault();move(e.key === "ArrowLeft" ? -1 : 1)} }}>{evidence.products.map((p,i) => <li key={`${p.url}-${i}`}><ProductPhoto key={p.image_url} url={p.image_url} title={p.title}/><div><AnswerLink href={p.url} brand={brand}>{highlightedText(p.title, brand)}</AnswerLink>{p.price && <p className="answer-product-price">{p.price}</p>}</div></li>)}</ul></section>}
    {evidence.source_cards.length > 0 && <section className="answer-source-cards" aria-label="Карточки ответа"><h3>Карточки ответа</h3><ul>{evidence.source_cards.map((s,i) => <li key={`${s.url}-${i}`}><AnswerLink href={s.url} brand={brand}>{highlightedText(s.title || s.url, brand)}</AnswerLink>{s.text && s.text !== s.title && <p>{highlightedText(s.text, brand)}</p>}</li>)}</ul></section>}
  </div>
}

export function HighlightedSources({ sources, brand }: { sources: string[]; brand?: BrandHighlight }) {
  const values = sourcesOf(sources)
  return values.length ? <ol className="answer-sources">{values.map(value => <li key={value}><AnswerLink href={value} brand={brand}>{highlightedText(value, brand)}</AnswerLink></li>)}</ol> : <p className="answer-note">Сохранённых ссылок на источники нет.</p>
}
