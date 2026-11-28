import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react"
import { Activity, CalendarClock, CalendarDays, ChartNoAxesCombined, Check, ChevronRight, CircleAlert, Clock3, Flag, Link, List, Pause, Play, Plus, Search, Settings2, SlidersHorizontal, Square, Trash2, UserPlus, UserRoundPlus, Users, X } from "lucide-react"
import { Tooltip } from "@base-ui/react/tooltip"
import { accountRequest as request } from "./account-api"
import { SCAN_SERVICES, MONTH_DAYS } from "./lib/scan-preferences"
import { ReportView } from "./report-view"
import { ProjectAnalysis, SourceNavigation } from "./project-analysis"
import { QueryLibrary } from "./query-library"
import "./workspace.scss"
import { SiteHeader } from "./site-header"
import { CabinetSkeleton } from "./cabinet-loading"
import { IconNavLink } from "./icon-nav-link"
import { AppChoice } from "./app-choice"
import { ReportCalendar, type ReportDateSelection } from "./report-calendar"
import { today } from "./lib/dates"
import { plural } from "./lib/format"
import { recomputeSelection, selectionLabel, type RecomputeSelection } from "./recompute-selection"
import { ServiceMark, isCurrentService } from "./service-mark"
import { ProjectIcon } from "./project-icon"
import "./prototype.scss"
import "./app-layout.scss"
import { publicError } from "./lib/public-error"
import "./control-center.scss"
import "./icon-sidebar.scss"
import "./project-registry.scss"
import "./project-analysis.scss"
import "./run-history.scss"

type Query = { id: string; text: string; group_tag: string; active: boolean }
type Config = { brand_aliases: string[]; brand_domains: string[]; brand_clarification?: string; region_code: string; services: string[]; browser_mode: string; speed_profile: string; parallel: boolean }
type Schedule = { enabled: boolean; device_id: string | null; month_days: number[]; last_day?: boolean; time: string; timezone: string }
type Project = { id: string; revision: number; name: string; brand_name: string; device_id: string | null; config: Config; schedule: Schedule; queries: Query[]; query_count: number; active_queries: number; role?: "owner"|"editor"|"viewer"; shared?: boolean; brand_clarifications_enabled?: boolean }
type Run = { id: string; project_id: string; project_name: string; device_id: string | null; device_name: string; phase?: string; state: string; desired_state: string; error: string | null; total: number; created_at: string; scheduled_for: string | null; progress: { done?: number; total?: number; services?: Record<string, {done:number; total:number; state?:string; error?:string}> } }
type Quote = { count: number; free_count?: number; unit_kopeks: number; total_kopeks: number; available_kopeks: number; revision: number; provider_state?: string; free_scans_state?: string; payer?: string }
type RecomputeQuote = Quote & RecomputeSelection & { result_ids: string[]; skipped: number }
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
export function scanPercent(done: number, total: number, step = 5) {
  return total > 0 ? Math.max(0, Math.min(100, Math.floor(done * (100 / step) / total) * step)) : 0
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
  return <div ref={dialog} className={`cc-quote-popover${above ? " above" : ""}`} role="dialog" aria-modal="false" aria-label={`Подтверждение: ${action}`}><p>К списанию: до <b>{money(quote.total_kopeks)}</b></p><small>{quote.free_count ? `${quote.free_count} бесплатно по промокоду · ${quote.count - quote.free_count} платных × ${money(quote.unit_kopeks)}` : `${quote.count} ${item} × ${money(quote.unit_kopeks)}`} · доступно {money(quote.available_kopeks)}</small>{quote.payer === "owner" && <p className="cc-quote-note">Оплата и промокоды владельца проекта.</p>}<p className="cc-quote-note">{note}</p><div><button className="cc-quote-cancel" onClick={onCancel}>Отменить</button><button className="cc-button primary" onClick={() => { confirmed.current = true; onConfirm(); requestAnimationFrame(() => afterConfirm?.current?.focus()) }}>{action}</button></div></div>
}

const registryFilters = [
  { id: "all", label: "Все проекты" },
  { id: "scheduled", label: "По расписанию" },
  { id: "active", label: "Активные проверки" },
] as const
type RegistryFilter = typeof registryFilters[number]["id"]
const registryNumber = new Intl.NumberFormat("ru-RU")
const registryPlural = new Intl.PluralRules("ru-RU")

function registryScheduleDays(schedule: Schedule) {
  const days = schedule.month_days.map(day => String(day) + "-го").join(", ")
  if (!days) return scheduleDaysLabel(schedule)
  return schedule.last_day ? days + " и в последний день месяца" : days + " числа"
}

function ProjectTotals({ projects }: { projects: Project[] }) {
  const count = projects.length
  const queries = projects.reduce((total, project) => total + project.query_count, 0)
  const projectWord = { one: "проект", few: "проекта", many: "проектов" }[registryPlural.select(count) as "one" | "few" | "many"]
  const queryWord = { one: "запрос", few: "запроса", many: "запросов" }[registryPlural.select(queries) as "one" | "few" | "many"]
  return <p className="project-registry__summary">
    <strong>{registryNumber.format(count)}</strong> {projectWord} <span aria-hidden="true">·</span> <strong>{registryNumber.format(queries)}</strong> {queryWord}
  </p>
}

function RegistryCheck({ project, run, openRun }: { project: Project; run?: Run; openRun: (id: string) => void }) {
  if (!run) return <span className="project-registry__status-label"><Check size={16} aria-hidden="true"/>Готов к проверкам</span>
  const status = runStatus(run)
  const queued = status === names.queued
  const paused = status === names.paused
  const Icon = paused ? Pause : queued ? Clock3 : Activity
  const label = status === names.running ? "Идёт проверка" : status
  const percent = scanPercent(run.progress.done ?? 0, run.total, 1)
  const showProgress = !queued || percent > 0
  return <button
    type="button"
    className={paused || queued ? "project-registry__check-button project-registry__check-button--waiting" : "project-registry__check-button"}
    aria-label={`${label}${showProgress ? ` ${percent}%` : ""} — ${project.name}`}
    aria-haspopup="dialog"
    onClick={() => openRun(run.id)}
  >
    <span className="project-registry__status-label"><Icon size={16} aria-hidden="true"/><span>{label}</span>{showProgress && <strong>{percent}%</strong>}</span>
    {showProgress && <progress max={100} value={percent} aria-hidden="true"/>}
  </button>
}

