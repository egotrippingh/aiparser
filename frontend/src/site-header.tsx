import { useEffect, useId, useRef, useState, type ReactNode } from "react"
import { BookOpen, BriefcaseBusiness, ChevronDown, CirclePlus, FolderOpen, LogOut, Mail, Plus, Search, Settings, ShieldCheck, Wallet } from "lucide-react"
import { Brand } from "./brand"
import { ProjectIcon } from "./project-icon"
import { IconNavLink } from "./icon-nav-link"
import { SUPPORT_EMAIL } from "./site-footer"
import { accountRequest, COOKIE_SESSION } from "./account-api"
import "./site-header.css"

type HeaderProject = { id: string; name: string; config: { brand_domains: string[] } }
type Props = { email?: string; balance?: string; projects?: HeaderProject[]; selectedId?: string; loading?: boolean; projectError?: boolean; admin?: boolean; cabinet?: boolean; projectTab?: string; logout?: () => void; onLogin?: () => void; onRegister?: () => void }

function Dropdown({ label, trigger, children, className = "" }: { label: string; trigger: ReactNode; children: ReactNode; className?: string }) {
  const id = useId(), button = useRef<HTMLButtonElement>(null), panel = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ left: 12, top: 64 })
  useEffect(() => {
    if (!open) return
    const close = () => panel.current?.hidePopover()
    window.addEventListener("resize", close)
    window.addEventListener("scroll", close, { passive: true })
    return () => { window.removeEventListener("resize", close); window.removeEventListener("scroll", close) }
  }, [open])
  return <div className={`sh-dropdown ${className}`}>
    <button ref={button} type="button" className="sh-trigger" popoverTarget={id} aria-label={label} aria-expanded={open} aria-controls={id}>{trigger}<ChevronDown size={16}/></button>
    <div ref={panel} id={id} popover="auto" className="sh-popover" style={position} onToggle={event => {
      setOpen(event.newState === "open")
      if (event.newState === "open" && button.current) {
        const rect = button.current.getBoundingClientRect()
        setPosition({ left: Math.max(12, Math.min(rect.left, window.innerWidth - 352)), top: rect.bottom + 10 })
        panel.current?.querySelector<HTMLInputElement>("input")?.focus()
      }
    }} onClick={event => { if ((event.target as HTMLElement).closest("a, button")) panel.current?.hidePopover() }}>{children}</div>
  </div>
}

