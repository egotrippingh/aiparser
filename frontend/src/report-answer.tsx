import { useEffect, useRef, useState } from "react"
import { X } from "lucide-react"
import { accountRequest } from "./account-api"
import { CabinetSkeleton } from "./cabinet-loading"
import { AnswerDialog } from "./components/answer-dialog"
import type { AnswerEvidence, BrandHighlight } from "./components/answer-evidence"
import { ScanFeedbackForm, type ScanFeedback, type FeedbackResult } from "./scan-feedback"

type Detail = {
  id: number; feedback: ScanFeedback | null; mention_types: string[]; query_text: string; service: string;
  scan_date: string; status: string; original_status: string; answer_text: string | null; error_message?: string | null;
  evidence_quote: string | null; sources: string[]; check_id: string | null; answer_evidence?: AnswerEvidence | null;
  highlight?: BrandHighlight; has_screenshot?: boolean;
}

export function useReportAnswer(base: string, token: string, canEdit: boolean, onFeedback: () => void) {
  const [detail, setDetail] = useState<(Detail & {requestId: number}) | null>(null)
  const [error, setError] = useState("")
  const [screenshot, setScreenshot] = useState("")
  const dialog = useRef<HTMLDialogElement>(null)
  const request = useRef(0)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  function current(requestId: number) {
    return mounted.current && requestId === request.current && dialog.current?.open
  }

  function close() {
    request.current++
    dialog.current?.close()
  }

  async function openResult(id: number) {
    const requestId = ++request.current
    setDetail(null)
    setError("")
    setScreenshot("")
    dialog.current?.showModal()
    try {
      const data = await accountRequest<Detail>(`${base}/results/${id}`, token)
      if (current(requestId)) setDetail({ ...data, requestId })
    } catch (cause) {
      if (current(requestId)) setError(cause instanceof Error ? cause.message : "Не удалось загрузить ответ")
    }
  }

  async function openScreenshot(id: number) {
    const requestId = request.current
    setScreenshot("")
    try {
      const data = await accountRequest<{ url: string }>(`${base}/results/${id}/screenshot`, token)
      if (current(requestId)) setScreenshot(data.url)
    } catch (cause) {
      if (current(requestId)) setError(cause instanceof Error ? cause.message : "Не удалось открыть снимок")
    }
  }

  function feedbackSaved(id: number, requestId: number, result: FeedbackResult) {
    if (!mounted.current) return
    if (current(requestId)) setDetail(previous => previous?.id === id ? { ...previous, ...result } : previous)
    onFeedback()
  }

  const answerDialog = <dialog className="ws-dialog report-detail" ref={dialog} aria-labelledby="result-title"
    onClose={() => { if (!dialog.current?.open) request.current++ }}>
    {!detail && <div className="ws-dialog-head"><h2 id="result-title">Ответ ИИ</h2>
      <button className="cc-button icon" type="button" aria-label="Закрыть ответ" onClick={close}><X size={16} aria-hidden="true"/></button>
    </div>}
    {error && <p className="cc-alert" role="alert">{error}</p>}
    {detail ? <AnswerDialog key={detail.id} service={detail.service} scanDate={detail.scan_date} status={detail.status}
      originalStatus={detail.original_status} query={detail.query_text} quote={detail.evidence_quote} answer={detail.answer_text}
      evidence={detail.answer_evidence} sources={detail.sources} brand={detail.highlight} mentionTypes={detail.mention_types}
      error={detail.error_message} onClose={close}>
      {canEdit && ["found", "not_found"].includes(detail.status) && detail.answer_text && <ScanFeedbackForm
        key={detail.id} token={token} base={base} id={detail.id} status={detail.original_status} feedback={detail.feedback}
        onSaved={result => feedbackSaved(detail.id, detail.requestId, result)}/>}
      {detail.check_id && detail.has_screenshot !== false && !detail.answer_evidence &&
        <button className="cc-button" type="button" onClick={() => openScreenshot(detail.id)}>Открыть скриншот</button>}
      {screenshot && <img className="report-shot" src={screenshot} alt="Скриншот ответа ИИ"/>}
    </AnswerDialog> : !error && <CabinetSkeleton label="Загружаем ответ…"/>}
  </dialog>
  return { openResult, answerDialog }
}
