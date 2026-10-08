import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import { createRoot } from "react-dom/client"
import { ArrowDownLeft, ArrowUpRight, Download, Image as ImageIcon, LogOut, ShieldCheck } from "lucide-react"
import { ACCOUNT_API as API, COOKIE_SESSION, accountRequest as request, AccountError } from "./account-api"
import { AdminScans } from "./admin-scans"
import { ControlCenter } from "./control-center"
import "./cabinet.css"
import { SiteFooter } from "./site-footer"
import { Brand } from "./brand"
import { TopupForm } from "./components/topup-form"
import { paymentLabel, type Payment } from "./lib/payment"
import { initTelemetry, rootOptions } from "./telemetry"

const TOKEN_KEY = "aimt.account.token"
const money = (kopeks: number) => new Intl.NumberFormat("ru-RU", {
  style: "currency", currency: "RUB", maximumFractionDigits: 2,
}).format(kopeks / 100)

type User = { id: string; email: string; yandex_linked?: boolean; is_admin?: boolean; brand_clarifications_enabled?: boolean }
type Entry = { amount_kopeks: number; kind: string; reference: string; created_at: string }
type Wallet = { balance_kopeks: number; reserved_kopeks: number; available_kopeks: number; entries: Entry[] }
type Screenshot = { check_id: string; size_bytes: number; created_at: string }

