import { Fragment, createContext, isValidElement, useContext, useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react"
import { Popover } from "@base-ui/react/popover"
import { ArrowUpRight, ChevronLeft, ChevronRight } from "lucide-react"
import { toUnicode } from "punycode/"
import { publicError } from "../lib/public-error"
import { highlightedText, brandLink, type BrandHighlight } from "./brand-highlight"
import "./answer-content.scss"

function safeUrl(value: string) {
  try {
    const url = new URL(value)
    return /^https?:$/.test(url.protocol) && !url.username && !url.password ? url : null
  } catch { return null }
}

type References = Map<string, string>
const refKey = (value: string) => value.trim().replace(/\s+/g, " ").toLowerCase()
const fenceOpen = (line: string) => line.match(/^\s*(`{3,})(?:[^`]*)$/)?.[1] || ""
const fenceClose = (line: string, fence: string) => line.trim() === fence

function markdown(text: string) {
  const references: References = new Map(), kept: { line: string; value?: string }[] = []
  let fence = ""
  for (const line of text.replace(/\r\n?/g, "\n").split("\n")) {
    const marker = fenceOpen(line)
    if (marker && !fence) { fence = marker; kept.push({ line }); continue }
    if (fence) { kept.push({ line }); if (fenceClose(line, fence)) fence = ""; continue }
    const definition = line.match(/^\s*\[([^\]]+)\]:\s*(?:<([^>]+)>|(https?:\/\/\S+))(?:\s+(?:["'(].*?["')]))?\s*$/i)
    if (definition) {
      const value = definition[2] || definition[3]
      if (safeUrl(value)) { references.set(refKey(definition[1]), value); kept.push({ line, value }); continue }
    }
    kept.push({ line })
  }
  const targets = linkTargets(kept.filter(item => !item.value).map(item => item.line).join("\n"), references, [])
  return { text: kept.filter(item => !item.value || !targets.has(safeUrl(item.value)!.href)).map(item => item.line).join("\n"), references }
}

export function sourcesOf(values: string[]) {
  const seen = new Set<string>()
  return values.filter(value => {
    const url = safeUrl(value)
    if (!url || seen.has(url.href)) return false
    seen.add(url.href)
    return true
  })
}

function cleanChatGPTMap(text: string) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n")
  const move = lines.findIndex(line => line.trim() === "Use two fingers to move the map")
  const reviews = lines.flatMap((line, i) => line.trim() === "Оставить отзыв" ? [i] : [])
  const end = reviews[0]
  if (!/^[0-5][.,]\d$/.test(lines[0]?.trim()) || move < 1 || reviews.length !== 1 || end <= move) return { text, changed: false }
  const prose = lines.slice(end + 1).join("\n").trim()
  return prose ? { text: prose, changed: true } : { text, changed: false }
}

function trimUrlPunctuation(value: string) {
  value = value.replace(/[.,;:!?]+$/, "")
  while (value.endsWith(")") && (value.match(/\)/g)?.length || 0) > (value.match(/\(/g)?.length || 0)) value = value.slice(0, -1)
  return value
}

function readableUrlPart(value: string) {
  try { return decodeURIComponent(value) } catch { return value }
}

export type AnswerSourceCard = { title: string; text: string; name?: string; favicon?: string; image_url?: string }
export const CitationContext = createContext<{ service: string; container: RefObject<HTMLDivElement | null> } | null>(null)
export const AnswerSourceContext = createContext<ReturnType<typeof sourceCardLookup> | null>(null)

function sourceCardKey(url: URL) {
  const key = new URL(url)
  key.hostname = key.hostname.replace(/^www\./, "")
  const anchor = key.hash.split(":~:", 1)[0]
  key.hash = anchor === "#" ? "" : anchor
  return key.href
}

export function sourceCardLookup(cards: (Partial<AnswerSourceCard> & { url?: string })[]) {
  const exact = new Map<string, AnswerSourceCard>()
  const aliases = new Map<string, string | null>()
  for (const card of cards) {
    const url = safeUrl(card.url || "")
    if (!url) continue
    const previousCard = exact.get(url.href)
    exact.set(url.href, {
      title: previousCard?.title || card.title || "", text: previousCard?.text || card.text || "",
      ...(previousCard?.name || card.name ? { name: previousCard?.name || card.name } : {}),
      ...(previousCard?.favicon || card.favicon ? { favicon: previousCard?.favicon || card.favicon } : {}),
      ...(previousCard?.image_url || card.image_url ? { image_url: previousCard?.image_url || card.image_url } : {}),
    })
    const key = sourceCardKey(url)
    const previous = aliases.get(key)
    aliases.set(key, previous === undefined || previous === url.href ? url.href : null)
  }
  return (url: URL) => {
    const direct = exact.get(url.href)
    if (direct) return direct
    const alias = aliases.get(sourceCardKey(url))
    return alias ? exact.get(alias) : undefined
  }
}

export function sourceHost(value: string) {
  const url = safeUrl(value)
  if (!url) return ""
  let host = url.hostname
  try { host = toUnicode(host) } catch { /* Keep the validated host if decoding fails. */ }
  return `${host.replace(/^www\./, "")}${url.port ? `:${url.port}` : ""}`
}

export function sourcePreviewCopy(href: string, card?: AnswerSourceCard, label = "") {
  const url = sourcesOf([href])[0]
  if (!url) return null
  const host = sourceHost(url)
  const title = (card?.title || "").trim()
  const snippet = (card?.text || "").trim()
  const fromLabel = label.trim()
  const labelOk = Boolean(fromLabel) && fromLabel !== url && fromLabel !== host && !/^https?:\/\//i.test(fromLabel)
  const shown = title || (labelOk ? fromLabel : "") || sourceLabel(url)
  return { host, title: shown === host || shown === `${host}/` ? "" : shown, text: snippet && snippet !== shown ? snippet : "" }
}

export function chipLabel(href: string, group: string[]) {
  const host = sourceHost(href)
  if (!host) return href
  const twins = group.filter(item => sourceHost(item) === host)
  if (twins.length < 2) return host
  const url = new URL(href)
  return host + (url.pathname === "/" && !url.search ? "" : url.pathname + url.search)
}

export function safeAnswerImage(value: string) {
  const url = safeUrl(value)
  if (!url || url.protocol !== "https:") return ""
  const host = url.hostname.replace(/\.$/, "")
  return host.includes(".") && !host.endsWith(".local") && !host.endsWith(".localhost")
    && !/^(?:\d{1,3}\.){3}\d{1,3}$/.test(host) ? url.href : ""
}

export function SourceIcon({ href, favicon }: { href: string; favicon?: string }) {
  const src = safeAnswerImage(favicon || "")
  const [failed, setFailed] = useState("")
  return <span className="answer-source-icon" aria-hidden="true">{src && src !== failed
    ? <img src={src} alt="" width={14} height={14} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(src)}/>
    : sourceHost(href).slice(0, 1).toUpperCase()}</span>
}

export function CitationGroup({ sources, brand }: { sources: string[]; brand?: BrandHighlight }) {
  const context = useContext(CitationContext)
  const lookup = useContext(AnswerSourceContext)
  const [page, setPage] = useState(0)
  const values = sourcesOf(sources).map(href => {
    const card = lookup?.(new URL(href))
    return { href, card, copy: sourcePreviewCopy(href, card)!, branded: brandLink(href, brand) }
  })
  const first = values[0]
  if (!first) return null
  if (!context || context.service === "yandex_neuro") {
    return <span className="answer-citation-links">{values.map(({ href, card, copy, branded }) =>
      <a key={href} className={branded ? "answer-citation answer-citation--brand" : "answer-citation"} href={href} aria-label={sourceLabel(href)} title={sourceLabel(href)} target="_blank" rel="noopener noreferrer">
        <SourceIcon href={href} favicon={card?.favicon}/><span className="answer-citation__label">{copy.host}</span>
      </a>)}</span>
  }
  const { service, container } = context
  const paged = service === "perplexity"
  const name = first.card?.name || first.copy.host
  const triggerLabel = values.length === 1 ? "Источник: "+name : "Источники: "+name+" и ещё "+(values.length-1)
  const extra = values.length - 1
  const entries = paged ? values.slice(page, page + 1) : values
  return <Popover.Root onOpenChange={open => { if (open) setPage(0) }}>
    <Popover.Trigger openOnHover delay={140} closeDelay={180} aria-label={triggerLabel}
      className={values.some(value => value.branded) ? "answer-citation answer-citation--brand" : "answer-citation"}>
      {service !== "gemini" && service !== "perplexity" && <SourceIcon href={first.href} favicon={first.card?.favicon}/>}
      <span className="answer-citation__label">{name}</span>
      {extra > 0 && <span className="answer-citation__count">{service === "gemini" ? "ещё " : "+"}{extra}</span>}
    </Popover.Trigger>
    <Popover.Portal container={container}>
      <Popover.Positioner align="start" sideOffset={7} positionMethod="fixed" collisionPadding={12} className="answer-citation-position">
        <Popover.Popup className="answer-citation-popup" data-service={service} aria-label="Источники" initialFocus={false}>
          {paged && values.length > 1 && <div className="answer-citation-navigation">
            <button type="button" aria-label="Предыдущий источник" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft size={16}/></button>
            <span aria-live="polite">{page + 1}/{values.length}</span>
            <button type="button" aria-label="Следующий источник" disabled={page === extra} onClick={() => setPage(page + 1)}><ChevronRight size={16}/></button>
          </div>}
          <ul className="answer-citation-results">
            {entries.map(({ href, card, copy, branded }) =>
              <li key={href}><a href={href} className={branded ? "answer-citation-result answer-citation--brand" : "answer-citation-result"} target="_blank" rel="noopener noreferrer">
                <span>
                  <span className="answer-citation-result__host"><SourceIcon href={href} favicon={card?.favicon}/>{card?.name || copy.host}</span>
                  {copy.title && <strong className="answer-citation-result__title">{highlightedText(copy.title, brand)}</strong>}
                  {copy.text && <span className="answer-citation-result__text">{highlightedText(copy.text, brand)}</span>}
                </span>
                {service === "google_aio" && card?.image_url && <SourceThumbnail href={card.image_url}/>}
                <ArrowUpRight className="answer-citation-result__out" size={14} aria-hidden="true"/>
              </a></li>)}
          </ul>
        </Popover.Popup>
      </Popover.Positioner>
    </Popover.Portal>
  </Popover.Root>
}

function SourceThumbnail({ href }: { href: string }) {
  const src = safeAnswerImage(href)
  const [failed, setFailed] = useState(false)
  return src && !failed && <img className="answer-citation-result__photo" src={src} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)}/>
}

