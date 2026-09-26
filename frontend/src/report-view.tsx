import { Fragment, useEffect, useState } from "react"
import { ChevronDown, FileSearch, RefreshCw } from "lucide-react"
import { accountRequest } from "./account-api"
import { SCAN_SERVICES } from "./lib/scan-preferences"

type Stats = { found: number; checked: number }
type Result = { id: number; query_text: string; group_tag: string | null; service: string; scan_date: string;
  status: string; counts_as_found: boolean; answer_text: string | null; evidence_quote: string | null;
  sources: string[]; check_id: string | null }
type Report = { total: number; results: Result[]; summary: Stats & { visibility_pct: number | null;
  by_service: Record<string, Stats>; by_date: Record<string, Stats> } }
const statuses: Record<string, string> = { found: "Упоминание", not_found: "Нет упоминания", skipped: "Нет AI-блока",
  auth_required: "Нужен вход", captcha: "Капча", limit_reached: "Лимит сервиса", error: "Ошибка" }
const name = (id: string) => SCAN_SERVICES.find(s => s.id === id)?.label || id

export function ReportView({ token, projectId }: { token: string; projectId: string }) {
  const [days, setDays] = useState(30)
  const [cards, setCards] = useState(true)
  const [report, setReport] = useState<Report | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [shot, setShot] = useState("")
  const [error, setError] = useState("")
  const [offset, setOffset] = useState(0)
  const [tick, setTick] = useState(0)
  const [loading, setLoading] = useState(true)
  useEffect(() => { setOffset(0); setExpanded(null); setShot("") }, [projectId, days, cards])
  useEffect(() => {
    let alive = true
    setLoading(true)
    const params = new URLSearchParams({ project: projectId, days: String(days), include_cards: String(cards), offset: String(offset), limit: "50" })
    accountRequest<Report>(`/reports?${params}`, token).then(data => {
      if (alive) { setReport(data); setError("") }
    }).catch(e => { if (alive) setError(e.message) }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [token, projectId, days, cards, offset, tick])
  useEffect(() => { const timer = setInterval(() => { if (document.visibilityState === "visible") setTick(n => n + 1) }, 20000); return () => clearInterval(timer) }, [])
  async function openShot(id: string) {
    try { setShot((await accountRequest<{ url: string }>(`/screenshots/${encodeURIComponent(id)}/url`, token)).url) }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось открыть снимок") }
  }
  return <section className="cc-report" aria-busy={loading}>
    <div className="cc-toolbar"><label>Период<select value={days} onChange={e => setDays(Number(e.target.value))}><option value={7}>7 дней</option><option value={30}>30 дней</option><option value={90}>90 дней</option><option value={365}>Год</option></select></label>
      <label className="cc-check"><input type="checkbox" checked={cards} onChange={e => setCards(e.target.checked)} />Учитывать карточки товаров</label>
      <button className="cc-button" onClick={() => setTick(n => n + 1)} disabled={loading}><RefreshCw size={16} />Обновить</button></div>
    {error && <p className="cc-alert" role="alert">{error}</p>}
    {!report ? <div className="cc-skeleton" aria-label="Загрузка отчёта" /> : <>
      <div className="cc-summary"><span>Упоминаемость <b>{report.summary.visibility_pct == null ? "—" : `${report.summary.visibility_pct}%`}</b></span><span>Упоминания <b>{report.summary.found} / {report.summary.checked}</b></span><span>Результаты <b>{report.total}</b></span></div>
      {!report.total ? <div className="cc-empty"><FileSearch size={32} /><h3>Здесь появится первый отчёт</h3><p>Добавьте запросы, выберите компьютер и запустите проверку. Результаты будут появляться по мере выполнения.</p></div> : <>
        <div className="cc-service-summary">{Object.entries(report.summary.by_service).map(([id, s]) => <div key={id}><span>{name(id)}</span><progress max={s.checked || 1} value={s.found} aria-label={`Упоминания в ${name(id)}`} /><b>{s.found} из {s.checked}</b></div>)}</div>
        <div className="cc-table-scroll"><table className="cc-table"><thead><tr><th>Запрос</th><th>Система</th><th>Дата</th><th>Результат</th><th><span className="sr-only">Ответ</span></th></tr></thead><tbody>{report.results.map(row => <Fragment key={row.id}><tr>
          <td><strong>{row.query_text}</strong>{row.group_tag && <small>{row.group_tag}</small>}</td><td>{name(row.service)}</td><td>{new Date(`${row.scan_date}T12:00:00`).toLocaleDateString("ru-RU")}</td>
          <td><span className={`cc-status ${row.counts_as_found ? "good" : ""}`}>{row.status === "found" ? row.counts_as_found ? "Упоминание" : "Карточка исключена" : statuses[row.status] || row.status}</span></td>
          <td><button className="cc-button" aria-expanded={expanded === row.id} onClick={() => setExpanded(expanded === row.id ? null : row.id)}>Ответ<ChevronDown size={14} /></button></td></tr>
          {expanded === row.id && <tr><td colSpan={5}><div className="cc-answer"><p>{row.answer_text || row.evidence_quote || "Ответ не получен."}</p><ul>{row.sources.map(source => <li key={source}><a href={source} target="_blank" rel="noreferrer">{source}</a></li>)}</ul>{row.check_id && <button className="cc-button" onClick={() => openShot(row.check_id!)}>Открыть скриншот</button>}</div></td></tr>}</Fragment>)}</tbody></table></div>
        <div className="cc-toolbar"><span>{offset + 1}–{Math.min(offset + 50, report.total)} из {report.total}</span><button className="cc-button" disabled={!offset || loading} onClick={() => setOffset(n => Math.max(0, n - 50))}>Назад</button><button className="cc-button" disabled={offset + 50 >= report.total || loading} onClick={() => setOffset(n => n + 50)}>Далее</button></div>
      </>}
    </>}
    {shot && <div className="cc-shot"><button className="cc-button" onClick={() => setShot("")}>Закрыть снимок</button><img src={shot} alt="Скриншот ответа ИИ" /></div>}
  </section>
}