export function ProjectRegistry({ projects, activeRuns, loading, loadFailed, search, filter, onSearch, onFilter, openRun }: {
  projects: Project[]
  activeRuns: Run[]
  loading: boolean
  loadFailed: boolean
  search: string
  filter: RegistryFilter
  onSearch: (search: string) => void
  onFilter: (filter: RegistryFilter) => void
  openRun: (id: string) => void
}) {
  const searchInput = useRef<HTMLInputElement>(null)
  const term = search.trim().toLocaleLowerCase("ru-RU")
  const rows = projects.map(project => ({ project, run: activeRuns.find(item => item.project_id === project.id) })).filter(({ project, run }) => {
    if (filter === "scheduled" && (project.role === "viewer" || !project.schedule.enabled)) return false
    if (filter === "active" && !run) return false
    return [project.name, project.brand_name, project.id].some(value => value.toLocaleLowerCase("ru-RU").includes(term))
  })

  return <section className="project-registry" aria-label="Реестр проектов">
    <div className="project-registry__toolbar">
      <label className="search-box project-registry__search">
        <Search size={17} aria-hidden="true"/>
        <input ref={searchInput} type="search" aria-label="Поиск проекта" placeholder="Найти проект или бренд" value={search} onChange={event => onSearch(event.target.value)}/>
      </label>
      <div className="project-registry__filters" role="group" aria-label="Фильтр проектов">
        {registryFilters.map(option => <button type="button" key={option.id} aria-pressed={filter === option.id} onClick={() => onFilter(option.id)}>{option.label}</button>)}
      </div>
    </div>
    {loading ? <div className="panel"><CabinetSkeleton label="Загрузка проектов…"/></div> : !projects.length ? (
      !loadFailed && <div className="panel empty-state"><h2>Начните с первого проекта</h2><p>Укажите бренд, добавьте запросы и выберите ИИ-системы.</p><a className="btn primary" href="#/project/new/settings">Создать проект</a></div>
    ) : !rows.length ? (
      <div className="panel empty-state project-registry__empty">
        <h2>Проекты не найдены</h2>
        <p>Попробуйте другой запрос или сбросьте фильтры.</p>
        <button type="button" className="btn" onClick={() => { onSearch(""); onFilter("all"); searchInput.current?.focus() }}>Сбросить фильтры</button>
      </div>
    ) : (
      <div className="panel table-scroll project-registry__table-wrap" role="region" tabIndex={0} aria-label="Список проектов">
        <table className="project-registry__table" role="table" aria-label="Проекты">
          <thead role="rowgroup"><tr role="row">
            <th scope="col" role="columnheader">Проект</th>
            <th scope="col" role="columnheader" className="project-registry__check">Проверка</th>
            <th scope="col" role="columnheader">Запросы</th>
            <th scope="col" role="columnheader">ИИ-системы</th>
            <th scope="col" role="columnheader">Расписание</th>
          </tr></thead>
          <tbody role="rowgroup">
            {rows.map(({ project, run }) => {
              const services = project.config.services.filter(isCurrentService)
              return <tr key={project.id} role="row">
                <td role="cell" className="project-registry__identity">
                  <a href={`#/project/${project.id}/report`}>
                    <ProjectIcon name={project.name} domains={project.config.brand_domains}/>
                    <span><strong>{project.name}</strong><small>{project.brand_name}{project.shared ? (project.role === "editor" ? " · редактор" : " · только просмотр") : ""}</small></span>
                    <ChevronRight size={16} className="project-registry__mobile-chevron" aria-hidden="true"/>
                  </a>
                </td>
                <td role="cell" className="project-registry__check"><RegistryCheck project={project} run={run} openRun={openRun}/></td>
                <td role="cell" className="project-registry__queries"><span className="project-registry__mobile-label">Запросы </span><strong>{registryNumber.format(project.query_count)}</strong><small>{registryNumber.format(project.active_queries)} активно</small></td>
                <td role="cell" className="project-registry__systems">
                  {services.length ? <ul aria-label="ИИ-системы">{services.map(id => <li key={id} title={service(id)} aria-label={service(id)}><ServiceMark id={id}/></li>)}</ul> : <small>Не выбраны</small>}
                </td>
                <td role="cell" className="project-registry__schedule">
                  {project.role === "viewer" ? <span title="Расписание недоступно">—</span> : (
                    <a href={`#/project/${project.id}/schedule`}>
                      <CalendarDays size={16} aria-hidden="true"/>
                      {project.schedule.enabled
                        ? <span><strong>{project.schedule.time}</strong><small>{registryScheduleDays(project.schedule)}</small></span>
                        : <small>По запросу</small>}
                    </a>
                  )}
                </td>
              </tr>
            })}
          </tbody>
        </table>
      </div>
    )}
    <p className="project-registry__count" role="status">{!loading && projects.length > 0 && `Показано ${rows.length} из ${projects.length}`}</p>
  </section>
}


const runSources = [
  { value: "all", label: "Все запуски" },
  { value: "manual", label: "Вручную" },
  { value: "scheduled", label: "По расписанию" },
] as const
const runStatuses = [{ value: "", label: "Все статусы" }, ...[...Object.values(names), "Останавливается"].map(label => ({ value: label, label }))]
const runDate = new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" })

