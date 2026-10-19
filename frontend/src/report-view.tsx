import { ScanFeedbackForm, type ScanFeedback, type FeedbackResult } from "./scan-feedback"
import { AnswerContent, ResultIssue } from "./components/answer-content"
import { AnswerEvidenceView, EvidenceSources, type AnswerEvidence, type BrandHighlight } from "./components/answer-evidence"
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { Download, RefreshCw, Search, X } from "lucide-react"
import { accountDownload, accountRequest } from "./account-api"
import { today } from "./lib/dates"
import { ReportCalendar, shortDate, defaultDateSelection, restoreDateSelection, type ReportDateSelection } from "./report-calendar"
import { AppChoice } from "./app-choice"
import { ReportChart } from "./report-chart"
import { ServiceMark, isCurrentService, serviceColors, serviceName as name } from "./service-mark"
import { SCAN_SERVICES } from "./lib/scan-preferences"

type Stats = { found: number; checked: number; issues: number; skipped: number; visibility_pct: number | null }
export type Trend = { current: Stats; previous: Stats; delta: number | null; relative: number | null; baseline_complete: boolean; baseline_from: string | null; baseline_to: string | null }
type Cell = { id: number; status: string; found: boolean; date?: string }
type Query = { id: string; text: string; group_tag: string; cells: Record<string,Record<string,Cell>>; latest: Record<string,Cell>; trend: Trend }
type Source = { domain: string; count: number; own: boolean; urls: string[]; queries: number; services: string[]; results: { id: number; query_text: string; date: string; service: string }[] }
type Report = { date_from: string; date_to: string; available_dates: string[]; dates: string[]; visible_dates: string[]; services: string[]; available_services: string[]; groups: string[]; summary: Stats; trend: Trend; service_stats: Record<string,Trend>; comparison: { from: Stats; to: Stats; delta: number | null }; timeline: (Stats & {date: string; services: Record<string,Stats>})[]; total: number; rows: Query[]; sources: Source[] }
type Detail = { id: number; feedback: ScanFeedback | null; mention_types: string[]; query_text: string; service: string; scan_date: string; status: string; original_status: string; answer_text: string | null; error_message?: string | null; evidence_quote: string | null; sources: string[]; check_id: string | null; answer_evidence?: AnswerEvidence | null; highlight?: BrandHighlight; has_screenshot?: boolean }
const statuses: Record<string,string> = {found:"Упоминание",not_found:"Нет упоминания",skipped:"Нет AI-блока",error:"Требует внимания",captcha:"Требует внимания",auth_required:"Требует внимания",limit_reached:"Требует внимания"}
const pct = (value: number | null) => value == null ? "—" : `${value}%`
const cellLabel = (cell: Cell) => cell.status === "found" && !cell.found ? "Не учитывается по фильтрам" : statuses[cell.status] || cell.status
export const trendTone = (delta: number | null) => delta === null || delta === 0 ? "neutral" : delta > 0 ? "positive" : "negative"
export function trendText(trend: Trend) {
  const delta = trend.delta
  return delta === null ? "Нет полных данных для сравнения" : `${delta > 0 ? "Рост" : delta < 0 ? "Снижение" : "Без изменения"}: ${delta > 0 ? "+" : ""}${delta} п.п.${trend.relative === null ? "" : ` (${trend.relative > 0 ? "+" : ""}${trend.relative}%)`}`
}
export function reportRows(rows: Query[], status: string, sort: boolean, dates?: string[]) {
  const filtered = rows.filter(query => {
    const cells = dates ? dates.flatMap(day => Object.values(query.cells[day] || {})) : Object.values(query.latest)
    if (!status) return true
    if (!dates) return status === "found" ? query.trend.current.found > 0 : query.trend.current.checked > query.trend.current.found
    return cells.some(cell => status === "found" ? cell.found : ["found","not_found","skipped"].includes(cell.status) && !cell.found)
  })
  return sort ? [...filtered].sort((a,b) => (b.trend.current.visibility_pct ?? -1) - (a.trend.current.visibility_pct ?? -1)) : filtered
}

