import { Fragment, useEffect, useRef, useState } from "react"
import { Download, FileSearch, RefreshCw, Search, X } from "lucide-react"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { accountDownload, accountRequest } from "./account-api"
import { SCAN_SERVICES } from "./lib/scan-preferences"
import { ReportCalendar, shortDate } from "./report-calendar"

type Stats = { found: number; checked: number; issues: number; skipped: number; visibility_pct: number | null }
type Cell = { id: number; status: string; found: boolean }
type Report = { date_from: string; date_to: string; available_dates: string[]; dates: string[]; visible_dates: string[]; services: string[]; available_services?: string[]; groups: string[]; summary: Stats; comparison: { from: Stats; to: Stats; delta: number | null }; timeline: (Stats & {date: string; services: Record<string, Stats>})[]; total: number; rows: {id:string;text:string;group_tag:string;cells:Record<string,Record<string,Cell>>}[] }
type Detail = { query_text: string; service: string; scan_date: string; status: string; answer_text: string | null; evidence_quote: string | null; sources: string[]; check_id: string | null }
const name = (id: string) => SCAN_SERVICES.find(s => s.id === id)?.label || id
const shortNames: Record<string,string> = {google_aio:"Google",chatgpt:"ChatGPT",perplexity:"Perplexity",alice:"Алиса",yandex_neuro:"Нейро"}
const colors: Record<string,string> = {google_aio:"#8bb7fb",chatgpt:"#79d8c0",perplexity:"#f2c585",alice:"#c995f4",yandex_neuro:"#f795aa"}
const statuses: Record<string,string> = {found:"Упоминание",not_found:"Нет упоминания",skipped:"Нет AI-блока",error:"Ошибка",captcha:"Капча",auth_required:"Нужен вход",limit_reached:"Лимит сервиса"}
const pct = (value: number | null) => value == null ? "—" : `${value}%`
const cellLabel = (cell: Cell) => cell.status === "found" && !cell.found ? "Карточки исключены" : statuses[cell.status] || cell.status
const safeUrl = (url: string) => { try { return ["https:","http:"].includes(new URL(url).protocol) } catch { return false } }

