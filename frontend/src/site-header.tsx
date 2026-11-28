import { useEffect, useId, useRef, useState, type ReactNode } from "react"
import { BookOpen, BriefcaseBusiness, ChevronDown, CirclePlus, FolderOpen, LogOut, Plus, Search, Send, Settings, Wallet } from "lucide-react"
import { CabinetSkeleton } from "./cabinet-loading"
import { Brand } from "./brand"
import { ProjectIcon } from "./project-icon"
import { IconNavLink } from "./icon-nav-link"
import { SUPPORT_URL } from "./site-footer"
import { accountRequest, COOKIE_SESSION } from "./account-api"
import "./site-header.scss"

type HeaderProject = { id: string; name: string; config: { brand_domains: string[] } }
type Props = { email?: string; avatarUrl?: string | null; balance?: string; projects?: HeaderProject[]; selectedId?: string; loading?: boolean; projectError?: boolean; admin?: boolean; cabinet?: boolean; projectTab?: string; landing?: boolean; logout?: () => void; onLogin?: () => void; onRegister?: () => void }

function AccountAvatar({ email, url }: { email: string; url?: string | null }) {
  const [failed, setFailed] = useState(false)
  return <span className="sh-avatar" aria-hidden="true">{url && !failed
    ? <img src={url} alt="" referrerPolicy="no-referrer" onError={() => setFailed(true)}/>
    : email.slice(0, 2).toUpperCase()}</span>
}

function Dropdown({ label, trigger, children, className = "" }: { label: string; trigger: ReactNode; children: ReactNode; className?: string }) {
  const id = useId(), button = useRef<HTMLButtonElement>(null), panel = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const close = () => panel.current?.hidePopover()
    window.addEventListener("resize", close)
    window.addEventListener("scroll", close, { passive: true })
    return () => { window.removeEventListener("resize", close); window.removeEventListener("scroll", close) }
  }, [open])
  return <div className={`sh-dropdown ${className}`}>
    <button ref={button} type="button" className="sh-trigger" popoverTarget={id} aria-label={label} aria-expanded={open} aria-controls={id}>{trigger}<ChevronDown size={16}/></button>
    <div ref={panel} id={id} popover="auto" className="sh-popover" onBeforeToggle={event => {
      if (event.newState !== "open" || !button.current) return
      const rect = button.current.getBoundingClientRect()
      event.currentTarget.style.setProperty("--sh-popover-left", `${Math.max(12, Math.min(rect.left, window.innerWidth - 352))}px`)
      event.currentTarget.style.top = `${rect.bottom + 10}px`
    }} onToggle={event => {
      setOpen(event.newState === "open")
      if (event.newState === "open") panel.current?.querySelector<HTMLInputElement>("input")?.focus()
    }} onClick={event => { if ((event.target as HTMLElement).closest("a, button")) panel.current?.hidePopover() }}>{children}</div>
  </div>
}

