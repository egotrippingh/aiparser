import { useEffect, useState } from "react"
import { createRoot } from "react-dom/client"
import { ArrowUpRight, CheckCircle2, LogIn, Monitor, Pause, Play, Settings2 } from "lucide-react"
import "./agent-view.css"
import { BrowserInstallProgress, type InstallProgress } from "./components/browser-install-progress"
import { sessionLabel, type ServiceSession } from "./lib/service-auth"

type State = { configured: boolean; connected: boolean; has_token: boolean; name: string; error: string; sync_error?: string;
  login_pending: boolean; paused: boolean; last_sync: string | null; user?: {email:string;is_admin?:boolean};
  wallet?: {available_kopeks:number}; autostart: {available:boolean;enabled:boolean};
  scan: {done:number;total:number}|null; job?: {project_name:string}|null;
  browser: {installed:boolean;installing:boolean;install_error:string|null;install_progress?:InstallProgress|null;services:Record<string,ServiceSession>} }
const services: Record<string,string> = {google_aio:"Google AI Overview",chatgpt:"ChatGPT",perplexity:"Perplexity",alice:"Алиса AI"}
async function api<T>(path:string,body?:unknown,method?:string):Promise<T>{
  const r=await fetch(path,{method:method||(body===undefined?"GET":"POST"),headers:body===undefined?{}:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)})
  const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==="string"?data.detail:"Не удалось выполнить действие");return data
}
function Agent(){
  const [state,setState]=useState<State|null>(null)
  const [error,setError]=useState("")
  const [busy,setBusy]=useState("")
  const [settings,setSettings]=useState(false)
  const refresh=()=>api<State>("/api/desktop/state").then(setState)
  useEffect(()=>{refresh().catch(e=>setError(e.message));const timer=setInterval(()=>refresh().catch(e=>setError(e.message)),state?.browser.installing?1000:4000);return()=>clearInterval(timer)},[state?.browser.installing])
  async function act(path:string,body:unknown={},method?:string){setBusy(path);setError("");try{await api(path,body,method);await refresh()}catch(e){setError(e instanceof Error?e.message:"Ошибка")}finally{setBusy("")}}
  const problem=error||state?.error||state?.sync_error
  return <main className="agent-window"><header><a href="#" onClick={e=>e.preventDefault()} className="agent-brand"><span aria-hidden="true">a</span>AI Mentions</a><span>Агент</span></header>
    {!state?<div className="agent-loading" role="status">Подключаемся…</div>:<>
      <section className="agent-identity"><div className={`agent-status-icon ${state.connected?"connected":""}`}><Monitor size={28}/></div><h1>{state.connected?state.name:"Подключите компьютер"}</h1><p>{state.connected?state.user?.email:"Войдите через сайт. Проекты, запросы и отчёты будут доступны в личном кабинете."}</p></section>
      {!state.connected?<section className="agent-login"><button className="agent-primary" disabled={!!busy||state.login_pending||!state.configured} onClick={()=>act("/api/desktop/login")}><LogIn size={18}/>{state.login_pending?"Ожидаем подтверждение на сайте…":"Войти через браузер"}</button>{!state.configured&&<p>В этой сборке не указан адрес сайта. Скачайте агент из кабинета.</p>}<small>После входа агент свернётся в трей.</small></section>:<>
        <section className="agent-state"><div><span className={`agent-dot ${state.paused?"paused":""}`}/><strong>{state.paused?"Агент на паузе":state.scan?"Проверка выполняется":"Готов к заданиям сайта"}</strong></div><p>{state.scan?`${state.job?.project_name||"Проект"} · ${state.scan.done} / ${state.scan.total} проверок`:state.paused?"Новые задания будут ждать в очереди.":"Можно закрыть окно. Агент продолжит работать в трее."}</p>{state.scan&&<progress value={state.scan.done} max={state.scan.total||1} aria-label="Прогресс проверки"/>}</section>
        <div className="agent-balance"><span>Баланс аккаунта</span><b>{state.user?.is_admin?"Безлимит":state.wallet?new Intl.NumberFormat("ru-RU",{style:"currency",currency:"RUB"}).format(state.wallet.available_kopeks/100):"Обновляется…"}</b></div>
        <button className="agent-primary" onClick={()=>act("/api/desktop/cabinet")} disabled={!!busy}>Открыть кабинет<ArrowUpRight size={18}/></button>
        <div className="agent-actions"><button onClick={()=>act("/api/desktop/pause",{paused:!state.paused})} disabled={!!busy}>{state.paused?<Play size={16}/>:<Pause size={16}/>} {state.paused?"Продолжить":"Приостановить проверки на этом ПК"}</button><button onClick={()=>act("/api/desktop/hide")} disabled={!!busy}>Свернуть в трей</button></div>
      </>}
      <button className="agent-details-toggle" aria-expanded={settings} onClick={()=>setSettings(!settings)}><Settings2 size={16}/>Подключения и автозапуск<span>{settings?"−":"+"}</span></button>
      {settings&&<section className="agent-settings">
        <label><input type="checkbox" disabled={!state.autostart.available||!!busy} checked={state.autostart.enabled} onChange={e=>act("/api/agent/autostart",{enabled:e.target.checked},"PUT")}/>Запускать вместе с Windows</label>
        {state.browser.install_progress&&<BrowserInstallProgress progress={state.browser.install_progress}/>}
        {!state.browser.installed||state.browser.installing?<div><p>Для проверок нужен браузер агента.</p><button onClick={()=>act("/api/browser/install")} disabled={state.browser.installing||!!busy}>{state.browser.installing?"Устанавливается…":state.browser.install_error?"Повторить установку":"Установить браузер"}</button>{state.browser.install_error&&<p role="alert">{state.browser.install_error}</p>}</div>:<>
          <h2>Сессии ИИ-сервисов</h2><p>Войдите в нужные сервисы на этом компьютере. После входа закройте окно браузера.</p>
          {Object.entries(services).map(([id,name])=>{const s=state.browser.services[id];const starting=busy===`/api/browser/services/${id}/login`||s?.login_state==="starting";return <div className="agent-service" key={id}><div><b>{name}</b><small role="status">{starting?"Открываем браузер…":sessionLabel(s)}</small>{s?.login_error&&<p className="agent-error" role="alert">{s.login_error}</p>}</div><button aria-label={`Открыть вход: ${name}`} disabled={!!state.scan||!!busy||s?.login_open} onClick={()=>act(`/api/browser/services/${id}/login`)}>{starting?"Открываем…":s?.login_open?"Окно открыто":s?.login_state==="error"?"Повторить":"Войти"}</button></div>})}
          <p>Сохранённая сессия проверяется сервисом при следующем скане. Если окно не видно, проверьте панель задач Windows.</p>
          {state.scan&&<p>Чтобы войти заново, сначала остановите проверку на сайте.</p>}
        </>}
        {state.has_token&&<button className="agent-signout" disabled={!!state.scan||!!busy} onClick={()=>act("/api/account/logout")}>Отключить аккаунт</button>}
      </section>}
      {problem&&<p className="agent-error" role="alert">{problem}</p>}
      <footer><CheckCircle2 size={13}/>{state.last_sync?`Последняя связь: ${new Date(state.last_sync).toLocaleTimeString("ru-RU")}`:"Ожидаем подключение"}</footer>
    </>}
  </main>
}
createRoot(document.getElementById("root")!).render(<Agent/> )
