import { createElement, Fragment, useContext, useRef, useState, type ReactNode } from "react"
import { ChevronLeft, ChevronRight, ImageOff } from "lucide-react"
import { AnswerContent, AnswerSourceContext, CitationContext, CitationGroup, PreviewAnchor, SourceIcon, chipLabel, renderedSources, safeAnswerImage, sourceHost, sourceLabel, sourcesOf, type AnswerSourceCard } from "./answer-content"
import { highlightedText, type BrandHighlight } from "./brand-highlight"
import "./answer-evidence.scss"

export { highlightedText, brandLink } from "./brand-highlight"
export type { BrandHighlight } from "./brand-highlight"
export type AnswerNode = string | { tag: string; href?: string; children: AnswerNode[]; sources?: string[] }
export type AnswerEvidence = {
  format?: "markdown"
  answer_text?: string
  content: AnswerNode[]
  products: { title: string; url: string; image_url: string; price: string; description?: string }[]
  source_cards: (AnswerSourceCard & { url: string })[]
}

function AnswerLink({ href, brand, children }: { href: string; brand?: BrandHighlight; children: ReactNode }) {
  return <PreviewAnchor href={href} brand={brand}>{children}</PreviewAnchor>
}

const tags = new Set(["a","article","b","blockquote","br","code","dd","div","dl","dt","em","h1","h2","h3","h4","h5","h6","hr","i","li","ol","p","pre","s","section","small","span","strong","table","tbody","td","th","thead","tr","u","ul"])
function answerNodes(nodes: AnswerNode[], brand: BrandHighlight | undefined, citations: boolean, depth = 0): ReactNode {
  if (depth > 128) return null
  return nodes.map((node,i) => {
    if (typeof node === "string") return <Fragment key={i}>{highlightedText(node, brand)}</Fragment>
    if (node.tag === "citation") return <CitationGroup key={i} sources={node.sources || []} brand={brand}/>
    if (!tags.has(node.tag)) return null
    const children = answerNodes(node.children, brand, citations, depth+1)
    if (node.tag === "a") {
      const href = node.href || "", host = sourceHost(href)
      const label = node.children.length === 1 && typeof node.children[0] === "string" ? node.children[0].trim() : ""
      if (citations && host && (label.toLowerCase().replace(/^www\./, "") === host.toLowerCase() || /^\[?\d+\]?$/.test(label))) {
        return <CitationGroup key={i} sources={[href]} brand={brand}/>
      }
      return <AnswerLink key={i} href={href} brand={brand}>{children}</AnswerLink>
    }
    if (node.tag === "table") return <div key={i} className="answer-table-scroll" role="region" aria-label="Таблица ответа" tabIndex={0}><table className="answer-table">{children}</table></div>
    return createElement(node.tag, {key:i}, ["br","hr"].includes(node.tag) ? undefined : children)
  })
}

export { safeAnswerImage as safeProductImage }

function ProductPhoto({ url, title }: { url: string; title: string }) {
  const [failed, setFailed] = useState(false), src = safeAnswerImage(url)
  return src && !failed ? <img src={src} alt={title} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)}/> : <div className="answer-product-no-photo"><ImageOff size={24} aria-hidden="true"/><span>Фото недоступно</span></div>
}

