import { Fragment, type ReactNode } from "react"
import { publicError } from "../lib/public-error"
import "./answer-content.css"

function safeUrl(value: string) {
  try {
    const url = new URL(value)
    return /^https?:$/.test(url.protocol) && !url.username && !url.password ? url : null
  } catch { return null }
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

function inlineCode(text: string, index: number) {
  const ticks = text.slice(index).match(/^`+/)?.[0]
  if (!ticks) return null
  const start = index + ticks.length
  let end = text.indexOf(ticks, start)
  while (end >= 0 && /(?:^|[^\\])(?:\\\\)*\\$/.test(text.slice(start, end))) end = text.indexOf(ticks, end + ticks.length)
  return end < 0 ? null : { value: text.slice(start, end).replace(/\\([\\`])/g, "$1"), end: end + ticks.length }
}

function linkedText(text: string, sources: string[], bold = true) {
  const saved = sourcesOf(sources).map(value => new URL(value)), output: ReactNode[] = []
  let index = 0, plain = ""
  const flush = () => { if (plain) { output.push(plain); plain = "" } }
  const link = (label: string, url: URL) => {
    flush()
    output.push(<a key={output.length} href={url.href} target="_blank" rel="noopener noreferrer">{label}</a>)
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
        output.push(<strong key={output.length}>{linkedText(text.slice(index + 2, end), sources, false)}</strong>)
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
      if (href) {
        const url = safeUrl(href)
        if (url) link(label[1].replace(/\\([\\\[\]])/g, "$1"), url)
        else plain += text.slice(index, end)
        index = end; continue
      }
    }
    const email = rest.match(/^[\w.+-]+@[\w.-]+/)
    if (email) { plain += email[0]; index += email[0].length; continue }
    const direct = rest.match(/^https?:\/\/[^\s<>]+/i)
    if (direct) {
      const value = trimUrlPunctuation(direct[0]), url = safeUrl(value)
      if (url) { link(value, url); index += value.length; continue }
      plain += direct[0]; index += direct[0].length; continue
    }
    const domain = !/[\w@]/.test(text[index - 1] || "") && rest.match(/^(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/?#][^\s<>]*)?/i)
    if (domain) {
      const value = trimUrlPunctuation(domain[0]), url = safeUrl(`https://${value}`)
      const hasPath = /[/?#]/.test(value)
      const matches = url ? saved.filter(source => source.hostname.replace(/^www\./, "") === url.hostname.replace(/^www\./, "") && (!hasPath || source.pathname + source.search + source.hash === url.pathname + url.search + url.hash)) : []
      if (matches.length === 1) { link(value, matches[0]); index += value.length; continue }
      plain += domain[0]; index += domain[0].length; continue
    }
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

function blocks(text: string, sources: string[]) {
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
    return <div key={key++} className="answer-table-scroll" role="region" aria-label="Таблица ответа" tabIndex={0}><table className="answer-table">{data.headers.some(Boolean) && <thead><tr>{data.headers.map((cell, i) => <th key={i} scope="col" style={{textAlign:data.alignment[i]}}>{linkedText(cell, sources)}</th>)}</tr></thead>}<tbody>{data.rows.map((row, r) => <tr key={r}>{row.map((cell, i) => <td key={i} style={{textAlign:data.alignment[i]}}>{linkedText(cell, sources)}</td>)}</tr>)}</tbody></table></div>
  }
  const list = (indent: number, ordered: boolean): ReactNode => {
    const items: ReactNode[] = [], first = parseInt(listItem(lines[index])![2])
    while (index < lines.length) {
      const item = listItem(lines[index])
      if (!item || item[1].length !== indent || /^\d/.test(item[2]) !== ordered) break
      index++
      const content: ReactNode[] = [<Fragment key="text">{linkedText(item[3] || "", sources)}</Fragment>]
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
          content.push(<Fragment key={content.length}><br/>{linkedText(lines[index++].slice(indent + 2), sources)}</Fragment>); continue
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
    const fence = lines[index].match(/^(`{3,})(?:[^`]*)$/)
    if (fence) {
      const start = ++index
      while (index < lines.length && lines[index] !== fence[1]) index++
      output.push(<pre key={key++}><code>{lines.slice(start, index).join("\n")}</code></pre>)
      if (index < lines.length) index++
      continue
    }
    const grid = tableAt(index)
    if (grid) { output.push(table(grid)); continue }
    const heading = lines[index].match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      const Tag = `h${heading[1].length}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6"
      output.push(<Tag key={key++}>{linkedText(heading[2], sources)}</Tag>); index++; continue
    }
    const item = listItem(lines[index])
    if (item) { output.push(list(item[1].length, /^\d/.test(item[2]))); continue }
    const paragraph: string[] = []
    while (index < lines.length && lines[index].trim() && lines[index].trim() !== "•" && !sourceCounter(lines[index]) && !/^#{1,6}\s+/.test(lines[index]) && !/^(`{3,})(?:[^`]*)$/.test(lines[index]) && !listItem(lines[index]) && !tableAt(index)) paragraph.push(lines[index++])
    output.push(<p key={key++}>{paragraph.map((line, i) => <Fragment key={i}>{i > 0 && <br/>}{linkedText(line, sources)}</Fragment>)}</p>)
  }
  return { output, cleaned }
}

export function AnswerContent({ text, service, sources = [] }: { text: string; service?: string; sources?: string[] }) {
  const fixed = service === "chatgpt" ? cleanChatGPTMap(text) : { text, changed: false }
  const rendered = blocks(fixed.text, sources)
  return <div className="answer-content">{rendered.output}{(fixed.changed || rendered.cleaned) && <details className="answer-original"><summary>Исходный текст</summary><pre>{text}</pre></details>}</div>
}

export function SourceList({ sources }: { sources: string[] }) {
  const values = sourcesOf(sources)
  return values.length ? <ol className="answer-sources">{values.map(value => {
    const url = new URL(value)
    return <li key={value}><a href={value} target="_blank" rel="noopener noreferrer" title={value}>{url.hostname}{url.pathname === "/" ? "" : url.pathname}{url.search}</a></li>
  })}</ol> : <p className="answer-note">Сохранённых ссылок на источники нет.</p>
}

export function errorHint(status: string, error: string | null, answer: string | null) {
  if (status === "auth_required") return "Войдите в сервис через агент. Затем запустите новую проверку проекта."
  if (status === "captcha") return "Откройте агент и проверьте запрос на капчу. Если агент ожидает её решения, продолжите текущую проверку в нём. Для уже завершённой проверки потребуется новый запуск проекта."
  if (status === "limit_reached") return "Проверьте ограничения сервиса. После восстановления доступа можно запустить новую проверку проекта."
  if (status === "error") return `${error ? "" : "Причина не передана прежней версией агента. Обновите агент, чтобы отправить сохранённые причины. "}${error?.includes("main .prose") || error?.includes("контейнер ответа") ? "Агент не смог прочитать ответ со страницы сервиса. " : ""}Этот запрос автоматически не повторяется. Новый запуск проекта проверит все запросы заново.`
  if (answer) return null
  if (status === "skipped") return "Сервис не показал блок ответа ИИ."
  return "Текст ответа не сохранён."
}

export function ResultIssue({ status, error, answer }: { status: string; error?: string | null; answer?: string | null }) {
  const hint = errorHint(status, error || null, answer || null)
  return <>{error && <div className="answer-error"><b>Причина</b><p>{publicError(error)}</p></div>}{hint && <p className="answer-note">{hint}</p>}</>
}
