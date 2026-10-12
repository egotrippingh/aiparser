import { ScanFeedbackForm, type ScanFeedback } from "./scan-feedback"
import { AnswerContent, SourceList, ResultIssue } from "./components/answer-content"
import { AnswerEvidenceView, HighlightedSources, type AnswerEvidence, type BrandHighlight } from "./components/answer-evidence"
import { useEffect, useRef, useState, type CSSProperties } from "react"
import { Download, RefreshCw, Search, X } from "lucide-react"
import { accountDownload, accountRequest } from "./account-api"
import { today } from "./lib/dates"
import { ReportCalendar, shortDate } from "./report-calendar"
import { AppChoice } from "./app-choice"
import { ReportChart } from "./report-chart"
import { ServiceMark, serviceColors, serviceName as name } from "./service-mark"

type Stats = { found: number; checked: number; issues: number; skipped: number; visibility_pct: number | null }
export type Trend = { current: Stats; previous: Stats; delta: number | null; relative: number | null; baseline_complete: boolean; baseline_from: string | null; baseline_to: string | null }
type Cell = { id: number; status: string; found: boolean; date?: string }
type Query = { id: string; text: string; group_tag: string; cells: Record<string,Record<string,Cell>>; latest: Record<string,Cell>; trend: Trend }
type Source = { domain: string; count: number; own: boolean; urls: string[]; queries: number; services: string[]; results: { id: number; query_text: string; date: string; service: string }[] }
type Report = { date_from: string; date_to: string; available_dates: string[]; services: string[]; available_services: string[]; groups: string[]; summary: Stats; trend: Trend; service_stats: Record<string,Trend>; comparison: { from: Stats; to: Stats; delta: number | null }; timeline: (Stats & {date: string; services: Record<string,Stats>})[]; total: number; rows: Query[]; sources: Source[] }
type Detail = { id: number; feedback: ScanFeedback | null; mention_types: string[]; query_text: string; service: string; scan_date: string; status: string; answer_text: string | null; error_message?: string | null; evidence_quote: string | null; sources: string[]; check_id: string | null; answer_evidence?: AnswerEvidence | null; highlight?: BrandHighlight; has_screenshot?: boolean }
const statuses: Record<string,string> = {found:"Упоминание",not_found:"Нет упоминания",skipped:"Нет AI-блока",error:"Требует внимания",captcha:"Требует внимания",auth_required:"Требует внимания",limit_reached:"Требует внимания"}
const pct = (value: number | null) => value == null ? "—" : `${value}%`
const cellLabel = (cell: Cell) => cell.status === "found" && !cell.found ? "Карточки исключены" : statuses[cell.status] || cell.status
export const trendTone = (delta: number | null) => delta === null || delta === 0 ? "neutral" : delta > 0 ? "positive" : "negative"
export function trendText(trend: Trend) {
  const delta = trend.delta
  return delta === null ? "Нет полных данных для сравнения" : `${delta > 0 ? "Рост" : delta < 0 ? "Снижение" : "Без изменения"}: ${delta > 0 ? "+" : ""}${delta} п.п.${trend.relative === null ? "" : ` (${trend.relative > 0 ? "+" : ""}${trend.relative}%)`}`
}
export function reportRows(rows: Query[], status: string, sort: boolean) {
  const filtered = rows.filter(query => !status || Object.values(query.latest).some(cell => status === "found" ? cell.found : cell.status === "not_found"))
  return sort ? [...filtered].sort((a,b) => (b.trend.current.visibility_pct ?? -1) - (a.trend.current.visibility_pct ?? -1)) : filtered
}

