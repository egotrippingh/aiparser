import { useEffect, useState, type FormEvent } from "react"
import { createRoot } from "react-dom/client"
import { ArrowDownLeft, ArrowUpRight, CreditCard, Image as ImageIcon, LogOut, ShieldCheck } from "lucide-react"
import "./cabinet.css"

const API = (import.meta.env.VITE_ACCOUNT_API_URL || "").replace(/\/$/, "")
const TOKEN_KEY = "aimt.account.token"
const money = (kopeks: number) => new Intl.NumberFormat("ru-RU", {
  style: "currency", currency: "RUB", maximumFractionDigits: 2,
}).format(kopeks / 100)

type User = { id: string; email: string; yandex_linked?: boolean }
type Entry = { amount_kopeks: number; kind: string; reference: string; created_at: string }
type Wallet = { balance_kopeks: number; reserved_kopeks: number; available_kopeks: number; entries: Entry[] }
type Payment = { id: string; amount_kopeks: number; method: string; status: string; payment_url: string | null; created_at: string }
type Screenshot = { check_id: string; size_bytes: number; created_at: string }

async function request<T>(path: string, token?: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API}/api/v1${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || `Ошибка ${response.status}`)
  return data as T
}

function Brand() {
  return <a className="cab-brand" href="/"><span className="cab-mark" aria-hidden="true"><i /></span>AI Mentions</a>
}