function RunHistory({ runs, projects, loading, loadFailed, busy, openRun, command }: {
  runs: Run[]; projects: Project[]; loading: boolean; loadFailed: boolean; busy: boolean
  openRun: (id: string) => void
  command: (id: string, action: "pause" | "resume" | "stop") => void
}) {
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("")
  const [source, setSource] = useState<typeof runSources[number]["value"]>("all")
  const searchInput = useRef<HTMLInputElement>(null)
  const term = search.trim().toLocaleLowerCase("ru-RU")
  const rows = runs.filter(run =>
    (!status || runStatus(run) === status) &&
    (source === "all" || (source === "scheduled") === !!run.scheduled_for) &&
    run.project_name.toLocaleLowerCase("ru-RU").includes(term)
  )
  const projectsById = new Map(projects.map(project => [project.id, project]))
  function reset() { setSearch(""); setStatus(""); setSource("all"); searchInput.current?.focus() }

  return <section className="project-registry run-history" aria-label="Запуски проверок">
    <div className="project-registry__toolbar">
      <label className="search-box project-registry__search"><Search size={17} aria-hidden="true"/>
        <input ref={searchInput} type="search" aria-label="Поиск проверок по проекту" placeholder="Найти проект" value={search} onChange={event => setSearch(event.target.value)}/>
      </label>
      <div className="run-history__filters">
        <div className="project-registry__filters" role="group" aria-label="Тип запуска">
          {runSources.map(option => <button key={option.value} type="button" aria-pressed={source === option.value} onClick={() => setSource(option.value)}>{option.label}</button>)}
        </div>
        <AppChoice label="Статус проверки" value={status} options={runStatuses} change={setStatus}/>
      </div>
    </div>
    {loading ? <div className="panel"><CabinetSkeleton label="Загрузка проверок…"/></div> : !runs.length ? (
      !loadFailed && <div className="panel empty-state project-registry__empty"><h2>Проверок пока нет</h2><p>Откройте проект, чтобы запустить первую проверку.</p><a className="btn" href="#/projects">К проектам</a></div>
    ) : !rows.length ? (
      <div className="panel empty-state project-registry__empty"><h2>Проверки не найдены</h2><button type="button" className="btn" onClick={reset}>Сбросить фильтры</button></div>
    ) : (
      <div className="panel table-scroll project-registry__table-wrap" role="region" tabIndex={0} aria-label="Список запусков">
        <table className="project-registry__table run-history__table" role="table" aria-label="История проверок">
          <thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">Проект и запуск</th><th scope="col" role="columnheader">Статус</th><th scope="col" role="columnheader">Проверки</th><th scope="col" role="columnheader">Действия</th></tr></thead>
          <tbody role="rowgroup">{rows.map(run => {
            const project = projectsById.get(run.project_id)
            const pending = !terminal(run)
            const label = runStatus(run)
            const paused = run.desired_state === "paused"
            const complete = run.progress.done ?? 0
            const StatusIcon = run.state === "done" ? Check : run.state === "failed" ? CircleAlert : paused ? Pause : pending && label === names.running ? Activity : Clock3
            const tone = run.state === "done" ? "good" : run.state === "failed" ? "bad" : paused || label === names.queued ? "waiting" : pending ? "active" : "muted"
            return <tr key={run.id} role="row">
              <td role="cell" className="project-registry__identity">
                <button type="button" className="run-history__project" aria-haspopup="dialog" onClick={() => openRun(run.id)}>
                  <ProjectIcon name={run.project_name} domains={project?.config.brand_domains ?? []}/>
                  <span><strong>{run.project_name}</strong><small><time dateTime={run.created_at}>{runDate.format(new Date(run.created_at))}</time> · {run.scheduled_for ? "По расписанию" : "Вручную"}</small></span>
                  <ChevronRight size={16} aria-hidden="true"/>
                </button>
              </td>
              <td role="cell"><span className={`run-history__status run-history__status--${tone}`}><StatusIcon size={16} aria-hidden="true"/>{label}</span></td>
              <td role="cell" className="run-history__completion">
                <span><strong>{complete}</strong> / {run.total}</span>
                {pending && <progress value={complete} max={run.total || 1} aria-label={`Ход проверки проекта ${run.project_name}`}/>}
              </td>
              <td role="cell" className="run-history__actions"><div className="cc-actions">
                {pending && <>
                  <button type="button" className="btn" disabled={busy} onClick={() => command(run.id, paused ? "resume" : "pause")}>{paused ? <Play size={14} aria-hidden="true"/> : <Pause size={14} aria-hidden="true"/>}{paused ? "Продолжить" : "Пауза"}</button>
                  <button type="button" className="btn" disabled={busy} onClick={() => command(run.id, "stop")}><Square size={13} aria-hidden="true"/>Стоп</button>
                </>}
                {project && <a className="btn" href={`#/project/${run.project_id}/report`}>Отчёт<ChevronRight size={14} aria-hidden="true"/></a>}
              </div></td>
            </tr>
          })}</tbody>
        </table>
      </div>
    )}
    <p className="project-registry__count" role="status">{!loading && runs.length > 0 && `Показано ${rows.length} из ${runs.length}`}</p>
  </section>
}

