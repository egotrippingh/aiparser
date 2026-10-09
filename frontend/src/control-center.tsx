import { useCallback, useEffect, useRef, useState, type RefObject } from "react"
import { CalendarClock, ChevronRight, CircleHelp, Download, FolderOpen, Monitor, Server, Pause, Play, Plus, Search, Settings2, ShieldCheck, Square, X } from "lucide-react"
import { accountRequest as request } from "./account-api"
import { SCAN_SERVICES, MONTH_DAYS } from "./lib/scan-preferences"
import { ReportView } from "./report-view"
import { QueryLibrary } from "./query-library"
import "./workspace.css"
import { sessionLabel, type ServiceSession } from "./lib/service-auth"
import "./control-center.css"

type Query = { id: string; text: string; group_tag: string; active: boolean }
type Config = { brand_aliases: string[]; brand_domains: string[]; brand_clarification?: string; region_code: string; services: string[]; browser_mode: string; speed_profile: string; parallel: boolean }
type Schedule = { enabled: boolean; device_id: string | null; month_days: number[]; time: string; timezone: string }
type Project = { id: string; revision: number; name: string; brand_name: string; device_id: string | null; config: Config; schedule: Schedule; queries: Query[]; query_count: number; active_queries: number }
type Device = { device_id: string; name: string; online: boolean; revoked: boolean; last_seen_at: string; capabilities: { installed?: boolean; paused?: boolean; active_scan?: boolean; services?: Record<string, ServiceSession> } }
type Run = { id: string; project_id: string; project_name: string; device_id: string | null; device_name: string; phase?: string; state: string; desired_state: string; error: string | null; total: number; created_at: string; scheduled_for: string | null; progress: { done?: number; total?: number; services?: Record<string, {done:number; total:number; state?:string; error?:string}> } }
type Quote = { count: number; unit_kopeks: number; total_kopeks: number; available_kopeks: number; revision: number }
type RecomputeQuote = Quote & { result_ids: string[]; skipped: number }
type RecomputeResult = { charged_kopeks: number; status: "done" | "skipped" | "error"; message: string }
const money = (kopeks: number) => new Intl.NumberFormat("ru-RU", {style:"currency",currency:"RUB"}).format(kopeks / 100)
const uuid = () => crypto.randomUUID().replaceAll("-", "")
const names: Record<string, string> = { queued: "В очереди", waiting_device: "Ожидает компьютер", running: "Выполняется", paused: "На паузе", connection_lost: "Нет связи с компьютером", done: "Завершено", failed: "Нужно действие", cancelled: "Остановлено", missed: "Пропущено" }
const terminal = (r: Run) => ["done", "failed", "cancelled", "missed"].includes(r.state)
export const needsAgent = (services: string[]) => services.some(id => !["google_aio", "yandex_neuro"].includes(id))
const service = (id: string) => SCAN_SERVICES.find(s => s.id === id)?.label || id
const blank = (): Project => ({ id: "new", revision: 0, name: "", brand_name: "", device_id: null, queries: [], query_count: 0, active_queries: 0,
  config: { brand_aliases: [], brand_domains: [], brand_clarification: "", region_code: "213", services: ["google_aio"], browser_mode: "headless", speed_profile: "fast", parallel: true },
  schedule: { enabled: false, device_id: null, month_days: [1], time: "09:00", timezone: "Europe/Moscow" } })
const routeNow = () => location.hash.startsWith("#/") ? location.hash.slice(2) : "projects"
const HISTORY_POSITION = "aimt.hashPosition"
const historyPosition = () => {
  const value = history.state && typeof history.state === "object" ? history.state[HISTORY_POSITION] : undefined
  return typeof value === "number" ? value : null
}
const stampHistoryPosition = (position: number) => history.replaceState({ ...(history.state && typeof history.state === "object" ? history.state : {}), [HISTORY_POSITION]: position }, "", location.href)
export const historyRecovery = (previousHash: string, previousPosition: number, targetPosition: number | null, nextPosition: number) => targetPosition === null
  ? { hash: previousHash, position: nextPosition + 1 }
  : { delta: previousPosition - targetPosition }

