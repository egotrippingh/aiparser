import { useEffect, useState } from "react"
import { createRoot } from "react-dom/client"
import { ArrowUpRight, ChartNoAxesCombined, ClipboardList, FileSearch, LogOut, Server, Ticket, Users } from "lucide-react"
import { AccountError, COOKIE_SESSION, accountRequest, onSessionExpired } from "./account-api"
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
  overview: { label: "Финансы", title: "Финансы и прогноз", icon: ChartNoAxesCombined },
  users: { label: "Пользователи", title: "Пользователи и балансы", icon: Users },
  runs: { label: "Запуски", title: "Запуски проверок", icon: ClipboardList },
  results: { label: "Результаты", title: "Результаты проверок", icon: FileSearch },
  providers: { label: "Провайдеры", title: "Провайдеры", icon: Server },
  promos: { label: "Промокоды", title: "Промокоды", icon: Ticket },
}

type Section = keyof typeof sections
type Identity = { id: string; email: string }

function readRoute() {
  const [path, search] = location.hash.slice(2).split("?")
  const section = (Object.hasOwn(sections, path) ? path : "overview") as Section
  const runId = new URLSearchParams(search).get("run_id") ?? ""
  return { section, runId: /^[a-f0-9]{32}$/.test(runId) ? runId : undefined }
}

function AdminConsole({ ticket }: { ticket: string | null }) {
  const [user, setUser] = useState<Identity | null>(null)
  const [loading, setLoading] = useState(true)
  const [signingOut, setSigningOut] = useState(false)
  const [error, setError] = useState("")
  const [{ section, runId }, setRoute] = useState(readRoute)

  useEffect(() => {
    let active = true
    const session = ticket
      ? accountRequest<Identity>("/admin/session", undefined, { ticket })
      : accountRequest<Identity>("/admin/session", COOKIE_SESSION)
    session.then(result => { if (active) setUser(result) }).catch(failure => {
      if (active && (ticket || !(failure instanceof AccountError && failure.status === 401))) setError(failure.message)
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [ticket])

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
    <section className="cab-panel operator-login__panel">
      <Brand/>
      <h1>Администрирование</h1>
      {error ? <p role="alert">{error}</p> : <p>Войдите в аккаунт AIRate с правами администратора.</p>}
      <a href="/sign-in" className="cc-button primary">Войти через AIRate <ArrowUpRight size={16} aria-hidden="true"/></a>
    </section>
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
        <a className="cc-button" href="/back-to-cabinet">Кабинет <ArrowUpRight size={16} aria-hidden="true"/></a>
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
        <h1>{sections[section].title}</h1>
        {error && <p role="alert">{error}</p>}
        {section === "overview" && <AdminDashboard token={COOKIE_SESSION}/>}
        {section === "users" && <AdminOverview key="users" section="users" token={COOKIE_SESSION} userId={user.id}/>}
        {section === "providers" && <AdminOverview key="providers" section="providers" token={COOKIE_SESSION} userId={user.id}/>}
        {section === "promos" && <AdminPromos token={COOKIE_SESSION}/>}
        {section === "runs" && <AdminRuns token={COOKIE_SESSION} resultsHref={id => "#/results?run_id=" + encodeURIComponent(id)}/>}
        {section === "results" && <AdminScans key={runId ?? "all"} token={COOKIE_SESSION} runId={runId}/>}
      </main>
    </div>
  </div>
}

const ticket = new URLSearchParams(location.hash.slice(1)).get("ticket")
if (ticket !== null) history.replaceState(history.state, "", location.pathname)
createRoot(document.getElementById("root")!).render(<AdminConsole ticket={ticket}/>)