export function ControlCenter({ token, brandClarificationsEnabled, onDirtyChange, email, avatarUrl, balance, admin, account, message, logout, walletChanged }: {
  token: string; brandClarificationsEnabled: boolean; onDirtyChange: (dirty: boolean) => void;
  email: string; avatarUrl?: string | null; balance: string; admin: boolean; account: ReactNode; message: string; logout: () => void; walletChanged: () => void
}) {
  const [route, setRoute] = useState(routeNow)
  const [lastProject, setLastProject] = useState(() => routeNow().split("/")[1] || "")
  const editorDirty = useRef(false), editorProject = useRef(""), previousHash = useRef(location.hash), previousPosition = useRef(0), restoringHistory = useRef(false)
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsLoaded, setProjectsLoaded] = useState(false)
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [projectNotice, setProjectNotice] = useState("")
  const [copyMessage, setCopyMessage] = useState<{id:string;text:string}|null>(null)
  const [busy, setBusy] = useState("")
  const [projectSearch, setProjectSearch] = useState("")
  const [projectFilter, setProjectFilter] = useState<RegistryFilter>("all")
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
    setProjects(p); setRuns(r); setProjectsLoaded(true); setError(""); setLoading(false)
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
      if (next !== "#/projects") setProjectNotice("")
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
    if (quote.total_kopeks > 0 && quote.available_kopeks < quote.total_kopeks) throw new Error(`Для запуска нужно до ${money(quote.total_kopeks)}. Сейчас доступно ${money(quote.available_kopeks)}.`)
    setScanQuote({projectId, quote})
  }
  async function launch(projectId: string, quote: Quote) {
    await request(`/control/projects/${projectId}/runs`, token, {request_id:uuid(), revision:quote.revision, provider_state:quote.provider_state, free_scans_state:quote.free_scans_state})
  }
  function projectArchived(id: string) {
    if (!mounted.current) return
    setProjects(current => current.filter(project => project.id !== id))
    if (routeNow().split("/")[1] === id) {
      setProjectNotice("Проект удалён.")
      location.hash = "/projects"
      requestAnimationFrame(() => projectHeading.current?.focus())
    }
    void refresh().catch(e => { if (mounted.current) setError(e.message) })
  }
  const [area, routeProject, projectTab] = route.split("/")
  const projectId = area === "projects" ? undefined : routeProject || projects.find(p => p.id === lastProject)?.id || projects[0]?.id
  const selected = projects.find(p => p.id === projectId)
  const activeRuns = runs.filter(r => !terminal(r))
  const projectRun = activeRuns.find(r => r.project_id === projectId)
  const lastFinishedRunId = runs.find(r => r.project_id === projectId && terminal(r))?.id
  const requestedTab = projectTab || "report"
  const viewer = selected?.role === "viewer"
  const tab = (viewer && !["report", "sources", "source-domains", "competitors"].includes(requestedTab)) || (requestedTab === "access" && selected?.role !== "owner") ? "report" : requestedTab
  const projectLink = (next: string) => projectId ? `#/project/${projectId}/${next}` : "#/projects"
  const nav = [
    ["report", "Обзор видимости", ChartNoAxesCombined],
    ...(!viewer ? [["queries", "Запросы", List] as const] : []), ["competitors", "Конкуренты", Users], ["sources", "Источники", Link],
    ...(!viewer ? [["settings", "Настройки проекта", SlidersHorizontal] as const, ["schedule", "Расписание", CalendarDays] as const] : []),
    ...(selected?.role === "owner" ? [["access", "Доступ", UserRoundPlus] as const] : []),
    ...(!viewer ? [["runs", "История проверок", Play] as const] : []),
  ] as const
  const page = area === "project" ? tab : area === "overview" ? "report" : area === "topup" ? "account" : area
  useEffect(() => { if (page === "help") location.replace("/docs/") }, [page])
  const title = projectId === "new" ? "Новый проект" : ({projects: "Проекты", account: "Аккаунт и оплата", help: "Документация"} as Record<string, string>)[page] || nav.find(([id]) => id === (page === "source-domains" ? "sources" : page))?.[1] || "Обзор видимости"
  const currentRun = runs.find(r => r.id === runDetail)
  const projectIds = new Set(projects.map(project => project.id))
  function openRun(id: string) {
    setRunDetail(id)
    runDialog.current?.showModal()
  }
  const progress = projectRun ? scanPercent(projectRun.progress.done ?? 0,projectRun.total) : 0
  const scanLabel = projectRun ? `${runStatus(projectRun)}: ${progress}%` : "Запустить проверку"
  const scanControl = <span className="cc-quote-anchor">
    <Tooltip.Root><Tooltip.Trigger delay={180} render={<button ref={scanButton} className="btn icon-only scan-launch" aria-label={scanLabel} aria-haspopup={projectRun ? undefined : "dialog"} aria-expanded={projectRun ? undefined : scanQuote?.projectId === projectId} aria-disabled={!!projectRun} disabled={!projectRun && (!!busy || !selected?.config.services.length || !selected.active_queries || needsAgent(selected.config.services))} onClick={() => { if (!projectRun) void action(projectId!, () => quoteLaunch(projectId!)) }}/>}>{projectRun ? <ScanProgress percent={progress}/> : <Play size={18} aria-hidden="true"/>}</Tooltip.Trigger>
      <Tooltip.Portal><Tooltip.Positioner side="bottom" sideOffset={12} className="air-nav-tip-positioner"><Tooltip.Popup className="air-nav-tip" role="tooltip"><Tooltip.Arrow className="air-nav-tip-arrow"/>{scanLabel}</Tooltip.Popup></Tooltip.Positioner></Tooltip.Portal>
    </Tooltip.Root>
    {scanQuote && scanQuote.projectId === projectId && <QuotePopover quote={scanQuote.quote} item="проверок" note={selected?.role === "editor" ? "Оплата с баланса владельца проекта. Списываем только за завершённые проверки с ответом." : "Оплачиваются только завершённые проверки с ответом."} action="Запустить" trigger={scanButton} afterConfirm={projectHeading} onCancel={dismissScanQuote} onConfirm={() => { if (scanSubmitting.current) return; scanSubmitting.current = true; const pending = scanQuote; setScanQuote(null); void action(projectId!, () => launch(projectId!, pending.quote)).finally(() => { scanSubmitting.current = false }) }}/>}
  </span>
  const analysisPage = ["sources", "source-domains", "competitors"].includes(page)
  return <div className={`air-app${page === "projects" ? " projects-page" : ""}${analysisPage ? " project-analysis-page" : ""}`}>
    <a className="skip-link" href="#app-content" onClick={event => { event.preventDefault(); main.current?.focus() }}>К содержимому</a>
    <SiteHeader cabinet email={email} avatarUrl={avatarUrl} balance={balance} projects={projects} selectedId={selected?.id} loading={loading} admin={admin} logout={logout}/>
    {page !== "projects" && <aside className="sidebar">
      <nav aria-label="Разделы приложения">{nav.map(([id, label, Icon]) => <IconNavLink key={id} className="nav-link" label={label} current={page === id || (id === "sources" && page === "source-domains")} href={["report","queries","sources","competitors","settings","schedule","access"].includes(id) ? projectLink(id) : `#/${id}`}><Icon size={16} strokeWidth={1.7} aria-hidden="true"/></IconNavLink>)}</nav>
    </aside>}
    <main ref={main} className="app-main" id="app-content" tabIndex={-1}>
      {page !== "projects" && <div className="breadcrumb"><a href="#/projects">Проекты</a><ChevronRight size={12}/>{selected && page !== "runs" && <><span>{selected.name}</span><ChevronRight size={12}/></>}<span className="current">{title}</span></div>}
      <div className={page === "queries" ? "heading-row project-registry__heading query-editor__heading" : ["projects", "runs"].includes(page) ? "heading-row project-registry__heading" : "heading-row"}><div><div className="heading-title"><h1 ref={projectHeading} tabIndex={-1}>{title}</h1>{selected && ["project","overview"].includes(area) && <span className="domain-label">{selected.config.brand_domains[0] || selected.brand_name}</span>}</div>{page === "projects" ? (projectsLoaded && <ProjectTotals projects={projects}/>) : page === "runs" ? (projectsLoaded && <p className="project-registry__summary"><strong>{registryNumber.format(runs.length)}</strong> {plural(runs.length, "запуск", "запуска", "запусков")} <span aria-hidden="true">·</span> <strong>{registryNumber.format(activeRuns.length)}</strong> {activeRuns.length === 1 ? "активный" : "активных"}</p>) : page !== "queries" && <p className="subtitle">{page === "report" ? "Как часто ИИ упоминает ваш бренд и откуда берёт информацию." : page === "sources" ? "Страницы, на которые ссылаются ИИ в ответах на запросы проекта." : page === "source-domains" ? "Домены в ответах с упоминанием бренда." : page === "competitors" ? "Кого ИИ упоминает по вашим запросам и где пропускает ваш бренд." : page === "schedule" ? "Автоматические проверки в выбранные дни месяца." : ""}</p>}</div>
        <div className="heading-actions">{selected && page !== "runs" && <span className="row-note">ID: <code style={{overflowWrap:"anywhere"}}>{selected.id}</code> · {selected.role === "owner" ? "Владелец" : selected.role === "editor" ? "Редактор" : "Просмотр"} <button className="text-link" aria-label="Копировать ID проекта" onClick={async()=>{try {await navigator.clipboard.writeText(selected.id);setCopyMessage({id:selected.id,text:"ID скопирован"})} catch {setCopyMessage({id:selected.id,text:"Не удалось скопировать. Выделите ID вручную."})}}}>Копировать</button>{copyMessage?.id === selected.id && <span role="status"> · {copyMessage.text}</span>}</span>}{page === "projects" ? <a className="btn primary project-registry__new" href="#/project/new/settings"><Plus size={17} aria-hidden="true"/>Новый проект</a> : null}</div>
      </div>
      {error && <div className="cc-alert" role="alert">{error}<button className="btn" onClick={() => refresh().catch(e => setError(e.message))}>Повторить</button>{(page !== "projects" || projectsLoaded) && <button className="btn icon-only" aria-label="Закрыть сообщение" onClick={() => setError("")}><X size={16}/></button>}</div>}
      {message && <p className="notice" role="status">{message}</p>}
      {page === "projects" && projectNotice && <p className="notice" role="status">{projectNotice}</p>}
      {page === "account" ? account : page === "help" ? <p className="page-intro">Открываем документацию… <a href="/docs/">Перейти к документации</a></p> : loading && ["project","overview"].includes(area) && projectId !== "new" ? <CabinetSkeleton label="Загрузка проекта…" format={page === "report" ? "report" : "rows"}/> : ["project","overview"].includes(area) && projectId ? <>
        {["sources", "source-domains"].includes(tab) && projectId !== "new" && <SourceNavigation projectId={projectId} pages={tab === "sources"}/>}
        {tab === "access" && selected?.role === "owner" ? <ProjectAccess key={projectId} token={token} projectId={projectId}/>
          : ["competitors", "sources"].includes(tab) && projectId !== "new" ? <ProjectAnalysis key={projectId + tab} token={token} projectId={projectId} mode={tab === "sources" ? "citations" : "competitors"} canEdit={!viewer} lastFinishedRunId={lastFinishedRunId}/>
          : ["report", "source-domains"].includes(tab) && projectId !== "new" ? <ReportView key={projectId} token={token} projectId={projectId} projectName={selected?.name ?? ""} projectServices={selected?.config.services || []} lastFinishedRunId={lastFinishedRunId} sourcesOnly={tab === "source-domains"} canEdit={!viewer} scanControl={viewer ? undefined : scanControl}/>
          : <ProjectEditor key={projectId} token={token} projectId={projectId} tab={projectId === "new" ? "settings" : tab} brandClarificationsEnabled={brandClarificationsEnabled} admin={admin} saved={refresh} archived={projectArchived} onDirtyChange={noteEditorDirty} walletChanged={walletChanged}/>}
      </> : page === "runs" ? <RunHistory runs={runs} projects={projects} loading={loading} loadFailed={!projectsLoaded} busy={!!busy} openRun={openRun} command={(id, command) => void action(id, () => request(`/control/runs/${id}/command`, token, {action:command}))}/> : (
        <ProjectRegistry projects={projects} activeRuns={activeRuns} loading={loading} loadFailed={!projectsLoaded} search={projectSearch} filter={projectFilter} onSearch={setProjectSearch} onFilter={setProjectFilter} openRun={openRun}/>
      )}
      <dialog ref={runDialog} aria-labelledby="run-title"><div className="dialog-head"><h2 id="run-title">Проверка проекта</h2><button className="btn icon-only" aria-label="Закрыть проверку" onClick={() => runDialog.current?.close()}><X size={16}/></button></div><div className="dialog-body">{currentRun ? <><h3>{currentRun.project_name}</h3><p>{runStatus(currentRun)} · {currentRun.progress.done || 0} / {currentRun.total} проверок</p>{currentRun.error && <p className="cc-error-text">{publicError(currentRun.error)}</p>}{Object.entries(currentRun.progress.services || {}).filter(([id])=>isCurrentService(id)).map(([id, stats]) => <p key={id}>{service(id)}: {stats.done} / {stats.total}{stats.error ? ` · ${publicError(stats.error)}` : ""}</p>)}<p>Незавершённые запросы остаются в очереди; счётчик показывает готовые ответы.</p>{projectIds.has(currentRun.project_id) && <a className="btn blue" href={`#/project/${currentRun.project_id}/report`} onClick={() => runDialog.current?.close()}>Открыть отчёт</a>}</> : <p>Проверка недоступна</p>}</div></dialog>
    </main>
  </div>
}