function plainText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return ""
  if (typeof node === "string" || typeof node === "number") return String(node)
  if (Array.isArray(node)) return node.map(plainText).join("")
  if (isValidElement(node)) return plainText((node.props as { children?: ReactNode }).children)
  return ""
}

function placeCard(anchor: HTMLElement) {
  const width = Math.min(300, window.innerWidth - 24)
  const rect = anchor.getBoundingClientRect()
  const height = 136
  let top = rect.bottom + 8
  if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 8)
  let left = rect.left
  if (left + width > window.innerWidth - 12) left = Math.max(12, window.innerWidth - width - 12)
  return { top, left, width }
}

export function PreviewAnchor({ href, brand, label, accessibleLabel, chip = false, children }: { href: string; brand?: BrandHighlight; label?: string; accessibleLabel?: string; chip?: boolean; children: ReactNode }) {
  const lookupCard = useContext(AnswerSourceContext)
  const link = useRef<HTMLAnchorElement>(null)
  const timer = useRef(0)
  const opened = useRef(0)
  const tip = useId()
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const url = sourcesOf([href])[0]
  const copy = url && lookupCard ? sourcePreviewCopy(url, lookupCard(new URL(url)), label ?? plainText(children)) : null
  useEffect(() => () => window.clearTimeout(timer.current), [])
  useEffect(() => {
    if (!pos) return
    const close = () => { if (performance.now() - opened.current < 250) return; setPos(null) }
    window.addEventListener("scroll", close, true)
    window.addEventListener("resize", close)
    return () => {
      window.removeEventListener("scroll", close, true)
      window.removeEventListener("resize", close)
    }
  }, [pos])
  if (!url) return <>{children}</>
  const branded = brandLink(url, brand)
  const className = [branded ? "answer-brand-link" : "", chip ? "source-chip" : ""].filter(Boolean).join(" ") || undefined
  const show = () => {
    window.clearTimeout(timer.current)
    opened.current = performance.now()
    if (link.current && copy) setPos(placeCard(link.current))
  }
  const hide = () => { timer.current = window.setTimeout(() => setPos(null), 120) }
  const dismiss = () => setPos(null)
  const anchor = <a ref={link} href={url} className={className} target="_blank" rel="noopener noreferrer" aria-label={accessibleLabel} aria-describedby={pos ? tip : undefined} onMouseEnter={copy ? show : undefined} onMouseLeave={copy ? hide : undefined} onFocus={copy ? show : undefined} onBlur={copy ? dismiss : undefined} onKeyDown={copy ? event => { if (event.key === "Escape") dismiss() } : undefined}>{children}</a>
  if (!copy) return anchor
  return <span className={chip ? "source-preview source-preview--chip" : "source-preview"} onMouseEnter={show} onMouseLeave={hide}><>{anchor}{pos && <span className="source-preview__card" id={tip} role="tooltip" style={{ top: pos.top, left: pos.left, width: pos.width }}><span className="source-preview__host"><span className="source-preview__mark" aria-hidden="true">{copy.host.slice(0, 1).toUpperCase()}</span>{branded ? <mark className="answer-brand">{copy.host}</mark> : copy.host}</span>{copy.title && <span className="source-preview__title">{highlightedText(copy.title, brand)}</span>}{copy.text && <span className="source-preview__text">{highlightedText(copy.text, brand)}</span>}</span>}</></span>
}