function Rate({ trend, from, to }: { trend: Trend; from: string; to: string }) {
  const [position, setPosition] = useState<{left:number;top:number}>({left:10,top:10})
  const text = trendText(trend)
  return <div className={`rate-wrap ${trendTone(trend.delta)}`}><span className="rate-number">{trend.delta === null || trend.delta === 0 ? "" : trend.delta > 0 ? "↑ " : "↓ "}{pct(trend.current.visibility_pct)}</span><span className="rate-hover" tabIndex={0} aria-label={text} onFocus={event => { const rect = event.currentTarget.getBoundingClientRect(); setPosition({left:Math.max(10,Math.min(rect.left,innerWidth-290)),top:Math.max(10,rect.top-110)}) }} onMouseEnter={event => { const rect = event.currentTarget.getBoundingClientRect(); setPosition({left:Math.max(10,Math.min(rect.left,innerWidth-290)),top:Math.max(10,rect.top-110)}) }}><span className="table-progress"><span style={{width:`${trend.current.visibility_pct || 0}%`}}/></span><span className="trend-tooltip" role="tooltip" style={position}><strong>{text}</strong><span>{trend.baseline_from && trend.baseline_to ? `${shortDate(trend.baseline_from)} — ${shortDate(trend.baseline_to)}: ${pct(trend.previous.visibility_pct)}` : "Предыдущий период недоступен"}</span><span>{shortDate(from)} — {shortDate(to)}: {pct(trend.current.visibility_pct)}</span></span></span></div>
}

