import { X } from "lucide-react"
import type { ReactNode } from "react"
import { AnswerContent, AnswerSourceContext, ResultIssue, renderedSources, sourceCardMap, sourcesOf } from "./answer-content"
import { AnswerEvidenceView, SourceChipList, evidenceSources, type AnswerEvidence, type BrandHighlight } from "./answer-evidence"
import { longDate } from "../lib/format"
import { ServiceMark, serviceName } from "../service-mark"

const statuses: Record<string, string> = {
  found: "Упоминание", not_found: "Нет упоминания", skipped: "Нет AI-блока",
  error: "Требует внимания", captcha: "Требует внимания", auth_required: "Требует внимания", limit_reached: "Требует внимания",
}

function tone(status: string) {
  if (status === "found") return "found"
  if (status === "not_found" || status === "skipped") return "missing"
  return "issue"
}

function serviceLabel(service: string) {
  return service === "alice" ? "Алиса (архив)" : serviceName(service)
}

export function AnswerDialog({ service, scanDate, status, originalStatus, query, quote, answer, evidence, sources, brand, mentionTypes, error, onClose, children }: {
  service: string
  scanDate: string
  status: string
  originalStatus: string
  query: string
  quote?: string | null
  answer?: string | null
  evidence?: AnswerEvidence | null
  sources: string[]
  brand?: BrandHighlight
  mentionTypes?: string[]
  error?: string | null
  onClose: () => void
  children?: ReactNode
}) {
  const cards = sourceCardMap(evidence?.source_cards || [])
  const remaining = evidence
    ? evidenceSources(evidence, sources, service, { skipRendered: true })
    : answer ? renderedSources(answer, sources, service) : sourcesOf(sources)
  const dated = /^\d{4}-\d{2}-\d{2}$/.test(scanDate) ? `${longDate(scanDate)} ${scanDate.slice(0, 4)}` : scanDate
  return <AnswerSourceContext.Provider value={cards}><div className="answer-dialog">
    <div className="answer-dialog__head">
      <div className="answer-dialog__service"><ServiceMark id={service}/><div><p className="answer-dialog__name">{serviceLabel(service)}</p><p className="answer-dialog__date">{dated}</p></div></div>
      <span className={`answer-dialog__status answer-dialog__status--${tone(status)}`}>{statuses[status] || status}</span>
      <button className="cc-button icon" type="button" aria-label="Закрыть ответ" onClick={onClose}><X size={18}/></button>
    </div>
    <h2 id="result-title" className="answer-dialog__query">{query}</h2>
    {status !== originalStatus && <p className="answer-dialog__note">Ручное исправление · оценка сервиса: {statuses[originalStatus] || originalStatus}</p>}
    {quote && <blockquote className="answer-dialog__quote"><AnswerContent text={quote} service={service} sources={sources} brand={brand}/></blockquote>}
    <div className="report-answer">{evidence ? <AnswerEvidenceView evidence={evidence} service={service} sources={sources} brand={brand} preview/> : answer && <AnswerContent text={answer} service={service} sources={sources} brand={brand}/>}<ResultIssue status={status} error={error} answer={answer}/></div>
    <p className="answer-dialog__meta">Типы упоминания: {mentionTypes?.join(", ") || "нет"}</p>
    <SourceChipList sources={remaining} brand={brand}/>
    {children}
  </div></AnswerSourceContext.Provider>
}