export function sourceLabel(value: string) {
  const url = safeUrl(value)
  if (!url) return value
  let host = url.hostname
  try { host = toUnicode(host) } catch { /* Keep the validated host if decoding fails. */ }
  return `${host}${url.port ? `:${url.port}` : ""}${readableUrlPart(url.pathname)}${readableUrlPart(url.search)}`
}

function displayText(text: string, service?: string, sources: string[] = []) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n")
  let fence = ""
  for (let line = 0; line < lines.length; line++) {
    const marker = fenceOpen(lines[line])
    if (marker && !fence) { fence = marker; continue }
    if (fence) { if (fenceClose(lines[line], fence)) fence = ""; continue }
    const parts = lines[line].split(/(`+[^`]*`+)/)
    lines[line] = parts.map((part, index) => index % 2 ? part : part
      .replace(/<(\/?)strong>/gi, "**")
      .replace(/\\([!"'(),.\-/:;?])/g, "$1")).join("")
  }
  if (service !== "yandex_neuro") return { text: lines.join("\n"), sourcesMoved: false }
  const start = lines.findIndex(line => /^(?:#{1,6}\s*)?(?:источники|sources?)\s*:?\s*$/i.test(line.trim()))
  const saved = sourcesOf(sources).map(value => new URL(value))
  const tail = lines.slice(start + 1).filter(line => line.trim())
  const onlySources = start >= 0 && tail.length > 0 && tail.every(line => {
    const value = line.trim().replace(/^(?:[-*]|\d+[.)])\s+/, "")
    const link = parsedLink(value, 0, new Map(), saved)
    return link && link.end === value.length && saved.some(source => source.href === link.url.href)
  })
  return !onlySources ? { text: lines.join("\n"), sourcesMoved: false } : {
    text: lines.slice(0, start).join("\n").trimEnd(), sourcesMoved: true,
  }
}

function inlineCode(text: string, index: number) {
  const ticks = text.slice(index).match(/^`+/)?.[0]
  if (!ticks) return null
  const start = index + ticks.length
  let end = text.indexOf(ticks, start)
  while (end >= 0 && /(?:^|[^\\])(?:\\\\)*\\$/.test(text.slice(start, end))) end = text.indexOf(ticks, end + ticks.length)
  return end < 0 ? null : { value: text.slice(start, end).replace(/\\([\\`])/g, "$1"), end: end + ticks.length }
}

type ParsedLink = { label: string; url: URL; end: number; reference?: string; explicit?: boolean }

function parsedLink(text: string, index: number, references: References, saved: URL[]): ParsedLink | null {
  const rest = text.slice(index)
  const label = rest.match(/^\[((?:\\.|[^\]\\])*)\]\(/)
  if (label) {
    const start = index + label[0].length
    let end = start, href = ""
    if (text[start] === "<") {
      end = text.indexOf(">)", start + 1)
      if (end >= 0) { href = text.slice(start + 1, end); end += 2 }
    } else {
      let depth = 1
      for (; end < text.length && depth; end++) {
        if (text[end] === "(") depth++
        if (text[end] === ")") depth--
      }
      if (!depth) href = text.slice(start, end - 1)
    }
    const url = safeUrl(href)
    if (url) return { label: label[1].replace(/\\([\\[\]])/g, "$1"), url, end, explicit: true }
    return null
  }
  const reference = rest.match(/^\[([^\]]+)\](?:\[([^\]]*)\])?/)
  if (reference) {
    const key = refKey(reference[2] || reference[1])
    const url = safeUrl(references.get(key) || "")
    if (url) return { label: reference[1], url, end: index + reference[0].length, reference: key, explicit: true }
  }
  if (/^[\w.+-]+@[\w.-]+/.test(rest)) return null
  const direct = rest.match(/^https?:\/\/[^\s<>]+/i)
  if (direct) {
    const value = trimUrlPunctuation(direct[0]), url = safeUrl(value)
    if (url) return { label: value, url, end: index + value.length }
    return null
  }
  const domain = !/[\w@]/.test(text[index - 1] || "") && rest.match(/^(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/?#][^\s<>]*)?/i)
  if (domain) {
    const value = trimUrlPunctuation(domain[0]), url = safeUrl(`https://${value}`)
    const hasPath = /[/?#]/.test(value)
    const matches = url ? saved.filter(source => source.hostname.replace(/^www\./, "") === url.hostname.replace(/^www\./, "") && (!hasPath || source.pathname + source.search + source.hash === url.pathname + url.search + url.hash)) : []
    if (matches.length === 1) return { label: value, url: matches[0], end: index + value.length }
  }
  return null
}

function linkTargets(text: string, references: References, saved: URL[]) {
  const targets = new Set<string>()
  let fence = ""
  for (const line of text.split("\n")) {
    const marker = fenceOpen(line)
    if (marker && !fence) { fence = marker; continue }
    if (fence) { if (fenceClose(line, fence)) fence = ""; continue }
    for (let index = 0; index < line.length;) {
      const code = line[index] === "`" && inlineCode(line, index)
      if (code) { index = code.end; continue }
      const link = parsedLink(line, index, references, saved)
      if (link) { targets.add(link.url.href); index = link.end; continue }
      index++
    }
  }
  return targets
}

function citationAt(text: string, start: number, references: References, saved: URL[]) {
  const read = (from: number) => {
    const wrapped = text[from] === "("
    let index = from + Number(wrapped)
    const sources: string[] = []
    do {
      if (text[index] !== "[") return null
      const link = parsedLink(text, index, references, saved)
      if (!link?.explicit) return null
      const numericReference = /^\d+$/.test(link.reference || "")
      const domainLabel = link.label.replace(/^www\./i, "").toLowerCase() === sourceHost(link.url.href).toLowerCase()
      if (!(numericReference && (wrapped || /^\d+$/.test(link.label))) &&
          !(domainLabel && saved.some(source => source.href === link.url.href))) return null
      sources.push(link.url.href)
      index = link.end
      if (!wrapped) return { sources, end: index }
      const separator = text.slice(index).match(/^[ \t]*(?:[,;][ \t]*|(?=\[))/)?.[0]
      if (separator === undefined) break
      index += separator.length
    } while (sources.length < 50)
    const closing = text.slice(index).match(/^[ \t]*\)/)
    return closing ? { sources, end: index + closing[0].length } : null
  }
  const first = read(start)
  if (!first) return null
  let { end } = first
  const { sources } = first
  while (sources.length < 50) {
    const gap = text.slice(end).match(/^[ \t]*/)?.[0].length || 0
    const next = read(end + gap)
    if (!next) break
    sources.push(...next.sources)
    end = next.end
  }
  return { sources, end }
}

function linkedText(text: string, sources: string[], references: References, decodeSpaces: boolean, bold = true, brand?: BrandHighlight, citations = false) {
  const saved = sourcesOf(sources).map(value => new URL(value)), output: ReactNode[] = []
  let index = 0, plain = ""
  const visibleText = (value: string) => decodeSpaces ? value.replaceAll("&#32;", " ") : value
  const flush = () => { if (plain) { output.push(highlightedText(visibleText(plain), brand)); plain = "" } }
  const link = (label: string, url: URL) => {
    flush()
    output.push(<PreviewAnchor key={output.length} href={url.href} brand={brand} label={label}>{highlightedText(label, brand)}</PreviewAnchor>)
  }
  while (index < text.length) {
    const rest = text.slice(index)
    if (bold && rest.startsWith("**")) {
      let end = index + 2
      while (end < text.length && text[end] !== "\n" && !text.startsWith("**", end)) {
        end = inlineCode(text, end)?.end || end + 1
      }
      if (end > index + 2 && text.startsWith("**", end)) {
        flush()
        output.push(<strong key={output.length}>{linkedText(text.slice(index + 2, end), sources, references, decodeSpaces, false, brand, citations)}</strong>)
        index = end + 2; continue
      }
    }
    if (rest[0] === "`") {
      const code = inlineCode(text, index)
      if (code) {
        flush()
        output.push(<code key={output.length}>{code.value}</code>)
        index = code.end; continue
      }
    }
    const citation = citations && (rest[0] === "(" || rest[0] === "[") && citationAt(text, index, references, saved)
    if (citation) {
      flush()
      output.push(<CitationGroup key={output.length} sources={citation.sources} brand={brand}/>)
      index = citation.end; continue
    }
    const parsed = parsedLink(text, index, references, saved)
    if (parsed) { link(parsed.explicit ? visibleText(parsed.label) : parsed.label, parsed.url); index = parsed.end; continue }
    plain += text[index++]
  }
  flush()
  return output
}

function tableCells(line: string) {
  const cells: string[] = []
  let cell = "", code = "", index = 0
  while (index < line.length) {
    const char = line[index]
    if (char === "\\" && /[\\|]/.test(line[index + 1] || "")) { cell += line[index + 1]; index += 2; continue }
    if (char === "`") {
      if (/(?:^|[^\\])(?:\\\\)*\\$/.test(cell)) { cell += char; index++; continue }
      const ticks = line.slice(index).match(/^`+/)![0]
      code = code === ticks ? "" : code || ticks
      cell += ticks; index += ticks.length; continue
    }
    if (char === "|" && !code) { cells.push(cell.trim()); cell = "" }
    else cell += char
    index++
  }
  cells.push(cell.trim())
  if (line.trim().startsWith("|") && !cells[0]) cells.shift()
  if (line.trim().endsWith("|") && !cells.at(-1)) cells.pop()
  return cells
}

function blocks(text: string, sources: string[], references: References, brand: BrandHighlight | undefined, citations: boolean, service?: string) {
  const inline = (line: string) => linkedText(line, sources, references, service === "gemini", true, brand, citations)
  const lines = text.replace(/\r\n?/g, "\n").split("\n"), output: ReactNode[] = []
  let index = 0, key = 0, cleaned = false
  // ponytail: only standalone source counters; ambiguous inline +N stays literal.
  const sourceCounter = (line: string) => /^\+\d+$/.test(line.trim())
  const listItem = (line: string) => line.match(/^( *)([-*•]|\d+[.)])(?:\s+(.*)|$)/)
  const tableAt = (start: number) => {
    const header = tableCells(lines[start]), separator = tableCells(lines[start + 1] || "")
    const markdown = header.length > 0 && (header.length > 1 || lines[start].trim().startsWith("|")) && separator.length === header.length && separator.every(cell => /^:?-{3,}:?$/.test(cell))
    const tab = lines[start].includes("\t") && lines[start + 1]?.includes("\t") && lines[start].split("\t").length === lines[start + 1].split("\t").length
    if (!markdown && !tab) return null
    const headers = markdown ? header : lines[start].split("\t").map(cell => cell.trim())
    const rows: string[][] = [], indent = lines[start].match(/^ */)![0].length
    let end = start + (markdown ? 2 : 1)
    while (end < lines.length && lines[end].match(/^ */)![0].length === indent) {
      if (markdown && headers.length === 1 && !lines[end].trim().startsWith("|")) break
      const values = markdown ? tableCells(lines[end]) : lines[end].split("\t").map(cell => cell.trim())
      if (!lines[end].trim() || values.length !== headers.length) break
      rows.push(values); end++
    }
    return { headers, rows, end, alignment: markdown ? separator.map(cell => cell.startsWith(":") && cell.endsWith(":") ? "center" as const : cell.endsWith(":") ? "right" as const : "left" as const) : headers.map(() => "left" as const) }
  }
  const table = (data: NonNullable<ReturnType<typeof tableAt>>) => {
    index = data.end
    return <div key={key++} className="answer-table-scroll" role="region" aria-label="Таблица ответа" tabIndex={0}><table className="answer-table">{data.headers.some(Boolean) && <thead><tr>{data.headers.map((cell, i) => <th key={i} scope="col" style={{textAlign:data.alignment[i]}}>{inline(cell)}</th>)}</tr></thead>}<tbody>{data.rows.map((row, r) => <tr key={r}>{row.map((cell, i) => <td key={i} style={{textAlign:data.alignment[i]}}>{inline(cell)}</td>)}</tr>)}</tbody></table></div>
  }
  const list = (indent: number, ordered: boolean): ReactNode => {
    const items: ReactNode[] = [], first = parseInt(listItem(lines[index])![2])
    while (index < lines.length) {
      const item = listItem(lines[index])
      if (!item || item[1].length !== indent || /^\d/.test(item[2]) !== ordered) break
      index++
      const content: ReactNode[] = [<Fragment key="text">{inline(item[3] || "")}</Fragment>]
      while (index < lines.length) {
        if (sourceCounter(lines[index])) { cleaned = true; index++; continue }
        if (!lines[index].trim()) {
          let next = index + 1
          while (next < lines.length && !lines[next].trim()) next++
          if (next < lines.length && listItem(lines[next])) { index = next; continue }
          break
        }
        const child = listItem(lines[index])
        if (child && child[1].length > indent) { content.push(list(child[1].length, /^\d/.test(child[2]))); continue }
        const fence = lines[index].match(/^( +)(`{3,})(?:[^`]*)$/)
        if (fence && fence[1].length > indent) {
          const start = ++index, closing = fence[1] + fence[2]
          while (index < lines.length && lines[index] !== closing) index++
          content.push(<pre key={content.length}><code>{lines.slice(start, index).map(line => line.slice(fence[1].length)).join("\n")}</code></pre>)
          if (index < lines.length) index++
          continue
        }
        const nestedTable = lines[index].startsWith(" ".repeat(indent + 2)) && tableAt(index)
        if (nestedTable) { content.push(table(nestedTable)); continue }
        if (!child && lines[index].startsWith(" ".repeat(indent + 2))) {
          content.push(<Fragment key={content.length}><br/>{inline(lines[index++].slice(indent + 2))}</Fragment>); continue
        }
        break
      }
      items.push(<li key={items.length} value={ordered ? parseInt(item[2]) : undefined}>{content}</li>)
    }
    return ordered ? <ol key={key++} start={first}>{items}</ol> : <ul key={key++}>{items}</ul>
  }
  while (index < lines.length) {
    if (sourceCounter(lines[index])) { cleaned = true; index++; continue }
    if (!lines[index].trim() || lines[index].trim() === "•") { index++; continue }
    const fence = fenceOpen(lines[index])
    if (fence) {
      const start = ++index
      while (index < lines.length && !fenceClose(lines[index], fence)) index++
      output.push(<pre key={key++}><code>{lines.slice(start, index).join("\n")}</code></pre>)
      if (index < lines.length) index++
      continue
    }
    const grid = tableAt(index)
    if (grid) { output.push(table(grid)); continue }
    const heading = lines[index].match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      const Tag = `h${heading[1].length}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6"
      output.push(<Tag key={key++}>{inline(heading[2])}</Tag>); index++; continue
    }
    const item = listItem(lines[index])
    if (item) { output.push(list(item[1].length, /^\d/.test(item[2]))); continue }
    const paragraph: string[] = []
    while (index < lines.length && lines[index].trim() && lines[index].trim() !== "•" && !sourceCounter(lines[index]) && !/^#{1,6}\s+/.test(lines[index]) && !fenceOpen(lines[index]) && !listItem(lines[index]) && !tableAt(index)) paragraph.push(lines[index++])
    output.push(<p key={key++}>{paragraph.map((line, i) => <Fragment key={i}>{i > 0 && <br/>}{inline(line)}</Fragment>)}</p>)
  }
  return { output, cleaned }
}

export function AnswerContent({ text, service, sources = [], brand }: { text: string; service?: string; sources?: string[]; brand?: BrandHighlight }) {
  const fixed = service === "chatgpt" ? cleanChatGPTMap(text) : { text, changed: false }
  const display = displayText(fixed.text, service, sources)
  const citations = Boolean(useContext(CitationContext))
  const parsed = markdown(display.text), rendered = blocks(parsed.text, sources, parsed.references, brand, citations, service)
  return <div className="answer-content">{rendered.output}{(fixed.changed || display.text !== fixed.text || rendered.cleaned) && <details className="answer-original"><summary>Исходный текст</summary><pre>{text}</pre></details>}</div>
}

export function renderedSources(text: string, sources: string[], service?: string) {
  const fixed = service === "chatgpt" ? cleanChatGPTMap(text) : { text, changed: false }
  const parsed = markdown(displayText(fixed.text, service, sources).text), targets = linkTargets(parsed.text, parsed.references, sourcesOf(sources).map(value => new URL(value)))
  return sourcesOf(sources).filter(value => !targets.has(new URL(value).href))
}

export function SourceList({ sources }: { sources: string[] }) {
  const values = sourcesOf(sources)
  return values.length ? <ol className="answer-sources">{values.map(value => {
    return <li key={value}><a href={value} target="_blank" rel="noopener noreferrer" title={value}>{sourceLabel(value)}</a></li>
  })}</ol> : <p className="answer-note">Сохранённых ссылок на источники нет.</p>
}

export function errorHint(status: string, error: string | null, answer: string | null) {
  if (status === "auth_required") return "Сервис не предоставил доступ к ответу. Запустите новую проверку позже; если ошибка повторится, обратитесь в поддержку."
  if (status === "captcha") return "Сервис запросил дополнительную проверку. Сбор выполняется на сервере; устанавливать программу или решать капчу на своём компьютере не нужно. Попробуйте новую проверку позже."
  if (status === "limit_reached") return "Достигнут лимит ИИ-сервиса. После восстановления доступа можно запустить новую проверку проекта."
  if (status === "error") return `${error ? "" : "Причина ошибки не сохранена. "}${error?.includes("main .prose") || error?.includes("контейнер ответа") ? "Не удалось прочитать ответ сервиса. " : ""}Этот запрос автоматически не повторяется. Новый запуск проекта проверит все запросы заново.`
  if (answer) return null
  if (status === "skipped") return "Сервис не показал блок ответа ИИ."
  return "Текст ответа не сохранён."
}

export function ResultIssue({ status, error, answer }: { status: string; error?: string | null; answer?: string | null }) {
  const hint = errorHint(status, error || null, answer || null)
  return <>{error && <div className="answer-error"><b>Причина</b><p>{publicError(error)}</p></div>}{hint && <p className="answer-note">{hint}</p>}</>
}