export function ReportView({ token, projectId, sourcesOnly = false }: {token:string;projectId:string;sourcesOnly?:boolean}) {
  const [range,setRange] = useState<{from:string;to:string}|null>(null)
  const [compare,setCompare] = useState(false), [cards,setCards] = useState(true)
  const serviceKey = `aimt.report.services.${projectId}`
  const [selectedServices,setSelectedServices] = useState<string[]|null>(() => {
    try { const saved: unknown = JSON.parse(sessionStorage.getItem(serviceKey) || "null"); return Array.isArray(saved) && saved.length && saved.every(s => typeof s === "string" && s in serviceColors) ? [...new Set(saved)] : null } catch { return null }
  })
  const [group,setGroup] = useState("*"), [querySearch,setQuerySearch] = useState(""), [status,setStatus] = useState(""), [sort,setSort] = useState(false)
  const [sourceSearch,setSourceSearch] = useState("")
  const [search,setSearch] = sourcesOnly ? [sourceSearch,setSourceSearch] : [querySearch,setQuerySearch]
  const [sourceKind,setSourceKind] = useState("all"), [expandedSource,setExpandedSource] = useState("")
  const [report,setReport] = useState<Report|null>(null), [error,setError] = useState("")
  const [loading,setLoading] = useState(true), [tick,setTick] = useState(0), [exporting,setExporting] = useState("")
  const [detail,setDetail] = useState<Detail|null>(null), [detailError,setDetailError] = useState(""), [shot,setShot] = useState("")
  const dialog = useRef<HTMLDialogElement>(null), detailRequest = useRef(0), mounted = useRef(true)
  const [loadedFilters, setLoadedFilters] = useState("")
  const base = `/control/projects/${encodeURIComponent(projectId)}/mentions`
  const params = new URLSearchParams({include_cards:String(cards),compare:String(compare && !sourcesOnly),date_to:range?.to||today()})
  if (!sourcesOnly) params.set("search",search)
  if (selectedServices) params.set("services",selectedServices.join(","))
  if (range?.from) params.set("date_from",range.from)
  if (group !== "*") params.set("group",group)
  const filters = params.toString()
  const stale = loadedFilters !== filters
  function chooseServices(next: string[]|null) {
    setSelectedServices(next); setLoading(true)
    try { if(next)sessionStorage.setItem(serviceKey,JSON.stringify(next));else sessionStorage.removeItem(serviceKey) } catch { /* Private browsing may disable storage. */ }
  }
  const availableServices = report?.available_services || []
  useEffect(() => {
    let alive = true
    setLoading(true)
    const timer = setTimeout(() => {
      accountRequest<Report>(`${base}/overview?${filters}`,token).then(data => { if(alive){setLoadedFilters(filters);setReport(data);setError("")} }).catch(e => {if(alive)setError(e.message)}).finally(() => {if(alive)setLoading(false)})
    },180)
    return () => {alive=false;clearTimeout(timer)}
  },[base,filters,tick,token])
  useEffect(() => { const timer=setInterval(() => {if(document.visibilityState === "visible")setTick(n => n+1)},20000);return () => clearInterval(timer) },[])
  useEffect(() => () => {mounted.current=false;detailRequest.current++},[])
  function closeDetail() { detailRequest.current++; dialog.current?.close() }
  async function openResult(id:number) {
    const requestId=++detailRequest.current;setDetail(null);setDetailError("");setShot("");dialog.current?.showModal()
    try { const data=await accountRequest<Detail>(`${base}/results/${id}`,token);if(mounted.current && requestId===detailRequest.current && dialog.current?.open)setDetail(data) } catch(e) {if(mounted.current && requestId===detailRequest.current && dialog.current?.open)setDetailError(e instanceof Error?e.message:"Не удалось загрузить ответ")}
  }
  async function exportReport(kind:string) {
    if (stale || loading) return
    setExporting(kind);setError("")
    const path = sourcesOnly ? `${base}/overview/export/sources?${filters}&${new URLSearchParams({source_kind:sourceKind,source_search:search})}` : `${base}/export/${kind}?${filters}`
    try {await accountDownload(path,token,`${kind}-${report?.date_from}-${report?.date_to}.xlsx`)}
    catch(e) {if(mounted.current)setError(e instanceof Error?e.message:"Ошибка выгрузки")}
    finally {if(mounted.current)setExporting("")}
  }
  async function openShot(id:string) {const requestId=detailRequest.current;setShot("");try{const data=await accountRequest<{url:string}>(`/screenshots/${encodeURIComponent(id)}/url`,token);if(mounted.current && requestId===detailRequest.current && dialog.current?.open)setShot(data.url)}catch(e){if(mounted.current && requestId===detailRequest.current && dialog.current?.open)setDetailError(e instanceof Error?e.message:"Не удалось открыть снимок")}}
  const rows = report ? reportRows(report.rows,status,sort) : []
  const groups = [...new Set(rows.map(query => query.group_tag))]
  const sources = report?.sources.filter(source => (sourceKind === "all" || source.own === (sourceKind === "own")) && source.domain.toLowerCase().includes(search.toLowerCase())) || []
  function cellButton(cell:Cell|undefined, query:Query, id:string, day?:string) {
    return <button disabled={!cell || loading || stale} className={cell?.found?"found":""} title={cell ? cellLabel(cell) : "Не проверялось"} aria-label={`${query.text} · ${name(id)} · ${day || cell?.date || ""} · ${cell ? cellLabel(cell) : "Не проверялось"}`} onClick={() => cell && openResult(cell.id)}>{cell?.found?"✓":cell?.status==="skipped"?"н/д":cell && !["found","not_found"].includes(cell.status)?"!":"—"}</button>
  }
  return <section aria-busy={loading}>
    <div className="filterbar">{report && <ReportCalendar from={range?.from||report.date_from} to={range?.to||report.date_to} available={report.available_dates} change={(from,to) => setRange({from,to})}/>}
      <AppChoice label="Системы в отчёте" value={selectedServices?.length === 1 ? selectedServices[0] : selectedServices ? "custom" : "all"} options={[{value:"all",label:"Все ИИ-системы"},...availableServices.map(id => ({value:id,label:name(id)})),...(selectedServices && selectedServices.length > 1 ? [{value:"custom",label:"Выбрано несколько"}] : [])]} change={value => {if(value!=="custom")chooseServices(value==="all"?null:[value])}}/>
      <AppChoice label="Группа запросов" value={group} searchable options={[{value:"*",label:"Все группы"},{value:"",label:"Без группы"},...(report?.groups || []).map(label => ({value:label,label}))]} change={setGroup}/>
      <label className="check-control"><input type="checkbox" checked={cards} onChange={e => setCards(e.target.checked)}/>Учитывать карточки</label>
      {!sourcesOnly && <AppChoice label="Режим отчёта" value={compare?"compare":"period"} options={[{value:"period",label:"За период"},{value:"compare",label:"Сравнить даты"}]} change={value => setCompare(value==="compare")}/>}
      <span className="spacer"/><button className="btn" disabled={!!exporting||!report||loading||stale} onClick={() => exportReport(sourcesOnly?"sources":"mentions")}><Download size={14}/>{exporting?"Готовим…":"Экспорт XLSX"}</button><button className="btn icon-only" aria-label="Обновить отчёт" disabled={loading || stale} onClick={() => setTick(n=>n+1)}><RefreshCw size={14}/></button>
    </div>
    {error && <p className="cc-alert" role="alert">{error}<button className="btn" onClick={() => setTick(n=>n+1)}>Повторить</button></p>}
    {report && stale && <p className="notice" role="status">По выбранным фильтрам данных ещё нет. Ниже показан предыдущий отчёт.</p>}
    {!report ? <p className="empty-state" role="status">{loading ? "Загрузка отчёта…" : "Отчёт недоступен"}</p> : sourcesOnly ? <>
      <div className="stat-inline"><span><strong>{sources.length}</strong> источников</span><span>Учитываются ответы с упоминанием бренда</span></div><section className="panel"><div className="table-toolbar"><label className="search-box"><Search size={14}/><input aria-label="Поиск источника" placeholder="Найти домен" value={search} onChange={e => setSearch(e.target.value)}/></label><AppChoice label="Тип источника" value={sourceKind} options={[{value:"all",label:"Все источники"},{value:"own",label:"Сайт бренда"},{value:"external",label:"Внешние источники"}]} change={setSourceKind}/></div><div className="table-wrap"><table><thead><tr><th>Домен</th><th>Тип</th><th>Ответов со ссылкой</th><th>Запросы</th><th>ИИ-системы</th><th/></tr></thead>{sources.map(source => <tbody key={source.domain}><tr><td><a href={source.urls[0]} target="_blank" rel="noopener noreferrer">{source.domain} ↗</a></td><td><span className={`badge ${source.own?"blue":""}`}>{source.own?"Сайт бренда":"Внешний источник"}</span></td><td>{source.count}</td><td>{source.queries}</td><td><div className="system-marks">{source.services.map(id => <span key={id} title={name(id)}><ServiceMark id={id}/></span>)}</div></td><td><button className="text-link" aria-expanded={expandedSource === source.domain} onClick={() => setExpandedSource(expandedSource === source.domain ? "" : source.domain)}>Ответы →</button></td></tr>{expandedSource === source.domain && <tr><td colSpan={6}><div className="source-answers"><small>Последние {source.results.length} ответов со ссылкой</small>{source.results.map(result => <button className="btn" key={result.id} disabled={loading || stale} onClick={() => openResult(result.id)}>{shortDate(result.date)} · {name(result.service)} · {result.query_text}</button>)}</div></td></tr>}</tbody>)}</table>{!sources.length && <div className="empty-state">Источников по выбранным фильтрам нет.</div>}</div></section><p className="page-note">Число ответов со ссылкой на домен; несколько ссылок из одного ответа считаются один раз. Источники показываются только в ответах с упоминанием бренда. XLSX содержит домены и показатели с учётом выбранного типа источника и поиска.</p>
    </> : <>
      <section className="metrics" aria-label="Основные показатели">
        <div className="metric primary-metric"><div className="metric-label">{compare?`Начальная дата · ${shortDate(report.date_from)}`:"Упоминаемость"}</div><div className="metric-value">{pct(compare?report.comparison.from.visibility_pct:report.summary.visibility_pct)}</div><div className="metric-caption">{compare?`${report.comparison.from.found} / ${report.comparison.from.checked} ответов`:<><span className={`change ${trendTone(report.trend.delta)}`} title={trendText(report.trend)}>{report.trend.delta === null ? "Нет данных для сравнения" : `${report.trend.delta > 0 ? "↑ +" : report.trend.delta < 0 ? "↓ " : ""}${report.trend.delta} п.п.`}</span><span>к предыдущему периоду</span></>}</div></div>
        <div className="metric"><div className="metric-label">{compare?`Конечная дата · ${shortDate(report.date_to)}`:"Ответы с упоминанием"}</div><div className="metric-value">{compare?pct(report.comparison.to.visibility_pct):<>{report.summary.found}<span className="muted-value">/ {report.summary.checked}</span></>}</div><div className="metric-caption">{compare?`${report.comparison.to.found} / ${report.comparison.to.checked} ответов`:"В выбранном периоде"}</div></div>
        <div className="metric"><div className="metric-label">{compare?"Изменение упоминаемости":"Запросов в отчёте"}</div><div className={`metric-value ${compare?trendTone(report.trend.delta):""}`}>{compare?(report.trend.delta === null ? "—" : `${report.trend.delta > 0 ? "↑ +" : report.trend.delta < 0 ? "↓ " : ""}${report.trend.delta} п.п.`):<>{report.rows.filter(q => Object.keys(q.latest).length).length}<span className="muted-value">/ {report.total}</span></>}</div><div className="metric-caption">{compare?`${shortDate(report.date_from)} → ${shortDate(report.date_to)}`:`${report.services.length} ИИ-системы · дней с данными: ${report.timeline.filter(day => day.checked || day.skipped || day.issues).length}`}</div></div>
      </section><div className="dashboard-grid"><ReportChart days={report.timeline} services={report.services} available={availableServices} choose={chooseServices}/><section className="panel"><div className="panel-head"><h2>По ИИ-системам</h2><span className="note">{compare?"Конечная дата":"За период"}</span></div><div className="service-list">{report.services.map(id => <div className="service-row" key={id} style={{"--series":serviceColors[id]} as CSSProperties}><ServiceMark id={id}/><strong>{name(id)}</strong><span className="value">{pct(report.service_stats[id].current.visibility_pct)}</span><div className="bar-track"><div className="bar-fill" style={{width:`${report.service_stats[id].current.visibility_pct||0}%`}}/></div></div>)}</div><div className="panel-foot"><span>Сравнить ответы систем</span><a href={`#/project/${projectId}/queries`}>К запросам →</a></div></section></div>
      <section className="panel report-panel"><div className="panel-head report-head"><h2>Упоминаемость по запросам <span className="count">{report.total}</span></h2><span className="note">{compare?"Конечная дата к начальной":"Изменение к предыдущему периоду"}</span></div><div className="table-toolbar"><label className="search-box"><Search size={14}/><input aria-label="Поиск запросов в отчёте" placeholder="Поиск по запросам" value={search} onChange={e => setSearch(e.target.value)}/></label><AppChoice label="Результат проверки" value={status} options={[{value:"",label:"Все результаты"},{value:"found",label:"Есть упоминание"},{value:"not_found",label:"Нет упоминания"}]} change={setStatus}/><div className="right"><a className="text-link" href={`#/project/${projectId}/queries`}>Все запросы →</a></div></div>
        <div className="table-wrap continuous-report" tabIndex={0} role="region" aria-label="Запросы по группам"><table><thead><tr><th className="query-heading">Запрос</th>{report.services.map(id => <th scope="col" className="query-cell" key={id}><span className="table-service"><ServiceMark id={id}/>{name(id)}</span></th>)}<th scope="col"><button className="sort-btn" aria-pressed={sort} onClick={() => setSort(value => !value)}>Упоминаемость ↓</button></th></tr></thead>{groups.map(groupName => {const grouped=rows.filter(q => q.group_tag === groupName);return <tbody key={groupName}><tr className="report-group-heading"><th scope="rowgroup" colSpan={report.services.length+2}><span>{groupName || "Без группы"}</span><span className="group-total">{grouped.length}</span></th></tr>{grouped.map(query => <tr key={query.id}><td className="query-text"><button disabled={loading || stale || !Object.keys(query.latest).length} onClick={() => {const result=Object.values(query.latest)[0];if(result)openResult(result.id)}}>{query.text}</button></td>{report.services.map(id => <td className="query-cell" key={id}>{compare?<>{cellButton(query.cells[report.date_from]?.[id],query,id,report.date_from)}<span className="muted"> → </span>{cellButton(query.cells[report.date_to]?.[id],query,id,report.date_to)}</>:cellButton(query.latest[id],query,id)}</td>)}<td className="rate-cell"><Rate trend={query.trend} from={compare ? report.date_to : report.date_from} to={report.date_to}/></td></tr>)}</tbody>})}</table>{!rows.length && <div className="empty-state"><h2>Запросы не найдены</h2><p>Измените фильтры или добавьте запросы в проект.</p></div>}</div><div className="table-footer"><span>{rows.length} запросов · групп: {groups.length} · {compare?"Сравнение двух дат":"В ячейках — последняя проверка за период"}</span><span>Непрерывный список</span></div>
      </section><p className="page-note">Упоминаемость — доля ответов с брендом среди успешных проверок. Отсутствие AI-блока исключено из знаменателя. Цвет и стрелка показывают изменение {compare ? "конечной даты к начальной" : "к предыдущему периоду той же длины"}; без полной базы для сравнения изменение не рассчитывается. Исторические незавершённые проверки доступны для просмотра.</p>
    </>}
    <dialog className="ws-dialog report-detail" ref={dialog} aria-labelledby="result-title" onClose={()=>{detailRequest.current++}}><div className="ws-dialog-head"><h2 id="result-title">Ответ ИИ</h2><button className="cc-button icon" aria-label="Закрыть ответ" onClick={()=>closeDetail()}><X size={18}/></button></div>{detailError&&<p className="cc-alert" role="alert">{detailError}</p>}{detail?<><p className="ws-note">{name(detail.service)} · {shortDate(detail.scan_date)}.{detail.scan_date.slice(0,4)} · {statuses[detail.status]||detail.status}</p><h3>{detail.query_text}</h3>{detail.evidence_quote&&<blockquote>{detail.evidence_quote}</blockquote>}<div className="report-answer">{detail.answer_evidence?<AnswerEvidenceView key={detail.id} evidence={detail.answer_evidence} brand={detail.highlight}/>:detail.answer_text&&<AnswerContent text={detail.answer_text} service={detail.service} sources={detail.sources}/>}<ResultIssue status={detail.status} error={detail.error_message} answer={detail.answer_text}/></div><p className="ws-note">Типы упоминания: {detail.mention_types?.join(", ") || "нет"}</p><h3>Источники</h3>{detail.answer_evidence?<HighlightedSources sources={detail.sources} brand={detail.highlight}/>:<SourceList sources={detail.sources}/>}{(detail.status === "found" || detail.status === "not_found") && detail.answer_text && <ScanFeedbackForm key={detail.id} token={token} base={base} id={detail.id} status={detail.status} feedback={detail.feedback} onSaved={feedback => setDetail(current => current?.id === detail.id ? {...current, feedback} : current)} />}{detail.check_id&&detail.has_screenshot!==false&&!detail.answer_evidence&&<button className="cc-button" onClick={()=>openShot(detail.check_id!)}>Открыть скриншот</button>}{shot&&<img className="report-shot" src={shot} alt="Скриншот ответа ИИ"/>}</>:!detailError&&<p role="status">Загружаем ответ…</p>}</dialog>
  </section>
}
