import { useEffect, useState, type FormEvent } from "react"
import { createRoot } from "react-dom/client"
import { ChartNoAxesCombined, ClipboardList, FileSearch, LogOut, Shield, Server, Ticket, Users } from "lucide-react"
import { AccountError, COOKIE_SESSION, accountRequest, onSessionExpired } from "./account-api"
import { AdminAccess } from "./admin-access"
import { AdminDashboard } from "./admin-dashboard"
import { AdminOverview } from "./admin-overview"
import { AdminPromos } from "./admin-promos"
import { AdminRuns } from "./admin-runs"
import { AdminScans } from "./admin-scans"
import { Brand } from "./brand"
import { CabinetSkeleton } from "./cabinet-loading"
import "./cabinet-theme.scss"
import "./cabinet.scss"
import "./control-center.scss"
import "./admin-console.scss"

const sections = {
  overview: { label: "Финансы", title: "Финансы и прогноз", lead: "Выручка, расходы API, прогноз и пополнения поставщиков.", icon: ChartNoAxesCombined },
  users: { label: "Пользователи", title: "Пользователи и балансы", lead: "Поиск аккаунтов и ручное пополнение кошелька.", icon: Users },
  runs: { label: "Запуски", title: "Запуски проверок", lead: "Журнал запусков по всем аккаунтам.", icon: ClipboardList },
  results: { label: "Результаты", title: "Результаты проверок", lead: "Ответы, статусы и скриншоты для разбора.", icon: FileSearch },
  providers: { label: "Провайдеры", title: "Провайдеры", lead: "Балансы и пауза приёма по ИИ-системам.", icon: Server },
  promos: { label: "Промокоды", title: "Промокоды", lead: "Создание и правка промокодов на бесплатные проверки.", icon: Ticket },
  access: { label: "Доступ", title: "Доступ по IP", lead: "Разрешённые адреса для открытия админки.", icon: Shield },
}

type Section = keyof typeof sections
type Identity = { id: string; email: string }

function readRoute() {
  const [path, search] = location.hash.slice(2).split("?")
  const section = (Object.hasOwn(sections, path) ? path : "overview") as Section
  const runId = new URLSearchParams(search).get("run_id") ?? ""
  return { section, runId: /^[a-f0-9]{32}$/.test(runId) ? runId : undefined }
}

function AdminConsole() {
  const [user, setUser] = useState<Identity | null>(null)
  const [loading, setLoading] = useState(true)
  const [signingIn, setSigningIn] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [login, setLogin] = useState("admin")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [{ section, runId }, setRoute] = useState(readRoute)

  useEffect(() => {
    let active = true
    accountRequest<Identity>("/admin/session", COOKIE_SESSION)
      .then(result => { if (active) setUser(result) })
      .catch(failure => {
        if (active && !(failure instanceof AccountError && failure.status === 401)) setError(failure.message)
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!user) return
    return onSessionExpired(COOKIE_SESSION, () => {
      setUser(null)
      setError("Сессия истекла. Войдите снова.")
    })
  }, [user])

  useEffect(() => {
    const change = () => setRoute(readRoute())
    window.addEventListener("hashchange", change)
    return () => window.removeEventListener("hashchange", change)
  }, [])

  useEffect(() => {
    document.title = `${sections[section].label} — Администрирование AIRate`
  }, [section])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (signingIn) return
    setSigningIn(true)
    setError("")
    try {
      const result = await accountRequest<Identity>("/admin/session", undefined, { login, password })
      setUser(result)
      setPassword("")
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Не удалось войти")
    } finally {
      setSigningIn(false)
    }
  }

  async function logout() {
    setSigningOut(true)
    setError("")
    try {
      await accountRequest("/admin/session", COOKIE_SESSION, undefined, "DELETE")
      setUser(null)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Не удалось выйти. Попробуйте ещё раз.")
    } finally {
      setSigningOut(false)
    }
  }

  if (loading) return <CabinetSkeleton label="Открываем админку…" format="screen"/>
  if (!user) return <main className="air-app operator-login">
    <form className="cab-panel operator-login__panel" onSubmit={event => void submit(event)}>
      <Brand/>
      <h1>Администрирование</h1>
      {error ? <p role="alert">{error}</p> : <p>Вход только для операторов.</p>}
      <label>Логин<input name="username" autoComplete="username" required maxLength={64} disabled={signingIn} value={login} onChange={event => setLogin(event.target.value)}/></label>
      <label>Пароль<input name="password" type="password" autoComplete="current-password" required maxLength={200} disabled={signingIn} value={password} onChange={event => setPassword(event.target.value)}/></label>
      <button className="cc-button primary" disabled={signingIn}>{signingIn ? "Входим…" : "Войти"}</button>
    </form>
  </main>

  return <div className="air-app operator">
    <a className="operator__skip" href="#operator-content" onClick={event => {
      event.preventDefault()
      document.getElementById("operator-content")?.focus()
    }}>Перейти к содержимому</a>
    <header className="operator__header">
      <div className="operator__identity"><Brand href="#/overview"/><span>Администрирование</span></div>
      <div className="operator__account">
        <span>{user.email}</span>
        <button className="cc-button" onClick={() => void logout()} disabled={signingOut} aria-label="Выйти из админки">
          <LogOut size={17} aria-hidden="true"/>
        </button>
      </div>
    </header>
    <div className="operator__layout">
      <nav className="operator__nav" aria-label="Разделы админки">
        {Object.entries(sections).map(([id, { label, icon: Icon }]) =>
          <a key={id} href={"#/" + id} aria-current={section === id ? "page" : undefined}>
            <Icon size={19} aria-hidden="true"/>{label}
          </a>
        )}
      </nav>
      <main className="operator__main" id="operator-content" tabIndex={-1}>
        <header className="operator__pagehead">
          <h1>{sections[section].title}</h1>
          <p className="operator__lead">{sections[section].lead}</p>
        </header>
        {error && <p role="alert">{error}</p>}
        {section === "overview" && <AdminDashboard token={COOKIE_SESSION}/>}
        {section === "users" && <AdminOverview key="users" section="users" token={COOKIE_SESSION} userId={user.id}/>}
        {section === "providers" && <AdminOverview key="providers" section="providers" token={COOKIE_SESSION} userId={user.id}/>}
        {section === "promos" && <AdminPromos token={COOKIE_SESSION}/>}
        {section === "access" && <AdminAccess token={COOKIE_SESSION}/>}
        {section === "runs" && <AdminRuns token={COOKIE_SESSION} resultsHref={id => "#/results?run_id=" + encodeURIComponent(id)}/>}
        {section === "results" && <AdminScans key={runId ?? "all"} token={COOKIE_SESSION} runId={runId}/>}
      </main>
    </div>
  </div>
}

createRoot(document.getElementById("root")!).render(<AdminConsole/>)
