import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react"
import { CalendarClock, ChevronRight, Flag, LayoutDashboard, Link, List, Pause, Play, Plus, RefreshCw, Search, Settings2, ShieldCheck, Square, X } from "lucide-react"
import { Tooltip } from "@base-ui/react/tooltip"
import { accountRequest as request } from "./account-api"
import { SCAN_SERVICES, MONTH_DAYS } from "./lib/scan-preferences"
import { ReportView } from "./report-view"
import { QueryLibrary } from "./query-library"
import "./workspace.css"
import { SiteHeader } from "./site-header"
import { IconNavLink } from "./icon-nav-link"
import { AppChoice } from "./app-choice"
import { ServiceMark, isCurrentService } from "./service-mark"
import { ProjectIcon } from "./project-icon"
import "./prototype.css"
import "./app-layout.css"
import { publicError } from "./lib/public-error"
import "./control-center.css"
import "./icon-sidebar.css"

type Query = { id: string; text: string; group_tag: string; active: boolean }
type Config = { brand_aliases: string[]; brand_domains: string[]; brand_clarification?: string; region_code: string; services: string[]; browser_mode: string; speed_profile: string; parallel: boolean }
type Schedule = { enabled: boolean; device_id: string | null; month_days: number[]; last_day?: boolean; time: string; timezone: string }
type Project = { id: string; revision: number; name: string; brand_name: string; device_id: string | null; config: Config; schedule: Schedule; queries: Query[]; query_count: number; active_queries: number }
type Run = { id: string; project_id: string; project_name: string; device_id: string | null; device_name: string; phase?: string; state: string; desired_state: string; error: string | null; total: number; created_at: string; scheduled_for: string | null; progress: { done?: number; total?: number; services?: Record<string, {done:number; total:number; state?:string; error?:string}> } }
type Quote = { count: number; free_count?: number; unit_kopeks: number; total_kopeks: number; available_kopeks: number; revision: number; provider_state?: string; free_scans_state?: string }
type RecomputeQuote = Quote & { result_ids: string[]; skipped: number }
type RecomputeResult = { charged_kopeks: number; status: "done" | "skipped" | "error"; message: string }
const money = (kopeks: number) => new Intl.NumberFormat("ru-RU", {style:"currency",currency:"RUB"}).format(kopeks / 100)
const uuid = () => crypto.randomUUID().replaceAll("-", "")
const names: Record<string, string> = { queued: "В очереди", waiting_device: "Ожидает компьютер", running: "В процессе", paused: "На паузе", connection_lost: "Нет связи с компьютером", done: "Завершено", failed: "Нужно действие", cancelled: "Остановлено", missed: "Пропущено" }
const terminal = (r: Run) => ["done", "failed", "cancelled", "missed"].includes(r.state)
export function runStatus(run: Pick<Run,"state"|"desired_state"|"phase">) {
  if (["done","failed","cancelled","missed"].includes(run.state)) return names[run.state]
  if (run.desired_state === "cancelled") return "Останавливается"
  if (run.desired_state === "paused") return "На паузе"
  if (run.phase === "cloud" && run.state === "paused") return "В процессе"
  return names[run.state] || run.state
}
export function scanPercent(done: number, total: number) {
  return total > 0 ? Math.max(0,Math.min(100,Math.floor(done / total * 20) * 5)) : 0
}
export function ScanProgress({ percent }: {percent:number}) {
  return <span className="scan-pie" role="progressbar" aria-label="Прогресс проверки" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} style={{"--scan-target":`${percent}%`} as CSSProperties}/>
}
export const needsAgent = (services: string[]) => services.some(id => !["google_aio", "yandex_neuro", "chatgpt", "perplexity", "gemini"].includes(id))
const service = (id: string) => SCAN_SERVICES.find(s => s.id === id)?.label || id
const scheduleDaysLabel = (schedule: Schedule) => [...schedule.month_days.map(String), ...(schedule.last_day ? ["последний день месяца"] : [])].join(", ") || "не выбраны"
export function ScheduleDays({ days, lastDay, change }: {days:number[];lastDay:boolean;change:(days:number[],lastDay:boolean)=>void}) {
  const legacy = days.filter(day=>day > 28)
  return <fieldset><legend>Числа месяца</legend><div className="cc-days">
    {MONTH_DAYS.slice(0,28).map(day=><button type="button" key={day} aria-pressed={days.includes(day)} onClick={()=>change(days.includes(day) ? days.filter(d=>d!==day) : [...days,day].sort((a,b)=>a-b),lastDay)}>{day}</button>)}
    <button type="button" aria-label="Последний день месяца" aria-pressed={lastDay} title="Последний день месяца" onClick={()=>change(days,!lastDay)}><Flag size={17}/></button><span className="cc-last-day-label">Последний день месяца</span>
  </div>{!!legacy.length && <div className="cc-legacy-days"><p className="cc-hint">Ранее выбраны числа {legacy.join(", ")}. В месяце без этих чисел скан пропускается. Уберите их, если хотите перейти на последний день месяца.</p>{legacy.map(day=><button type="button" className="cc-button" key={day} aria-label={`Убрать число ${day}`} onClick={()=>change(days.filter(d=>d!==day),lastDay)}>{day} <X size={14}/></button>)}</div>}</fieldset>
}
const blank = (): Project => ({ id: "new", revision: 0, name: "", brand_name: "", device_id: null, queries: [], query_count: 0, active_queries: 0,
  config: { brand_aliases: [], brand_domains: [], brand_clarification: "", region_code: "213", services: ["google_aio"], browser_mode: "headless", speed_profile: "fast", parallel: true },
  schedule: { enabled: false, device_id: null, month_days: [1], last_day: false, time: "09:00", timezone: "Europe/Moscow" } })
