import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react"
import { createRoot } from "react-dom/client"
import { ArrowDownLeft, ArrowUpRight, Eye, EyeOff } from "lucide-react"
import { ACCOUNT_API as API, COOKIE_SESSION, accountRequest as request, AccountError, onSessionExpired } from "./account-api"
import { AdminScans } from "./admin-scans"
import { AdminOverview } from "./admin-overview"
import { AdminPromos } from "./admin-promos"
import { PromoForm, type FreeScans } from "./components/promo-form"
import { ControlCenter } from "./control-center"
import "./cabinet.css"
import "./account-refresh.css"
import { AccountBalance } from "./components/account-balance"
import { SiteHeader } from "./site-header"
import { TopupForm } from "./components/topup-form"
import { PasswordSettings } from "./components/password-settings"
import { paymentLabel, type Payment } from "./lib/payment"
import { EMAIL_PROOF_KEY, needsRegistrationPassword, restoreEmailProof } from "./lib/registration"
import { initTelemetry, rootOptions } from "./telemetry"

const TOKEN_KEY = "aimt.account.token"
const money = (kopeks: number) => new Intl.NumberFormat("ru-RU", {
  style: "currency", currency: "RUB", maximumFractionDigits: 2,
}).format(kopeks / 100)

type User = { id: string; email: string; has_password?: boolean; yandex_linked?: boolean; is_admin?: boolean; brand_clarifications_enabled?: boolean }
type Entry = { amount_kopeks: number; kind: string; reference: string; created_at: string }
type Wallet = { balance_kopeks: number; reserved_kopeks: number; available_kopeks: number; entries: Entry[]; free_scans?: FreeScans }

function PasswordField({ label, value, onChange, disabled, autoComplete = "new-password", confirmation = false }: {
  label: string; value: string; onChange: (value: string) => void; disabled: boolean; autoComplete?: string; confirmation?: boolean
}) {
  const [visible, setVisible] = useState(false)
  const id = useId()
  return <div className="cab-password-field"><label htmlFor={id}>{label}</label><span><input id={id} type={visible ? "text" : "password"} autoComplete={autoComplete} required minLength={12} maxLength={256} disabled={disabled} value={value} onChange={event => onChange(event.target.value)} />
    <button type="button" className="cab-password-toggle" disabled={disabled} aria-pressed={visible} aria-label={visible ? `Скрыть ${confirmation ? "повтор пароля" : "пароль"}` : `Показать ${confirmation ? "повтор пароля" : "пароль"}`} onClick={() => setVisible(!visible)}>{visible ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}</button></span></div>
}