function Rate({ trend, from, to }: { trend: Trend; from: string; to: string }) {
  const [position, setPosition] = useState<{left:number;top:number}>({left:10,top:10})
  const text = trendText(trend)
  return <><td className={`rate-percent ${trendTone(trend.delta)}`}><span className="rate-number">{trend.delta === null || trend.delta === 0 ? "" : trend.delta > 0 ? "↑ " : "↓ "}{pct(trend.current.visibility_pct)}</span></td><td className={`rate-dynamic ${trendTone(trend.delta)}`}><span className="rate-hover" tabIndex={0} aria-label={text} onFocus={event => { const rect = event.currentTarget.getBoundingClientRect(); setPosition({left:Math.max(10,Math.min(rect.left,innerWidth-290)),top:Math.max(10,rect.top-110)}) }} onMouseEnter={event => { const rect = event.currentTarget.getBoundingClientRect(); setPosition({left:Math.max(10,Math.min(rect.left,innerWidth-290)),top:Math.max(10,rect.top-110)}) }}><span className="table-progress"><span style={{width:`${trend.current.visibility_pct || 0}%`}}/></span><span className="trend-tooltip" role="tooltip" style={position}><strong>{text}</strong><span>{trend.baseline_from && trend.baseline_to ? `${shortDate(trend.baseline_from)} — ${shortDate(trend.baseline_to)}: ${pct(trend.previous.visibility_pct)}` : "Предыдущий период недоступен"}</span><span>{shortDate(from)} — {shortDate(to)}: {pct(trend.current.visibility_pct)}</span></span></span></td></>
}