export function SiteHeader({ email, avatarUrl, balance, projects = [], selectedId, loading, projectError, admin, cabinet, projectTab = "report", landing = false, logout, onLogin, onRegister }: Props) {
  const [search, setSearch] = useState("")
  const base = cabinet ? "" : (import.meta.env.VITE_APP_URL || "/cabinet/")
  const href = (route: string) => `${base}#/${route}`
  const selected = projects.find(project => project.id === selectedId)
  const shown = projects.filter(project => `${project.name} ${project.config.brand_domains.join(" ")} ${project.id}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  return <header className="sh-header ym-hide-content ym-disable-clickmap ym-disable-tracklink"><div className="sh-inner">
    <Brand className="sh-brand"/>
    {email ? <div className="sh-project-tools"><IconNavLink className="sh-project-home" label="Все проекты" href={href("projects")} side="bottom"><BriefcaseBusiness size={23} aria-hidden="true"/></IconNavLink><Dropdown label="Выбрать проект" className="sh-projects" trigger={<span>{selected?.name || "Выбрать проект"}</span>}>
      <label className="sh-search"><Search size={18}/><input className="ym-disable-keys" aria-label="Поиск проекта" placeholder="Найти проект" value={search} onChange={event => setSearch(event.target.value)}/></label>
      <a className="sh-all" href={href("projects")}><FolderOpen size={18}/>Все проекты<span>{projects.length}</span></a>
      <div className="sh-project-list">{loading ? <CabinetSkeleton label="Загрузка проектов…"/> : projectError ? <p role="status">Не удалось загрузить проекты. <a href={href("projects")}>Открыть кабинет</a></p> : shown.map(project => <a key={project.id} href={href(`project/${project.id}/${projectTab}`)} aria-current={project.id === selectedId ? "true" : undefined}><ProjectIcon name={project.name} domains={project.config.brand_domains}/><span><strong>{project.name}</strong><small>{project.config.brand_domains[0] || `ID ${project.id}`}</small></span></a>)}{!loading && !projectError && !shown.length && <p>{projects.length ? "Проекты не найдены" : "У вас пока нет проектов"}</p>}</div>
      <a className="sh-create" href={href("project/new/settings")}><Plus size={18}/>Создать проект</a>
    </Dropdown></div> : <nav className="sh-guest-nav" aria-label="О сервисе">{landing && <><a href="/#report">Что в отчёте</a><a href="/#audience">Для кого</a></>}<a href="/#how">Как работает</a><a href="/docs/">Документация</a><a className="sh-mobile-support" href={SUPPORT_URL}>Поддержка</a></nav>}
    <div className="sh-actions"><a className="sh-support" aria-label="Поддержка" href={SUPPORT_URL}><Send size={17} aria-hidden="true"/><span>Поддержка</span></a>
      {email ? <><a className="sh-help" aria-label="Документация" href="/docs/"><BookOpen size={21}/><span>Документация</span></a><a className="sh-balance" href={href("topup")} aria-label={`Пополнить баланс${balance ? `: ${balance}` : ""}`}><span>{balance || "Баланс"}</span><CirclePlus size={23}/></a>
        <Dropdown label="Меню аккаунта" trigger={<AccountAvatar key={avatarUrl} email={email} url={avatarUrl}/>}>
          <div className="sh-identity"><AccountAvatar key={avatarUrl} email={email} url={avatarUrl}/><span><strong>{email}</strong><small>{admin ? "Администратор" : "Личный аккаунт"}</small></span></div>
          <a href={href("topup")}><Wallet size={19}/>Пополнить баланс</a><a href={href("account")}><Settings size={19}/>Настройки аккаунта</a><a href="/docs/"><BookOpen size={19}/>Документация</a><a href={SUPPORT_URL}><Send size={17} aria-hidden="true"/>Поддержка</a>
          <button type="button" className="sh-logout" onClick={logout}><LogOut size={19}/>Выйти из аккаунта</button>
        </Dropdown></> : <>{onLogin ? <button className="sh-login" onClick={onLogin}>Войти</button> : <a className="sh-login" href={base}>Войти</a>}{!landing && (onRegister ? <button className="sh-register" onClick={onRegister}>Регистрация</button> : <a className="sh-register" href={`${base}?register=1`}>Регистрация</a>)}</>}
    </div>
  </div></header>
}

export function PublicSiteHeader({ landing = false }: { landing?: boolean } = {}) {
  const [state, setState] = useState<Props>({})
  const generation = useRef(0)
  useEffect(() => {
    let active = true
    const version = ++generation.current
    const token = sessionStorage.getItem("aimt.account.token") || COOKIE_SESSION
    accountRequest<{ email: string; avatar_url?: string | null; is_admin?: boolean }>("/me", token).then(async user => {
      if (!active || version !== generation.current) return
      const account = { email: user.email, avatarUrl: user.avatar_url, admin: user.is_admin }
      setState({ ...account, loading: true })
      const [projects, wallet] = await Promise.allSettled([accountRequest<HeaderProject[]>("/control/projects", token), accountRequest<{balance_kopeks: number}>("/wallet", token)])
      if (active && version === generation.current) setState({ ...account, projects: projects.status === "fulfilled" ? projects.value : [], projectError: projects.status === "rejected", balance: wallet.status === "fulfilled" ? new Intl.NumberFormat("ru-RU", {style: "currency", currency: "RUB"}).format(wallet.value.balance_kopeks / 100) : undefined })
    }).catch(() => { /* Public navigation remains available without a session. */ })
    return () => { active = false }
  }, [])
  const [error, setError] = useState("")
  async function logout() {
    try { await accountRequest("/auth/logout", sessionStorage.getItem("aimt.account.token") || COOKIE_SESSION, {}); generation.current++; sessionStorage.removeItem("aimt.account.token"); setState({}); setError("") }
    catch { setError("Не удалось выйти. Попробуйте ещё раз.") }
  }
  return <><SiteHeader {...state} landing={landing} logout={logout}/>{error && <p role="alert">{error}</p>}</>
}
