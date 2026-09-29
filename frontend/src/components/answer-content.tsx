import { Fragment } from "react"
import "./answer-content.css"

function safeUrl(value: string) {
  try { const url = new URL(value); return /^https?:$/.test(url.protocol) && !url.username && !url.password ? url : null }
  catch { return null }
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

function linkedText(text: string) {
  return text.split(/(https?:\/\/[^\s<>]+)/gi).map((part, i) => {
    let value = part.replace(/[.,;:!?]*$/, "")
    while (value.endsWith(")") && (value.match(/\)/g)?.length || 0) > (value.match(/\(/g)?.length || 0)) value = value.slice(0, -1)
    return safeUrl(value) ? <Fragment key={i}><a href={value} target="_blank" rel="noopener noreferrer">{value}</a>{part.slice(value.length)}</Fragment> : part
  })
}

export function AnswerContent({ text }: { text: string }) {
  // Plain captured text has no reliable heading/citation metadata.
  return <div className="answer-content">{text.replace(/\r\n?/g, "\n").split(/\n\s*\n/).map((part, i) => {
    const lines = part.split("\n")
    const bullets = lines.every(line => /^[-*•]\s+/.test(line))
    const numbered = lines.every((line, j) => /^\d+[.)]\s+/.test(line) && parseInt(line) === parseInt(lines[0]) + j)
    if (bullets || numbered) {
      const items = lines.map((line, j) => <li key={j}>{linkedText(line.replace(bullets ? /^[-*•]\s+/ : /^\d+[.)]\s+/, ""))}</li>)
      return bullets ? <ul key={i}>{items}</ul> : <ol key={i} start={parseInt(lines[0])}>{items}</ol>
    }
    return <p key={i}>{lines.map((line, j) => <Fragment key={j}>{j > 0 && <br />}{linkedText(line)}</Fragment>)}</p>
  })}</div>
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
  return <>{error && <div className="answer-error"><b>Причина</b><p>{error}</p></div>}{hint && <p className="answer-note">{hint}</p>}</>
}