function Cabinet() {
  const [token, setToken] = useState(() => location.hash.includes("auth_ticket=") ? "" : sessionStorage.getItem(TOKEN_KEY) || "")
  const [user, setUser] = useState<User | null>(null)
  const [wallet, setWallet] = useState<Wallet | null>(null)
  const [payments, setPayments] = useState<Payment[]>([])
  const [screenshots, setScreenshots] = useState<Screenshot[]>([])
  const [visibleScreenshots, setVisibleScreenshots] = useState(12)
  const [openedScreenshot, setOpenedScreenshot] = useState<{ id: string; url: string } | null>(null)
  const [price, setPrice] = useState(150)
  const [minimum, setMinimum] = useState(30000)
  const [authMode, setAuthMode] = useState<"login" | "register">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [amount, setAmount] = useState("300")
  const [method, setMethod] = useState<"sbp" | "card">("sbp")
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const [yandexEnabled, setYandexEnabled] = useState(false)
  const [deviceCode, setDeviceCode] = useState("")

  async function refresh(activeToken: string) {
    const p = await request<Payment[]>("/payments", activeToken)
    const reconciled = await Promise.all(p.map((payment) => payment.status === "pending"
      ? request<Payment>(`/payments/${encodeURIComponent(payment.id)}`, activeToken).catch(() => payment)
      : payment))
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
    request<{ yandex: boolean }>("/auth/providers").then((p) => setYandexEnabled(p.yandex)).catch(() => null)
    const ticket = new URLSearchParams(location.hash.slice(1)).get("auth_ticket")
    if (ticket) {
      history.replaceState(null, "", location.pathname + location.search)
      sessionStorage.removeItem(TOKEN_KEY)
      request<{ token: string; user: User }>("/auth/yandex/exchange", undefined, { ticket })
        .then((result) => {
          sessionStorage.setItem(TOKEN_KEY, result.token)
          setToken(result.token)
          setMessage("Вы вошли через Яндекс")
        })
        .catch(() => setMessage("Не удалось завершить вход через Яндекс. Попробуйте ещё раз."))
    }
    const params = new URLSearchParams(location.search)
    const authError = params.get("auth_error")
    if (authError) {
      const errors: Record<string, string> = {
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
    if (params.has("linked")) {
      setMessage("Яндекс ID подключён к аккаунту")
      params.delete("linked")
    }
    history.replaceState(null, "", location.pathname + (params.size ? `?${params}` : "") + location.hash)
  }, [])

  useEffect(() => {
    request<{ check_price_kopeks: number; min_topup_kopeks: number }>("/pricing")
      .then((p) => { setPrice(p.check_price_kopeks); setMinimum(p.min_topup_kopeks); setAmount(String(p.min_topup_kopeks / 100)) })
      .catch(() => setMessage("Сервер кабинета пока недоступен"))
    if (token) {
      refresh(token).then(async () => {
        const order = new URLSearchParams(location.search).get("order")
        if (order) {
          const payment = await request<Payment>(`/payments/${encodeURIComponent(order)}`, token)
          setMessage(payment.status === "paid" ? "Пополнение зачислено" : "Платёж обрабатывается. Обновите страницу через минуту.")
          await refresh(token)
        }
      }).catch(() => { sessionStorage.removeItem(TOKEN_KEY); setToken(""); setMessage("Войдите снова") })
    }
  }, [token])

  async function authenticate(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage("")
    try {
      const result = await request<{ token: string; user: User }>(`/auth/${authMode}`, undefined, { email, password })
      sessionStorage.setItem(TOKEN_KEY, result.token)
      setToken(result.token)
      setPassword("")
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось войти")
    } finally { setBusy(false) }
  }

  async function topup(event: FormEvent) {
    event.preventDefault()
    const kopeks = Math.round(Number(amount.replace(",", ".")) * 100)
    if (!Number.isSafeInteger(kopeks) || kopeks < minimum) {
      setMessage(`Минимальное пополнение — ${money(minimum)}`)
      return
    }
    setBusy(true)
    setMessage("")
    try {
      const order = await request<Payment>("/payments", token, { amount_kopeks: kopeks, method })
      if (!order.payment_url) throw new Error("Платёжная ссылка не получена")
      location.assign(order.payment_url)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось создать платёж")
      setBusy(false)
    }
  }

  async function logout() {
    await fetch(`${API}/api/v1/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${token}` } }).catch(() => null)
    sessionStorage.removeItem(TOKEN_KEY)
    setToken("")
    setUser(null)
    setWallet(null)
    setScreenshots([])
    setOpenedScreenshot(null)
  }

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

  async function createDeviceCode() {
    setBusy(true)
    try {
      const result = await request<{ code: string; expires_in: number }>("/auth/device/code", token, {})
      setDeviceCode(result.code)
      setMessage("Код действует 5 минут и может быть использован один раз")
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось создать код")
    } finally { setBusy(false) }
  }

  async function copyDeviceCode() {
    try {
      await navigator.clipboard.writeText(deviceCode)
      setMessage("Код скопирован")
    } catch { setMessage("Выделите и скопируйте код вручную") }
  }

  return <div className="cabinet">
    <header className="cab-header"><div className="cab-container cab-header-inner"><Brand /><span className="cab-header-label">Личный кабинет</span>{user && <button className="cab-logout" onClick={logout}><LogOut size={16} /> Выйти</button>}</div></header>
    <main className="cab-container cab-main">
      {!user ? <section className="cab-auth-wrap">
        <div className="cab-intro"><span className="cab-kicker">AI MENTIONS / АККАУНТ</span><h1>Проверки под вашим контролем.</h1><p>Пополняйте баланс и смотрите историю проверок. Проекты и отчёты хранятся на вашем компьютере. При подключённом облачном хранилище снимки проверок доступны и в кабинете.</p><div className="cab-price-note"><ShieldCheck size={18} /> {money(price)} за запрос в одном ИИ-сервисе</div></div>
        <form className="cab-panel cab-auth" onSubmit={authenticate}>
          <button className="cab-yandex" type="button" disabled={!yandexEnabled || busy}
            title={yandexEnabled ? "" : "Доступно после настройки Яндекс ID на сервере"}
            onClick={() => location.assign(`${API}/api/v1/auth/yandex/start`)}>
            <span className="cab-yandex-mark" aria-hidden="true">Я</span> Продолжить через Яндекс
          </button>
          <div className="cab-auth-divider"><span>или по email</span></div>
          <div className="cab-tabs"><button type="button" className={authMode === "login" ? "active" : ""} onClick={() => setAuthMode("login")}>Войти</button><button type="button" className={authMode === "register" ? "active" : ""} onClick={() => setAuthMode("register")}>Создать аккаунт</button></div>
          <label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Пароль<input type="password" minLength={12} autoComplete={authMode === "login" ? "current-password" : "new-password"} required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {authMode === "register" && <small>Не менее 12 символов.</small>}
          <button className="cab-primary" disabled={busy}>{busy ? "Подождите…" : authMode === "login" ? "Войти" : "Зарегистрироваться"}</button>
        </form>
      </section> : <>
        <div className="cab-title-row"><div><span className="cab-kicker">ВАШ АККАУНТ</span><h1>Баланс и проверки</h1><p>{user.email}</p>{yandexEnabled && <button className="cab-link-yandex" disabled={busy || user.yandex_linked} onClick={linkYandex}>{user.yandex_linked ? "Яндекс ID подключён" : "Привязать Яндекс ID"}</button>}</div><span className="cab-rate">Одна проверка · {money(price)}</span></div>
        <div className="cab-grid">
          <section className="cab-panel cab-balance"><span className="cab-kicker">ДОСТУПНО ДЛЯ ПРОВЕРОК</span><strong>{money(wallet?.available_kopeks || 0)}</strong><p>На балансе {money(wallet?.balance_kopeks || 0)}{wallet?.reserved_kopeks ? ` · Зарезервировано ${money(wallet.reserved_kopeks)}` : ""}</p><div className="cab-balance-foot">Примерно {Math.floor((wallet?.available_kopeks || 0) / price)} проверок по текущей цене</div></section>
          <form className="cab-panel cab-topup" onSubmit={topup}><span className="cab-kicker">ПОПОЛНЕНИЕ</span><h2>Добавить средства</h2><label>Сумма, ₽<input type="number" min={minimum / 100} max="100000" step="1" value={amount} onChange={(e) => setAmount(e.target.value)} /></label><fieldset><legend>Способ оплаты</legend><label><input type="radio" name="method" checked={method === "sbp"} onChange={() => setMethod("sbp")} /> СБП</label><label><input type="radio" name="method" checked={method === "card"} onChange={() => setMethod("card")} /> Карта</label></fieldset><button className="cab-primary" disabled={busy}><CreditCard size={17} /> Перейти к оплате</button><small>Минимальная сумма — {money(minimum)}. После оплаты средства появятся на балансе.</small></form>
        </div>
        <section className="cab-panel cab-device"><div><span className="cab-kicker">НАСТОЛЬНОЕ ПРИЛОЖЕНИЕ</span><h2>Подключить парсер</h2><p>Откройте экран скана на компьютере и выберите «Код из кабинета». Код создаётся на 5 минут и подходит для одного входа.</p></div><button className="cab-primary" onClick={createDeviceCode} disabled={busy}>Получить код</button>{deviceCode && <div className="cab-device-code"><code>{deviceCode}</code><button onClick={copyDeviceCode}>Скопировать</button></div>}</section>
        <section className="cab-panel cab-history"><div className="cab-section-head"><div><span className="cab-kicker">ИСТОРИЯ</span><h2>Операции по балансу</h2></div><button onClick={() => refresh(token)} className="cab-refresh">Обновить</button></div>{wallet?.entries.length ? <div className="cab-list">{wallet.entries.map((entry) => <div className="cab-entry" key={entry.reference}><span className={entry.amount_kopeks > 0 ? "cab-entry-icon in" : "cab-entry-icon out"}>{entry.amount_kopeks > 0 ? <ArrowDownLeft size={18} /> : <ArrowUpRight size={18} />}</span><span><b>{entry.kind === "topup" ? "Пополнение" : "Проверка запроса"}</b><small>{new Date(entry.created_at).toLocaleString("ru-RU")}</small></span><strong className={entry.amount_kopeks > 0 ? "positive" : ""}>{entry.amount_kopeks > 0 ? "+" : ""}{money(entry.amount_kopeks)}</strong></div>)}</div> : <p className="cab-empty">Пока нет операций. Пополните баланс, чтобы начать проверки.</p>}</section>
        <section className="cab-panel cab-history"><div className="cab-section-head"><div><span className="cab-kicker">СКРИНШОТЫ</span><h2>Снимки проверок</h2></div><button onClick={() => refresh(token)} className="cab-refresh">Обновить</button></div>{screenshots.length ? <><div className="cab-list">{screenshots.slice(0, visibleScreenshots).map((shot) => { const parts = shot.check_id.split(":"); return <div className="cab-entry" key={shot.check_id}><span className="cab-entry-icon out" aria-hidden="true"><ImageIcon size={18} /></span><span><b>Запрос №{parts.at(-2)} · {parts.at(-1)}</b><small>{new Date(shot.created_at).toLocaleString("ru-RU")}</small></span><button className="cab-shot-button" onClick={() => openScreenshot(shot.check_id)}>Открыть</button></div> })}</div>{screenshots.length > visibleScreenshots && <button className="cab-refresh" onClick={() => setVisibleScreenshots((count) => count + 12)}>Показать ещё</button>}</> : <p className="cab-empty">Загруженных снимков пока нет. Снимки остаются в настольном приложении.</p>}{openedScreenshot && <div className="cab-shot-preview"><div className="cab-section-head"><b>Снимок проверки</b><button className="cab-refresh" onClick={() => setOpenedScreenshot(null)}>Закрыть</button></div><img src={openedScreenshot.url} alt="Скриншот ответа ИИ по выбранной проверке" /></div>}</section>
        {payments.some((p) => p.status === "pending") && <p className="cab-pending">Есть незавершённое пополнение. Если вы уже оплатили, нажмите «Обновить» после возврата на сайт.</p>}
      </>}
      {message && <p className="cab-message" role="status">{message}</p>}
    </main>
  </div>
}

createRoot(document.getElementById("root")!).render(<Cabinet />)