function ProjectAccess({ token, projectId }: {token:string;projectId:string}) {
  const [members,setMembers] = useState<{email:string;role:"owner"|"editor"|"viewer"}[]>([])
  const [email,setEmail] = useState("")
  const [role,setRole] = useState<"editor"|"viewer">("editor")
  const [busy,setBusy] = useState(false), [loading,setLoading] = useState(true), [error,setError] = useState("")
  const load = useCallback(async (alive: () => boolean = () => true) => { try {const next=await request<{email:string;role:"owner"|"editor"|"viewer"}[]>(`/control/projects/${projectId}/members`,token);if(alive()){setMembers(next);setError("")}} catch(e) {if(alive())setError(e instanceof Error?e.message:"Не удалось загрузить доступ")} finally {if(alive())setLoading(false)} }, [projectId,token])
  useEffect(() => { let alive=true; void load(()=>alive); return () => {alive=false} }, [load])
  async function save() { if (!email.trim() || busy) return; setBusy(true);setError("");try {await request(`/control/projects/${projectId}/members`,token,{email,role},"PUT");setEmail("");await load()} catch(e) {setError(e instanceof Error?e.message:"Не удалось сохранить доступ")} finally {setBusy(false)} }
  async function remove(memberEmail:string) { if (busy) return;setBusy(true);setError("");try {await request(`/control/projects/${projectId}/members/${encodeURIComponent(memberEmail)}`,token,undefined,"DELETE");await load()} catch(e) {setError(e instanceof Error?e.message:"Не удалось отозвать доступ")} finally {setBusy(false)} }
  return <section className="panel cc-editor"><div className="cc-form-section"><div><h2><UserPlus size={21}/>Доступ к проекту</h2><p>Добавляйте только уже зарегистрированные email. Приглашения по почте не отправляются.</p></div><div className="cc-fields"><label>Email участника<input type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="user@company.ru" disabled={busy}/></label><AppChoice label="Роль" value={role} options={[{value:"editor",label:"Редактор — настройки, запросы и запуски"},{value:"viewer",label:"Просмотр — только результаты"}]} change={value=>setRole(value as "editor"|"viewer")}/><button className="cc-button primary" disabled={busy||!email.trim()} onClick={save}>Добавить или изменить роль</button>{error&&<p className="cc-alert" role="alert">{error}</p>}</div></div>{loading?<CabinetSkeleton label="Загружаем участников…"/>:<div className="table-scroll"><table><thead><tr><th>Email</th><th>Роль</th><th/></tr></thead><tbody>{members.map(member=><tr key={member.email}><td>{member.email}</td><td>{member.role === "owner" ? "Владелец" : member.role === "editor" ? "Редактор" : "Просмотр"}</td><td>{member.role !== "owner"&&<button className="btn" disabled={busy} onClick={()=>remove(member.email)}>Отозвать</button>}</td></tr>)}</tbody></table>{!members.length&&<p className="empty-state">Участников пока нет.</p>}</div>}</section>
}

