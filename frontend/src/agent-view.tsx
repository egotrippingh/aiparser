import { useEffect, useState, type FormEvent } from "react"
import { createRoot } from "react-dom/client"
import { ArrowUpRight, Check, CheckCircle2, LogIn, Monitor, Pause, Play } from "lucide-react"
import "./agent-view.css"
import { BrowserInstallProgress, type InstallProgress } from "./components/browser-install-progress"
import { sessionLabel, sessionReady, type ServiceSession } from "./lib/service-auth"

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
  const [pollError,setPollError]=useState("")
  const [busy,setBusy]=useState("")
  const [passwordForm,setPasswordForm]=useState(false)
  const [email,setEmail]=useState("")
  const [password,setPassword]=useState("")
  const refresh=()=>api<State>("/api/desktop/state").then(next=>{setState(next);setPollError("")})
  useEffect(()=>{refresh().catch(e=>setPollError(e.message));const timer=setInterval(()=>refresh().catch(e=>setPollError(e.message)),state?.browser.installing?1000:4000);return()=>clearInterval(timer)},[state?.browser.installing])
  async function act(path:string,body:unknown={},method?:string){setBusy(path);setError("");try{await api(path,body,method);await refresh()}catch(e){setError(e instanceof Error?e.message:"Ошибка")}finally{setBusy("")}}
  async function signIn(event: FormEvent){
    event.preventDefault()
    const enteredPassword=password
    setPassword("")
    await act("/api/desktop/login/password",{email,password:enteredPassword})
  }
  const problem=error||state?.error||state?.sync_error
  return <main className="agent-window"><header><a href="#" onClick={e=>e.preventDefault()} className="agent-brand"><img src="/assets/brand/airvision-icon-graphite.png" alt="" width={36} height={36}/><strong>AIRate</strong></a><span>Агент</span></header>
    {pollError&&<p className="agent-error" role="alert">{pollError}</p>}
    {!state?<div className="agent-loading" role="status">Подключаемся…</div>:<>
      <section className="agent-identity"><div className={`agent-status-icon ${state.connected?"connected":""}`}><Monitor size={28}/></div><h1>{state.connected?state.name:"Подключите компьютер"}</h1><p>{state.connected?state.user?.email:"Войдите в аккаунт, чтобы подключить этот компьютер. Проекты и отчёты будут доступны на сайте."}</p></section>
      {!state.connected?<section className="agent-login">
        {state.has_token?<><p role="status">Проверяем подключение к аккаунту…</p><button className="agent-login-alternative" disabled={!!busy} onClick={()=>act("/api/account/logout")}>Войти в другой аккаунт</button></>:<>
          {state.login_pending?<div className="agent-login-pending"><p role="status">Завершите вход в открывшемся браузере. Компьютер подключится автоматически.</p><button className="agent-login-alternative" disabled={!!busy} onClick={()=>act("/api/desktop/login/cancel")}>Отменить вход</button></div>:<>
            <button className="agent-primary" disabled={!!busy||!state.configured} onClick={()=>act("/api/desktop/login",{provider:"yandex"})}><span className="agent-yandex-mark" aria-hidden="true">Я</span>Войти через Яндекс</button>
            <button className="agent-login-browser" disabled={!!busy||!state.configured} onClick={()=>act("/api/desktop/login",{provider:"browser"})}><LogIn size={18}/>Войти через браузер</button>
            <button className="agent-login-alternative" aria-expanded={passwordForm} disabled={!!busy} onClick={()=>setPasswordForm(!passwordForm)}>{passwordForm?"Скрыть форму":"Войти по email и паролю"}</button>
            {passwordForm&&<form className="agent-password-form" onSubmit={signIn}>
              <label>Email<input type="email" autoComplete="username" required maxLength={190} value={email} onChange={e=>setEmail(e.target.value)}/></label>
              <label>Пароль<input type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={e=>setPassword(e.target.value)}/></label>
              <button className="agent-primary" disabled={!!busy||!state.configured} type="submit">{busy==="/api/desktop/login/password"?"Подключаем…":"Войти и подключить компьютер"}</button>
            </form>}
          </>}
          {!state.configured&&<p>В этой сборке не указан адрес сайта. Скачайте агент из кабинета.</p>}
          <small>После входа этот компьютер привяжется к аккаунту. Подключите нужные ИИ-сервисы ниже. Код не нужен.</small>
        </>}
      </section>:<>
        <section className="agent-state"><div><span className={`agent-dot ${state.paused?"paused":""}`}/><strong>{state.paused?"Агент на паузе":state.scan?"Проверка выполняется":"Готов к заданиям сайта"}</strong></div><p>{state.scan?`${state.job?.project_name||"Проект"} · ${state.scan.done} / ${state.scan.total} проверок`:state.paused?"Новые задания будут ждать в очереди.":"Можно закрыть окно. Агент продолжит работать в трее."}</p>{state.scan&&<progress value={state.scan.done} max={state.scan.total||1} aria-label="Прогресс проверки"/>}</section>
        <div className="agent-balance"><span>Баланс аккаунта</span><div><b>{state.user?.is_admin?"Безлимит":state.wallet?new Intl.NumberFormat("ru-RU",{style:"currency",currency:"RUB"}).format(state.wallet.available_kopeks/100):"Обновляется…"}</b><button disabled={!!busy} onClick={()=>act("/api/desktop/cabinet",{destination:"topup"})}>Пополнить</button></div></div>
        <button className="agent-primary" onClick={()=>act("/api/desktop/cabinet")} disabled={!!busy}>Открыть кабинет<ArrowUpRight size={18}/></button>
        <div className="agent-actions"><button onClick={()=>act("/api/desktop/pause",{paused:!state.paused})} disabled={!!busy}>{state.paused?<Play size={16}/>:<Pause size={16}/>} {state.paused?"Продолжить":"Приостановить проверки на этом ПК"}</button><button onClick={()=>act("/api/desktop/hide")} disabled={!!busy}>Свернуть в трей</button></div>
      </>}
      <section className="agent-settings">
        <h2>Подключения и автозапуск</h2>
        <label><input type="checkbox" disabled={!state.autostart.available||!!busy} checked={state.autostart.enabled} onChange={e=>act("/api/agent/autostart",{enabled:e.target.checked},"PUT")}/>Запускать вместе с Windows</label>
        {state.browser.install_progress&&<BrowserInstallProgress progress={state.browser.install_progress}/>}
        {!state.browser.installed||state.browser.installing?<div><p>Для проверок нужен браузер агента.</p><button onClick={()=>act("/api/browser/install")} disabled={state.browser.installing||!!busy}>{state.browser.installing?"Устанавливается…":state.browser.install_error?"Повторить установку":"Установить браузер"}</button>{state.browser.install_error&&<p role="alert">{state.browser.install_error}</p>}</div>:<>
          <h2>Сессии ИИ-сервисов</h2><p>Войдите в нужные сервисы на этом компьютере. После входа закройте окно браузера.</p>
          {Object.entries(services).map(([id,name])=>{const s=state.browser.services[id];const starting=busy===`/api/browser/services/${id}/login`||s?.login_state==="starting";const ready=!starting&&sessionReady(s);return <div className="agent-service" key={id}><div><b>{name}</b><small role="status">{starting?"Открываем браузер…":sessionLabel(s)}</small>{s?.login_error&&<p className="agent-error" role="alert">{s.login_error}</p>}</div><button className={`agent-service-login${ready?" is-ready":""}`} aria-label={ready?`${name}: сессия сохранена. Открыть вход заново`:`Открыть вход: ${name}`} title={ready?"Сессия сохранена. Нажмите, чтобы войти заново":undefined} disabled={!!state.scan||!!busy||s?.login_open} onClick={()=>act(`/api/browser/services/${id}/login`)}><span aria-hidden={ready}>{starting?"Открываем…":s?.login_open?"Окно открыто":s?.login_state==="error"?"Повторить":"Войти"}</span>{ready&&<Check className="agent-service-check" size={18} aria-hidden="true"/>}</button></div>})}
          <p>Сохранённая сессия проверяется сервисом при следующем скане. Если окно не видно, проверьте панель задач Windows.</p>
          {state.scan&&<p>Чтобы войти заново, сначала остановите проверку на сайте.</p>}
        </>}
        {state.has_token&&<button className="agent-signout" disabled={!!state.scan||!!busy} onClick={()=>act("/api/account/logout")}>Отключить аккаунт</button>}
      </section>
      {problem&&<p className="agent-error" role="alert">{problem}</p>}
      <footer><CheckCircle2 size={13}/>{state.last_sync?`Последняя связь: ${new Date(state.last_sync).toLocaleTimeString("ru-RU")}`:"Ожидаем подключение"}</footer>
    </>}
  </main>
}
createRoot(document.getElementById("root")!).render(<Agent/> )
