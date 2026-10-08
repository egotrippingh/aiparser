import { useEffect, useState } from "react"
import { accountRequest } from "./account-api"
import { AnswerContent, ResultIssue, SourceList } from "./components/answer-content"
import type { ScanFeedback } from "./scan-feedback"

type Row = { id: number; email: string; project_name: string; brand_name: string; query_text: string; service: string; scan_date: string; status: string; mention_types: string[] }
type Detail = { check_id: string | null; id: number; answer_text: string | null; evidence_quote: string | null; error_message: string | null; sources: string[]; status: string; service: string; feedback: ScanFeedback | null; analysis: { reasoning?: string } | null; arbitration: { reasoning?: string } | null; analysis_model: string | null; arbitration_model: string | null }
const statuses: Record<string, string> = { found: "Упоминание", not_found: "Нет упоминания", error: "Ошибка", skipped: "Нет AI-блока", captcha: "Капча", auth_required: "Нужен вход", limit_reached: "Лимит сервиса" }
const labels = { correct: "Верно", false_positive: "Ложное срабатывание", missed: "Пропущено упоминание" }

export function AdminScans({ token }: { token: string }) {
  const [search, setSearch] = useState(""), [status, setStatus] = useState("")
  const [shot, setShot] = useState<{ id: number; url?: string; error?: string; loading?: boolean } | null>(null)
  const [offset, setOffset] = useState(0), [tick, setTick] = useState(0)
  const [data, setData] = useState<{ total: number; results: Row[] } | null>(null)
  const [selected, setSelected] = useState<number | null>(null), [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState(""), [detailError, setDetailError] = useState(""), [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    const timer = setTimeout(() => {
      setLoading(true); setError(""); setData(null)
      accountRequest<{ total: number; results: Row[] }>(`/admin/scan-results?${new URLSearchParams({ search, status, offset: String(offset) })}`, token)
        .then(d => { if (alive) setData(d) }).catch(e => { if (alive) setError(e.message) }).finally(() => { if (alive) setLoading(false) })
    }, 180)
    return () => { alive = false; clearTimeout(timer) }
  }, [search, status, offset, tick, token])
  useEffect(() => {
    let alive = true
    setDetailError("")
    if (selected !== null) accountRequest<Detail>(`/admin/scan-results/${selected}`, token).then(d => { if (alive) setDetail(d) }).catch(e => { if (alive) setDetailError(e.message) })
    return () => { alive = false }
  }, [selected, token])
  return <section className="cab-panel admin-scans"><div className="cab-section-head"><div><h1>Сканы пользователей</h1><p>Сохранённые ответы ИИ, доказательства и отметки для проверки точности.</p></div><button className="cc-button" disabled={loading} onClick={() => setTick(n => n + 1)}>Обновить</button></div>
    <div className="cc-two"><label>Пользователь, проект, бренд или запрос<input value={search} onChange={e => { setSearch(e.target.value); setOffset(0); setSelected(null) }} /></label><label>Результат<select value={status} onChange={e => { setStatus(e.target.value); setOffset(0); setSelected(null) }}><option value="">Все результаты</option>{Object.entries(statuses).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label></div>
    {error && <p role="alert">{error}</p>}{loading && <p role="status">Загружаем сканы…</p>}
    {data && <><p>{data.total} результатов</p><div className="admin-scan-list">{data.results.map(row => <article key={row.id}>
      <p className="ws-note">{row.email} · {row.project_name} · {row.scan_date} · {row.service}</p><h3>{row.query_text}</h3><p>Бренд: {row.brand_name} · {statuses[row.status] || row.status} · {row.mention_types.join(", ")}</p>
      <button className="cc-button" aria-expanded={selected === row.id} onClick={() => setSelected(selected === row.id ? null : row.id)}>{selected === row.id ? "Скрыть ответ" : "Ответ и причина"}</button>
      {selected === row.id && <div className="admin-scan-detail">{detailError && <p role="alert">{detailError}</p>}{detail?.id !== row.id && !detailError && <p role="status">Загружаем ответ…</p>}{detail?.id === row.id && <>
        {detail.feedback && <p>Отметка пользователя: <b>{labels[detail.feedback.label]}</b>{detail.feedback.comment && ` · ${detail.feedback.comment}`}</p>}
        {detail.evidence_quote && <blockquote>{detail.evidence_quote}</blockquote>}
        {detail.analysis?.reasoning && <p>Анализ ({detail.analysis_model}): {detail.analysis.reasoning}</p>}{detail.arbitration?.reasoning && <p>Арбитр ({detail.arbitration_model}): {detail.arbitration.reasoning}</p>}
        {detail.answer_text && <AnswerContent text={detail.answer_text} service={detail.service} sources={detail.sources} />}<ResultIssue status={detail.status} error={detail.error_message} answer={detail.answer_text} />
        <h3>Источники</h3><SourceList sources={detail.sources} />
        {detail.check_id && <button className="cc-button" disabled={shot?.id === row.id && shot.loading} onClick={() => {
          setShot({ id: row.id, loading: true })
          accountRequest<{ url: string }>(`/admin/scan-results/${row.id}/screenshot`, token).then(d => setShot(current => current?.id === row.id ? { id: row.id, url: d.url } : current)).catch(e => setShot(current => current?.id === row.id ? { id: row.id, error: e.message } : current))
        }}>Открыть скриншот</button>}
        {shot?.id === row.id && shot.error && <p role="alert">{shot.error}</p>}
        {shot?.id === row.id && shot.url && <img className="report-shot" src={shot.url} alt="Скриншот ответа ИИ" />}
      </>}</div>}
    </article>)}</div>{!data.results.length && <p>Нет результатов по выбранным фильтрам.</p>}<div className="cc-actions"><button className="cc-button" disabled={offset === 0 || loading} onClick={() => { setOffset(n => Math.max(0, n - 50)); setSelected(null) }}>Назад</button><button className="cc-button" disabled={offset + 50 >= data.total || loading} onClick={() => { setOffset(n => n + 50); setSelected(null) }}>Далее</button></div></>}
  </section>
}