const routeNow = () => location.hash.startsWith("#/") ? location.hash.slice(2) : "overview"
const HISTORY_POSITION = "aimt.hashPosition"
const historyPosition = () => {
  const value = history.state && typeof history.state === "object" ? history.state[HISTORY_POSITION] : undefined
  return typeof value === "number" ? value : null
}
const stampHistoryPosition = (position: number) => history.replaceState({ ...(history.state && typeof history.state === "object" ? history.state : {}), [HISTORY_POSITION]: position }, "", location.href)
export const historyRecovery = (previousHash: string, previousPosition: number, targetPosition: number | null, nextPosition: number) => targetPosition === null
  ? { hash: previousHash, position: nextPosition + 1 }
  : { delta: previousPosition - targetPosition }

function QuotePopover({ quote, item, note, action, above = false, trigger, afterConfirm, onCancel, onConfirm }: { quote: Quote; item: string; note: string; action: string; above?: boolean; trigger: RefObject<HTMLButtonElement | null>; afterConfirm?: RefObject<HTMLElement | null>; onCancel: () => void; onConfirm: () => void }) {
  const dialog = useRef<HTMLDivElement>(null)
  const confirmed = useRef(false)
  useEffect(() => {
    const triggerButton = trigger.current
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus()
    const dismiss = (event: KeyboardEvent) => { if (event.key === "Escape") onCancel() }
    const outside = (event: MouseEvent) => { if (!dialog.current?.parentElement?.contains(event.target as Node)) onCancel() }
    document.addEventListener("keydown", dismiss)
    document.addEventListener("mousedown", outside)
    return () => { document.removeEventListener("keydown", dismiss); document.removeEventListener("mousedown", outside); if (!confirmed.current) triggerButton?.focus() }
  }, [onCancel, trigger])
  return <div ref={dialog} className={`cc-quote-popover${above ? " above" : ""}`} role="dialog" aria-modal="false" aria-label={`Подтверждение: ${action}`}><p>К списанию: до <b>{money(quote.total_kopeks)}</b></p><small>{quote.free_count ? `${quote.free_count} бесплатно по промокоду · ${quote.count - quote.free_count} платных × ${money(quote.unit_kopeks)}` : `${quote.count} ${item} × ${money(quote.unit_kopeks)}`} · доступно {money(quote.available_kopeks)}</small><p className="cc-quote-note">{note}</p><div><button className="cc-quote-cancel" onClick={onCancel}>Отменить</button><button className="cc-button primary" onClick={() => { confirmed.current = true; onConfirm(); requestAnimationFrame(() => afterConfirm?.current?.focus()) }}>{action}</button></div></div>
}