export function ReportView({token,projectId}:{token:string;projectId:string}) {
  const [range,setRange] = useState<{from:string;to:string}|null>(null)
  const [compare,setCompare] = useState(false), [cards,setCards] = useState(true)
  const serviceKey = `aimt.report.services.${projectId}`
  const [selectedServices,setSelectedServices] = useState<string[]|null>(()=>{
    try { const saved: unknown = JSON.parse(sessionStorage.getItem(serviceKey) || "null")
      return Array.isArray(saved) && saved.length && saved.every(s=>typeof s === "string" && s in shortNames) ? [...new Set(saved)] : null
    } catch { return null }
  })
  const [group,setGroup] = useState("*"), [search,setSearch] = useState("")
  const [offset,setOffset] = useState(0), [dateOffset,setDateOffset] = useState(0)
  const [report,setReport] = useState<Report|null>(null), [error,setError] = useState("")
  const [loading,setLoading] = useState(true), [tick,setTick] = useState(0), [exporting,setExporting] = useState("")
  const [detail,setDetail] = useState<Detail|null>(null), [detailError,setDetailError] = useState(""), [shot,setShot] = useState("")
  const dialog = useRef<HTMLDialogElement>(null), detailRequest = useRef(0)
  const base = `/control/projects/${encodeURIComponent(projectId)}/mentions`
  const params = new URLSearchParams({include_cards:String(cards),compare:String(compare),search})
  if(selectedServices)params.set("services",selectedServices.join(","))
  if(range){params.set("date_from",range.from);params.set("date_to",range.to)}
  if(group!=="*")params.set("group",group)
  const filters = params.toString()
  function chooseServices(next: string[]|null) {
    setSelectedServices(next); setLoading(true)
    try { if(next)sessionStorage.setItem(serviceKey,JSON.stringify(next));else sessionStorage.removeItem(serviceKey) } catch { /* Storage may be unavailable in private browsing. */ }
  }
  const availableServices = report?.available_services || report?.services || []
  const visibleServices = selectedServices || availableServices
  useEffect(()=>{setOffset(0);setDateOffset(0)},[filters])
  useEffect(()=>{
    let alive=true
    const timer=setTimeout(()=>{
      setLoading(true)
      accountRequest<Report>(`${base}?${filters}&offset=${offset}&date_offset=${dateOffset}`,token).then(data=>{
        if(alive){setReport(data);setError("")}
      }).catch(e=>{if(alive)setError(e.message)}).finally(()=>{if(alive)setLoading(false)})
    },180)
    return()=>{alive=false;clearTimeout(timer)}
  },[base,filters,offset,dateOffset,tick,token])
  useEffect(()=>{const timer=setInterval(()=>{if(document.visibilityState==="visible")setTick(n=>n+1)},20000);return()=>clearInterval(timer)},[])
  async function openResult(id:number){
    const requestId=++detailRequest.current;setDetail(null);setDetailError("");setShot("");dialog.current?.showModal()
    try{const data=await accountRequest<Detail>(`${base}/results/${id}`,token);if(requestId===detailRequest.current)setDetail(data)}catch(e){if(requestId===detailRequest.current)setDetailError(e instanceof Error?e.message:"Не удалось загрузить ответ")}
  }
  async function exportReport(kind:string){setExporting(kind);setError("");try{await accountDownload(`${base}/export/${kind}?${filters}`,token,`${kind}-${report?.date_from}-${report?.date_to}.xlsx`)}catch(e){setError(e instanceof Error?e.message:"Ошибка выгрузки")}finally{setExporting("")}}
  async function openShot(id:string){try{setShot((await accountRequest<{url:string}>(`/screenshots/${encodeURIComponent(id)}/url`,token)).url)}catch(e){setDetailError(e instanceof Error?e.message:"Не удалось открыть снимок")}}
  const chart=report?.timeline.map(day=>({date:day.date,total:day.visibility_pct,...Object.fromEntries(Object.entries(day.services).map(([id,s])=>[id,s.visibility_pct]))})) || []
  return <section className="cc-report" aria-busy={loading}>
    <div className="report-toolbar"><div className="report-period">{report&&<ReportCalendar from={range?.from||report.date_from} to={range?.to||report.date_to} available={report.available_dates} change={(from,to)=>setRange({from,to})}/>}<div className="ws-segment" aria-label="Режим отчёта"><button aria-pressed={!compare} onClick={()=>setCompare(false)}>За период</button><button aria-pressed={compare} onClick={()=>setCompare(true)}>Сравнить даты</button></div></div><div className="cc-actions"><button className="cc-button" disabled={!!exporting||!report||loading} onClick={()=>exportReport("mentions")}><Download size={15}/>{exporting==="mentions"?"Готовим…":"Упоминаемость"}</button><button className="cc-button" disabled={!!exporting||!report||loading} onClick={()=>exportReport("sources")}><Download size={15}/>{exporting==="sources"?"Готовим…":"Внешние источники"}</button><button className="cc-button icon" aria-label="Обновить отчёт" disabled={loading} onClick={()=>setTick(n=>n+1)}><RefreshCw size={16}/></button></div></div>
    {error&&<p className="cc-alert" role="alert">{error}</p>}
    {!report?<div className="cc-skeleton" aria-label="Загрузка отчёта"/>:<>
      <div className="report-filters"><label className="cc-search"><Search size={16}/><span className="sr-only">Поиск запроса в отчёте</span><input placeholder="Найти запрос" value={search} onChange={e=>setSearch(e.target.value)}/></label><label><span className="sr-only">Группа</span><select value={group} onChange={e=>setGroup(e.target.value)}><option value="*">Все группы</option><option value="">Без группы</option>{report.groups.map(g=><option key={g} value={g}>{g}</option>)}</select></label><label className="cc-check"><input type="checkbox" checked={cards} onChange={e=>setCards(e.target.checked)}/>Учитывать карточки товаров</label></div>
      <div className="report-service-picker" role="group" aria-label="ИИ-системы в отчёте"><span>Показывать:</span><button className="cc-button" aria-pressed={availableServices.every(id=>visibleServices.includes(id))} onClick={()=>chooseServices(null)}>Все системы</button>{availableServices.map(id=>{
        const active=visibleServices.includes(id), last=active&&visibleServices.filter(s=>availableServices.includes(s)).length===1
        return <button key={id} className="cc-button" aria-pressed={active} disabled={last} title={last?"Оставьте хотя бы одну систему":active?`Скрыть ${name(id)}`:`Показать ${name(id)}`} onClick={()=>chooseServices(active?visibleServices.filter(s=>s!==id):[...visibleServices,id])}><span className="service-toggle-mark" aria-hidden="true">{active?"✓":""}</span>{name(id)}</button>
      })}<small>Выбор применяется к таблице, графику и выгрузкам</small></div>
      <div className="report-metrics"><div><span>{compare?"Начальная дата":"Упоминаемость"}</span><strong>{pct(compare?report.comparison.from.visibility_pct:report.summary.visibility_pct)}</strong>{compare&&<small>{shortDate(report.date_from)}</small>}</div><div><span>{compare?"Конечная дата":"Ответы с упоминанием"}</span><strong>{compare?pct(report.comparison.to.visibility_pct):report.summary.found}</strong>{compare&&<small>{shortDate(report.date_to)}</small>}</div><div><span>{compare?"Изменение":"Успешные проверки"}</span><strong>{compare?(report.comparison.delta===null?"—":`${report.comparison.delta>0?"+":""}${report.comparison.delta} п.п.`):report.summary.checked}</strong></div><div><span>Требуют внимания / без AI-блока</span><strong>{report.summary.issues}<em> / {report.summary.skipped}</em></strong></div></div>
      <div className="report-chart"><div className="report-chart-title"><h2>Динамика упоминаемости</h2><span>{shortDate(report.date_from)} — {shortDate(report.date_to)}</span></div>{report.timeline.some(d=>d.checked)?<ResponsiveContainer width="100%" height={240}><LineChart data={chart} margin={{top:18,right:18,left:0,bottom:0}} accessibilityLayer><CartesianGrid stroke="#302939" vertical={false}/><XAxis dataKey="date" tickFormatter={shortDate} tick={{fill:"#b5a9c9",fontSize:11}} minTickGap={36} axisLine={false} tickLine={false}/><YAxis domain={[0,100]} tickFormatter={v=>`${v}%`} width={44} tick={{fill:"#b5a9c9",fontSize:11}} axisLine={false} tickLine={false}/><Tooltip labelFormatter={label=>String(label)} formatter={(value,label)=>[`${value}%`,label]} contentStyle={{background:"#201a2b",border:"1px solid #554360",borderRadius:8,color:"#f5efff"}}/><Legend wrapperStyle={{fontSize:12,paddingTop:12}}/><Line connectNulls dataKey="total" name={report.services.length===1?name(report.services[0]):"Выбранные системы"} stroke="#d1adff" strokeWidth={2.5} dot={{r:3}} isAnimationActive={false}/>{report.services.length>1&&report.services.map(id=><Line connectNulls key={id} dataKey={id} name={name(id)} stroke={colors[id]} strokeWidth={1.5} dot={{r:2}} isAnimationActive={false}/>)}</LineChart></ResponsiveContainer>:<div className="report-chart-empty"><FileSearch size={24}/><p>В этом периоде нет успешных проверок</p></div>}</div>
      <p className="ws-note">Доля ответов с упоминанием среди успешных проверок. Ошибки и отсутствие AI-блока исключены. За каждый день учитывается последняя проверка запроса в каждой системе. Линии соединяют даты успешных проверок; пропуски не считаются нулями.{compare&&" Сравниваются две выбранные даты; состав успешных проверок может отличаться."}</p>
      <div className="report-table-heading"><h2>Запросы <small>{report.total}</small></h2><div className="cc-actions">{!compare&&report.dates.length>4&&<><button className="cc-button" disabled={dateOffset+4>=report.dates.length||loading} onClick={()=>setDateOffset(n=>n+4)}>← Раньше</button><button className="cc-button" disabled={!dateOffset||loading} onClick={()=>setDateOffset(n=>Math.max(0,n-4))}>Позже →</button></>}</div></div>
      {report.total&&report.visible_dates.length?<div className="report-matrix-scroll" tabIndex={0} role="region" aria-label="Упоминаемость по запросам и датам"><table className="report-matrix" style={{minWidth:`calc(var(--report-query-width) + ${report.visible_dates.length * report.services.length * 84}px)`}}><colgroup><col className="report-query-col"/>{report.visible_dates.flatMap(day=>report.services.map(id=><col key={`${day}-${id}`} className="report-service-col"/>))}</colgroup><thead><tr><th rowSpan={2} scope="col">Запрос / группа</th>{report.visible_dates.map(day=><th key={day} colSpan={report.services.length} scope="colgroup">{shortDate(day)}.{day.slice(0,4)}</th>)}</tr><tr>{report.visible_dates.map(day=>report.services.map(id=><th key={`${day}-${id}`} scope="col" title={name(id)}>{shortNames[id]||id}</th>))}</tr></thead><tbody>{report.rows.map(q=><tr key={q.id}><th scope="row"><span>{q.text}</span>{q.group_tag&&<small>{q.group_tag}</small>}</th>{report.visible_dates.map(day=>report.services.map(id=>{const cell=q.cells[day]?.[id];const kind=cell?.found?"found":cell?.status==="not_found"||cell?.status==="found"?"absent":cell?.status==="skipped"?"skipped":"issue";return <td key={`${day}-${id}`}>{cell?<button className={`report-cell ${kind}`} title={cellLabel(cell)} aria-label={`${q.text}, ${name(id)}, ${day}: ${cellLabel(cell)}. Открыть ответ`} onClick={()=>openResult(cell.id)}>{kind==="found"?"✓":kind==="absent"?"×":kind==="skipped"?"—":"!"}</button>:<span className="report-no-data" title="Не проверялся" aria-label="Не проверялся">·</span>}</td>}))}</tr>)}</tbody></table></div>:<div className="cc-empty"><FileSearch size={28}/><h3>{report.available_dates.length?"Нет результатов по выбранным фильтрам":"Здесь появится первый отчёт"}</h3><p>{report.available_dates.length?"Измените период, группу или строку поиска.":"Добавьте запросы и запустите проверку на подключённом компьютере."}</p></div>}
      <div className="report-legend"><span><b className="found">✓</b> Упоминание</span><span>× Нет упоминания</span><span>— Нет AI-блока</span><span><b className="issue">!</b> Требует внимания</span><span>· Не проверялся</span></div>
      <div className="report-pagination"><span>{report.total?`${Math.min(offset+1,report.total)}–${Math.min(offset+50,report.total)} из ${report.total} запросов`:"0 запросов"}</span><div className="cc-actions"><button className="cc-button" disabled={!offset||loading} onClick={()=>setOffset(n=>Math.max(0,n-50))}>Назад</button><button className="cc-button" disabled={offset+50>=report.total||loading} onClick={()=>setOffset(n=>n+50)}>Далее</button></div></div><p className="ws-note">XLSX содержит все запросы по выбранным фильтрам и все даты периода, независимо от страницы таблицы. Внешние источники — сохранённые ссылки из ответов ИИ, без доменов бренда.</p>
    </>}
    <dialog className="ws-dialog report-detail" ref={dialog} aria-labelledby="result-title" onClose={()=>{detailRequest.current++}}><div className="ws-dialog-head"><h2 id="result-title">Ответ ИИ</h2><button className="cc-button icon" aria-label="Закрыть ответ" onClick={()=>dialog.current?.close()}><X size={18}/></button></div>{detailError&&<p className="cc-alert" role="alert">{detailError}</p>}{detail?<><p className="ws-note">{name(detail.service)} · {shortDate(detail.scan_date)}.{detail.scan_date.slice(0,4)} · {statuses[detail.status]||detail.status}</p><h3>{detail.query_text}</h3>{detail.evidence_quote&&<blockquote>{detail.evidence_quote}</blockquote>}<div className="report-answer">{detail.answer_text||"Текст ответа не сохранён."}</div>{detail.sources.length>0&&<><h3>Источники</h3><ul>{detail.sources.filter(safeUrl).map((url,i)=><Fragment key={`${url}-${i}`}><li><a href={url} target="_blank" rel="noreferrer">{url}</a></li></Fragment>)}</ul></>}{detail.check_id&&<button className="cc-button" onClick={()=>openShot(detail.check_id!)}>Открыть скриншот</button>}{shot&&<img className="report-shot" src={shot} alt="Скриншот ответа ИИ"/>}</>:!detailError&&<p role="status">Загружаем ответ…</p>}</dialog>
  </section>
}