function Cabinet() {
  const editorDirty = useRef(false)
  const [token, setToken] = useState(() =>
    location.hash.includes("auth_ticket=") || location.hash.includes("browser_ticket=") || location.hash.includes("reset_token=") || location.hash.includes("registration_ticket=")
      ? "" : sessionStorage.getItem(TOKEN_KEY) || COOKIE_SESSION)
  const [checkingSession, setCheckingSession] = useState(true)
  const [user, setUser] = useState<User | null>(null)
  const [wallet, setWallet] = useState<Wallet | null>(null)
  const [payments, setPayments] = useState<Payment[]>([])
  const [price, setPrice] = useState(165)
  const [minimum, setMinimum] = useState(30000)
  const [resetToken, setResetToken] = useState(() => new URLSearchParams(location.hash.slice(1)).get("reset_token") || "")
  const [registrationTicket, setRegistrationTicket] = useState(() => new URLSearchParams(location.hash.slice(1)).get("registration_ticket") || "")
  const [savedEmailProof, setSavedEmailProof] = useState(() => restoreEmailProof(sessionStorage.getItem(EMAIL_PROOF_KEY)))
  const [authMode, setAuthMode] = useState<"login" | "register" | "forgot" | "reset" | "yandex-register">(() =>
    new URLSearchParams(location.hash.slice(1)).has("reset_token") ? "reset" : savedEmailProof || new URLSearchParams(location.search).has("register") ? "register" : "login")
  const [email, setEmail] = useState(savedEmailProof?.email || "")
  const [password, setPassword] = useState("")
  const [confirmation, setConfirmation] = useState("")
  const [promoCode, setPromoCode] = useState("")
  const [emailTicket, setEmailTicket] = useState(savedEmailProof?.ticket || "")
  const [emailCode, setEmailCode] = useState("")
  const [resendAfter, setResendAfter] = useState(() => Math.max(0, Math.ceil(((savedEmailProof?.resendAt || 0) - Date.now()) / 1000)))
  const codeInput = useRef<HTMLInputElement>(null)
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

  useEffect(() => {
    if (!resendAfter) return
    const timer = setTimeout(() => setResendAfter(resendAfter - 1), 1000)
    return () => clearTimeout(timer)
  }, [resendAfter])

  useEffect(() => { if (emailTicket) codeInput.current?.focus() }, [emailTicket])

  async function sendRegistrationCode() {
    const result = await request<{ticket: string; expires_in: number; resend_after: number}>("/auth/registration/code", undefined, {email})
    sessionStorage.setItem(EMAIL_PROOF_KEY, JSON.stringify({email, ticket: result.ticket,
      expiresAt: Date.now() + result.expires_in * 1000, resendAt: Date.now() + result.resend_after * 1000}))
    setEmailTicket(result.ticket)
    setEmailCode("")
    setResendAfter(result.resend_after)
    setMessage("Код отправлен на почту. Введите его, чтобы создать аккаунт.")
  }

  async function resendRegistrationCode() {
    if (busy || resendAfter) return
    setBusy(true)
    setMessage("")
    try { await sendRegistrationCode() }
    catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось отправить код") }
    finally { setBusy(false) }
  }

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
    const registration = new URLSearchParams(location.hash.slice(1)).get("registration_ticket")
    if (registration) {
      history.replaceState(null, "", location.pathname + location.search)
      sessionStorage.removeItem(TOKEN_KEY)
      request<{email: string}>("/auth/yandex/registration", undefined, {ticket: registration})
        .then(result => {setEmail(result.email); setAuthMode("yandex-register"); setMessage("Яндекс подтвердил вашу почту. Создайте пароль, чтобы завершить регистрацию.")})
        .catch(e => {setRegistrationTicket(""); setMessage(e.message)})
        .finally(() => setCheckingSession(false))
    }
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
    if (busy) return
    if (["register", "reset", "yandex-register"].includes(authMode) && password !== confirmation) {setMessage("Пароли не совпадают."); return}
    setBusy(true)
    setMessage("")
    try {
      if (authMode === "register" && !emailTicket) {
        await sendRegistrationCode()
        return
      }
      if (authMode === "forgot") {
        await request("/auth/password/request", undefined, { email })
        setMessage("Если такой аккаунт есть, мы отправили ссылку для смены пароля на почту.")
        return
      }
      if (authMode === "reset") {
        await request("/auth/password/confirm", undefined, { token: resetToken, password })
        setResetToken("")
        setPassword("")
        setConfirmation("")
        setAuthMode("login")
        setMessage("Пароль изменён. Войдите с новым паролем.")
        return
      }
      const result = authMode === "yandex-register"
        ? await request<{token?: string; user: User}>("/auth/yandex/register", undefined, {ticket: registrationTicket, password, promo_code: promoCode.trim()})
        : await request<{ token?: string; user: User }>(`/auth/${authMode}`, undefined, { email, password, ...(authMode === "register" ? { promo_code: promoCode.trim(), ticket: emailTicket, code: emailCode } : {}) })
      acceptSession(result)
      setAuthMode("login")
      setRegistrationTicket("")
      setPassword("")
      setConfirmation("")
      setPromoCode("")
      setEmailTicket("")
      setEmailCode("")
      sessionStorage.removeItem(EMAIL_PROOF_KEY)
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

  const showRegistrationCredentials = needsRegistrationPassword(emailTicket, !!savedEmailProof, password, confirmation)
  const confirmingEmail = authMode === "register" && !!emailTicket

  if (user && !checkingSession) return <ControlCenter key={token} token={token} email={user.email}
    balance={user.is_admin ? "Безлимитно" : money(wallet?.available_kopeks || 0)} admin={!!user.is_admin}
    brandClarificationsEnabled={!!user.brand_clarifications_enabled} onDirtyChange={setEditorDirty}
    logout={logout} walletChanged={walletChanged} message={message} administration={<><AdminPromos token={token}/><AdminOverview token={token}/><AdminScans token={token}/></>}
    account={<div className="app-account"><div className="cab-title-row"><div><span className="cab-kicker">АККАУНТ И ОПЛАТА</span><h2>Пополнение баланса</h2><p>{user.email}</p></div><AccountBalance available={money(wallet?.available_kopeks ?? 0)} balance={money(wallet?.balance_kopeks ?? 0)} reserved={wallet?.reserved_kopeks ? money(wallet.reserved_kopeks) : undefined} admin={!!user.is_admin} paidRecompute={!!user.brand_clarifications_enabled}/></div>
        <div className="cab-billing-grid">
          <TopupForm token={token} minimum={minimum} checkPrice={user.is_admin ? 0 : price} />
        </div>
        <div className="cab-account-tools"><PromoForm token={token} freeScans={wallet?.free_scans} applied={walletChanged} /><PasswordSettings token={token} hasPassword={!!user.has_password} email={user.email} resetEnabled={resetEnabled} saved={result => {acceptSession(result); setUser({...user, has_password:true}); setMessage("Пароль сохранён. Другие сеансы завершены.")}}/>
        {yandexEnabled && <section className="cab-panel cab-yandex-settings"><h2>Яндекс ID</h2><p>{user.yandex_linked ? "Яндекс ID подключён к этому аккаунту." : "Подключите Яндекс ID, чтобы входить без пароля."}</p><button className="cab-secondary" disabled={busy || user.yandex_linked} onClick={linkYandex}>{user.yandex_linked ? "Яндекс ID подключён" : "Привязать Яндекс ID"}</button></section>}</div>
        {payments.length > 0 && <section className="cab-panel cab-history"><div className="cab-section-head"><div><span className="cab-kicker">ПОПОЛНЕНИЯ</span><h2>История платежей</h2></div><button className="cab-refresh" onClick={walletChanged}>Обновить</button></div><div className="cab-list">{payments.map(payment => <div className="cab-entry cab-payment-row" key={payment.id}><span><b>{money(payment.amount_kopeks)} · {payment.method === "crypto" ? "Криптовалюта" : payment.method === "sbp" ? "СБП" : "Банковская оплата"}</b><small>{new Date(payment.created_at).toLocaleString("ru-RU")}</small></span><span className={`cab-payment-status ${payment.status}`} role="status">{paymentLabel(payment.status)}</span>{payment.status === "pending" && payment.payment_url && <a className="cab-download" href={payment.payment_url}>Продолжить оплату</a>}</div>)}</div></section>}
        {(wallet?.entries.length || !user.is_admin) && <section className="cab-panel cab-history"><div className="cab-section-head"><div><span className="cab-kicker">ИСТОРИЯ</span><h2>Операции по балансу</h2></div><button onClick={walletChanged} className="cab-refresh">Обновить</button></div>{wallet?.entries.length ? <div className="cab-list">{wallet.entries.map((entry) => <div className="cab-entry" key={entry.reference}><span className={entry.amount_kopeks > 0 ? "cab-entry-icon in" : "cab-entry-icon out"}>{entry.amount_kopeks > 0 ? <ArrowDownLeft size={18} /> : <ArrowUpRight size={18} />}</span><span><b>{entry.kind === "topup" ? "Пополнение" : entry.kind === "recompute" ? "Пересчёт ответа" : "Проверка запроса"}</b><small>{new Date(entry.created_at).toLocaleString("ru-RU")}</small></span><strong className={entry.amount_kopeks > 0 ? "positive" : ""}>{entry.amount_kopeks > 0 ? "+" : ""}{money(entry.amount_kopeks)}</strong></div>)}</div> : <p className="cab-empty">Пока нет операций по денежному балансу.</p>}</section>}
        {payments.some((p) => p.status === "pending") && <p className="cab-pending">Есть незавершённое пополнение. Если вы уже оплатили, нажмите «Обновить» после возврата на сайт.</p>}</div>}/>
  return <div className="cabinet cab-auth-page">
    <SiteHeader onLogin={() => {if (!busy) {setAuthMode("login"); setResetToken(""); setRegistrationTicket(""); setPassword(""); setConfirmation(""); setMessage("")}}} onRegister={() => {if (!busy) {setAuthMode("register"); setResetToken(""); setRegistrationTicket(""); setPassword(""); setConfirmation(""); setMessage("")}}}/>
    <main className="cab-container cab-main">{checkingSession ? <p role="status">Открываем кабинет…</p> : <section className="cab-auth-wrap"><form className="cab-panel cab-auth" onSubmit={authenticate}>
          {authMode !== "login" && <button className="cab-back" type="button" disabled={busy} onClick={() => { setAuthMode("login"); setResetToken(""); setRegistrationTicket(""); setPassword(""); setConfirmation(""); setMessage("") }}>← Вернуться ко входу</button>}
          <div className="cab-auth-heading"><h1>{authMode === "login" ? "Вход в аккаунт" : confirmingEmail ? "Проверьте почту" : authMode === "register" ? "Создать аккаунт" : authMode === "forgot" ? "Забыли пароль?" : authMode === "reset" ? "Новый пароль" : "Завершите регистрацию"}</h1>
            {confirmingEmail ? <p>Введите код из письма на {email}.</p> : (authMode === "login" || authMode === "register") && <p>{authMode === "login" ? <>Нет аккаунта? <button type="button" className="cab-inline-link" disabled={busy} onClick={() => {setAuthMode("register"); setMessage("")}}>Зарегистрироваться</button></> : <>Уже есть аккаунт? <button type="button" className="cab-inline-link" disabled={busy} onClick={() => {setAuthMode("login"); setMessage("")}}>Войти</button></>}</p>}</div>
          {(authMode === "login" || authMode === "register") && !confirmingEmail && <><button className="cab-yandex" type="button" disabled={!yandexEnabled || busy}
            title={yandexEnabled ? "" : "Доступно после настройки Яндекс ID на сервере"}
            onClick={() => location.assign(`${API}/api/v1/auth/yandex/start`)}>
            <span className="cab-yandex-mark" aria-hidden="true"><svg viewBox="44 16 24 24" xmlns="http://www.w3.org/2000/svg"><rect x="44" y="16" width="24" height="24" rx="12" fill="#FC3F1D"/><path d="M57.6912 35.212H60.1982V20.812H56.5516C52.8843 20.812 50.9574 22.6975 50.9574 25.4739C50.9574 27.6909 52.0141 28.9962 53.8995 30.3429L50.6259 35.212H53.3401L56.9867 29.7628L55.7228 28.9133C54.1896 27.8773 53.4437 27.0693 53.4437 25.3288C53.4437 23.7956 54.5211 22.7596 56.5723 22.7596H57.6912V35.212Z" fill="white"/></svg></span> Продолжить с Яндекс
          </button>
          <p className="cab-provider-note">Для входа и регистрации</p><div className="cab-auth-divider"><span>или по email</span></div></>}
          {authMode === "reset" ? <p>Придумайте новый пароль для аккаунта.</p>
            : (!confirmingEmail || showRegistrationCredentials) && <label>Электронная почта<input type="email" autoComplete="email" placeholder="you@company.ru" required disabled={busy} readOnly={authMode === "yandex-register"} value={email} onChange={(e) => {setEmail(e.target.value); setEmailTicket(""); setEmailCode(""); setResendAfter(0); setSavedEmailProof(null); sessionStorage.removeItem(EMAIL_PROOF_KEY)}} /></label>}
          {authMode === "yandex-register" && <p>Завершите регистрацию: пароль позволит входить без Яндекса.</p>}
          {authMode === "forgot" && <><p>Укажите почту аккаунта: использованную при регистрации или полученную от Яндекса.</p>{!resetEnabled && <p role="status">Отправка писем ещё не подключена. Восстановление по почте станет доступно позже.</p>}</>}
          {authMode !== "forgot" && (showRegistrationCredentials || authMode !== "register") && <PasswordField label={authMode === "reset" ? "Новый пароль" : "Пароль"} value={password} onChange={setPassword} disabled={busy} autoComplete={authMode === "login" ? "current-password" : "new-password"} />}
          {["register", "reset", "yandex-register"].includes(authMode) && (showRegistrationCredentials || authMode !== "register") && <><small>Не менее 12 символов.</small><PasswordField label="Повторите пароль" value={confirmation} onChange={setConfirmation} disabled={busy} confirmation /></>}
          {(authMode === "register" || authMode === "yandex-register") && <details className="cab-promo-details"><summary>Есть промокод?</summary><label>Промокод<input autoComplete="off" maxLength={64} disabled={busy} value={promoCode} onChange={e => setPromoCode(e.target.value)} aria-describedby="registration-promo-hint" /></label><small id="registration-promo-hint">Его также можно ввести позже в разделе «Аккаунт и оплата».</small></details>}
          {authMode === "register" && emailTicket && <>
            <label>Код из письма<input ref={codeInput} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required disabled={busy} value={emailCode} onChange={e => setEmailCode(e.target.value.replace(/[^0-9]/g, ""))} aria-describedby="registration-code-hint" /></label>
            <small id="registration-code-hint">6 цифр. Код действует 10 минут. Если письма нет, проверьте папку «Спам».</small>
            <div className="cab-code-actions"><button className="cab-inline-link" type="button" disabled={busy || resendAfter > 0} onClick={resendRegistrationCode}>{resendAfter > 0 ? `Отправить повторно через ${resendAfter} с` : "Отправить код повторно"}</button><button className="cab-inline-link" type="button" disabled={busy} onClick={() => {setEmailTicket(""); setEmailCode(""); setResendAfter(0); setSavedEmailProof(null); sessionStorage.removeItem(EMAIL_PROOF_KEY)}}>Изменить почту</button></div>
          </>}
          <button className="cab-primary" disabled={busy || (authMode === "forgot" && !resetEnabled)}>{busy ? "Подождите…" : authMode === "login" ? "Войти" : authMode === "register" ? emailTicket ? "Подтвердить почту и создать аккаунт" : "Получить код на почту" : authMode === "yandex-register" ? "Завершить регистрацию" : authMode === "forgot" ? "Отправить ссылку" : "Сменить пароль"}</button>
          {authMode === "login" && <button className="cab-inline-link cab-forgot" type="button" onClick={() => setAuthMode("forgot")}>Забыли пароль?</button>}
          {message && <p className="cab-auth-message" role="status">{message}</p>}
        </form></section>}
      {checkingSession && message && <p className="cab-auth-message" role="status">{message}</p>}
    </main><footer className="cab-auth-footer"><span>© {new Date().getFullYear()} AIRate</span><a href="/privacy/">Конфиденциальность</a></footer>
  </div>
}

if (location.hash === "#/help") location.replace("/docs/")
else initTelemetry().finally(() => createRoot(document.getElementById("root")!, rootOptions).render(<Cabinet />))
