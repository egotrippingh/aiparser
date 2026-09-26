import { useCallback, useEffect, useState } from "react"
import { CalendarClock, ChevronRight, CircleHelp, Download, FolderOpen, Monitor, Pause, Play, Plus, Search, Settings2, ShieldCheck, Square, Upload, X } from "lucide-react"
import { accountRequest as request } from "./account-api"
import { SCAN_SERVICES, MONTH_DAYS } from "./lib/scan-preferences"
import { ReportView } from "./report-view"
import { parseQueryImport } from "./query-import"
import "./control-center.css"

type Query = { id: string; text: string; group_tag: string; active: boolean }
type Config = { brand_aliases: string[]; brand_domains: string[]; region_code: string; services: string[]; browser_mode: string; speed_profile: string; parallel: boolean }
type Schedule = { enabled: boolean; device_id: string | null; month_days: number[]; time: string; timezone: string }
type Project = { id: string; revision: number; name: string; brand_name: string; device_id: string | null; config: Config; schedule: Schedule; queries: Query[]; query_count: number; active_queries: number }
type Device = { device_id: string; name: string; online: boolean; revoked: boolean; last_seen_at: string; capabilities: { installed?: boolean; paused?: boolean; active_scan?: boolean; services?: Record<string, { cookie_state: string; last_scan_state: string | null }> } }
type Run = { id: string; project_id: string; project_name: string; device_id: string; device_name: string; state: string; desired_state: string; error: string | null; total: number; created_at: string; scheduled_for: string | null; progress: { done?: number; total?: number; services?: Record<string, {done:number; total:number; state?:string; error?:string}> } }
const uuid = () => crypto.randomUUID().replaceAll("-", "")
const names: Record<string, string> = { queued: "В очереди", waiting_device: "Ожидает компьютер", running: "Выполняется", paused: "На паузе", connection_lost: "Нет связи с компьютером", done: "Завершено", failed: "Нужно действие", cancelled: "Остановлено", missed: "Пропущено" }
const terminal = (r: Run) => ["done", "failed", "cancelled", "missed"].includes(r.state)
const service = (id: string) => SCAN_SERVICES.find(s => s.id === id)?.label || id
const blank = (): Project => ({ id: "new", revision: 0, name: "", brand_name: "", device_id: null, queries: [], query_count: 0, active_queries: 0,
  config: { brand_aliases: [], brand_domains: [], region_code: "213", services: ["google_aio"], browser_mode: "headless", speed_profile: "balanced", parallel: true },
  schedule: { enabled: false, device_id: null, month_days: [1], time: "09:00", timezone: "Europe/Moscow" } })
const routeNow = () => location.hash.startsWith("#/") ? location.hash.slice(2) : "projects"

function ComputerSelect({ label, value, devices, change, required = false }: { label: string; value: string | null; devices: Device[]; change: (id: string | null) => void; required?: boolean }) {
  return <label>{label}<select required={required} value={value || ""} onChange={e => change(e.target.value || null)}><option value="">Выберите компьютер</option>{devices.map(d => <option key={d.device_id} value={d.device_id} disabled={d.revoked}>{d.name} · {d.revoked ? "отключён" : d.online ? "на связи" : "не в сети"}</option>)}</select></label>
}