export function AnswerEvidenceView({ evidence, brand, sources = [], service, preview = false }: { evidence: AnswerEvidence; brand?: BrandHighlight; sources?: string[]; service?: string; preview?: boolean }) {
  const rail = useRef<HTMLUListElement>(null)
  const citations = Boolean(useContext(CitationContext))
  const move = (direction: number) => {
    const el = rail.current
    if (el) el.scrollBy({left:direction * el.clientWidth * .85, behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"})
  }
  const notes = preview ? evidence.source_cards.filter(card => card.title && !sourcesOf([card.url]).length) : []
  return <div className="answer-evidence">{!preview && <p className="answer-note">Сохранённый ответ ИИ. Выделены название бренда и ссылки на его сайт.</p>}<div className="answer-content">{evidence.format === "markdown" ? <AnswerContent text={evidence.answer_text || ""} service={service} sources={sources} brand={brand}/> : answerNodes(evidence.content, brand, citations)}</div>
    {service === "chatgpt" && evidence.products.length > 0 && <section className="answer-comparison">
      <h3>Товары из ответа</h3>
      <ul>{evidence.products.map((product, index) => <li key={index}>
        {product.image_url && <ProductPhoto key={product.image_url} url={product.image_url} title={product.title}/>}
        <div>
          <AnswerLink href={product.url} brand={brand}>{highlightedText(product.title, brand)}</AnswerLink>
          {product.description && <p>{highlightedText(product.description, brand)}</p>}
          {product.price && <p className="answer-product-price">{product.price}</p>}
        </div>
      </li>)}</ul>
    </section>}
    {service !== "chatgpt" && evidence.products.length > 0 && <section className="answer-products" aria-label="Товары из ответа"><div className="answer-products-heading"><h3>Товары из ответа <small>{evidence.products.length}</small></h3><div><button type="button" className="cc-button icon" aria-label="Предыдущие товары" onClick={() => move(-1)}><ChevronLeft size={18}/></button><button type="button" className="cc-button icon" aria-label="Следующие товары" onClick={() => move(1)}><ChevronRight size={18}/></button></div></div><ul ref={rail} className="answer-product-rail" tabIndex={0} aria-label="Карточки товаров; листайте стрелками" onKeyDown={e => { if (e.target === e.currentTarget && ["ArrowLeft","ArrowRight"].includes(e.key)) {e.preventDefault();move(e.key === "ArrowLeft" ? -1 : 1)} }}>{evidence.products.map((p,i) => <li key={`${p.url}-${i}`}><ProductPhoto key={p.image_url} url={p.image_url} title={p.title}/><div><AnswerLink href={p.url} brand={brand}>{highlightedText(p.title, brand)}</AnswerLink>{p.price && <p className="answer-product-price">{p.price}</p>}</div></li>)}</ul></section>}
    {!preview && evidence.format !== "markdown" && evidence.source_cards.length > 0 && <div className="answer-source-details">{evidence.source_cards.map((s,i) => <p key={`${s.url}-${i}`}>{s.url ? <AnswerLink href={s.url} brand={brand}>{highlightedText(s.title || s.url, brand)}</AnswerLink> : highlightedText(s.title, brand)}{s.text && s.text !== s.title && <> — {highlightedText(s.text, brand)}</>}</p>)}</div>}
    {notes.length > 0 && <div className="answer-source-notes">{notes.map((card, index) => <p key={`${card.title}-${index}`}>{highlightedText(card.title, brand)}{card.text && card.text !== card.title && <> — {highlightedText(card.text, brand)}</>}</p>)}</div>}
  </div>
}

export function evidenceSources(evidence: AnswerEvidence, sources: string[], service?: string, options?: { skipRendered?: boolean }) {
  const rendered = new Set<string>()
  const add = (value?: string) => { const safe = sourcesOf(value ? [value] : [])[0]; if (safe) rendered.add(new URL(safe).href) }
  const walk = (nodes: AnswerNode[]) => nodes.forEach(node => {
    if (typeof node === "string") return
    if (node.tag === "a") add(node.href)
    if (node.tag === "citation") node.sources?.forEach(add)
    walk(node.children)
  })
  if (evidence.format === "markdown") {
    evidence.products.forEach(product => add(product.url))
    return renderedSources(evidence.answer_text || "", sources, service).filter(source => !rendered.has(new URL(source).href))
  }
  if (service === "yandex_neuro" && !options?.skipRendered) return sourcesOf(sources)
  walk(evidence.content)
  evidence.products.forEach(product => add(product.url))
  if (!options?.skipRendered) evidence.source_cards.forEach(card => add(card.url))
  return sourcesOf(sources).filter(source => !rendered.has(new URL(source).href))
}

export function SourceChipList({ sources, brand, service }: { sources: string[]; brand?: BrandHighlight; service?: string }) {
  const lookup = useContext(AnswerSourceContext)
  const values = sourcesOf(sources)
  if (!values.length) return null
  const domainOnly = service === "yandex_neuro" || service === "perplexity"
  return <section className="answer-dialog__sources"><h3>Источники · <span>{values.length}</span></h3>
    {service === "google_aio" ? <CitationGroup sources={values} brand={brand}/> : <ul className="source-chips">{values.map(href => <li key={href}><PreviewAnchor href={href} brand={brand} chip label="" accessibleLabel={domainOnly ? sourceLabel(href) : undefined}>
      {domainOnly ? <SourceIcon href={href} favicon={lookup?.(new URL(href))?.favicon}/> : <span className="source-chip__mark" aria-hidden="true">{(sourceHost(href) || "?").slice(0, 1).toUpperCase()}</span>}
      <span className="source-chip__label" title={domainOnly ? sourceLabel(href) : undefined}>{domainOnly ? sourceHost(href) : chipLabel(href, values)}</span>
    </PreviewAnchor></li>)}</ul>}
  </section>
}

export function HighlightedSources({ sources, brand }: { sources: string[]; brand?: BrandHighlight }) {
  const values = sourcesOf(sources)
  return values.length ? <ol className="answer-sources">{values.map(value => <li key={value}><AnswerLink href={value} brand={brand}>{highlightedText(sourceLabel(value), brand)}</AnswerLink></li>)}</ol> : <p className="answer-note">Сохранённых ссылок на источники нет.</p>
}

export function EvidenceSources({ evidence, sources, answerText, service, brand }: { evidence?: AnswerEvidence | null; sources: string[]; answerText?: string | null; service?: string; brand?: BrandHighlight }) {
  const remaining = evidence ? evidenceSources(evidence, sources, service) : answerText ? renderedSources(answerText, sources, service) : sources
  return remaining.length ? <><h3>Источники</h3><HighlightedSources sources={remaining} brand={brand}/></> : null
}