function ProjectEditor({token,projectId,tab,brandClarificationsEnabled,admin,saved,archived,onDirtyChange,walletChanged}:{token:string;projectId:string;tab:string;brandClarificationsEnabled:boolean;admin:boolean;saved:()=>Promise<void>;archived:(id:string)=>void;onDirtyChange:(dirty:boolean,projectId:string)=>void;walletChanged:()=>void}) {
  const [project,setProject] = useState<Project|null>(projectId === "new" ? blank() : null)
  const [dirty,setDirty] = useState(false)
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState("")
  const [error,setError] = useState("")
  const [fromDate,setFromDate] = useState(today)
  const [toDate,setToDate] = useState(today)
  const [dateSelection,setDateSelection] = useState<ReportDateSelection>({mode:"from",picked:[],maxDates:30})
  const [availableDates,setAvailableDates] = useState<string[]>([])
  const [recomputeMessage,setRecomputeMessage] = useState("")
  const [recomputeQuote,setRecomputeQuote] = useState<RecomputeQuote|null>(null)
  const dirtyRef = useRef(false), busyRef = useRef(false), mounted = useRef(true)
  const recomputeButton = useRef<HTMLButtonElement>(null)
  const recomputeQuoteRequest = useRef(0)
  const recomputeHeading = useRef<HTMLHeadingElement>(null)
  const deleteDialog = useRef<HTMLDialogElement>(null)
  const [deleteError, setDeleteError] = useState("")
  const dismissRecomputeQuote = useCallback(() => { recomputeQuoteRequest.current++; setRecomputeQuote(null) }, [])
  useEffect(() => () => { mounted.current = false }, [])
  useEffect(() => { onDirtyChange(dirty, projectId); return () => onDirtyChange(false, projectId) }, [dirty, onDirtyChange, projectId])
  useEffect(() => {if(projectId !== "new"){let alive=true;request<Project>(`/control/projects/${projectId}`,token).then(p=>{if(alive)setProject(p)}).catch(e=>{if(alive)setError(e.message)});return()=>{alive=false}}},[projectId,token])
  useEffect(() => { recomputeQuoteRequest.current++; setRecomputeQuote(null) }, [fromDate, toDate, dateSelection, dirty, tab])
  useEffect(() => {
    if (projectId === "new" || tab !== "settings" || project?.role !== "owner") return
    let alive = true
    request<{dates:string[]}>(`/control/projects/${projectId}/recompute/dates`,token).then(data=>{if(alive)setAvailableDates(data.dates)}).catch(e=>{if(alive)setError(e.message)})
    return () => {alive=false}
  }, [projectId, project?.role, tab, token])
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
  function changeDates(from: string, to: string, selection: ReportDateSelection){
    if(busyRef.current || dirtyRef.current)return
    recomputeQuoteRequest.current++;setRecomputeQuote(null);setFromDate(from);setToDate(to);setDateSelection(selection);setRecomputeMessage("")
  }
  async function save(){if(!project)return;busyRef.current=true;setBusy(true);setError("");try{
    const {revision,name,brand_name,device_id,schedule,queries}=project
    const config={...project.config,services:project.config.services.filter(isCurrentService),speed_profile:"fast"}
    const next=await request<Project>(projectId==="new"?"/control/projects":`/control/projects/${projectId}`,token,{revision,name,brand_name,device_id,config,schedule,queries},projectId==="new"?"POST":"PUT")
    if(!mounted.current)return
    dirtyRef.current=false;onDirtyChange(false,projectId);setProject(next);setDirty(false);setMessage("Сохранено. Текущая проверка использует настройки на момент запуска.");await saved()
    if(mounted.current&&projectId==="new")location.hash=`/project/${next.id}/queries`
  }catch(e){if(mounted.current)setError(e instanceof Error?e.message:"Не удалось сохранить проект")}finally{busyRef.current=false;if(mounted.current)setBusy(false)}}
  async function removeProject() {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true); setDeleteError("")
    try {
      await request(`/control/projects/${projectId}`, token, undefined, "DELETE")
      if (mounted.current) {
        dirtyRef.current = false; setDirty(false); onDirtyChange(false, projectId)
        deleteDialog.current?.close()
      }
      archived(projectId)
    } catch (e) {
      if (mounted.current) setDeleteError(e instanceof Error ? e.message : "Не удалось удалить проект")
    } finally {
      busyRef.current = false
      if (mounted.current) setBusy(false)
    }
  }
  async function quoteRecompute(){
    if (!project || projectId === "new" || !fromDate || dirty || busyRef.current) return
    const scope = recomputeSelection(fromDate,toDate,availableDates,dateSelection)
    const params = new URLSearchParams({from_date:scope.from_date})
    if(scope.to_date)params.set("to_date",scope.to_date)
    if(scope.dates)params.set("dates",scope.dates.join(","))
    const requestVersion = ++recomputeQuoteRequest.current; setRecomputeQuote(null)
    busyRef.current=true;setBusy(true);setError("");setRecomputeMessage("")
    try {
      const quote=await request<RecomputeQuote>(`/control/projects/${projectId}/recompute/quote?${params}`,token)
      if (!mounted.current || requestVersion !== recomputeQuoteRequest.current) return
      if (!quote.count) {setRecomputeMessage(`Нет ответов для пересчёта: ${selectionLabel(quote)}.${quote.skipped ? ` Без достаточных сохранённых данных: ${quote.skipped}.` : ""}`);return}
      if (quote.total_kopeks > 0 && quote.available_kopeks < quote.total_kopeks) {setError(`Для пересчёта ${quote.count} ответов нужно до ${money(quote.total_kopeks)}. Сейчас доступно ${money(quote.available_kopeks)}. Пополните баланс или выберите более позднюю дату.`);return}
      setRecomputeQuote(quote)
    } catch(e) {if(mounted.current && requestVersion === recomputeQuoteRequest.current)setError(e instanceof Error?e.message:"Не удалось получить стоимость пересчёта")}
    finally {busyRef.current=false;if(mounted.current)setBusy(false)}
  }
  async function recompute(quote: RecomputeQuote){
    if (busyRef.current || dirtyRef.current) return
    busyRef.current=true;setBusy(true);setError("");setRecomputeMessage("")
    try {
      let done=0, skipped=0, failed=0, charged=0
      for (const id of quote.result_ids) {
        if (!mounted.current) break
        try {
          const result=await request<RecomputeResult>(`/control/projects/${projectId}/recompute/${id}`,token,{from_date:quote.from_date,to_date:quote.to_date,dates:quote.dates,revision:quote.revision})
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
  if(!project)return error?<p className="cc-alert" role="alert">{error}</p>:<CabinetSkeleton label="Загрузка проекта…"/>
  const clarificationEnabled = projectId === "new" ? brandClarificationsEnabled : !!project.brand_clarifications_enabled
  return <div className={tab === "queries" ? "cc-editor query-editor" : "cc-editor settings-layout"}><div>
    {error&&<p className="cc-alert" role="alert">{error}</p>}
    <fieldset disabled={busy}>
    {tab==="queries"?<QueryLibrary queries={project.queries} saving={busy} onChange={queries=>change({...project,queries})}/>:<>
    {tab !== "schedule" && <>
      <div className="cc-form-section"><div><h2>Проект и бренд</h2><p>По этим названиям и доменам ищем упоминания в ответах ИИ.</p></div><div className="cc-fields"><div className="cc-two"><label>Название проекта<input required maxLength={120} value={project.name} onChange={e=>change({...project,name:e.target.value})}/></label><label>Бренд<input required maxLength={120} value={project.brand_name} onChange={e=>change({...project,brand_name:e.target.value})}/></label></div><label>Другие написания бренда<textarea rows={3} value={project.config.brand_aliases.join("\n")} onChange={e=>change({...project,config:{...project.config,brand_aliases:e.target.value.split("\n")}})}/></label><label>Домены бренда<textarea rows={2} placeholder="example.ru" value={project.config.brand_domains.join("\n")} onChange={e=>change({...project,config:{...project.config,brand_domains:e.target.value.split("\n")}})}/></label>{clarificationEnabled && <label>Уточнения по бренду<textarea rows={4} maxLength={2000} placeholder="Например: Reflo — наш товар; Refprom — другой бренд, его не считать." value={project.config.brand_clarification || ""} onChange={e=>change({...project,config:{...project.config,brand_clarification:e.target.value}})}/><small>Сохраните, чтобы применять уточнение к будущим сканам. Это бесплатно и не меняет старые результаты.</small></label>}</div></div>
      <div className="cc-form-section"><div><h2>Выполнение проверок</h2><p>Все пять ИИ-систем проверяются на сервере. Ответы сохраняются в вашем аккаунте.</p></div><div className="cc-fields"><fieldset><legend>ИИ-системы</legend><div className="cc-checkboxes">{SCAN_SERVICES.map(s=><label className="cc-check" key={s.id}><input type="checkbox" checked={project.config.services.includes(s.id)} onChange={e=>change({...project,config:{...project.config,services:e.target.checked?[...project.config.services,s.id]:project.config.services.filter(id=>id!==s.id)}})}/><ServiceMark id={s.id}/>{s.label}</label>)}</div></fieldset>{!project.config.services.length && <p className="cc-hint" role="status">Выберите минимум один ИИ-сервис, чтобы запускать проверки и расписание.</p>}<label>Регион Яндекса<input value={project.config.region_code} onChange={e=>change({...project,config:{...project.config,region_code:e.target.value}})}/><small>213 — Москва. Для Google другой регион требует отдельной настройки на сервере. ChatGPT, Perplexity и Gemini собираются с географией США.</small></label></div></div>
      </>}
      {(tab === "schedule" || projectId === "new") && <div className="cc-form-section"><div><h2><CalendarClock size={21}/>Расписание</h2><p>Выберите дни месяца и точное время. Изменения применяются после сохранения.</p></div><div className="cc-fields"><label className="cc-check"><input type="checkbox" checked={project.schedule.enabled} onChange={e=>change({...project,schedule:{...project.schedule,enabled:e.target.checked,device_id:project.schedule.device_id}})}/>Проверять по расписанию</label><div className="cc-two"><label>Время запуска<input type="time" value={project.schedule.time} onChange={e=>change({...project,schedule:{...project.schedule,time:e.target.value}})}/></label><label>Часовой пояс<input list="timezones" value={project.schedule.timezone} onChange={e=>change({...project,schedule:{...project.schedule,timezone:e.target.value}})}/><datalist id="timezones">{["Europe/Moscow","Europe/Kaliningrad","Europe/Samara","Asia/Yekaterinburg","Asia/Novosibirsk","Asia/Vladivostok","UTC"].map(z=><option key={z} value={z}/>)}</datalist></label></div><ScheduleDays days={project.schedule.month_days} lastDay={!!project.schedule.last_day} change={(month_days,last_day)=>change({...project,schedule:{...project.schedule,month_days,last_day}})}/><p className="cc-hint">Флажок означает последний календарный день месяца. {!project.config.services.length ? "Сначала выберите ИИ-сервис." : "Проверка начнётся на сервере в выбранное время."}</p></div></div>}
    </>}
    </fieldset>
    <div className="cc-savebar"><span role="status">{message || (dirty?"Есть несохранённые изменения":"Все изменения сохранены")}</span><button className="cc-button primary" disabled={busy||(!dirty&&projectId!=="new")||!project.name.trim()||!project.brand_name.trim()||!project.config.services.length||(project.schedule.enabled && !project.schedule.month_days.length && !project.schedule.last_day)} onClick={save}><Settings2 size={16}/>{busy?"Сохраняем…":"Сохранить"}</button></div>
    {clarificationEnabled && project.role === "owner" && tab === "settings" && projectId !== "new" && <section className="cc-form-section"><div><h2 ref={recomputeHeading} tabIndex={-1}>Пересчитать старые ответы</h2><p>Действует только на сохранённые ответы этого проекта. Новые запросы к поисковым системам не отправляются.</p></div><div className="cc-fields"><div><p className="cc-hint">Выберите даты пересчёта</p><ReportCalendar from={fromDate} to={toDate} available={availableDates} selection={dateSelection} context="recompute" disabled={busy||dirty} change={changeDates}/><p className="cc-hint">{selectionLabel(recomputeSelection(fromDate,toDate,availableDates,dateSelection))}</p></div><p className="cc-hint">{admin ? "Для вашего аккаунта пересчёт бесплатный." : "Стоимость — 0,80 ₽ за каждый подходящий сохранённый ответ."} Меняются только ответы за выбранные даты. Перед запуском покажем верхнюю границу списания. Если уйти со страницы, обработка остановится после текущего ответа; её можно продолжить без повторной оплаты уже готовых ответов.</p><span className="cc-quote-anchor"><button ref={recomputeButton} className="cc-button" aria-haspopup="dialog" aria-expanded={!!recomputeQuote} disabled={busy||dirty||!fromDate||!project.config.brand_clarification?.trim()} onClick={quoteRecompute}>Рассчитать стоимость пересчёта</button>{recomputeQuote && <QuotePopover quote={recomputeQuote} item="ответов" note={`Даты: ${selectionLabel(recomputeQuote)}. Без достаточных данных: ${recomputeQuote.skipped} — бесплатно. Новые проверки ИИ-сервисов не запускаются.`} action="Пересчитать" above trigger={recomputeButton} afterConfirm={recomputeHeading} onCancel={dismissRecomputeQuote} onConfirm={() => { const pending = recomputeQuote; setRecomputeQuote(null); void recompute(pending) }}/>}</span>{dirty && <p className="cc-hint">Сначала сохраните уточнение.</p>}{recomputeMessage && <p role="status">{recomputeMessage}</p>}</div></section>}
    {tab === "settings" && project.role === "owner" && projectId !== "new" && <section className="cc-form-section">
      <div><h2>Удаление проекта</h2><p>Проект исчезнет из списка, а проверки по расписанию прекратятся.</p></div>
      <div className="cc-fields"><button className="btn danger large" disabled={busy} aria-haspopup="dialog" onClick={() => { setDeleteError(""); deleteDialog.current?.showModal() }}><Trash2 size={16} aria-hidden="true"/>Удалить проект</button></div>
      <dialog ref={deleteDialog} aria-labelledby="delete-project-title" aria-describedby="delete-project-description" onCancel={event => { if (busyRef.current) event.preventDefault() }}>
        <div className="dialog-head"><h2 id="delete-project-title">Удалить проект?</h2></div>
        <div className="dialog-body"><p id="delete-project-description">Отчёты проекта «{project.name}» станут недоступны владельцу и участникам. Восстановление через кабинет недоступно.{dirty && " Несохранённые изменения будут потеряны."}</p>
          {deleteError && <p className="cab-payment-error" role="alert">{deleteError}</p>}
        </div>
        <div className="dialog-footer">
          <button className="btn" autoFocus disabled={busy} onClick={() => deleteDialog.current?.close()}>Отмена</button>
          <button className="btn danger" disabled={busy} onClick={() => void removeProject()}>{busy ? "Удаляем…" : "Удалить проект"}</button>
        </div>
      </dialog>
    </section>}
    </div>{tab !== "queries" && <aside className="side-note"><h3>{tab === "schedule" ? "Регулярные проверки" : "Что учитывается"}</h3><p>{tab === "schedule" ? project.schedule.enabled ? `${project.schedule.time} · ${project.schedule.timezone}. Числа месяца: ${scheduleDaysLabel(project.schedule)}.` : "Расписание выключено" : "Название, варианты написания и домены помогают находить бренд в ответах ИИ."}</p><hr className="form-divider"/><p>{tab === "schedule" ? "Сбор запускается автоматически. Последний день месяца определяется по выбранному часовому поясу, включая февраль в високосный год." : "Настройки применяются к новым проверкам после сохранения. Готовые ответы и история сохраняются."}</p><p>Перед ручным запуском показываем максимальную стоимость. Списываем оплату только за готовые ответы.</p></aside>}
  </div>
}