export function SiteHeader({ email, balance, projects = [], selectedId, loading, projectError, admin, cabinet, projectTab = "report", logout, onLogin, onRegister }: Props) {
  const [search, setSearch] = useState("")
  const base = cabinet ? "" : (import.meta.env.VITE_APP_URL || "/cabinet/")
  const href = (route: string) => `${base}#/${route}`
  const selected = projects.find(project => project.id === selectedId)
  const shown = projects.filter(project => `${project.name} ${project.config.brand_domains.join(" ")} ${project.id}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  return <header className="sh-header"><div className="sh-inner">
    <Brand className="sh-brand"/>
    {email ? <div className="sh-project-tools"><IconNavLink className="sh-project-home" label="Все проекты" href={href("projects")} side="bottom"><BriefcaseBusiness size={23} aria-hidden="true"/></IconNavLink><Dropdown label="Выбрать проект" className="sh-projects" trigger={<span>{selected?.name || "Проекты"}</span>}>
      <label className="sh-search"><Search size={18}/><input aria-label="Поиск проекта" placeholder="Найти проект" value={search} onChange={event => setSearch(event.target.value)}/></label>
      <a className="sh-all" href={href("projects")}><FolderOpen size={18}/>Все проекты<span>{projects.length}</span></a>
      <div className="sh-project-list">{loading ? <p role="status">Загрузка проектов…</p> : projectError ? <p role="status">Не удалось загрузить проекты. <a href={href("projects")}>Открыть кабинет</a></p> : shown.map(project => <a key={project.id} href={href(`project/${project.id}/${projectTab}`)} aria-current={project.id === selectedId ? "true" : undefined}><ProjectIcon name={project.name} domains={project.config.brand_domains}/><span><strong>{project.name}</strong><small>{project.config.brand_domains[0] || `ID ${project.id}`}</small></span></a>)}{!loading && !projectError && !shown.length && <p>{projects.length ? "Проекты не найдены" : "У вас пока нет проектов"}</p>}</div>
      <a className="sh-create" href={href("project/new/settings")}><Plus size={18}/>Создать проект</a>
    </Dropdown></div> : <nav className="sh-guest-nav" aria-label="О сервисе"><a href="/#how">Как работает</a><a href="/#approach">Наш подход</a><a href="/#faq">Вопросы</a><a href="/help/">Помощь</a><a className="sh-mobile-support" href={SUPPORT_EMAIL}>Поддержка</a></nav>}
    <div className="sh-actions"><a className="sh-support" aria-label="Поддержка" href={SUPPORT_EMAIL}><Mail size={21}/><span>Поддержка</span></a>
      {email ? <><a className="sh-help" aria-label="Помощь" href="/help/"><BookOpen size={21}/><span>Помощь</span></a><a className="sh-balance" href={href("topup")} aria-label={`Пополнить баланс${balance ? `: ${balance}` : ""}`}><span>{balance || "Баланс"}</span><CirclePlus size={23}/></a>
        <Dropdown label="Меню аккаунта" trigger={<span className="sh-avatar">{email.slice(0, 2).toUpperCase()}</span>}>
          <div className="sh-identity"><span className="sh-avatar">{email.slice(0, 2).toUpperCase()}</span><span><strong>{email}</strong><small>{admin ? "Администратор" : "Личный аккаунт"}</small></span></div>
          <a href={href("topup")}><Wallet size={19}/>Пополнить баланс</a><a href={href("account")}><Settings size={19}/>Настройки аккаунта</a><a href="/help/"><BookOpen size={19}/>Помощь</a><a href={SUPPORT_EMAIL}><Mail size={19}/>Поддержка</a>{admin && <a href={href("admin")}><ShieldCheck size={19}/>Администрирование</a>}
          <button type="button" className="sh-logout" onClick={logout}><LogOut size={19}/>Выйти из аккаунта</button>
        </Dropdown></> : <>{onLogin ? <button className="sh-login" onClick={onLogin}>Войти</button> : <a className="sh-login" href={base}>Войти</a>}{onRegister ? <button className="sh-register" onClick={onRegister}>Регистрация</button> : <a className="sh-register" href={`${base}?register=1`}>Регистрация</a>}</>}
    </div>
  </div></header>
}

export function PublicSiteHeader() {
  const [state, setState] = useState<Props>({})
  const generation = useRef(0)
  useEffect(() => {
    let active = true
    const version = ++generation.current
    const token = sessionStorage.getItem("aimt.account.token") || COOKIE_SESSION
    accountRequest<{ email: string; is_admin?: boolean }>("/me", token).then(async user => {
      if (!active || version !== generation.current) return
      setState({ email: user.email, admin: user.is_admin, loading: true })
      const [projects, wallet] = await Promise.allSettled([accountRequest<HeaderProject[]>("/control/projects", token), accountRequest<{balance_kopeks: number}>("/wallet", token)])
      if (active && version === generation.current) setState({ email: user.email, admin: user.is_admin, projects: projects.status === "fulfilled" ? projects.value : [], projectError: projects.status === "rejected", balance: wallet.status === "fulfilled" ? new Intl.NumberFormat("ru-RU", {style: "currency", currency: "RUB"}).format(wallet.value.balance_kopeks / 100) : undefined })
    }).catch(() => { /* Public navigation remains available without a session. */ })
    return () => { active = false }
  }, [])
  const [error, setError] = useState("")
  async function logout() {
    try { await accountRequest("/auth/logout", sessionStorage.getItem("aimt.account.token") || COOKIE_SESSION, {}); generation.current++; sessionStorage.removeItem("aimt.account.token"); setState({}); setError("") }
    catch { setError("Не удалось выйти. Попробуйте ещё раз.") }
  }
  return <><SiteHeader {...state} logout={logout}/>{error && <p role="alert">{error}</p>}</>
}