function Cabinet() {
  const editorDirty = useRef(false)
  const [token, setToken] = useState(() =>
    new URLSearchParams(location.search).get("provider") === "yandex" || location.hash.includes("auth_ticket=") || location.hash.includes("browser_ticket=") || location.hash.includes("reset_token=")
      ? "" : sessionStorage.getItem(TOKEN_KEY) || COOKIE_SESSION)
  const [checkingSession, setCheckingSession] = useState(true)
  const [connectId, setConnectId] = useState(() => new URLSearchParams(location.search).get("connect") || "")
  const [connectName, setConnectName] = useState("")
  const [user, setUser] = useState<User | null>(null)
  const [wallet, setWallet] = useState<Wallet | null>(null)
  const [payments, setPayments] = useState<Payment[]>([])
  const [screenshots, setScreenshots] = useState<Screenshot[]>([])
  const [visibleScreenshots, setVisibleScreenshots] = useState(12)
  const [openedScreenshot, setOpenedScreenshot] = useState<{ id: string; url: string } | null>(null)
  const [price, setPrice] = useState(120)
  const [minimum, setMinimum] = useState(30000)
  const [resetToken, setResetToken] = useState(() => new URLSearchParams(location.hash.slice(1)).get("reset_token") || "")
  const [authMode, setAuthMode] = useState<"login" | "register" | "forgot" | "reset">(() =>
    new URLSearchParams(location.hash.slice(1)).has("reset_token") ? "reset" : "login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const [yandexEnabled, setYandexEnabled] = useState(false)
  const [resetEnabled, setResetEnabled] = useState(false)
  const [section, setSection] = useState<"dashboard" | "account" | "admin">(location.hash === "#/topup" ? "account" : "dashboard")
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)

  function acceptSession(result: {token?: string}) {
    // Keep compatibility while the site and agent are deployed separately.
    if (result.token) sessionStorage.setItem(TOKEN_KEY, result.token)
    else sessionStorage.removeItem(TOKEN_KEY)
    setToken(result.token || COOKIE_SESSION)
  }

  async function refresh(activeToken: string) {
    const p = await request<Payment[]>("/payments", activeToken)
    const reconciled = p
    const [u, w, shots] = await Promise.all([
      request<User>("/me", activeToken),
      request<Wallet>("/wallet", activeToken),
      request<{ screenshots: Screenshot[] }>("/screenshots", activeToken)
        .catch(() => ({ screenshots: [] })),
    ])
    setUser(u)
    setWallet(w)
    setPayments(reconciled)
    setScreenshots(shots.screenshots)
  }

  useEffect(() => {
    const connect = new URLSearchParams(location.search).get("connect")
    if (connect && /^[a-f0-9]{32}$/.test(connect)) {
      sessionStorage.setItem("aimt.connect", connect)
      request<{name:string}>(`/auth/connect/${connect}`)
        .then(info => {
          setConnectName(info.name)
          if (new URLSearchParams(location.search).get("provider") === "yandex")
            location.assign(`${API}/api/v1/auth/yandex/start?connect=${encodeURIComponent(connect)}`)
        }).catch(e => {setMessage(e.message);setCheckingSession(false)})
    }
    request<{ available: boolean; url: string | null }>("/agent-download")
      .then((result) => setDownloadUrl(result.available ? result.url : null)).catch(() => null)
    request<{ yandex: boolean; password_reset: boolean }>("/auth/providers")
      .then((p) => { setYandexEnabled(p.yandex); setResetEnabled(p.password_reset) }).catch(() => null)
    if (new URLSearchParams(location.hash.slice(1)).has("reset_token")) {
      sessionStorage.removeItem(TOKEN_KEY)
      history.replaceState(null, "", location.pathname + location.search)
      setCheckingSession(false)
    }
    const browserTicket = new URLSearchParams(location.hash.slice(1)).get("browser_ticket")
    if (browserTicket) {
      history.replaceState(null, "", location.pathname + location.search)
      sessionStorage.removeItem(TOKEN_KEY)
      request<{destination: string}>("/auth/browser/exchange", undefined, {ticket: browserTicket})
        .then(result => {
          setSection(result.destination === "topup" ? "account" : "dashboard")
          history.replaceState(null, "", location.pathname + (result.destination === "topup" ? "#/topup" : ""))
          setToken(COOKIE_SESSION)
        })
        .catch(e => {setCheckingSession(false); setMessage(e.message)})
    }
    const ticket = new URLSearchParams(location.hash.slice(1)).get("auth_ticket")
    if (ticket) {
      history.replaceState(null, "", location.pathname + location.search)
      sessionStorage.removeItem(TOKEN_KEY)
      request<{ token?: string; user: User }>("/auth/yandex/exchange", undefined, { ticket })
        .then((result) => {
          acceptSession(result)
          setMessage("Вы вошли через Яндекс")
        })
        .catch(() => {setCheckingSession(false); setMessage("Не удалось завершить вход через Яндекс. Попробуйте ещё раз.")})
    }
    const params = new URLSearchParams(location.search)
    const authError = params.get("auth_error")
    if (authError) {
      const errors: Record<string, string> = {
        connect_expired: "Запрос подключения истёк. Начните вход из агента заново.",
        cancelled: "Вход через Яндекс отменён.",
        provider: "Яндекс не подтвердил вход. Попробуйте ещё раз.",
        email_required: "Разрешите доступ к email в Яндекс ID, чтобы создать аккаунт.",
        link_required: "Аккаунт с таким email уже есть. Войдите по паролю и привяжите Яндекс ID в кабинете.",
        already_linked: "Этот Яндекс ID уже привязан к другому аккаунту.",
        retry: "Не удалось привязать Яндекс ID. Попробуйте ещё раз.",
      }
      setMessage(errors[authError] || "Не удалось войти через Яндекс.")
      params.delete("auth_error")
    }
    if (params.has("agent_connected")) {
      sessionStorage.removeItem("aimt.connect")
      setConnectId("")
      setMessage("Компьютер подключён. Агент готов к работе.")
      params.delete("agent_connected")
      params.delete("connect")
    }
    if (params.has("linked")) {
      setMessage("Яндекс ID подключён к аккаунту")
      params.delete("linked")
    }
    history.replaceState(null, "", location.pathname + (params.size ? `?${params}` : "") + location.hash)
  }, [])

  useEffect(() => {
    request<{ check_price_kopeks: number; min_topup_kopeks: number }>("/pricing")
      .then((p) => { setPrice(p.check_price_kopeks); setMinimum(p.min_topup_kopeks) })
      .catch(() => setMessage("Сервер кабинета пока недоступен"))
    if (token) {
      refresh(token).then(async () => {
        const params = new URLSearchParams(location.search)
        const order = params.get("order") || params.get("custom")
        if (order) {
          setSection("account")
          try {
            const payment = await request<Payment>(`/payments/${encodeURIComponent(order)}`, token)
            setMessage(paymentLabel(payment.status))
            await refresh(token)
          } catch (e) { setMessage(e instanceof Error ? e.message : "Не удалось проверить платёж") }
        }
      }).catch(e => { if (e instanceof AccountError && e.status === 401) {sessionStorage.removeItem(TOKEN_KEY); setToken(""); setUser(null)} else setMessage(e.message || "Сервер недоступен") }).finally(() => setCheckingSession(false))
    }
  }, [token])

  useEffect(() => {
    if (!token || !user || !payments.some(p => p.status === "pending")) return
    let stopped = false, running = false
    const timer = window.setInterval(async () => {
      if (document.hidden || running) return
      running = true
      try {
        await Promise.all(payments.filter(p => p.status === "pending").slice(0, 5).map(p => request(`/payments/${p.id}`, token).catch(() => null)))
        if (!stopped) await refresh(token)
      } catch (e) { if (!stopped) setMessage(e instanceof Error ? e.message : "Не удалось обновить платёж") }
      finally { running = false }
    }, 15000)
    return () => { stopped = true; clearInterval(timer) }
  }, [token, user?.id, payments.map(p => `${p.id}:${p.status}`).join(",")])

  async function authenticate(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage("")
    try {
      if (authMode === "forgot") {
        await request("/auth/password/request", undefined, { email })
        setMessage("Если такой аккаунт есть, мы отправили ссылку для смены пароля на почту.")
        return
      }
      if (authMode === "reset") {
        await request("/auth/password/confirm", undefined, { token: resetToken, password })
        setResetToken("")
        setPassword("")
        setAuthMode("login")
        setMessage("Пароль изменён. Войдите с новым паролем.")
        return
      }
      const result = await request<{ token?: string; user: User; agent_connected?:boolean }>(`/auth/${authMode}`, undefined, { email, password, ...(connectId?{connect_id:connectId}:{}) })
      if(result.agent_connected){
        sessionStorage.removeItem("aimt.connect")
        setConnectId("")
        const url=new URL(location.href);url.searchParams.delete("connect");history.replaceState(null,"",url)
        setMessage("Компьютер подключён. Агент готов к работе.")
      }
      acceptSession(result)
      setPassword("")
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось войти")
    } finally { setBusy(false) }
  }

  async function logout() {
    if (editorDirty.current && !window.confirm("Изменения не сохранены. Уйти со страницы?")) return
    try { await request("/auth/logout", token, {}) }
    catch { setMessage("Не удалось выйти. Проверьте связь и повторите."); return }
    sessionStorage.removeItem(TOKEN_KEY)
    setToken("")
    setUser(null)
    setWallet(null)
    setScreenshots([])
    setOpenedScreenshot(null)
  }

  const setEditorDirty = useCallback((dirty: boolean) => { editorDirty.current = dirty }, [])
  const leaveEditor = useCallback(() => !editorDirty.current || window.confirm("Изменения не сохранены. Уйти со страницы?"), [])

  async function openScreenshot(checkId: string) {
    try {
      const result = await request<{ url: string }>(`/screenshots/${encodeURIComponent(checkId)}/url`, token)
      setOpenedScreenshot({ id: checkId, url: result.url })
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось открыть скриншот")
    }
  }

  async function linkYandex() {
    setBusy(true)
    try {
      const result = await request<{ authorization_url: string }>("/auth/yandex/link/start", token, {})
      location.assign(result.authorization_url)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось открыть Яндекс ID")
      setBusy(false)
    }
  }

  return <div className={`cabinet ${user && section === "dashboard" ? "cab-workspace" : ""}`}>
    <header className="cab-header"><div className="cab-container cab-header-inner"><Brand className="cab-brand" /><span className="cab-header-label">Личный кабинет</span>{user && <nav className="cab-nav" aria-label="Разделы кабинета"><button className={section === "dashboard" ? "active" : ""} onClick={() => setSection("dashboard")}>Рабочее пространство</button><button className={section === "account" ? "active" : ""} onClick={() => { if (leaveEditor()) { setSection("account"); refresh(token).catch(e => setMessage(e.message)) } }}>{user.is_admin ? "Аккаунт" : "Аккаунт и оплата"}</button>{user.is_admin && <button className={section === "admin" ? "active" : ""} onClick={() => { if (leaveEditor()) setSection("admin") }}>Сканы пользователей</button>}</nav>}{user && <button className="cab-logout" onClick={logout}><LogOut size={16} /> Выйти</button>}</div></header>
    <main className="cab-container cab-main">
      {checkingSession ? <p role="status">Открываем кабинет…</p> : !user ? <section className="cab-auth-wrap">
        <div className="cab-intro"><span className="cab-kicker">AI MENTIONS / АККАУНТ</span><h1>Проверки под вашим контролем.</h1><p>Смотрите отчёты в браузере, задавайте расписание для агента и пополняйте баланс. Новые результаты синхронизируются с вашим аккаунтом после проверки на компьютере.</p><div className="cab-price-note"><ShieldCheck size={18} /> {money(price)} за запрос в одном ИИ-сервисе</div>{downloadUrl && <p><a className="cab-download" href={downloadUrl}><Download size={17} /> Скачать агент для Windows</a></p>}</div>
        <form className="cab-panel cab-auth" onSubmit={authenticate}>
          {connectId&&<p role="status">Вход подключит компьютер <strong>{connectName||"из агента"}</strong> к вашему аккаунту. Вводить код не нужно.</p>}
          <button className="cab-yandex" type="button" disabled={!yandexEnabled || busy}
            title={yandexEnabled ? "" : "Доступно после настройки Яндекс ID на сервере"}
            onClick={() => location.assign(`${API}/api/v1/auth/yandex/start${connectId?`?connect=${encodeURIComponent(connectId)}`:""}`)}>
            <span className="cab-yandex-mark" aria-hidden="true">Я</span> Продолжить через Яндекс
          </button>
          <div className="cab-auth-divider"><span>или по email</span></div>
          {authMode === "forgot" || authMode === "reset"
            ? <div className="cab-tabs"><button type="button" onClick={() => { setAuthMode("login"); setResetToken("") }}>← Вернуться ко входу</button></div>
            : <div className="cab-tabs"><button type="button" className={authMode === "login" ? "active" : ""} onClick={() => setAuthMode("login")}>Войти</button><button type="button" className={authMode === "register" ? "active" : ""} onClick={() => setAuthMode("register")}>Создать аккаунт</button></div>}
          {authMode === "reset" ? <p>Придумайте новый пароль для аккаунта.</p>
            : <label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>}
          {authMode !== "forgot" && <label>{authMode === "reset" ? "Новый пароль" : "Пароль"}<input type="password" minLength={12} autoComplete={authMode === "login" ? "current-password" : "new-password"} required value={password} onChange={(e) => setPassword(e.target.value)} /></label>}
          {(authMode === "register" || authMode === "reset") && <small>Не менее 12 символов.</small>}
          <button className="cab-primary" disabled={busy}>{busy ? "Подождите…" : authMode === "login" ? (connectId ? "Войти и подключить компьютер" : "Войти") : authMode === "register" ? "Зарегистрироваться" : authMode === "forgot" ? "Отправить ссылку" : "Сменить пароль"}</button>
          {authMode === "login" && resetEnabled && <button className="cab-refresh" type="button" onClick={() => setAuthMode("forgot")}>Забыли пароль?</button>}
        </form>
      </section> : section === "admin" && user.is_admin ? <AdminScans token={token} /> : section === "dashboard" ? <ControlCenter token={token} downloadUrl={downloadUrl} brandClarificationsEnabled={!!user.brand_clarifications_enabled} onDirtyChange={setEditorDirty} /> : <>
        <div className="cab-title-row"><div><span className="cab-kicker">ВАШ АККАУНТ</span><h1>Баланс и проверки</h1><p>{user.email}</p>{yandexEnabled && <button className="cab-link-yandex" disabled={busy || user.yandex_linked} onClick={linkYandex}>{user.yandex_linked ? "Яндекс ID подключён" : "Привязать Яндекс ID"}</button>}</div><span className="cab-rate">{user.is_admin ? "Администратор · проверки бесплатно" : `Одна проверка · ${money(price)}`}</span></div>
        <div className="cab-grid">
          <section className="cab-panel cab-balance"><span className="cab-kicker">ДОСТУПНО ДЛЯ ПРОВЕРОК</span><strong>{user.is_admin ? "Безлимитно" : money(wallet?.available_kopeks || 0)}</strong><p>{user.is_admin ? `Обычные проверки бесплатны.${user.brand_clarifications_enabled ? ` Пересчёт сохранённых ответов — 0,80 ₽ за ответ; доступный баланс ${money(wallet?.available_kopeks || 0)}.` : ""}` : `На балансе ${money(wallet?.balance_kopeks || 0)}${wallet?.reserved_kopeks ? ` · Зарезервировано ${money(wallet.reserved_kopeks)}` : ""}`}</p><div className="cab-balance-foot">{user.is_admin ? "Обычная проверка запроса в ИИ-сервисе · 0 ₽" : `Примерно ${Math.floor((wallet?.available_kopeks || 0) / price)} проверок по текущей цене`}</div><button className="cab-primary" type="button" onClick={() => document.getElementById("topup-amount")?.focus()}>Пополнить баланс</button></section>
          <TopupForm token={token} minimum={minimum} />
        </div>
        {payments.length > 0 && <section className="cab-panel cab-history"><div className="cab-section-head"><div><span className="cab-kicker">ПОПОЛНЕНИЯ</span><h2>История платежей</h2></div><button className="cab-refresh" onClick={() => refresh(token).catch(e => setMessage(e.message))}>Обновить</button></div><div className="cab-list">{payments.map(payment => <div className="cab-entry cab-payment-row" key={payment.id}><span><b>{money(payment.amount_kopeks)} · {payment.method === "crypto" ? "Криптовалюта" : payment.method === "sbp" ? "СБП" : "Банковская оплата"}</b><small>{new Date(payment.created_at).toLocaleString("ru-RU")}</small></span><span className={`cab-payment-status ${payment.status}`} role="status">{paymentLabel(payment.status)}</span>{payment.status === "pending" && payment.payment_url && <a className="cab-download" href={payment.payment_url}>Продолжить оплату</a>}</div>)}</div></section>}
        <section className="cab-panel cab-device"><div><span className="cab-kicker">НАСТОЛЬНЫЙ АГЕНТ</span><h2>Подключите компьютер</h2><p>Запустите агент и войдите через Яндекс, браузер или по email и паролю. Компьютер привяжется к аккаунту без кода, а агент будет выполнять назначенные ему проверки из трея.</p></div><div className="cab-device-actions">{downloadUrl && <a className="cab-download" href={downloadUrl}><Download size={17} /> Скачать для Windows</a>}</div></section>
        {(wallet?.entries.length || !user.is_admin) && <section className="cab-panel cab-history"><div className="cab-section-head"><div><span className="cab-kicker">ИСТОРИЯ</span><h2>Операции по балансу</h2></div><button onClick={() => refresh(token)} className="cab-refresh">Обновить</button></div>{wallet?.entries.length ? <div className="cab-list">{wallet.entries.map((entry) => <div className="cab-entry" key={entry.reference}><span className={entry.amount_kopeks > 0 ? "cab-entry-icon in" : "cab-entry-icon out"}>{entry.amount_kopeks > 0 ? <ArrowDownLeft size={18} /> : <ArrowUpRight size={18} />}</span><span><b>{entry.kind === "topup" ? "Пополнение" : entry.kind === "recompute" ? "Пересчёт ответа" : "Проверка запроса"}</b><small>{new Date(entry.created_at).toLocaleString("ru-RU")}</small></span><strong className={entry.amount_kopeks > 0 ? "positive" : ""}>{entry.amount_kopeks > 0 ? "+" : ""}{money(entry.amount_kopeks)}</strong></div>)}</div> : <p className="cab-empty">Пока нет операций. Пополните баланс, чтобы начать проверки.</p>}</section>}
        <section className="cab-panel cab-history"><div className="cab-section-head"><div><span className="cab-kicker">СКРИНШОТЫ · 90 ДНЕЙ</span><h2>Снимки проверок</h2></div><button onClick={() => refresh(token)} className="cab-refresh">Обновить</button></div>{screenshots.length ? <><div className="cab-list">{screenshots.slice(0, visibleScreenshots).map((shot) => { const parts = shot.check_id.split(":"); return <div className="cab-entry" key={shot.check_id}><span className="cab-entry-icon out" aria-hidden="true"><ImageIcon size={18} /></span><span><b>Запрос №{parts.at(-2)} · {parts.at(-1)}</b><small>{new Date(shot.created_at).toLocaleString("ru-RU")}</small></span><button className="cab-shot-button" onClick={() => openScreenshot(shot.check_id)}>Открыть</button></div> })}</div>{screenshots.length > visibleScreenshots && <button className="cab-refresh" onClick={() => setVisibleScreenshots((count) => count + 12)}>Показать ещё</button>}</> : <p className="cab-empty">Загруженных снимков пока нет. Снимки остаются в настольном приложении.</p>}{openedScreenshot && <div className="cab-shot-preview"><div className="cab-section-head"><b>Снимок проверки</b><button className="cab-refresh" onClick={() => setOpenedScreenshot(null)}>Закрыть</button></div><img src={openedScreenshot.url} alt="Скриншот ответа ИИ по выбранной проверке" /></div>}</section>
        {payments.some((p) => p.status === "pending") && <p className="cab-pending">Есть незавершённое пополнение. Если вы уже оплатили, нажмите «Обновить» после возврата на сайт.</p>}
      </>}
      {message && <p className="cab-message" role="status">{message}</p>}
    </main>
    <SiteFooter />
  </div>
}

initTelemetry().finally(() => createRoot(document.getElementById("root")!, rootOptions).render(<Cabinet />))
