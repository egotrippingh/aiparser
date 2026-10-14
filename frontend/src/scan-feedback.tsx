import { useState } from "react"
import { accountRequest } from "./account-api"

export type ScanFeedback = { label: "correct" | "false_positive" | "missed"; comment: string; updated_at: string; active: boolean }
export type FeedbackResult = { feedback: ScanFeedback | null; status: string; original_status: string }
const labels = { correct: "Верно", false_positive: "Ложное срабатывание", missed: "Пропущено упоминание" }

export function ScanFeedbackForm({ token, base, id, status, feedback, onSaved }: {
  token: string; base: string; id: number; status: string; feedback: ScanFeedback | null;
  onSaved: (result: FeedbackResult) => void
}) {
  const [comment, setComment] = useState(feedback?.comment || "")
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("")
  async function save(label: ScanFeedback["label"] | null) {
    setBusy(true); setMessage("")
    try {
      const data = await accountRequest<FeedbackResult>(`${base}/results/${id}/feedback`, token, { label, comment }, "PUT")
      onSaved(data)
      setMessage(label === "correct" ? "Отметка сохранена." : label ? "Исправление сохранено. Статистика обновляется." : "Отметка снята. Возвращена оценка сервиса.")
    } catch (e) { setMessage(e instanceof Error ? e.message : "Не удалось сохранить отметку") }
    finally { setBusy(false) }
  }
  return <section className="scan-feedback" aria-label="Точность распознавания">
    <h3>Правильно определили упоминание?</h3>
    <p className="ws-note">Исправление меняет галочку и статистику этого ответа. Снятие отметки возвращает оценку сервиса. В проекте можно сохранить до 20 отметок; до 6 последних исправлений помогают распознавать бренд в следующих сканах.</p>
    {feedback && <p>Ваша отметка: <b>{labels[feedback.label]}</b></p>}
    {feedback && feedback.label !== "correct" && !feedback.active && <p className="ws-note">Пример не используется в следующих сканах: параметры бренда изменились. Ручное исправление этого ответа сохранено.</p>}
    <label>Что нужно учесть?<textarea maxLength={400} value={comment} onChange={e => setComment(e.target.value)} placeholder="Например: эксперт — обычное слово, а бренд — Neighbours Expert" /></label>
    <div className="cc-actions"><button className="cc-button" disabled={busy} onClick={() => save("correct")}>Верно</button>
      <button className="cc-button" disabled={busy} onClick={() => save(status === "found" ? "false_positive" : "missed")}>{status === "found" ? "Ложное срабатывание" : "Пропущено упоминание"}</button>
      {feedback && <button className="cc-button" disabled={busy} onClick={() => save(null)}>Снять отметку</button>}</div>
    {message && <p role="status">{message}</p>}
  </section>
}