export function ControlCenter({ token, brandClarificationsEnabled, onDirtyChange, email, balance, admin, account, administration, message, logout, walletChanged }: {
  token: string; brandClarificationsEnabled: boolean; onDirtyChange: (dirty: boolean) => void;
  email: string; balance: string; admin: boolean; account: ReactNode; administration: ReactNode; message: string; logout: () => void; walletChanged: () => void
}) {
  const [route, setRoute] = useState(routeNow)
  const [lastProject, setLastProject] = useState(() => routeNow().split("/")[1] || "")
  const editorDirty = useRef(false), editorProject = useRef(""), previousHash = useRef(location.hash), previousPosition = useRef(0), restoringHistory = useRef(false)
  const [projects, setProjects] = useState<Project[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState("")
  const [filter, setFilter] = useState("")
  const [runState, setRunState] = useState("")
  const [runDetail, setRunDetail] = useState<string | null>(null)
  const runDialog = useRef<HTMLDialogElement>(null)
  const mounted = useRef(true), refreshVersion = useRef(0)
  useEffect(() => () => { mounted.current = false; refreshVersion.current++ }, [])
  const [scanQuote, setScanQuote] = useState<{projectId:string; quote:Quote}|null>(null)
  const scanButton = useRef<HTMLButtonElement>(null)
  const scanQuoteRequest = useRef(0)
  const scanSubmitting = useRef(false)
  const projectHeading = useRef<HTMLHeadingElement>(null)
  const main = useRef<HTMLElement>(null)
  const dismissScanQuote = useCallback(() => { scanQuoteRequest.current++; setScanQuote(null) }, [])
  const refresh = useCallback(async () => {
    const version = ++refreshVersion.current
    const [p, r] = await Promise.all([request<Project[]>("/control/projects", token), request<Run[]>("/control/runs", token)])
    if (!mounted.current || version !== refreshVersion.current) return
    setProjects(p); setRuns(r); setError(""); setLoading(false)
  }, [token])
  const noteEditorDirty = useCallback((dirty: boolean, projectId: string) => {
    editorDirty.current = dirty
    if (dirty) editorProject.current = projectId
    if (dirty) { scanQuoteRequest.current++; setScanQuote(null) }
    onDirtyChange(dirty)
  }, [onDirtyChange])
  useEffect(() => {
    const currentPosition = historyPosition()
    previousPosition.current = currentPosition ?? 0
    if (currentPosition === null) stampHistoryPosition(previousPosition.current)
    const change = () => {
      const next = location.hash
      if (next === previousHash.current) {
        restoringHistory.current = false
        return
      }
      if (restoringHistory.current) {
        restoringHistory.current = false
        previousHash.current = next
        if (historyPosition() === null) stampHistoryPosition(previousPosition.current)
        return
      }
      let nextPosition = historyPosition()
      const hasPosition = nextPosition !== null
      if (nextPosition === null || nextPosition === previousPosition.current) {
        nextPosition = previousPosition.current + 1
        stampHistoryPosition(nextPosition)
      }
      const staysInEditor = [`#/project/${editorProject.current}/queries`, `#/project/${editorProject.current}/settings`, `#/project/${editorProject.current}/schedule`].includes(next)
      if (editorDirty.current && !staysInEditor && !window.confirm("Изменения не сохранены. Уйти со страницы?")) {
        const recovery = historyRecovery(previousHash.current, previousPosition.current, hasPosition ? nextPosition : null, nextPosition)
        if ("delta" in recovery) {
          restoringHistory.current = true
          history.go(recovery.delta)
        } else {
          history.pushState({ ...(history.state && typeof history.state === "object" ? history.state : {}), [HISTORY_POSITION]: recovery.position }, "", location.pathname + location.search + recovery.hash)
          previousHash.current = recovery.hash
          previousPosition.current = recovery.position
        }
        return
      }
      previousHash.current = next
      previousPosition.current = nextPosition
      scanQuoteRequest.current++; setScanQuote(null)
      const [nextArea, nextProject] = routeNow().split("/")
      if (nextArea === "project" && nextProject !== "new") setLastProject(nextProject)
      setRoute(routeNow())
    }
    const clearRestore = () => {
      if (location.hash === previousHash.current) {
        previousPosition.current = historyPosition() ?? previousPosition.current
        restoringHistory.current = false
      }
    }
    window.addEventListener("hashchange", change)
    window.addEventListener("popstate", clearRestore)
    return () => { window.removeEventListener("hashchange", change); window.removeEventListener("popstate", clearRestore) }
  }, [])
  useEffect(() => {
    refresh().catch(e => { setError(e.message); setLoading(false) })
    const timer = setInterval(() => { if (document.visibilityState === "visible") refresh().catch(e => setError(e.message)) }, 15000)
    return () => clearInterval(timer)
  }, [refresh])
  async function action(key: string, callback: () => Promise<unknown>) {
    setBusy(key); setError("")
    try { await callback(); await refresh(); if (mounted.current) walletChanged() } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : "Не удалось выполнить действие") }
    finally { setBusy("") }
  }
  async function quoteLaunch(projectId: string) {
    if (editorDirty.current && editorProject.current === projectId) throw new Error("Сначала сохраните изменения проекта перед запуском проверки")
    const requestVersion = ++scanQuoteRequest.current; setScanQuote(null)
    let quote: Quote
    try { quote = await request<Quote>(`/control/projects/${projectId}/quote`, token) } catch (error) { if (requestVersion === scanQuoteRequest.current) throw error; return }
    if (requestVersion !== scanQuoteRequest.current) return
    if (!quote.count) throw new Error("Нет проверок для запуска")
    if (quote.available_kopeks < quote.total_kopeks) throw new Error(`Для запуска нужно до ${money(quote.total_kopeks)}. Сейчас доступно ${money(quote.available_kopeks)}.`)
    setScanQuote({projectId, quote})
  }
  async function launch(projectId: string, quote: Quote) {
    await request(`/control/projects/${projectId}/runs`, token, {request_id:uuid(), revision:quote.revision, provider_state:quote.provider_state, free_scans_state:quote.free_scans_state})
  }
  const [area, routeProject, projectTab] = route.split("/")
  const projectId = routeProject || projects.find(p => p.id === lastProject)?.id || projects[0]?.id
  const selected = projects.find(p => p.id === projectId)
  const activeRuns = runs.filter(r => !terminal(r))
  const projectRun = activeRuns.find(r => r.project_id === projectId)
  const tab = projectTab || "report"
  const projectLink = (next: string) => projectId ? `#/project/${projectId}/${next}` : "#/projects"
  const nav = [
    ["report", "Обзор видимости", LayoutDashboard],
    ["queries", "Запросы", List], ["sources", "Источники", Link], ["settings", "Настройки проекта", Settings2],
    ["schedule", "Расписание", CalendarClock], ["runs", "История проверок", Play], ...(admin ? [["admin", "Администрирование", ShieldCheck] as const] : []),
  ] as const
  const page = area === "project" ? tab : area === "overview" ? "report" : area === "topup" ? "account" : area
  useEffect(() => { if (page === "help") location.replace("/docs/") }, [page])
  const title = projectId === "new" ? "Новый проект" : ({projects: "Проекты", account: "Аккаунт и оплата", help: "Документация"} as Record<string, string>)[page] || nav.find(([id]) => id === page)?.[1] || "Обзор видимости"
  const currentRun = runs.find(r => r.id === runDetail)
  function runRows(items: Run[]) {
    return <div className="table-scroll"><table><thead><tr><th>Проект / запуск</th><th>Статус</th><th>Проверки</th><th>Действия</th></tr></thead><tbody>{items.map(r => <tr key={r.id}><td><button className="text-link" onClick={() => { setRunDetail(r.id); runDialog.current?.showModal() }}>{r.project_name}</button><small className="row-note">{new Date(r.created_at).toLocaleString("ru-RU")} · {r.scheduled_for ? "По расписанию" : "Вручную"}</small></td><td><span className={`badge ${r.state === "done" ? "green" : r.state === "failed" ? "red" : "blue"}`}>{runStatus(r)}</span></td><td>{r.progress.done || 0} / {r.total}<progress max={r.total || 1} value={r.progress.done || 0} aria-label={`Прогресс ${r.project_name}`}/></td><td><div className="cc-actions">{!terminal(r) && <><button className="btn" disabled={!!busy} onClick={() => action(r.id, () => request(`/control/runs/${r.id}/command`, token, {action:r.desired_state === "paused" ? "resume" : "pause"}))}>{r.desired_state === "paused" ? <Play size={14}/> : <Pause size={14}/>} {r.desired_state === "paused" ? "Продолжить" : "Пауза"}</button><button className="btn" disabled={!!busy} onClick={() => action(r.id, () => request(`/control/runs/${r.id}/command`, token, {action:"stop"}))}><Square size={13}/>Стоп</button></>}<a className="btn" href={`#/project/${r.project_id}/report`}>Отчёт</a></div></td></tr>)}</tbody></table></div>
  }
  const progress = projectRun ? scanPercent(projectRun.progress.done ?? 0,projectRun.total) : 0
  const scanLabel = projectRun ? `${runStatus(projectRun)}: ${progress}%` : "Проверить видимость"
  const scanControl = <span className="cc-quote-anchor">
    <Tooltip.Root><Tooltip.Trigger delay={180} render={<button ref={scanButton} className="btn icon-only scan-launch" aria-label={scanLabel} aria-haspopup={projectRun ? undefined : "dialog"} aria-expanded={projectRun ? undefined : scanQuote?.projectId === projectId} aria-disabled={!!projectRun} disabled={!projectRun && (!!busy || !selected?.config.services.length || !selected.active_queries || needsAgent(selected.config.services))} onClick={() => { if (!projectRun) void action(projectId!, () => quoteLaunch(projectId!)) }}/>}>{projectRun ? <ScanProgress percent={progress}/> : <RefreshCw size={19}/>}</Tooltip.Trigger>
      <Tooltip.Portal><Tooltip.Positioner side="bottom" sideOffset={12} className="air-nav-tip-positioner"><Tooltip.Popup className="air-nav-tip"><Tooltip.Arrow className="air-nav-tip-arrow"/>{scanLabel}</Tooltip.Popup></Tooltip.Positioner></Tooltip.Portal>
    </Tooltip.Root>
    {scanQuote && scanQuote.projectId === projectId && <QuotePopover quote={scanQuote.quote} item="проверок" note="Оплачиваются только завершённые проверки с ответом." action="Запустить" trigger={scanButton} afterConfirm={projectHeading} onCancel={dismissScanQuote} onConfirm={() => { if (scanSubmitting.current) return; scanSubmitting.current = true; const pending = scanQuote; setScanQuote(null); void action(projectId!, () => launch(projectId!, pending.quote)).finally(() => { scanSubmitting.current = false }) }}/>}
  </span>
  return <div className="air-app">
    <a className="skip-link" href="#app-content" onClick={event => { event.preventDefault(); main.current?.focus() }}>К содержимому</a>
    <SiteHeader cabinet email={email} balance={balance} projects={projects} selectedId={selected?.id} loading={loading} admin={admin} logout={logout} projectTab={["report","queries","sources","settings","schedule"].includes(page) ? page : "report"}/>
    <aside className="sidebar">
      <nav aria-label="Разделы приложения">{nav.map(([id, label, Icon]) => <IconNavLink key={id} className="nav-link" label={label} current={page === id} href={["report","queries","sources","settings","schedule"].includes(id) ? projectLink(id) : `#/${id}`}><Icon size={24} strokeWidth={1.7} aria-hidden="true"/></IconNavLink>)}</nav>
    </aside>
    <main ref={main} className="app-main" id="app-content" tabIndex={-1}>
      <div className="breadcrumb"><a href="#/projects">Проекты</a><ChevronRight size={12}/>{selected && <><span>{selected.name}</span><ChevronRight size={12}/></>}<span className="current">{title}</span></div>
      <div className="heading-row"><div><div className="heading-title"><h1 ref={projectHeading} tabIndex={-1}>{title}</h1>{selected && ["project","overview"].includes(area) && <span className="domain-label">{selected.config.brand_domains[0] || selected.brand_name}</span>}</div><p className="subtitle">{page === "report" ? "Как часто ИИ упоминает ваш бренд и откуда берёт информацию." : page === "projects" ? "Бренды, запросы и результаты — в одном рабочем пространстве." : page === "queries" ? "Промптовая база проекта: запросы и группы для регулярных проверок." : page === "sources" ? "Сайты, на которые ссылаются ответы с упоминанием бренда." : page === "schedule" ? "Автоматические проверки в выбранные дни месяца." : page === "runs" ? "Ручные запуски и расписания проектов аккаунта." : ""}</p></div>
        <div className="heading-actions">{page === "projects" ? <a className="btn primary" href="#/project/new/settings"><Plus size={15}/>Новый проект</a> : null}</div>
      </div>
      {error && <div className="cc-alert" role="alert">{error}<button className="btn" onClick={() => refresh().catch(e => setError(e.message))}>Повторить</button><button className="btn icon-only" aria-label="Закрыть сообщение" onClick={() => setError("")}><X size={16}/></button></div>}
      {message && <p className="notice" role="status">{message}</p>}
      {page === "account" ? account : page === "admin" && admin ? administration : page === "help" ? <p className="page-intro">Открываем документацию… <a href="/docs/">Перейти к документации</a></p> : ["project","overview"].includes(area) && projectId ? <>
        {["report","sources"].includes(tab) && projectId !== "new" ? <ReportView key={projectId} token={token} projectId={projectId} projectServices={selected?.config.services || []} sourcesOnly={tab === "sources"} scanControl={scanControl}/> : <ProjectEditor key={projectId} token={token} projectId={projectId} tab={projectId === "new" ? "settings" : tab} brandClarificationsEnabled={brandClarificationsEnabled} saved={refresh} onDirtyChange={noteEditorDirty} walletChanged={walletChanged}/>}
      </> : page === "runs" ? <><div className="filterbar"><label className="search-box"><Search size={15}/><input aria-label="Поиск проверки" placeholder="Поиск по проекту" value={filter} onChange={e => setFilter(e.target.value)}/></label><AppChoice label="Статус проверки" value={runState} options={[{value:"",label:"Все статусы"},...Object.entries(names).map(([value,label]) => ({value,label}))]} change={setRunState}/></div><section className="panel">{loading ? <p className="empty-state" role="status">Загрузка проверок…</p> : runs.length ? runRows(runs.filter(r => (!runState || runStatus(r) === names[runState]) && r.project_name.toLowerCase().includes(filter.toLowerCase()))) : <div className="empty-state">Проверок пока нет. <a href="#/projects">К проектам</a></div>}</section></> : <>
        <div className="stat-inline"><span><strong>{projects.length}</strong> проектов</span><span><strong>{projects.reduce((n,p) => n + p.query_count, 0)}</strong> запросов</span></div><div className="filterbar"><label className="search-box"><Search size={15}/><input aria-label="Поиск проекта" placeholder="Найти проект или бренд" value={filter} onChange={e => setFilter(e.target.value)}/></label></div><section className="panel">{loading ? <p className="empty-state" role="status">Загрузка проектов…</p> : !projects.length ? <div className="empty-state"><h2>Начните с первого проекта</h2><p>Укажите бренд, добавьте запросы и выберите ИИ-системы.</p><a className="btn primary" href="#/project/new/settings">Создать проект</a></div> : <div className="table-scroll"><table><thead><tr><th>Проект</th><th>Запросы</th><th>ИИ-системы</th><th>Расписание</th><th>Статус</th></tr></thead><tbody>{projects.filter(p => `${p.name} ${p.brand_name}`.toLowerCase().includes(filter.toLowerCase())).map(p => <tr key={p.id}><td><a className="project-name" href={`#/project/${p.id}/report`}><ProjectIcon name={p.name} domains={p.config.brand_domains}/>{p.name}</a><small className="row-note">{p.brand_name}</small></td><td>{p.query_count}<small className="row-note">{p.active_queries} активно</small></td><td><div className="system-marks">{p.config.services.filter(isCurrentService).map(id => <span key={id} title={service(id)}><ServiceMark id={id}/></span>)}</div></td><td><a href={`#/project/${p.id}/schedule`}>{p.schedule.enabled ? `${p.schedule.time} · ${scheduleDaysLabel(p.schedule)}` : "По запросу"}</a></td><td><span className="badge blue">{activeRuns.find(r => r.project_id === p.id) ? runStatus(activeRuns.find(r => r.project_id === p.id)!) : p.config.services.length && !needsAgent(p.config.services) ? "Готов к проверкам" : "Требует настройки"}</span></td></tr>)}</tbody></table></div>}</section>
      </>}
      <dialog ref={runDialog} aria-labelledby="run-title"><div className="dialog-head"><h2 id="run-title">Проверка проекта</h2><button className="btn icon-only" aria-label="Закрыть проверку" onClick={() => runDialog.current?.close()}><X size={16}/></button></div><div className="dialog-body">{currentRun ? <><h3>{currentRun.project_name}</h3><p>{runStatus(currentRun)} · {currentRun.progress.done || 0} / {currentRun.total} проверок</p>{currentRun.error && <p className="cc-error-text">{publicError(currentRun.error)}</p>}{Object.entries(currentRun.progress.services || {}).filter(([id])=>isCurrentService(id)).map(([id, stats]) => <p key={id}>{service(id)}: {stats.done} / {stats.total}{stats.error ? ` · ${publicError(stats.error)}` : ""}</p>)}<p>Незавершённые запросы остаются в очереди; счётчик показывает готовые ответы.</p><a className="btn blue" href={`#/project/${currentRun.project_id}/report`}>Открыть отчёт</a></> : <p>Проверка недоступна</p>}</div></dialog>
    </main>
  </div>
}