export function ControlCenter({ token, downloadUrl }: { token: string; downloadUrl: string | null }) {
  const [route, setRoute] = useState(routeNow)
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
  const refresh = useCallback(async () => {
    const [p, d, r] = await Promise.all([request<Project[]>("/control/projects", token), request<Device[]>("/control/devices", token), request<Run[]>("/control/runs", token)])
    setProjects(p); setDevices(d); setRuns(r); setLoading(false)
  }, [token])
  useEffect(() => {
    const change = () => setRoute(routeNow()); window.addEventListener("hashchange", change)
    return () => window.removeEventListener("hashchange", change)
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
    return <div className="cc-run-list">{items.map(r => <article className="cc-run" key={r.id}><div><strong>{r.project_name}</strong><small><Monitor size={13} />{r.device_name} · {r.scheduled_for ? "По расписанию" : "Ручной запуск"}</small>
      <span className={`cc-status ${r.state === "failed" || r.state === "connection_lost" ? "warn" : r.state === "done" ? "good" : ""}`}>{r.desired_state === "cancelled" && !terminal(r) ? "Останавливается" : r.desired_state === "paused" ? "На паузе" : names[r.state] || r.state}</span></div>
      <div className="cc-run-progress"><span>{r.progress.done || 0} / {r.total} проверок</span><progress max={r.total || 1} value={r.progress.done || 0} aria-label={`Прогресс ${r.project_name}`} />
        {r.error && <p className="cc-error-text">{r.error}</p>}
        {r.progress.services && <small>{Object.entries(r.progress.services).map(([id, s]) => `${service(id)} ${s.done}/${s.total}${s.state === "failed" ? ": ошибка" : ""}`).join(" · ")}</small>}
      </div><div className="cc-actions">{!terminal(r) && <><button className="cc-button" disabled={!!busy} onClick={() => action(r.id, () => request(`/control/runs/${r.id}/command`, token, { action: r.desired_state === "paused" ? "resume" : "pause" }))}>{r.desired_state === "paused" ? <Play size={15} /> : <Pause size={15} />}{r.desired_state === "paused" ? "Продолжить" : "Пауза"}</button><button className="cc-button" disabled={!!busy} onClick={() => action(r.id, () => request(`/control/runs/${r.id}/command`, token, {action:"stop"}))}><Square size={14} />Стоп</button></>}<a className="cc-button" href={`#/project/${r.project_id}/report`}>Отчёт</a></div></article>)}</div>
  }
  return <div className="cc-shell">
    <aside className="cc-sidebar"><span className="cc-eyebrow">Рабочее пространство</span><nav aria-label="Управление сервисом">
      <a href="#/projects" aria-current={area === "projects" || area === "project" ? "page" : undefined}><FolderOpen size={18} />Проекты<span>{projects.length}</span></a>
      <a href="#/runs" aria-current={area === "runs" ? "page" : undefined}><Play size={18} />Проверки{activeRuns.length > 0 && <span>{activeRuns.length}</span>}</a>
      <a href="#/devices" aria-current={area === "devices" ? "page" : undefined}><Monitor size={18} />Компьютеры<span>{devices.filter(d => d.online).length}</span></a></nav>
      <div className="cc-sidebar-foot"><span className="cc-dot" />{devices.filter(d => d.online).length} на связи{downloadUrl && <a href={downloadUrl}><Download size={15} />Скачать агент</a>}<p>Управляйте здесь.<br />Агент выполнит проверку.</p></div></aside>
    <div className="cc-content">
      {connectId && <section className="cc-connect"><ShieldCheck size={26} /><div><h2>Подключить {connectName || "компьютер"}?</h2><p>Он сможет выполнять назначенные ему проверки этого аккаунта. Доступ можно отозвать в разделе «Компьютеры».</p></div><button className="cc-button primary" disabled={!!busy || !connectName} onClick={() => action("connect", approve)}>Подключить</button></section>}
      {connected && <p className="cc-notice" role="status">Компьютер подключён. Агент свернётся в трей и будет ждать заданий.</p>}
      {error && <div className="cc-alert" role="alert"><span>{error}</span><button aria-label="Закрыть сообщение" onClick={() => setError("")}><X size={18}/></button></div>}
      {area === "project" && projectId ? <>
        <a href="#/projects" className="cc-back">Все проекты</a>
        <div className="cc-heading"><div><span className="cc-eyebrow">Проект</span><h1>{projectId === "new" ? "Новый проект" : selected?.name || "Проект"}</h1></div>
          {selected && <button className="cc-button primary" disabled={!!busy || !selected.device_id || !selected.active_queries || activeRuns.some(r => r.project_id === projectId)} onClick={() => action(projectId, () => request(`/control/projects/${projectId}/runs`, token, {request_id:uuid()}))}><Play size={16} />Запустить проверку</button>}</div>
        {selected && <p className="cc-subline">{selected.active_queries} запросов · {selected.config.services.length} системы · {selected.active_queries * selected.config.services.length} проверок за запуск · {devices.find(d => d.device_id === selected.device_id)?.name || "Компьютер не выбран"}</p>}
        <nav className="cc-tabs" aria-label="Разделы проекта">{[ ["report", "Отчёт"], ["queries", "Запросы"], ["settings", "Настройки и расписание"] ].map(([tab, label]) => <a key={tab} aria-current={(projectTab || "report") === tab ? "page" : undefined} href={`#/project/${projectId}/${tab}`}>{label}</a>)}</nav>
        {projectId !== "new" && (projectTab || "report") === "report" ? <>{shownRuns.some(r => !terminal(r)) && runRows(shownRuns.filter(r => !terminal(r)))}<ReportView token={token} projectId={projectId}/></>
          : <ProjectEditor key={projectId} token={token} projectId={projectId} tab={projectId === "new" ? "settings" : projectTab || "settings"} devices={devices} saved={refresh} />}
      </> : area === "devices" ? <>
        <div className="cc-heading"><div><span className="cc-eyebrow">Исполнители</span><h1>Компьютеры</h1><p>Назначайте проекты и расписания конкретному агенту.</p></div>{downloadUrl && <a className="cc-button primary" href={downloadUrl}><Download size={16} />Скачать агент</a>}</div>
        {!devices.length && <div className="cc-empty"><Monitor size={34}/><h2>Подключите первый компьютер</h2><p>Скачайте агент, запустите его и нажмите «Войти через браузер». Подтвердите подключение на сайте.</p></div>}
        <div className="cc-device-list">{devices.map(d => <article className="cc-device" key={d.device_id}><div className="cc-device-main"><Monitor size={22}/><div>{rename?.id === d.device_id ? <form onSubmit={e => {e.preventDefault(); action(d.device_id, async () => {await request(`/control/devices/${d.device_id}`, token, {device_id:d.device_id,name:rename.name}, "PATCH");setRename(null)})}}><label className="sr-only" htmlFor="rename-device">Имя компьютера</label><input id="rename-device" required maxLength={100} value={rename.name} onChange={e => setRename({...rename,name:e.target.value})}/><button className="cc-button" disabled={!!busy}>Сохранить</button><button type="button" className="cc-button" onClick={() => setRename(null)}>Отмена</button></form> : <h2>{d.name}</h2>}
          <p className={`cc-status ${d.online ? "good" : ""}`}>{d.revoked ? "Доступ отозван" : d.capabilities.paused ? "Приём заданий приостановлен" : d.online ? "На связи" : "Не в сети"}</p><small>Последняя связь: {new Date(d.last_seen_at).toLocaleString("ru-RU")}</small></div>
          {!d.revoked && <div className="cc-actions"><button className="cc-button" onClick={() => setRename({id:d.device_id,name:d.name})}>Переименовать</button>{confirm === d.device_id ? <><button className="cc-button danger" disabled={!!busy} onClick={() => action(d.device_id, () => request(`/control/devices/${d.device_id}`, token, undefined, "DELETE"))}>Да, отозвать доступ</button><button className="cc-button" onClick={() => setConfirm("")}>Отмена</button></> : <button className="cc-button" onClick={() => setConfirm(d.device_id)}>Отключить</button>}</div>}</div>
          {!d.revoked && <div className="cc-device-details"><span>Проекты: {projects.filter(p => p.device_id === d.device_id || p.schedule.device_id === d.device_id).map(p => p.name).join(", ") || "пока не назначены"}</span>
            <span>{d.capabilities.installed === false ? "Откройте агент и установите браузер" : "Вход в ИИ-сервисы выполняется на этом компьютере"}</span>
            <div className="cc-session-list">{Object.entries(d.capabilities.services || {}).filter(([id]) => id !== "yandex_neuro").map(([id,s]) => <span key={id}>{service(id)}<b>{s.last_scan_state === "auth_required" ? "Нужен вход" : s.last_scan_state === "ok" ? "Проверен" : s.cookie_state === "ok" || s.cookie_state === "present" ? "Сессия сохранена" : "Не проверен"}</b></span>)}</div></div>}</article>)}</div>
      </> : area === "runs" ? <><div className="cc-heading"><div><span className="cc-eyebrow">Очередь аккаунта</span><h1>Проверки</h1><p>Ручные запуски и расписания со всех компьютеров.</p></div><span className="cc-status">В работе и очереди: {activeRuns.length}</span></div>{runs.length ? runRows(runs) : <div className="cc-empty"><CalendarClock size={34}/><h2>Очередь пока пуста</h2><p>Запустите проект или включите расписание в его настройках.</p><a className="cc-button" href="#/projects">К проектам</a></div>}</> : <>
        <div className="cc-heading"><div><span className="cc-eyebrow">Общая история аккаунта</span><h1>Проекты</h1><p>Запросы, расписания и отчёты, доступные с любого компьютера.</p></div><a className="cc-button primary" href="#/project/new/settings"><Plus size={17}/>Новый проект</a></div>
        <label className="cc-search"><Search size={17}/><span className="sr-only">Поиск проекта</span><input placeholder="Найти проект или бренд" value={filter} onChange={e => setFilter(e.target.value)}/></label>
        {loading ? <div className="cc-skeleton" aria-label="Загрузка проектов"/> : !projects.length ? <div className="cc-empty"><FolderOpen size={34}/><h2>Начните с первого проекта</h2><p>Укажите бренд, добавьте запросы и выберите компьютер. Существующие проекты агента появятся после его обновления и подключения.</p><a className="cc-button primary" href="#/project/new/settings">Создать проект</a></div> : <div className="cc-project-list">{projects.filter(p => `${p.name} ${p.brand_name}`.toLowerCase().includes(filter.toLowerCase())).map(p => {
          const pc = devices.find(d => d.device_id === p.device_id); const run = activeRuns.find(r => r.project_id === p.id)
          return <a key={p.id} className="cc-project-row" href={`#/project/${p.id}/report`}><div className="cc-project-icon"><FolderOpen size={21}/></div><div><h2>{p.name}</h2><small>{p.brand_name} · {p.query_count} запросов</small></div><div className="cc-project-device"><span><Monitor size={14}/>{pc?.name || "Компьютер не выбран"}</span><small>{run ? names[run.state] : pc?.online ? "Готов к проверкам" : "Ожидает компьютер"}</small></div><div className="cc-project-schedule"><span><CalendarClock size={14}/>{p.schedule.enabled ? `${p.schedule.time} · ${p.schedule.month_days.join(", ")}` : "По запросу"}</span><small>{p.schedule.enabled ? `${p.schedule.timezone} · ${devices.find(d => d.device_id === p.schedule.device_id)?.name || "ПК не выбран"}` : "Расписание выключено"}</small></div><ChevronRight size={18}/></a>
        })}</div>}
        <p className="cc-footnote"><CircleHelp size={15}/>Компьютер выполняет проверку, а результаты остаются в аккаунте. Для расписания можно выбрать отдельного исполнителя.</p>
      </>}
    </div>
  </div>
}

function ProjectEditor({token,projectId,tab,devices,saved}:{token:string;projectId:string;tab:string;devices:Device[];saved:()=>Promise<void>}) {
  const [project,setProject] = useState<Project|null>(projectId === "new" ? blank() : null)
  const [dirty,setDirty] = useState(false)
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState("")
  const [error,setError] = useState("")
  const [text,setText] = useState("")
  const [group,setGroup] = useState("")
  const [queryFilter,setQueryFilter] = useState("")
  const [limit,setLimit] = useState(100)
  useEffect(() => {if(projectId !== "new") request<Project>(`/control/projects/${projectId}`,token).then(setProject).catch(e => setError(e.message))},[projectId,token])
  useEffect(() => {const prevent=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue=""}};window.addEventListener("beforeunload",prevent);return()=>window.removeEventListener("beforeunload",prevent)},[dirty])
  useEffect(() => {
    if (!dirty) return
    const guard = (event: MouseEvent) => {
      const link = (event.target as Element).closest<HTMLAnchorElement>("a[href]")
      if (!link || link.target === "_blank" || link.hasAttribute("download")) return
      const target = new URL(link.href, location.href)
      const staysInEditor = target.pathname === location.pathname &&
        [`#/project/${projectId}/queries`, `#/project/${projectId}/settings`].includes(target.hash)
      if (!staysInEditor && !window.confirm("Изменения не сохранены. Уйти со страницы?")) {
        event.preventDefault(); event.stopPropagation()
      }
    }
    document.addEventListener("click", guard, true)
    return () => document.removeEventListener("click", guard, true)
  }, [dirty, projectId])
  function change(next:Project){setProject(next);setDirty(true);setMessage("")}
  async function save(){if(!project)return;setBusy(true);setError("");try{
    const {revision,name,brand_name,device_id,config,schedule,queries}=project
    const next=await request<Project>(projectId==="new"?"/control/projects":`/control/projects/${projectId}`,token,{revision,name,brand_name,device_id,config,schedule,queries},projectId==="new"?"POST":"PUT")
    setProject(next);setDirty(false);setMessage("Сохранено. Текущая проверка использует настройки на момент запуска.");await saved()
    if(projectId==="new")location.hash=`/project/${next.id}/queries`
  }catch(e){setError(e instanceof Error?e.message:"Не удалось сохранить проект")}finally{setBusy(false)}}
  function addQueries(value=text){if(!project)return;try{
    const known=new Set(project.queries.map(q=>q.text));const added:Query[]=[]
    for(const q of parseQueryImport(value,group)){const clean=q.text.replace(/\s+/g," ").trim();if(clean&&!known.has(clean)){known.add(clean);added.push({id:uuid(),text:clean,group_tag:q.group_tag,active:true})}}
    if(project.queries.length+added.length>5000)throw new Error("В проекте можно сохранить до 5 000 запросов")
    change({...project,queries:[...project.queries,...added]});setText("");setMessage(`Добавлено: ${added.length}. Сохраните изменения.`)
  }catch(e){setError(e instanceof Error?e.message:"Не удалось прочитать запросы")}}
  if(!project)return error?<p className="cc-alert" role="alert">{error}</p>:<div className="cc-skeleton"/>
  const active=project.queries.filter(q=>q.active).length
  return <div className="cc-editor">
    {error&&<p className="cc-alert" role="alert">{error}</p>}
    {tab==="queries"?<>
      <div className="cc-form-section"><div><h2>Добавить запросы</h2><p>Вставьте по одному запросу в строке или загрузите TXT, CSV, TSV. Для таблицы используйте столбцы «Запрос» и «Группа».</p></div><div className="cc-fields"><label>Группа для новых запросов<input maxLength={120} placeholder="Например, выбор оборудования" value={group} onChange={e=>setGroup(e.target.value)}/></label><label>Запросы<textarea rows={5} value={text} onChange={e=>setText(e.target.value)} placeholder="Где купить оригинальное оборудование?"/></label><div className="cc-actions"><button className="cc-button" onClick={()=>addQueries()} disabled={!text.trim()}><Plus size={16}/>Добавить</button><label className="cc-button cc-upload"><Upload size={16}/>Загрузить файл<input type="file" accept=".txt,.csv,.tsv" onChange={async e=>{const file=e.target.files?.[0];if(file){if(file.size>4000000){setError("Файл больше 4 МБ");return}addQueries(await file.text());e.target.value=""}}}/></label></div></div></div>
      <div className="cc-toolbar"><h2>Запросы <small>{active} активных / {project.queries.length}</small></h2><label className="cc-search"><Search size={16}/><span className="sr-only">Поиск запроса</span><input placeholder="Запрос или группа" value={queryFilter} onChange={e=>{setQueryFilter(e.target.value);setLimit(100)}}/></label></div>
      <div className="cc-table-scroll"><table className="cc-table cc-query-table"><thead><tr><th>Активен</th><th>Запрос</th><th>Группа</th><th><span className="sr-only">Удаление</span></th></tr></thead><tbody>{project.queries.filter(q=>`${q.text} ${q.group_tag}`.toLowerCase().includes(queryFilter.toLowerCase())).slice(0,limit).map(q=><tr key={q.id}><td><input type="checkbox" aria-label={`Проверять: ${q.text}`} checked={q.active} onChange={e=>change({...project,queries:project.queries.map(item=>item.id===q.id?{...item,active:e.target.checked}:item)})}/></td><td><input aria-label="Текст запроса" maxLength={2000} value={q.text} onChange={e=>change({...project,queries:project.queries.map(item=>item.id===q.id?{...item,text:e.target.value}:item)})}/></td><td><input aria-label={`Группа запроса ${q.text}`} maxLength={120} value={q.group_tag} onChange={e=>change({...project,queries:project.queries.map(item=>item.id===q.id?{...item,group_tag:e.target.value}:item)})}/></td><td><button className="cc-button" aria-label={`Удалить запрос: ${q.text}`} onClick={()=>change({...project,queries:project.queries.filter(item=>item.id!==q.id)})}><X size={16}/></button></td></tr>)}</tbody></table></div>{project.queries.length>limit&&<button className="cc-button" onClick={()=>setLimit(n=>n+100)}>Показать ещё</button>}
      {!project.queries.length&&<p className="cc-footnote">Список пуст. Добавьте запросы выше.</p>}
    </>:<>
      <div className="cc-form-section"><div><h2>Проект и бренд</h2><p>По этим названиям и доменам ищем упоминания в ответах ИИ.</p></div><div className="cc-fields"><div className="cc-two"><label>Название проекта<input required maxLength={120} value={project.name} onChange={e=>change({...project,name:e.target.value})}/></label><label>Бренд<input required maxLength={120} value={project.brand_name} onChange={e=>change({...project,brand_name:e.target.value})}/></label></div><label>Другие написания бренда<textarea rows={3} value={project.config.brand_aliases.join("\n")} onChange={e=>change({...project,config:{...project.config,brand_aliases:e.target.value.split("\n")}})}/></label><label>Домены бренда<textarea rows={2} placeholder="example.ru" value={project.config.brand_domains.join("\n")} onChange={e=>change({...project,config:{...project.config,brand_domains:e.target.value.split("\n")}})}/></label></div></div>
      <div className="cc-form-section"><div><h2>Выполнение проверок</h2><p>Этот компьютер получает ручные запуски. Если он не в сети, проверка останется в очереди.</p></div><div className="cc-fields"><ComputerSelect label="Компьютер для запуска" value={project.device_id} devices={devices} change={id=>change({...project,device_id:id})}/><fieldset><legend>ИИ-системы</legend><div className="cc-checkboxes">{SCAN_SERVICES.filter(s=>s.id!=="yandex_neuro").map(s=><label className="cc-check" key={s.id}><input type="checkbox" checked={project.config.services.includes(s.id)} onChange={e=>change({...project,config:{...project.config,services:e.target.checked?[...project.config.services,s.id]:project.config.services.filter(id=>id!==s.id)}})}/>{s.label}</label>)}</div></fieldset><div className="cc-two"><label>Режим браузера<select value={project.config.browser_mode} onChange={e=>change({...project,config:{...project.config,browser_mode:e.target.value}})}><option value="headless">Без окон (headless)</option><option value="headful">С окнами (headful)</option></select></label><label>Скорость<select value={project.config.speed_profile} onChange={e=>change({...project,config:{...project.config,speed_profile:e.target.value}})}><option value="careful">Осторожная</option><option value="balanced">Сбалансированная</option><option value="fast">Быстрая</option></select></label></div><label className="cc-check"><input type="checkbox" checked={project.config.parallel} onChange={e=>change({...project,config:{...project.config,parallel:e.target.checked}})}/>Проверять системы параллельно</label><label>Регион Яндекса<input value={project.config.region_code} onChange={e=>change({...project,config:{...project.config,region_code:e.target.value}})}/><small>213 — Москва. Вход в ИИ-сервисы и капча выполняются на выбранном ПК.</small></label></div></div>
      <div className="cc-form-section"><div><h2><CalendarClock size={21}/>Расписание</h2><p>Выберите дни месяца, точное время и компьютер. Часовой пояс задаётся здесь и не зависит от настроек Windows.</p></div><div className="cc-fields"><label className="cc-check"><input type="checkbox" checked={project.schedule.enabled} onChange={e=>change({...project,schedule:{...project.schedule,enabled:e.target.checked,device_id:project.schedule.device_id||project.device_id}})}/>Проверять по расписанию</label><ComputerSelect label="Компьютер для расписания" value={project.schedule.device_id} devices={devices} required={project.schedule.enabled} change={id=>change({...project,schedule:{...project.schedule,device_id:id}})}/><div className="cc-two"><label>Время запуска<input type="time" value={project.schedule.time} onChange={e=>change({...project,schedule:{...project.schedule,time:e.target.value}})}/></label><label>Часовой пояс<input list="timezones" value={project.schedule.timezone} onChange={e=>change({...project,schedule:{...project.schedule,timezone:e.target.value}})}/><datalist id="timezones">{["Europe/Moscow","Europe/Kaliningrad","Europe/Samara","Asia/Yekaterinburg","Asia/Novosibirsk","Asia/Vladivostok","UTC"].map(z=><option key={z} value={z}/>)}</datalist></label></div><fieldset><legend>Числа месяца</legend><div className="cc-days">{MONTH_DAYS.map(day=><button type="button" key={day} aria-pressed={project.schedule.month_days.includes(day)} onClick={()=>change({...project,schedule:{...project.schedule,month_days:project.schedule.month_days.includes(day)?project.schedule.month_days.filter(d=>d!==day):[...project.schedule.month_days,day].sort((a,b)=>a-b)}})}>{day}</button>)}</div></fieldset><p className="cc-hint">Если выбранного числа нет в месяце, запуск пропускается. Выключенный ПК может забрать задание в течение 24 часов. Позже запуск отмечается как пропущенный.</p></div></div>
    </>}
    <div className="cc-savebar"><span role="status">{message || (dirty?"Есть несохранённые изменения":"Все изменения сохранены")}</span><button className="cc-button primary" disabled={busy||(!dirty&&projectId!=="new")||!project.name.trim()||!project.brand_name.trim()||!project.config.services.length||!project.schedule.month_days.length||(project.schedule.enabled&&!project.schedule.device_id)} onClick={save}><Settings2 size={16}/>{busy?"Сохраняем…":"Сохранить"}</button></div>
  </div>
}