function ComputerSelect({ label, value, devices, change, required = false }: { label: string; value: string | null; devices: Device[]; change: (id: string | null) => void; required?: boolean }) {
  return <label>{label}<select required={required} value={value || ""} onChange={e => change(e.target.value || null)}><option value="">Выберите компьютер</option>{devices.map(d => <option key={d.device_id} value={d.device_id} disabled={d.revoked}>{d.name} · {d.revoked ? "отключён" : d.online ? "на связи" : "не в сети"}</option>)}</select></label>
}

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
  return <div ref={dialog} className={`cc-quote-popover${above ? " above" : ""}`} role="dialog" aria-modal="false" aria-label={`Подтверждение: ${action}`}><p>К списанию: до <b>{money(quote.total_kopeks)}</b></p><small>{quote.count} {item} × {money(quote.unit_kopeks)} · доступно {money(quote.available_kopeks)}</small><p className="cc-quote-note">{note}</p><div><button className="cc-quote-cancel" onClick={onCancel}>Отменить</button><button className="cc-button primary" onClick={() => { confirmed.current = true; onConfirm(); requestAnimationFrame(() => afterConfirm?.current?.focus()) }}>{action}</button></div></div>
}

export function ControlCenter({ token, downloadUrl, brandClarificationsEnabled, onDirtyChange }: { token: string; downloadUrl: string | null; brandClarificationsEnabled: boolean; onDirtyChange: (dirty: boolean) => void }) {
  const [route, setRoute] = useState(routeNow)
  const editorDirty = useRef(false), editorProject = useRef(""), previousHash = useRef(location.hash), previousPosition = useRef(0), restoringHistory = useRef(false)
  const [projects, setProjects] = useState<Project[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState("")
  const [filter, setFilter] = useState("")
  const [rename, setRename] = useState<{id:string;name:string}|null>(null)
  const [confirm, setConfirm] = useState("")
  const [connectId, setConnectId] = useState(() => sessionStorage.getItem("aimt.connect") || "")
  const [connectName, setConnectName] = useState("")
  const [connected, setConnected] = useState(false)
  const [scanQuote, setScanQuote] = useState<{projectId:string; quote:Quote}|null>(null)
  const scanButton = useRef<HTMLButtonElement>(null)
  const scanQuoteRequest = useRef(0)
  const scanSubmitting = useRef(false)
  const projectHeading = useRef<HTMLHeadingElement>(null)
  const dismissScanQuote = useCallback(() => { scanQuoteRequest.current++; setScanQuote(null) }, [])
  const refresh = useCallback(async () => {
    const [p, d, r] = await Promise.all([request<Project[]>("/control/projects", token), request<Device[]>("/control/devices", token), request<Run[]>("/control/runs", token)])
    setProjects(p); setDevices(d); setRuns(r); setLoading(false)
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
      const staysInEditor = [`#/project/${editorProject.current}/queries`, `#/project/${editorProject.current}/settings`].includes(next)
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
  useEffect(() => {
    if (connectId) request<{name:string}>(`/control/connect/${connectId}`, token).then(r => setConnectName(r.name)).catch(e => setError(e.message))
  }, [connectId, token])
  async function action(key: string, callback: () => Promise<unknown>) {
    setBusy(key); setError("")
    try { await callback(); await refresh() } catch (e) { setError(e instanceof Error ? e.message : "Не удалось выполнить действие") }
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
    await request(`/control/projects/${projectId}/runs`, token, {request_id:uuid(), revision:quote.revision})
  }
  async function approve() {
    await request(`/control/connect/${connectId}/approve`, token, {})
    sessionStorage.removeItem("aimt.connect"); setConnectId(""); setConnected(true)
    const url = new URL(location.href); url.searchParams.delete("connect"); history.replaceState(null, "", url)
  }
  const [area, projectId, projectTab] = route.split("/")
  const selected = projects.find(p => p.id === projectId)
  const activeRuns = runs.filter(r => !terminal(r))
  const shownRuns = area === "project" ? runs.filter(r => r.project_id === projectId) : runs
  function runRows(items: Run[]) {
    return <div className="cc-run-list">{items.map(r => <article className="cc-run" key={r.id}><div><strong>{r.project_name}</strong><small>{r.phase === "cloud" ? <Server size={13}/> : <Monitor size={13} />}{r.phase === "cloud" ? "Сервер" : r.device_name} · {r.scheduled_for ? "По расписанию" : "Ручной запуск"}</small>
      <span className={`cc-status ${r.state === "failed" || r.state === "connection_lost" ? "warn" : r.state === "done" ? "good" : ""}`}>{r.desired_state === "cancelled" && !terminal(r) ? "Останавливается" : r.desired_state === "paused" ? "На паузе" : names[r.state] || r.state}</span></div>
      <div className="cc-run-progress"><span>{r.progress.done || 0} / {r.total} проверок</span><progress max={r.total || 1} value={r.progress.done || 0} aria-label={`Прогресс ${r.project_name}`} />
        {r.error && <p className="cc-error-text">{r.error}</p>}
        {r.progress.services && <small>{Object.entries(r.progress.services).map(([id, s]) => `${service(id)} ${s.done}/${s.total}${s.state === "failed" ? ": ошибка" : ""}`).join(" · ")}</small>}
        {r.progress.services && Object.entries(r.progress.services).filter(([, s])=>s.error).map(([id,s])=><p className="cc-error-text" key={id}>{service(id)}: {s.error}</p>)}
        <small>Счётчик включает попытки с ошибками. Причины — в отчёте по запросу. Обычные ошибки не повторяются автоматически; новый запуск проекта проверяет все запросы заново.</small>
      </div><div className="cc-actions">{!terminal(r) && <><button className="cc-button" disabled={!!busy} onClick={() => action(r.id, () => request(`/control/runs/${r.id}/command`, token, { action: r.desired_state === "paused" ? "resume" : "pause" }))}>{r.desired_state === "paused" ? <Play size={15} /> : <Pause size={15} />}{r.desired_state === "paused" ? "Продолжить" : "Пауза"}</button><button className="cc-button" disabled={!!busy} onClick={() => action(r.id, () => request(`/control/runs/${r.id}/command`, token, {action:"stop"}))}><Square size={14} />Стоп</button></>}<a className="cc-button" href={`#/project/${r.project_id}/report`}>Отчёт</a></div></article>)}</div>
  }
  return <div className="cc-shell">
    <aside className="cc-sidebar"><span className="cc-eyebrow">Рабочее пространство</span><nav aria-label="Управление сервисом">
      <a href="#/projects" aria-current={area === "projects" || area === "project" ? "page" : undefined}><FolderOpen size={18} />Проекты<span>{projects.length}</span></a>
      <a href="#/runs" aria-current={area === "runs" ? "page" : undefined}><Play size={18} />Проверки{activeRuns.length > 0 && <span>{activeRuns.length}</span>}</a>
      <a href="#/devices" aria-current={area === "devices" ? "page" : undefined}><Monitor size={18} />Компьютеры<span>{devices.filter(d => d.online).length}</span></a></nav>
      <div className="cc-sidebar-foot"><span className="cc-dot" />{devices.filter(d => d.online).length} на связи{downloadUrl && <a href={downloadUrl}><Download size={15} />Скачать агент</a>}<p>Google и Яндекс — на сервере.<br />Другие системы — через агент.</p></div></aside>
    <div className="cc-content">
      {connectId && <section className="cc-connect"><ShieldCheck size={26} /><div><h2>Подключить {connectName || "компьютер"}?</h2><p>Он сможет выполнять назначенные ему проверки этого аккаунта. Доступ можно отозвать в разделе «Компьютеры».</p></div><button className="cc-button primary" disabled={!!busy || !connectName} onClick={() => action("connect", approve)}>Подключить</button></section>}
      {connected && <p className="cc-notice" role="status">Компьютер подключён. Агент готов к заданиям.</p>}
      {error && <div className="cc-alert" role="alert"><span>{error}</span><button aria-label="Закрыть сообщение" onClick={() => setError("")}><X size={18}/></button></div>}
      {area === "project" && projectId ? <>
        <a href="#/projects" className="cc-back">Все проекты</a>
        <div className="cc-heading"><div><span className="cc-eyebrow">Проект</span><h1 ref={projectHeading} tabIndex={-1}>{projectId === "new" ? "Новый проект" : selected?.name || "Проект"}</h1></div>
          {selected && <span className="cc-quote-anchor"><button ref={scanButton} className="cc-button primary" aria-haspopup="dialog" aria-expanded={scanQuote?.projectId === projectId} disabled={!!busy || (needsAgent(selected.config.services) && !selected.device_id) || !selected.active_queries || activeRuns.some(r => r.project_id === projectId)} onClick={() => action(projectId, () => quoteLaunch(projectId))}><Play size={16} />Запустить проверку</button>{scanQuote?.projectId === projectId && <QuotePopover quote={scanQuote.quote} item="проверок" note="Ошибки и пропуски могут уменьшить итоговую сумму." action="Запустить" trigger={scanButton} afterConfirm={projectHeading} onCancel={dismissScanQuote} onConfirm={() => { if (scanSubmitting.current) return; scanSubmitting.current = true; const pending = scanQuote; setScanQuote(null); void action(projectId, () => launch(projectId, pending.quote)).finally(() => { scanSubmitting.current = false }) }}/>}</span>}</div>
        {selected && <p className="cc-subline">{selected.active_queries} запросов · {selected.config.services.length} системы · {selected.active_queries * selected.config.services.length} проверок за запуск · {needsAgent(selected.config.services) ? devices.find(d => d.device_id === selected.device_id)?.name || "Компьютер не выбран" : "Сервер"}</p>}
        <nav className="cc-tabs" aria-label="Разделы проекта">{[ ["queries", "Промптовая база"], ["report", "Упоминаемость"], ["settings", "Настройки и расписание"] ].map(([tab, label]) => <a key={tab} aria-current={(projectTab || "report") === tab ? "page" : undefined} href={`#/project/${projectId}/${tab}`}>{label}</a>)}</nav>
        {projectId !== "new" && (projectTab || "report") === "report" ? <>{shownRuns.some(r => !terminal(r)) && runRows(shownRuns.filter(r => !terminal(r)))}<ReportView key={projectId} token={token} projectId={projectId}/></>
          : <ProjectEditor key={projectId} token={token} projectId={projectId} tab={projectId === "new" ? "settings" : projectTab || "settings"} devices={devices} brandClarificationsEnabled={brandClarificationsEnabled} saved={refresh} onDirtyChange={noteEditorDirty} />}
      </> : area === "devices" ? <>
        <div className="cc-heading"><div><span className="cc-eyebrow">Исполнители</span><h1>Компьютеры</h1><p>Назначайте проекты и расписания конкретному агенту.</p></div>{downloadUrl && <a className="cc-button primary" href={downloadUrl}><Download size={16} />Скачать агент</a>}</div>
        {!devices.length && <div className="cc-empty"><Monitor size={34}/><h2>Подключите первый компьютер</h2><p>Скачайте агент, запустите его и нажмите «Войти через браузер». Подтвердите подключение на сайте.</p></div>}
        <div className="cc-device-list">{devices.map(d => <article className="cc-device" key={d.device_id}><div className="cc-device-main"><Monitor size={22}/><div>{rename?.id === d.device_id ? <form onSubmit={e => {e.preventDefault(); action(d.device_id, async () => {await request(`/control/devices/${d.device_id}`, token, {device_id:d.device_id,name:rename.name}, "PATCH");setRename(null)})}}><label className="sr-only" htmlFor="rename-device">Имя компьютера</label><input id="rename-device" required maxLength={100} value={rename.name} onChange={e => setRename({...rename,name:e.target.value})}/><button className="cc-button" disabled={!!busy}>Сохранить</button><button type="button" className="cc-button" onClick={() => setRename(null)}>Отмена</button></form> : <h2>{d.name}</h2>}
          <p className={`cc-status ${d.online ? "good" : ""}`}>{d.revoked ? "Доступ отозван" : d.capabilities.paused ? "Приём заданий приостановлен" : d.online ? "На связи" : "Не в сети"}</p><small>Последняя связь: {new Date(d.last_seen_at).toLocaleString("ru-RU")}</small></div>
          {!d.revoked && <div className="cc-actions"><button className="cc-button" onClick={() => setRename({id:d.device_id,name:d.name})}>Переименовать</button>{confirm === d.device_id ? <><button className="cc-button danger" disabled={!!busy} onClick={() => action(d.device_id, () => request(`/control/devices/${d.device_id}`, token, undefined, "DELETE"))}>Да, отозвать доступ</button><button className="cc-button" onClick={() => setConfirm("")}>Отмена</button></> : <button className="cc-button" onClick={() => setConfirm(d.device_id)}>Отключить</button>}</div>}</div>
          {!d.revoked && <div className="cc-device-details"><span>Проекты: {projects.filter(p => p.device_id === d.device_id || p.schedule.device_id === d.device_id).map(p => p.name).join(", ") || "пока не назначены"}</span>
            <span>{d.capabilities.installed === false ? "Откройте агент и установите браузер" : "Сессии браузерных сервисов и доступ XMLRiver настроены на этом компьютере"}</span>
            <div className="cc-session-list">{Object.entries(d.capabilities.services || {}).map(([id,s]) => <span key={id}>{service(id)}<b>{sessionLabel(s)}</b></span>)}</div></div>}</article>)}</div>
      </> : area === "runs" ? <><div className="cc-heading"><div><span className="cc-eyebrow">Очередь аккаунта</span><h1>Проверки</h1><p>Ручные запуски и расписания со всех компьютеров.</p></div><span className="cc-status">В работе и очереди: {activeRuns.length}</span></div>{runs.length ? runRows(runs) : <div className="cc-empty"><CalendarClock size={34}/><h2>Очередь пока пуста</h2><p>Запустите проект или включите расписание в его настройках.</p><a className="cc-button" href="#/projects">К проектам</a></div>}</> : <>
        <div className="cc-heading"><div><span className="cc-eyebrow">Общая история аккаунта</span><h1>Проекты</h1><p>Запросы, расписания и отчёты, доступные с любого компьютера.</p></div><a className="cc-button primary" href="#/project/new/settings"><Plus size={17}/>Новый проект</a></div>
        <label className="cc-search"><Search size={17}/><span className="sr-only">Поиск проекта</span><input placeholder="Найти проект или бренд" value={filter} onChange={e => setFilter(e.target.value)}/></label>
        {loading ? <div className="cc-skeleton" aria-label="Загрузка проектов"/> : !projects.length ? <div className="cc-empty"><FolderOpen size={34}/><h2>Начните с первого проекта</h2><p>Укажите бренд, добавьте запросы и выберите компьютер. Существующие проекты агента появятся после его обновления и подключения.</p><a className="cc-button primary" href="#/project/new/settings">Создать проект</a></div> : <div className="cc-project-list">{projects.filter(p => `${p.name} ${p.brand_name}`.toLowerCase().includes(filter.toLowerCase())).map(p => {
          const pc = devices.find(d => d.device_id === p.device_id); const run = activeRuns.find(r => r.project_id === p.id)
          return <a key={p.id} className="cc-project-row" href={`#/project/${p.id}/report`}><div className="cc-project-icon"><FolderOpen size={21}/></div><div><h2>{p.name}</h2><small>{p.brand_name} · {p.query_count} запросов</small></div><div className="cc-project-device"><span>{needsAgent(p.config.services)?<Monitor size={14}/>:<Server size={14}/>} {needsAgent(p.config.services) ? pc?.name || "Компьютер не выбран" : "Сервер"}</span><small>{run ? names[run.state] : !needsAgent(p.config.services) || pc?.online ? "Готов к проверкам" : "Ожидает компьютер"}</small></div><div className="cc-project-schedule"><span><CalendarClock size={14}/>{p.schedule.enabled ? `${p.schedule.time} · ${p.schedule.month_days.join(", ")}` : "По запросу"}</span><small>{p.schedule.enabled ? `${p.schedule.timezone} · ${needsAgent(p.config.services) ? devices.find(d => d.device_id === p.schedule.device_id)?.name || "ПК не выбран" : "Сервер"}` : "Расписание выключено"}</small></div><ChevronRight size={18}/></a>
        })}</div>}
        <p className="cc-footnote"><CircleHelp size={15}/>Компьютер выполняет проверку, а результаты остаются в аккаунте. Для расписания можно выбрать отдельного исполнителя.</p>
      </>}
    </div>
  </div>
}

function ProjectEditor({token,projectId,tab,devices,brandClarificationsEnabled,saved,onDirtyChange}:{token:string;projectId:string;tab:string;devices:Device[];brandClarificationsEnabled:boolean;saved:()=>Promise<void>;onDirtyChange:(dirty:boolean,projectId:string)=>void}) {
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
    const config={...project.config,speed_profile:"fast"}
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
    finally {busyRef.current=false;if(mounted.current)setBusy(false)}
  }
  if(!project)return error?<p className="cc-alert" role="alert">{error}</p>:<div className="cc-skeleton"/>
  return <div className="cc-editor">
    {error&&<p className="cc-alert" role="alert">{error}</p>}
    <fieldset disabled={busy}>
    {tab==="queries"?<QueryLibrary queries={project.queries} saving={busy} onChange={queries=>change({...project,queries})}/>:<>
      <div className="cc-form-section"><div><h2>Проект и бренд</h2><p>По этим названиям и доменам ищем упоминания в ответах ИИ.</p></div><div className="cc-fields"><div className="cc-two"><label>Название проекта<input required maxLength={120} value={project.name} onChange={e=>change({...project,name:e.target.value})}/></label><label>Бренд<input required maxLength={120} value={project.brand_name} onChange={e=>change({...project,brand_name:e.target.value})}/></label></div><label>Другие написания бренда<textarea rows={3} value={project.config.brand_aliases.join("\n")} onChange={e=>change({...project,config:{...project.config,brand_aliases:e.target.value.split("\n")}})}/></label><label>Домены бренда<textarea rows={2} placeholder="example.ru" value={project.config.brand_domains.join("\n")} onChange={e=>change({...project,config:{...project.config,brand_domains:e.target.value.split("\n")}})}/></label>{brandClarificationsEnabled && <label>Уточнения по бренду<textarea rows={4} maxLength={2000} placeholder="Например: Reflo — наш товар; Refprom — другой бренд, его не считать." value={project.config.brand_clarification || ""} onChange={e=>change({...project,config:{...project.config,brand_clarification:e.target.value}})}/><small>Сохраните, чтобы применять уточнение к будущим сканам. Это бесплатно и не меняет старые результаты.</small></label>}</div></div>
      <div className="cc-form-section"><div><h2>Выполнение проверок</h2><p>Google и Яндекс проверяются на сервере. Для остальных систем нужен подключённый компьютер.</p></div><div className="cc-fields">{needsAgent(project.config.services) && <ComputerSelect label="Компьютер для запуска" value={project.device_id} devices={devices} change={id=>change({...project,device_id:id})}/>}<fieldset><legend>ИИ-системы</legend><div className="cc-checkboxes">{SCAN_SERVICES.map(s=><label className="cc-check" key={s.id}><input type="checkbox" checked={project.config.services.includes(s.id)} onChange={e=>change({...project,config:{...project.config,services:e.target.checked?[...project.config.services,s.id]:project.config.services.filter(id=>id!==s.id)}})}/>{s.label}</label>)}</div></fieldset>{needsAgent(project.config.services) && <><label>Режим браузера<select value={project.config.browser_mode} onChange={e=>change({...project,config:{...project.config,browser_mode:e.target.value}})}><option value="headless">Без окон (headless)</option><option value="headful">С окнами (headful)</option></select></label><label className="cc-check"><input type="checkbox" checked={project.config.parallel} onChange={e=>change({...project,config:{...project.config,parallel:e.target.checked}})}/>Проверять системы параллельно</label></>}<label>Регион Яндекса<input value={project.config.region_code} onChange={e=>change({...project,config:{...project.config,region_code:e.target.value}})}/><small>213 — Москва. Для Google через XMLRiver другой регион требует отдельной настройки на сервере.</small></label></div></div>
      <div className="cc-form-section"><div><h2><CalendarClock size={21}/>Расписание</h2><p>Выберите дни месяца и точное время. Для Google и Яндекса компьютер не требуется.</p></div><div className="cc-fields"><label className="cc-check"><input type="checkbox" checked={project.schedule.enabled} onChange={e=>change({...project,schedule:{...project.schedule,enabled:e.target.checked,device_id:project.schedule.device_id||project.device_id}})}/>Проверять по расписанию</label>{needsAgent(project.config.services) && <ComputerSelect label="Компьютер для расписания" value={project.schedule.device_id} devices={devices} required={project.schedule.enabled} change={id=>change({...project,schedule:{...project.schedule,device_id:id}})}/>}<div className="cc-two"><label>Время запуска<input type="time" value={project.schedule.time} onChange={e=>change({...project,schedule:{...project.schedule,time:e.target.value}})}/></label><label>Часовой пояс<input list="timezones" value={project.schedule.timezone} onChange={e=>change({...project,schedule:{...project.schedule,timezone:e.target.value}})}/><datalist id="timezones">{["Europe/Moscow","Europe/Kaliningrad","Europe/Samara","Asia/Yekaterinburg","Asia/Novosibirsk","Asia/Vladivostok","UTC"].map(z=><option key={z} value={z}/>)}</datalist></label></div><fieldset><legend>Числа месяца</legend><div className="cc-days">{MONTH_DAYS.map(day=><button type="button" key={day} aria-pressed={project.schedule.month_days.includes(day)} onClick={()=>change({...project,schedule:{...project.schedule,month_days:project.schedule.month_days.includes(day)?project.schedule.month_days.filter(d=>d!==day):[...project.schedule.month_days,day].sort((a,b)=>a-b)}})}>{day}</button>)}</div></fieldset><p className="cc-hint">Если выбранного числа нет в месяце, запуск пропускается. {needsAgent(project.config.services) ? "Агентская часть ожидает компьютер до 24 часов, затем запуск отмечается как пропущенный." : "Проверка начнётся на сервере в выбранное время."}</p></div></div>
    </>}
    </fieldset>
    <div className="cc-savebar"><span role="status">{message || (dirty?"Есть несохранённые изменения":"Все изменения сохранены")}</span><button className="cc-button primary" disabled={busy||(!dirty&&projectId!=="new")||!project.name.trim()||!project.brand_name.trim()||!project.config.services.length||!project.schedule.month_days.length||(project.schedule.enabled&&needsAgent(project.config.services)&&!project.schedule.device_id)} onClick={save}><Settings2 size={16}/>{busy?"Сохраняем…":"Сохранить"}</button></div>
    {brandClarificationsEnabled && tab === "settings" && projectId !== "new" && <section className="cc-form-section"><div><h2 ref={recomputeHeading} tabIndex={-1}>Пересчитать старые ответы</h2><p>Действует только на сохранённые ответы этого проекта. Новые запросы к поисковым системам не отправляются.</p></div><div className="cc-fields"><label>Начиная с даты включительно<input type="date" value={fromDate} onChange={e=>changeFromDate(e.target.value)}/></label><p className="cc-hint">Стоимость — 0,80 ₽ за каждый подходящий сохранённый ответ. Старые даты до выбранной не затрагиваются. Перед запуском покажем верхнюю границу списания. Если уйти со страницы, обработка остановится после текущего ответа; её можно продолжить без повторной оплаты уже готовых ответов.</p><span className="cc-quote-anchor"><button ref={recomputeButton} className="cc-button" aria-haspopup="dialog" aria-expanded={!!recomputeQuote} disabled={busy||dirty||!fromDate||!project.config.brand_clarification?.trim()} onClick={quoteRecompute}>Пересчитать ответы с этой даты</button>{recomputeQuote && <QuotePopover quote={recomputeQuote.quote} item="ответов" note={`Без достаточных данных: ${recomputeQuote.quote.skipped} — бесплатно. Новые проверки ИИ-сервисов не запускаются.`} action="Пересчитать" above trigger={recomputeButton} afterConfirm={recomputeHeading} onCancel={dismissRecomputeQuote} onConfirm={() => { const pending = recomputeQuote; setRecomputeQuote(null); void recompute(pending) }}/>}</span>{dirty && <p className="cc-hint">Сначала сохраните уточнение.</p>}{recomputeMessage && <p role="status">{recomputeMessage}</p>}</div></section>}
  </div>
}