function ProjectEditor({token,projectId,tab,brandClarificationsEnabled,saved,onDirtyChange,walletChanged}:{token:string;projectId:string;tab:string;brandClarificationsEnabled:boolean;saved:()=>Promise<void>;onDirtyChange:(dirty:boolean,projectId:string)=>void;walletChanged:()=>void}) {
  const [project,setProject] = useState<Project|null>(projectId === "new" ? blank() : null)
  const [dirty,setDirty] = useState(false)
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState("")
  const [error,setError] = useState("")
  const [fromDate,setFromDate] = useState("")
  const [recomputeMessage,setRecomputeMessage] = useState("")
  const [recomputeQuote,setRecomputeQuote] = useState<{quote:RecomputeQuote; fromDate:string}|null>(null)
  const dirtyRef = useRef(false), busyRef = useRef(false), mounted = useRef(true)
  const recomputeButton = useRef<HTMLButtonElement>(null)
  const recomputeQuoteRequest = useRef(0)
  const recomputeHeading = useRef<HTMLHeadingElement>(null)
  const dismissRecomputeQuote = useCallback(() => { recomputeQuoteRequest.current++; setRecomputeQuote(null) }, [])
  useEffect(() => () => { mounted.current = false }, [])
  useEffect(() => { onDirtyChange(dirty, projectId); return () => onDirtyChange(false, projectId) }, [dirty, onDirtyChange, projectId])
  useEffect(() => {if(projectId !== "new"){let alive=true;request<Project>(`/control/projects/${projectId}`,token).then(p=>{if(alive)setProject(p)}).catch(e=>{if(alive)setError(e.message)});return()=>{alive=false}}},[projectId,token])
  useEffect(() => { recomputeQuoteRequest.current++; setRecomputeQuote(null) }, [fromDate, dirty, tab])
  useEffect(() => {const prevent=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue=""}};window.addEventListener("beforeunload",prevent);return()=>window.removeEventListener("beforeunload",prevent)},[dirty])
  useEffect(() => {
    const guard = (event: MouseEvent) => {
      if (!dirtyRef.current) return
      const link = (event.target as Element).closest<HTMLAnchorElement>("a[href]")
      if (!link || link.target === "_blank" || link.hasAttribute("download")) return
      const target = new URL(link.href, location.href)
      if (target.pathname === location.pathname && target.hash.startsWith("#/")) return
      if (!window.confirm("Изменения не сохранены. Уйти со страницы?")) {
        event.preventDefault(); event.stopPropagation()
      }
    }
    document.addEventListener("click", guard, true)
    return () => document.removeEventListener("click", guard, true)
  }, [projectId])
  function change(next:Project){if(busyRef.current)return;recomputeQuoteRequest.current++;setRecomputeQuote(null);dirtyRef.current=true;onDirtyChange(true,projectId);setProject(next);setDirty(true);setMessage("")}
  function changeFromDate(value: string){recomputeQuoteRequest.current++;setRecomputeQuote(null);setFromDate(value)}
  async function save(){if(!project)return;busyRef.current=true;setBusy(true);setError("");try{
    const {revision,name,brand_name,device_id,schedule,queries}=project
    const config={...project.config,services:project.config.services.filter(isCurrentService),speed_profile:"fast"}
    const next=await request<Project>(projectId==="new"?"/control/projects":`/control/projects/${projectId}`,token,{revision,name,brand_name,device_id,config,schedule,queries},projectId==="new"?"POST":"PUT")
    if(!mounted.current)return
    dirtyRef.current=false;onDirtyChange(false,projectId);setProject(next);setDirty(false);setMessage("Сохранено. Текущая проверка использует настройки на момент запуска.");await saved()
    if(mounted.current&&projectId==="new")location.hash=`/project/${next.id}/queries`
  }catch(e){if(mounted.current)setError(e instanceof Error?e.message:"Не удалось сохранить проект")}finally{busyRef.current=false;if(mounted.current)setBusy(false)}}
  async function quoteRecompute(){
    if (!project || projectId === "new" || !fromDate || dirty || busyRef.current) return
    const quotedDate = fromDate
    const requestVersion = ++recomputeQuoteRequest.current; setRecomputeQuote(null)
    busyRef.current=true;setBusy(true);setError("");setRecomputeMessage("")
    try {
      const quote=await request<RecomputeQuote>(`/control/projects/${projectId}/recompute/quote?from_date=${encodeURIComponent(quotedDate)}`,token)
      if (requestVersion !== recomputeQuoteRequest.current) return
      if (!quote.count) {setRecomputeMessage(`С ${quotedDate} нет ответов для пересчёта.${quote.skipped ? ` Без достаточных сохранённых данных: ${quote.skipped}.` : ""}`);return}
      if (quote.available_kopeks < quote.total_kopeks) {setError(`Для пересчёта ${quote.count} ответов нужно до ${money(quote.total_kopeks)}. Сейчас доступно ${money(quote.available_kopeks)}. Пополните баланс или выберите более позднюю дату.`);return}
      setRecomputeQuote({quote, fromDate: quotedDate})
    } catch(e) {if(mounted.current && requestVersion === recomputeQuoteRequest.current)setError(e instanceof Error?e.message:"Не удалось получить стоимость пересчёта")}
    finally {busyRef.current=false;if(mounted.current)setBusy(false)}
  }
  async function recompute({quote, fromDate}: {quote:RecomputeQuote; fromDate:string}){
    if (busyRef.current) return
    busyRef.current=true;setBusy(true);setError("");setRecomputeMessage("")
    try {
      let done=0, skipped=0, failed=0, charged=0
      for (const id of quote.result_ids) {
        if (!mounted.current) break
        try {
          const result=await request<RecomputeResult>(`/control/projects/${projectId}/recompute/${id}`,token,{from_date:fromDate,revision:quote.revision})
          charged+=result.charged_kopeks
          if (result.status === "done") done++
          else if (result.status === "skipped") skipped++
          else {failed++;if(mounted.current)setError(result.message)}
        } catch (e) {
          failed++
          if (mounted.current) setError(e instanceof Error ? e.message : "Не удалось пересчитать ответ")
          break
        }
        if (mounted.current) setRecomputeMessage(`Пересчитано ${done} из ${quote.count}; списано ${money(charged)}.`)
      }
      if (mounted.current) setRecomputeMessage(`Готово: пересчитано ${done}, пропущено ${skipped + quote.skipped}, ошибок ${failed}. Списано ${money(charged)}. Откройте «Упоминаемость», чтобы увидеть обновлённые результаты и графики.`)
    } catch(e) {if(mounted.current)setError(e instanceof Error?e.message:"Не удалось пересчитать ответы")}
    finally {busyRef.current=false;if(mounted.current){setBusy(false);walletChanged()}}
  }
  if(!project)return error?<p className="cc-alert" role="alert">{error}</p>:<div className="cc-skeleton"/>
  return <div className={tab === "queries" ? "cc-editor" : "cc-editor settings-layout"}><div>
    {error&&<p className="cc-alert" role="alert">{error}</p>}
    <fieldset disabled={busy}>
    {tab==="queries"?<QueryLibrary queries={project.queries} saving={busy} onChange={queries=>change({...project,queries})}/>:<>
    {tab !== "schedule" && <>
      <div className="cc-form-section"><div><h2>Проект и бренд</h2><p>По этим названиям и доменам ищем упоминания в ответах ИИ.</p></div><div className="cc-fields"><div className="cc-two"><label>Название проекта<input required maxLength={120} value={project.name} onChange={e=>change({...project,name:e.target.value})}/></label><label>Бренд<input required maxLength={120} value={project.brand_name} onChange={e=>change({...project,brand_name:e.target.value})}/></label></div><label>Другие написания бренда<textarea rows={3} value={project.config.brand_aliases.join("\n")} onChange={e=>change({...project,config:{...project.config,brand_aliases:e.target.value.split("\n")}})}/></label><label>Домены бренда<textarea rows={2} placeholder="example.ru" value={project.config.brand_domains.join("\n")} onChange={e=>change({...project,config:{...project.config,brand_domains:e.target.value.split("\n")}})}/></label>{brandClarificationsEnabled && <label>Уточнения по бренду<textarea rows={4} maxLength={2000} placeholder="Например: Reflo — наш товар; Refprom — другой бренд, его не считать." value={project.config.brand_clarification || ""} onChange={e=>change({...project,config:{...project.config,brand_clarification:e.target.value}})}/><small>Сохраните, чтобы применять уточнение к будущим сканам. Это бесплатно и не меняет старые результаты.</small></label>}</div></div>
      <div className="cc-form-section"><div><h2>Выполнение проверок</h2><p>Все пять ИИ-систем проверяются на сервере. Ответы сохраняются в вашем аккаунте.</p></div><div className="cc-fields"><fieldset><legend>ИИ-системы</legend><div className="cc-checkboxes">{SCAN_SERVICES.map(s=><label className="cc-check" key={s.id}><input type="checkbox" checked={project.config.services.includes(s.id)} onChange={e=>change({...project,config:{...project.config,services:e.target.checked?[...project.config.services,s.id]:project.config.services.filter(id=>id!==s.id)}})}/><ServiceMark id={s.id}/>{s.label}</label>)}</div></fieldset>{!project.config.services.length && <p className="cc-hint" role="status">Выберите минимум один ИИ-сервис, чтобы запускать проверки и расписание.</p>}<label>Регион Яндекса<input value={project.config.region_code} onChange={e=>change({...project,config:{...project.config,region_code:e.target.value}})}/><small>213 — Москва. Для Google другой регион требует отдельной настройки на сервере. ChatGPT, Perplexity и Gemini собираются с географией США.</small></label></div></div>
      </>}
      {(tab === "schedule" || projectId === "new") && <div className="cc-form-section"><div><h2><CalendarClock size={21}/>Расписание</h2><p>Выберите дни месяца и точное время. Изменения применяются после сохранения.</p></div><div className="cc-fields"><label className="cc-check"><input type="checkbox" checked={project.schedule.enabled} onChange={e=>change({...project,schedule:{...project.schedule,enabled:e.target.checked,device_id:project.schedule.device_id}})}/>Проверять по расписанию</label><div className="cc-two"><label>Время запуска<input type="time" value={project.schedule.time} onChange={e=>change({...project,schedule:{...project.schedule,time:e.target.value}})}/></label><label>Часовой пояс<input list="timezones" value={project.schedule.timezone} onChange={e=>change({...project,schedule:{...project.schedule,timezone:e.target.value}})}/><datalist id="timezones">{["Europe/Moscow","Europe/Kaliningrad","Europe/Samara","Asia/Yekaterinburg","Asia/Novosibirsk","Asia/Vladivostok","UTC"].map(z=><option key={z} value={z}/>)}</datalist></label></div><ScheduleDays days={project.schedule.month_days} lastDay={!!project.schedule.last_day} change={(month_days,last_day)=>change({...project,schedule:{...project.schedule,month_days,last_day}})}/><p className="cc-hint">Флажок означает последний календарный день месяца. {!project.config.services.length ? "Сначала выберите ИИ-сервис." : "Проверка начнётся на сервере в выбранное время."}</p></div></div>}
    </>}
    </fieldset>
    <div className="cc-savebar"><span role="status">{message || (dirty?"Есть несохранённые изменения":"Все изменения сохранены")}</span><button className="cc-button primary" disabled={busy||(!dirty&&projectId!=="new")||!project.name.trim()||!project.brand_name.trim()||!project.config.services.length||(project.schedule.enabled && !project.schedule.month_days.length && !project.schedule.last_day)} onClick={save}><Settings2 size={16}/>{busy?"Сохраняем…":"Сохранить"}</button></div>
    {brandClarificationsEnabled && tab === "settings" && projectId !== "new" && <section className="cc-form-section"><div><h2 ref={recomputeHeading} tabIndex={-1}>Пересчитать старые ответы</h2><p>Действует только на сохранённые ответы этого проекта. Новые запросы к поисковым системам не отправляются.</p></div><div className="cc-fields"><label>Начиная с даты включительно<input type="date" value={fromDate} onChange={e=>changeFromDate(e.target.value)}/></label><p className="cc-hint">Стоимость — 0,80 ₽ за каждый подходящий сохранённый ответ. Старые даты до выбранной не затрагиваются. Перед запуском покажем верхнюю границу списания. Если уйти со страницы, обработка остановится после текущего ответа; её можно продолжить без повторной оплаты уже готовых ответов.</p><span className="cc-quote-anchor"><button ref={recomputeButton} className="cc-button" aria-haspopup="dialog" aria-expanded={!!recomputeQuote} disabled={busy||dirty||!fromDate||!project.config.brand_clarification?.trim()} onClick={quoteRecompute}>Пересчитать ответы с этой даты</button>{recomputeQuote && <QuotePopover quote={recomputeQuote.quote} item="ответов" note={`Без достаточных данных: ${recomputeQuote.quote.skipped} — бесплатно. Новые проверки ИИ-сервисов не запускаются.`} action="Пересчитать" above trigger={recomputeButton} afterConfirm={recomputeHeading} onCancel={dismissRecomputeQuote} onConfirm={() => { const pending = recomputeQuote; setRecomputeQuote(null); void recompute(pending) }}/>}</span>{dirty && <p className="cc-hint">Сначала сохраните уточнение.</p>}{recomputeMessage && <p role="status">{recomputeMessage}</p>}</div></section>}
    </div>{tab !== "queries" && <aside className="side-note"><h3>{tab === "schedule" ? "Регулярные проверки" : "Что учитывается"}</h3><p>{tab === "schedule" ? project.schedule.enabled ? `${project.schedule.time} · ${project.schedule.timezone}. Числа месяца: ${scheduleDaysLabel(project.schedule)}.` : "Расписание выключено" : "Название, варианты написания и домены помогают находить бренд в ответах ИИ."}</p><hr className="form-divider"/><p>{tab === "schedule" ? "Сбор запускается автоматически. Последний день месяца определяется по выбранному часовому поясу, включая февраль в високосный год." : "Настройки применяются к новым проверкам после сохранения. Готовые ответы и история сохраняются."}</p><p>Перед ручным запуском показываем максимальную стоимость. Списываем оплату только за готовые ответы.</p></aside>}
  </div>
}
