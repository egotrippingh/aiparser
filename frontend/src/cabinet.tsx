import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import { createRoot } from "react-dom/client"
import { ArrowDownLeft, ArrowUpRight, ShieldCheck } from "lucide-react"
import { ACCOUNT_API as API, COOKIE_SESSION, accountRequest as request, AccountError, onSessionExpired } from "./account-api"
import { AdminScans } from "./admin-scans"
import { AdminOverview } from "./admin-overview"
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

function Cabinet() {
  const editorDirty = useRef(false)
  const [token, setToken] = useState(() =>
    location.hash.includes("auth_ticket=") || location.hash.includes("browser_ticket=") || location.hash.includes("reset_token=")
      ? "" : sessionStorage.getItem(TOKEN_KEY) || COOKIE_SESSION)
  const [checkingSession, setCheckingSession] = useState(true)
  const [user, setUser] = useState<User | null>(null)
  const [wallet, setWallet] = useState<Wallet | null>(null)
  const [payments, setPayments] = useState<Payment[]>([])
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
  const refreshVersion = useRef(0), activeSession = useRef(token)
  activeSession.current = token

  useEffect(() => onSessionExpired(token, () => {
    refreshVersion.current++
    activeSession.current = ""
    sessionStorage.removeItem(TOKEN_KEY)
    setToken("")
    setUser(null)
    setWallet(null)
    setPayments([])
    setPassword("")
    setAuthMode("login")
    setCheckingSession(false)
    setMessage("Сессия недействительна. Войдите снова.")
  }), [token])

  function acceptSession(result: {token?: string}) {
    // Keep compatibility while the site and agent are deployed separately.
    refreshVersion.current++
    if (result.token) sessionStorage.setItem(TOKEN_KEY, result.token)
    else sessionStorage.removeItem(TOKEN_KEY)
    setToken(result.token || COOKIE_SESSION)
  }

  async function refresh(activeToken: string) {
    const version = ++refreshVersion.current
    const p = await request<Payment[]>("/payments", activeToken)
    const reconciled = p
    const [u, w] = await Promise.all([
      request<User>("/me", activeToken),
      request<Wallet>("/wallet", activeToken),
    ])
    if (version !== refreshVersion.current || activeToken !== activeSession.current) return
    setUser(u)
    setWallet(w)
    setPayments(reconciled)
  }

  useEffect(() => {
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
        connect_expired: "Ссылка входа истекла. Войдите в кабинет заново.",
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
    params.delete("connect")
    params.delete("provider")
    params.delete("agent_connected")
    sessionStorage.removeItem("aimt.connect")
    if (params.has("linked")) {
      setMessage("Яндекс ID подключён к аккаунту")
      params.delete("linked")
    }
    history.replaceState(null, "", location.pathname + (params.size ? `?${params}` : "") + location.hash)
  }, [])

  useEffect(() => {
    let alive = true
    request<{ check_price_kopeks: number; min_topup_kopeks: number }>("/pricing")
      .then((p) => { if (alive) {setPrice(p.check_price_kopeks); setMinimum(p.min_topup_kopeks)} })
      .catch(() => {if (alive) setMessage("Сервер кабинета пока недоступен")})
    if (token) {
      refresh(token).then(async () => {
        if (!alive || activeSession.current !== token) return
        const params = new URLSearchParams(location.search)
        const order = params.get("order") || params.get("custom")
        if (order) {
          location.hash = "/account"
          try {
            const payment = await request<Payment>(`/payments/${encodeURIComponent(order)}`, token)
            if (!alive || activeSession.current !== token) return
            setMessage(paymentLabel(payment.status))
            await refresh(token)
          } catch (e) { if (alive && activeSession.current === token) setMessage(e instanceof Error ? e.message : "Не удалось проверить платёж") }
        }
      }).catch(e => { if (!alive || activeSession.current !== token) return; if (e instanceof AccountError && e.status === 401) {sessionStorage.removeItem(TOKEN_KEY); setToken(""); setUser(null)} else setMessage(e.message || "Сервер недоступен") }).finally(() => {if (alive) setCheckingSession(false)})
    }
    return () => {alive = false}
  }, [token])

  const walletChanged = useCallback(() => {refresh(token).catch(e => {if(activeSession.current === token)setMessage(e.message)})}, [token])
  useEffect(() => {
    if (!token || !user) return
    const change = () => {if (["#/account", "#/topup"].includes(location.hash)) walletChanged()}
    window.addEventListener("hashchange", change)
    const timer = setInterval(() => {if (!document.hidden) walletChanged()}, 30000)
    return () => {window.removeEventListener("hashchange", change);clearInterval(timer)}
  }, [token, user?.id, walletChanged])

  useEffect(() => {
    if (!token || !user || !payments.some(p => p.status === "pending")) return
    let stopped = false, running = false
    const timer = window.setInterval(async () => {
      if (document.hidden || running) return
      running = true
      try {
        await Promise.all(payments.filter(p => p.status === "pending").slice(0, 5).map(p => request(`/payments/${p.id}`, token).catch(() => null)))
        if (!stopped && activeSession.current === token) await refresh(token)
      } catch (e) { if (!stopped && activeSession.current === token) setMessage(e instanceof Error ? e.message : "Не удалось обновить платёж") }
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
      const result = await request<{ token?: string; user: User }>(`/auth/${authMode}`, undefined, { email, password })
      acceptSession(result)
      setPassword("")
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось войти")
    } finally { setBusy(false) }
  }

  async function logout() {
    if (editorDirty.current && !window.confirm("Изменения не сохранены. Уйти со страницы?")) return
    refreshVersion.current++
    try { await request("/auth/logout", token, {}) }
    catch { if (activeSession.current === token) setMessage("Не удалось выйти. Проверьте связь и повторите."); return }
    if (activeSession.current !== token) return
    sessionStorage.removeItem(TOKEN_KEY)
    setToken("")
    setUser(null)
    setWallet(null)
  }

  const setEditorDirty = useCallback((dirty: boolean) => { editorDirty.current = dirty }, [])
  async function linkYandex() {
    setBusy(true)
    try {
      const result = await request<{ authorization_url: string }>("/auth/yandex/link/start", token, {})
      if (activeSession.current === token) location.assign(result.authorization_url)
    } catch (error) {
      if (activeSession.current === token) setMessage(error instanceof Error ? error.message : "Не удалось открыть Яндекс ID")
      setBusy(false)
    }
  }

  if (user && !checkingSession) return <ControlCenter key={token} token={token} email={user.email}
    balance={user.is_admin ? "Безлимитно" : money(wallet?.available_kopeks || 0)} admin={!!user.is_admin}
    brandClarificationsEnabled={!!user.brand_clarifications_enabled} onDirtyChange={setEditorDirty}
    logout={logout} walletChanged={walletChanged} message={message} administration={<><AdminOverview token={token}/><AdminScans token={token}/></>}
    account={<div className="app-account">        <div className="cab-title-row"><div><span className="cab-kicker">ВАШ АККАУНТ</span><h2>Баланс и проверки</h2><p>{user.email}</p>{yandexEnabled && <button className="cab-link-yandex" disabled={busy || user.yandex_linked} onClick={linkYandex}>{user.yandex_linked ? "Яндекс ID подключён" : "Привязать Яндекс ID"}</button>}</div><span className="cab-rate">{user.is_admin ? "Администратор · проверки бесплатно" : `Одна проверка · ${money(price)}`}</span></div>
        <div className="cab-grid">
          <section className="cab-panel cab-balance"><span className="cab-kicker">ДОСТУПНО ДЛЯ ПРОВЕРОК</span><strong>{user.is_admin ? "Безлимитно" : money(wallet?.available_kopeks || 0)}</strong><p>{user.is_admin ? `Обычные проверки бесплатны.${user.brand_clarifications_enabled ? ` Пересчёт сохранённых ответов — 0,80 ₽ за ответ; доступный баланс ${money(wallet?.available_kopeks || 0)}.` : ""}` : `На балансе ${money(wallet?.balance_kopeks || 0)}${wallet?.reserved_kopeks ? ` · Зарезервировано ${money(wallet.reserved_kopeks)}` : ""}`}</p><div className="cab-balance-foot">{user.is_admin ? "Обычная проверка запроса в ИИ-сервисе · 0 ₽" : `Примерно ${Math.floor((wallet?.available_kopeks || 0) / price)} проверок по текущей цене`}</div><button className="cab-primary" type="button" onClick={() => document.getElementById("topup-amount")?.focus()}>Пополнить баланс</button></section>
          <TopupForm token={token} minimum={minimum} />
        </div>
        {payments.length > 0 && <section className="cab-panel cab-history"><div className="cab-section-head"><div><span className="cab-kicker">ПОПОЛНЕНИЯ</span><h2>История платежей</h2></div><button className="cab-refresh" onClick={walletChanged}>Обновить</button></div><div className="cab-list">{payments.map(payment => <div className="cab-entry cab-payment-row" key={payment.id}><span><b>{money(payment.amount_kopeks)} · {payment.method === "crypto" ? "Криптовалюта" : payment.method === "sbp" ? "СБП" : "Банковская оплата"}</b><small>{new Date(payment.created_at).toLocaleString("ru-RU")}</small></span><span className={`cab-payment-status ${payment.status}`} role="status">{paymentLabel(payment.status)}</span>{payment.status === "pending" && payment.payment_url && <a className="cab-download" href={payment.payment_url}>Продолжить оплату</a>}</div>)}</div></section>}
        {(wallet?.entries.length || !user.is_admin) && <section className="cab-panel cab-history"><div className="cab-section-head"><div><span className="cab-kicker">ИСТОРИЯ</span><h2>Операции по балансу</h2></div><button onClick={walletChanged} className="cab-refresh">Обновить</button></div>{wallet?.entries.length ? <div className="cab-list">{wallet.entries.map((entry) => <div className="cab-entry" key={entry.reference}><span className={entry.amount_kopeks > 0 ? "cab-entry-icon in" : "cab-entry-icon out"}>{entry.amount_kopeks > 0 ? <ArrowDownLeft size={18} /> : <ArrowUpRight size={18} />}</span><span><b>{entry.kind === "topup" ? "Пополнение" : entry.kind === "recompute" ? "Пересчёт ответа" : "Проверка запроса"}</b><small>{new Date(entry.created_at).toLocaleString("ru-RU")}</small></span><strong className={entry.amount_kopeks > 0 ? "positive" : ""}>{entry.amount_kopeks > 0 ? "+" : ""}{money(entry.amount_kopeks)}</strong></div>)}</div> : <p className="cab-empty">Пока нет операций. Пополните баланс, чтобы начать проверки.</p>}</section>}
        {payments.some((p) => p.status === "pending") && <p className="cab-pending">Есть незавершённое пополнение. Если вы уже оплатили, нажмите «Обновить» после возврата на сайт.</p>}</div>}/>
  return <div className="cabinet">
    <header className="cab-header"><div className="cab-container cab-header-inner"><Brand className="cab-brand"/><span className="cab-header-label">Личный кабинет</span></div></header>
    <main className="cab-container cab-main">{checkingSession ? <p role="status">Открываем кабинет…</p> : <section className="cab-auth-wrap">        <div className="cab-intro"><span className="cab-kicker">AI MENTIONS / АККАУНТ</span><h1>Проверки под вашим контролем.</h1><p>Запускайте проверки и задавайте расписание в браузере. Ответы собираются на сервере и сохраняются в вашем аккаунте.</p><div className="cab-price-note"><ShieldCheck size={18} /> {money(price)} за запрос в одном ИИ-сервисе</div></div>
        <form className="cab-panel cab-auth" onSubmit={authenticate}>
          <button className="cab-yandex" type="button" disabled={!yandexEnabled || busy}
            title={yandexEnabled ? "" : "Доступно после настройки Яндекс ID на сервере"}
            onClick={() => location.assign(`${API}/api/v1/auth/yandex/start`)}>
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
          <button className="cab-primary" disabled={busy}>{busy ? "Подождите…" : authMode === "login" ? "Войти" : authMode === "register" ? "Зарегистрироваться" : authMode === "forgot" ? "Отправить ссылку" : "Сменить пароль"}</button>
          {authMode === "login" && resetEnabled && <button className="cab-refresh" type="button" onClick={() => setAuthMode("forgot")}>Забыли пароль?</button>}
        </form></section>}
      {message && <p className="cab-message" role="status">{message}</p>}
    </main><SiteFooter/>
  </div>
}

initTelemetry().finally(() => createRoot(document.getElementById("root")!, rootOptions).render(<Cabinet />))