export function reportRange(saved: unknown): {from:string;to:string}|null {
  if (!saved || typeof saved !== "object") return null
  const {from,to} = saved as {from:unknown;to:unknown}
  const validDate = (value: unknown): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !value.startsWith("0000") && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value
  if (!validDate(from) || !validDate(to) || from > to || (Date.parse(to)-Date.parse(from))/86400000 > 365) return null
  return {from,to}
}
export function reportSelection(saved: unknown, allowed = SCAN_SERVICES.map(service=>service.id)) {
  if (!Array.isArray(saved) || !saved.every(id=>typeof id === "string")) return null
  const services = [...new Set(saved.filter(id=>isCurrentService(id) && allowed.includes(id)))]
  return services.length ? services : null
}
export function ReportView({ token, projectId, projectServices, sourcesOnly = false, canEdit = true, scanControl }: {token:string;projectId:string;projectServices:string[];sourcesOnly?:boolean;canEdit?:boolean;scanControl?:ReactNode}) {
  const availableServices = [...new Set(projectServices.filter(isCurrentService))]
  const rangeKey = `aimt.report.range.${projectId}`
  const [range,setRange] = useState<{from:string;to:string}|null>(() => {
    try { return reportRange(JSON.parse(localStorage.getItem(rangeKey) || "null")) } catch { return null }
  })
  const [dateSelection,setDateSelection] = useState<ReportDateSelection>(() => {
    try { const saved=JSON.parse(localStorage.getItem(rangeKey) || "null"); return range ? restoreDateSelection(saved?.selection,range.from,range.to) : defaultDateSelection } catch { return defaultDateSelection }
  })
  const compare = dateSelection.mode === "two"
  function chooseRange(from: string, to: string, selection: ReportDateSelection) {
    setDateSelection(selection)
    const next = {from,to}; setRange(next)
    try { localStorage.setItem(rangeKey,JSON.stringify({...next,selection})) } catch { /* Private browsing may disable storage. */ }
  }
  const [cards,setCards] = useState(true), [external,setExternal] = useState(true)
  const serviceKey = `aimt.report.services.${projectId}`
  const [selectedServices,setSelectedServices] = useState<string[]|null>(() => {
    try { return reportSelection(JSON.parse(sessionStorage.getItem(serviceKey) || "null")) } catch { return null }
  })
  const selection = reportSelection(selectedServices, availableServices)
  const [group,setGroup] = useState("*"), [querySearch,setQuerySearch] = useState(""), [status,setStatus] = useState(""), [sort,setSort] = useState(false)
  const [sourceSearch,setSourceSearch] = useState("")
  const [search,setSearch] = sourcesOnly ? [sourceSearch,setSourceSearch] : [querySearch,setQuerySearch]
  const [sourceKind,setSourceKind] = useState("all"), [expandedSource,setExpandedSource] = useState("")
  const [loadedReport,setReport] = useState<Report|null>(null), [error,setError] = useState("")
  const report = loadedReport && {...loadedReport,services:loadedReport.services.filter(id=>availableServices.includes(id))}
  const [loading,setLoading] = useState(true), [tick,setTick] = useState(0), [exporting,setExporting] = useState("")
  const [detail,setDetail] = useState<(Detail & {requestId:number})|null>(null), [detailError,setDetailError] = useState(""), [shot,setShot] = useState("")
  const dialog = useRef<HTMLDialogElement>(null), detailRequest = useRef(0), mounted = useRef(true)
  const [loadedFilters, setLoadedFilters] = useState("")
  const [historyWindow,setHistoryWindow] = useState({filters:"",offset:0,limit:14})
  const base = `/control/projects/${encodeURIComponent(projectId)}/mentions`
  const params = new URLSearchParams({include_cards:String(cards),include_external:String(external),compare:String(compare),date_to:range?.to||today()})
  if (!sourcesOnly) params.set("search",search)
  params.set("services",(selection || availableServices).join(","))
  if (range?.from) params.set("date_from",range.from)
  params.set("max_dates",String(dateSelection.maxDates))
  params.set("date_mode",dateSelection.mode === "monthly" ? "monthly" : "period")
  if (dateSelection.mode === "custom") params.set("report_dates",dateSelection.picked.join(","))
  if (group !== "*") params.set("group",group)
  const historyFilters = params.toString()
  const historyOffset = historyWindow.filters === historyFilters ? historyWindow.offset : 0
  if (!sourcesOnly && !compare) {
    params.set("date_offset",String(historyOffset))
    params.set("date_limit",String(historyWindow.filters === historyFilters ? historyWindow.limit : 14))
  }
  const filters = params.toString()
  const hasServices = availableServices.length > 0
  const stale = loadedFilters !== filters
  function chooseServices(next: string[]|null) {
    setSelectedServices(next); setLoading(true)
    try { if(next)sessionStorage.setItem(serviceKey,JSON.stringify(next));else sessionStorage.removeItem(serviceKey) } catch { /* Private browsing may disable storage. */ }
  }
  useEffect(() => {
    let alive = true
    if (!hasServices) {setReport(null);setLoadedFilters(filters);setLoading(false);setError("");return}
    setLoading(true)
    const timer = setTimeout(() => {
      accountRequest<Report>(`${base}/overview?${filters}`,token).then(data => { if(alive){setLoadedFilters(filters);setReport({...data,services:data.services.filter(id=>data.available_services.includes(id))});setError("")} }).catch(e => {if(alive)setError(e.message)}).finally(() => {if(alive)setLoading(false)})
    },180)
    return () => {alive=false;clearTimeout(timer)}
  },[base,filters,hasServices,tick,token])
  useEffect(() => { const timer=setInterval(() => {if(document.visibilityState === "visible")setTick(n => n+1)},20000);return () => clearInterval(timer) },[])
  useEffect(() => () => {mounted.current=false;detailRequest.current++},[])
  function closeDetail() { detailRequest.current++; dialog.current?.close() }
  async function openResult(id:number) {
    const requestId=++detailRequest.current;setDetail(null);setDetailError("");setShot("");dialog.current?.showModal()
    try { const data=await accountRequest<Detail>(`${base}/results/${id}`,token);if(mounted.current && requestId===detailRequest.current && dialog.current?.open)setDetail({...data,requestId}) } catch(e) {if(mounted.current && requestId===detailRequest.current && dialog.current?.open)setDetailError(e instanceof Error?e.message:"Не удалось загрузить ответ")}
  }
  function feedbackSaved(id:number, requestId:number, result:FeedbackResult) {
    if (!mounted.current) return
    if (requestId === detailRequest.current && dialog.current?.open)
      setDetail(current => current?.id === id ? {...current,...result} : current)
    setLoading(true); setTick(value => value+1)
  }
  async function exportReport(kind:string) {
    if (stale || loading || !report?.services.length) return
    setExporting(kind);setError("")
    const exportFilters = new URLSearchParams(filters)
    exportFilters.set("services",report.services.join(","))
    const path = sourcesOnly ? `${base}/overview/export/sources?${exportFilters}&${new URLSearchParams({source_kind:sourceKind,source_search:search})}` : `${base}/export/${kind}?${exportFilters}`
    try {await accountDownload(path,token,`${kind}-${report?.date_from}-${report?.date_to}.xlsx`)}
    catch(e) {if(mounted.current)setError(e instanceof Error?e.message:"Ошибка выгрузки")}
    finally {if(mounted.current)setExporting("")}
  }
  async function openShot(id:number) {const requestId=detailRequest.current;setShot("");try{const data=await accountRequest<{url:string}>(`${base}/results/${id}/screenshot`,token);if(mounted.current && requestId===detailRequest.current && dialog.current?.open)setShot(data.url)}catch(e){if(mounted.current && requestId===detailRequest.current && dialog.current?.open)setDetailError(e instanceof Error?e.message:"Не удалось открыть снимок")}}
  const dates = report ? [...report.dates].reverse() : []
  const visibleDates = report ? [...report.visible_dates].reverse() : []
  const dateStart = visibleDates.length ? dates.indexOf(visibleDates[0]) : 0
  const dateEnd = dateStart + visibleDates.length
  const rows = report ? reportRows(report.rows,status,sort,compare ? dates : undefined) : []
  const groups = [...new Set(rows.map(query => query.group_tag))]
  const sources = report?.sources.filter(source => (sourceKind === "all" || source.own === (sourceKind === "own")) && source.domain.toLowerCase().includes(search.toLowerCase())) || []
  function scrollHistory(element:HTMLDivElement) {
    if (!report || compare) return
    const width = report.services.length * 44
    if (!width) return
    const queryWidth = Number.parseFloat(getComputedStyle(element).getPropertyValue("--history-query-width"))
    const offset = Math.max(0,Math.floor((element.scrollLeft-138)/width)-1)
    const limit = Math.min(64,Math.max(4,Math.ceil((element.clientWidth-queryWidth)/width)+3))
    setHistoryWindow(current => current.filters === historyFilters && current.offset === offset && current.limit === limit ? current : {filters:historyFilters,offset,limit})
  }
  function cellButton(cell:Cell|undefined, query:Query, id:string, day?:string) {
    return <button disabled={!cell || loading || stale} className={cell?.found?"found":""} title={cell ? cellLabel(cell) : "Не проверялось"} aria-label={`${query.text} · ${name(id)} · ${day || cell?.date || ""} · ${cell ? cellLabel(cell) : "Не проверялось"}`} onClick={() => cell && openResult(cell.id)}>{cell?.found?"✓":cell?.status==="skipped"?"н/д":cell && !["found","not_found"].includes(cell.status)?"!":"—"}</button>
  }
  return <section aria-busy={loading || stale}>
    <div className="filterbar">{scanControl}{report && <ReportCalendar from={range?.from||report.date_from} to={range?.to||report.date_to} available={report.available_dates} selection={{...dateSelection,mode:compare ? "two" : dateSelection.mode === "two" ? "period" : dateSelection.mode}} change={chooseRange}/>}
      <AppChoice label="Группа запросов" value={group} searchable options={[{value:"*",label:"Все группы"},{value:"",label:"Без группы"},...(report?.groups || []).map(label => ({value:label,label}))]} change={setGroup}/>
      <label className="report-switch"><input type="checkbox" role="switch" checked={external} onChange={e => setExternal(e.target.checked)}/>Внешние источники</label>
      <label className="report-switch"><input type="checkbox" role="switch" checked={cards} onChange={e => setCards(e.target.checked)}/>Учитывать карточки</label>
      <span className="spacer"/><button className="btn" disabled={!!exporting||!report?.services.length||loading||stale} onClick={() => exportReport(sourcesOnly?"sources":"mentions")}><Download size={14}/>{exporting?"Готовим…":"Экспорт XLSX"}</button><button className="btn icon-only" aria-label="Обновить отчёт" disabled={loading || stale} onClick={() => setTick(n=>n+1)}><RefreshCw size={14}/></button>
    </div>
    {!external && <p className="notice" role="status">Учитываются только ответы со ссылкой на домены бренда из настроек проекта. Если домены не указаны, упоминания не засчитываются.</p>}
    {error && <p className="cc-alert" role="alert">{error}<button className="btn" onClick={() => setTick(n=>n+1)}>Повторить</button></p>}
    {!report ? <p className="empty-state" role="status">{loading ? "Загрузка отчёта…" : !availableServices.length ? "Выберите ИИ-системы в настройках проекта." : "Отчёт недоступен"}</p> : sourcesOnly ? <>
      <div className="stat-inline"><span><strong>{sources.length}</strong> источников</span><span>Учитываются ответы с упоминанием бренда</span></div><section className="panel"><div className="table-toolbar"><label className="search-box"><Search size={14}/><input aria-label="Поиск источника" placeholder="Найти домен" value={search} onChange={e => setSearch(e.target.value)}/></label><AppChoice label="Тип источника" value={sourceKind} options={[{value:"all",label:"Все источники"},{value:"own",label:"Сайт бренда"},{value:"external",label:"Внешние источники"}]} change={setSourceKind}/></div><div className="table-wrap"><table><thead><tr><th>Домен</th><th>Тип</th><th>Ответов со ссылкой</th><th>Запросы</th><th>ИИ-системы</th><th/></tr></thead>{sources.map(source => <tbody key={source.domain}><tr><td><a href={source.urls[0]} target="_blank" rel="noopener noreferrer">{source.domain} ↗</a></td><td><span className={`badge ${source.own?"blue":""}`}>{source.own?"Сайт бренда":"Внешний источник"}</span></td><td>{source.count}</td><td>{source.queries}</td><td><div className="system-marks">{source.services.map(id => <span key={id} title={name(id)}><ServiceMark id={id}/></span>)}</div></td><td><button className="text-link" aria-expanded={expandedSource === source.domain} onClick={() => setExpandedSource(expandedSource === source.domain ? "" : source.domain)}>Ответы →</button></td></tr>{expandedSource === source.domain && <tr><td colSpan={6}><div className="source-answers"><small>Последние {source.results.length} ответов со ссылкой</small>{source.results.map(result => <button className="btn" key={result.id} disabled={loading || stale} onClick={() => openResult(result.id)}>{shortDate(result.date)} · {name(result.service)} · {result.query_text}</button>)}</div></td></tr>}</tbody>)}</table>{!sources.length && !loading && !stale && <div className="empty-state">Источников по выбранным фильтрам нет.</div>}</div></section><p className="page-note">Число ответов со ссылкой на домен; несколько ссылок из одного ответа считаются один раз. Источники показываются только в ответах с упоминанием бренда. XLSX содержит домены и показатели с учётом выбранного типа источника и поиска.</p>
    </> : <>
      <section className="metrics" aria-label="Основные показатели">
        <div className="metric primary-metric"><div className="metric-label">{compare?`Начальная дата · ${shortDate(report.date_from)}`:"Упоминаемость"}</div><div className="metric-value">{pct(compare?report.comparison.from.visibility_pct:report.summary.visibility_pct)}</div><div className="metric-caption">{compare?`${report.comparison.from.found} / ${report.comparison.from.checked} проверок`:<><span className={`change ${trendTone(report.trend.delta)}`} title={trendText(report.trend)}>{report.trend.delta === null ? "Нет данных для сравнения" : `${report.trend.delta > 0 ? "↑ +" : report.trend.delta < 0 ? "↓ " : ""}${report.trend.delta} п.п.`}</span><span>к предыдущему периоду</span></>}</div></div>
        <div className="metric"><div className="metric-label">{compare?`Конечная дата · ${shortDate(report.date_to)}`:"Ответы с упоминанием"}</div><div className="metric-value">{compare?pct(report.comparison.to.visibility_pct):<>{report.summary.found}<span className="muted-value">/ {report.summary.checked}</span></>}</div><div className="metric-caption">{compare?`${report.comparison.to.found} / ${report.comparison.to.checked} проверок`:"В выбранном периоде"}</div></div>
        <div className="metric"><div className="metric-label">{compare?"Изменение упоминаемости":"Запросов в отчёте"}</div><div className={`metric-value ${compare?trendTone(report.trend.delta):""}`}>{compare?(report.trend.delta === null ? "—" : `${report.trend.delta > 0 ? "↑ +" : report.trend.delta < 0 ? "↓ " : ""}${report.trend.delta} п.п.`):<>{report.rows.filter(q => Object.keys(q.latest).length).length}<span className="muted-value">/ {report.total}</span></>}</div><div className="metric-caption">{compare?`${shortDate(report.date_from)} → ${shortDate(report.date_to)}`:`${report.services.length} ИИ-системы · дней с данными: ${report.timeline.filter(day => day.checked || day.skipped || day.issues).length}`}</div></div>
      </section><div className="dashboard-grid"><ReportChart days={report.timeline} services={selection || availableServices} available={availableServices} choose={chooseServices}/><section className="panel"><div className="panel-head"><h2>По ИИ-системам</h2><span className="note">{compare?"Конечная дата":"За период"}</span></div><div className="service-list">{report.services.map(id => <div className="service-row" key={id} style={{"--series":serviceColors[id]} as CSSProperties}><ServiceMark id={id}/><strong>{name(id)}</strong><span className="value">{pct(report.service_stats[id].current.visibility_pct)}</span><div className="bar-track"><div className="bar-fill" style={{width:`${report.service_stats[id].current.visibility_pct||0}%`}}/></div></div>)}</div><div className="panel-foot"><span>Сравнить ответы систем</span>{canEdit&&<a href={`#/project/${projectId}/queries`}>К запросам →</a>}</div></section></div>
      <section className="panel report-panel"><div className="panel-head report-head"><h2>Упоминаемость по запросам <span className="count">{report.total}</span></h2><span className="note">{compare?"Конечная дата к начальной":"Изменение к предыдущему периоду"}</span></div><div className="table-toolbar"><label className="search-box"><Search size={14}/><input aria-label="Поиск запросов в отчёте" placeholder="Поиск по запросам" value={search} onChange={e => setSearch(e.target.value)}/></label><AppChoice label="Результат в выбранных датах" value={status} options={[{value:"",label:"Все результаты"},{value:"found",label:"Есть упоминание"},{value:"not_found",label:"Нет упоминания"}]} change={setStatus}/>{canEdit&&<div className="right"><a className="text-link" href={`#/project/${projectId}/queries`}>Все запросы →</a></div>}</div>
        <div className="table-wrap continuous-report" tabIndex={0} role="region" aria-label="История проверок по датам, прокрутка вправо" onScroll={event => scrollHistory(event.currentTarget)}><table>
          <colgroup><col className="history-query"/><col className="history-percent"/><col className="history-dynamic"/>{dateStart > 0 && <col style={{width:dateStart*report.services.length*44}}/>}{visibleDates.flatMap(day => report.services.map(id => <col className="history-service" key={`${day}-${id}`}/>))}{dateEnd < dates.length && <col style={{width:(dates.length-dateEnd)*report.services.length*44}}/>}</colgroup>
          <thead><tr><th rowSpan={2} scope="col" className="query-heading">Запрос</th><th colSpan={2} scope="colgroup" className="mention-heading"><button className="sort-btn" aria-pressed={sort} onClick={() => setSort(value => !value)}>Упоминаемость ↓</button></th>{dateStart > 0 && <th rowSpan={2} aria-hidden="true" className="history-spacer"/>}{visibleDates.map(day => <th scope="colgroup" className="history-date" colSpan={report.services.length} key={day}>{shortDate(day)}.{day.slice(0,4)}</th>)}{dateEnd < dates.length && <th rowSpan={2} aria-hidden="true" className="history-spacer"/>}</tr>
            <tr><th scope="col" className="rate-heading">%</th><th scope="col" className="rate-heading">Динамика</th>{visibleDates.flatMap(day => report.services.map((id,index) => <th scope="col" className={`query-cell ${index === 0 ? "date-start" : ""}`} key={`${day}-${id}`} aria-label={`${name(id)} · ${day}`}><span className="table-service" title={name(id)}><ServiceMark id={id}/></span></th>))}</tr></thead>
          {groups.map(groupName => {const grouped=rows.filter(q => q.group_tag === groupName);return <tbody key={groupName}><tr className="report-group-heading"><th scope="rowgroup" colSpan={visibleDates.length*report.services.length+3+Number(dateStart>0)+Number(dateEnd<dates.length)}><div className="history-group-label"><span>{groupName || "Без группы"}</span><span className="group-total">{grouped.length}</span></div></th></tr>{grouped.map(query => <tr key={query.id}>
            <td className="query-text"><button disabled={loading || stale || !Object.keys(query.latest).length} onClick={() => {const result=Object.values(query.latest)[0];if(result)openResult(result.id)}}>{query.text}</button></td>
            <Rate trend={query.trend} from={compare ? report.date_to : report.date_from} to={report.date_to}/>
            {dateStart > 0 && <td aria-hidden="true" className="history-spacer"/>}{visibleDates.flatMap(day => report.services.map((id,index) => <td className={`query-cell ${index === 0 ? "date-start" : ""}`} key={`${day}-${id}`}>{cellButton(query.cells[day]?.[id],query,id,day)}</td>))}{dateEnd < dates.length && <td aria-hidden="true" className="history-spacer"/>}
          </tr>)}</tbody>})}</table>{!loading && !stale && !rows.length && <div className="empty-state"><h2>Запросы не найдены</h2><p>Измените фильтры или добавьте запросы в проект.</p></div>}{!loading && !stale && !!rows.length && !dates.length && <div className="empty-state">В выбранном периоде нет проверок.</div>}</div>
        <div className="table-footer"><span>{rows.length} запросов · групп: {groups.length} · {dates.length} дат · последняя проверка за день</span><span role="status">{loading || stale ? "Обновляем отчёт…" : "Новые даты слева · прокрутка вправо →"}</span></div>
      </section><p className="page-note">Упоминаемость — доля проверок с упоминанием бренда. Отсутствие AI-блока считается проверкой без упоминания. Технические ошибки исключены из расчёта. Цвет и стрелка показывают изменение {compare ? "конечной даты к начальной" : "к предыдущему периоду той же длины"}; без полной базы для сравнения изменение не рассчитывается. Исторические незавершённые проверки доступны для просмотра.</p>
    </>}
    <dialog className="ws-dialog report-detail" ref={dialog} aria-labelledby="result-title" onClose={()=>{detailRequest.current++}}><div className="ws-dialog-head"><h2 id="result-title">Ответ ИИ</h2><button className="cc-button icon" aria-label="Закрыть ответ" onClick={()=>closeDetail()}><X size={18}/></button></div>{detailError&&<p className="cc-alert" role="alert">{detailError}</p>}{detail?<><p className="ws-note">{name(detail.service)} · {shortDate(detail.scan_date)}.{detail.scan_date.slice(0,4)} · {statuses[detail.status]||detail.status}</p>{detail.status !== detail.original_status && <p className="ws-note">Ручное исправление · оценка сервиса: {statuses[detail.original_status] || detail.original_status}</p>}<h3>{detail.query_text}</h3>{detail.evidence_quote&&<blockquote>{detail.evidence_quote}</blockquote>}<div className="report-answer">{detail.answer_evidence?<AnswerEvidenceView key={detail.id} evidence={detail.answer_evidence} service={detail.service} sources={detail.sources} brand={detail.highlight}/>:detail.answer_text&&<AnswerContent text={detail.answer_text} service={detail.service} sources={detail.sources}/>}<ResultIssue status={detail.status} error={detail.error_message} answer={detail.answer_text}/></div><p className="ws-note">Типы упоминания: {detail.mention_types?.join(", ") || "нет"}</p><EvidenceSources evidence={detail.answer_evidence} answerText={detail.answer_text} service={detail.service} sources={detail.sources} brand={detail.highlight}/>{canEdit && (detail.status === "found" || detail.status === "not_found") && detail.answer_text && <ScanFeedbackForm key={detail.id} token={token} base={base} id={detail.id} status={detail.original_status} feedback={detail.feedback} onSaved={result => feedbackSaved(detail.id,detail.requestId,result)} />}{detail.check_id&&detail.has_screenshot!==false&&!detail.answer_evidence&&<button className="cc-button" onClick={()=>openShot(detail.id)}>Открыть скриншот</button>}{shot&&<img className="report-shot" src={shot} alt="Скриншот ответа ИИ"/>}</>:!detailError&&<p role="status">Загружаем ответ…</p>}</dialog>
  </section>
}
