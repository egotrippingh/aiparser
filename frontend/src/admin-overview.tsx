import { useCallback, useEffect, useState } from "react"
import { ExternalLink } from "lucide-react"
import { AccountError, accountRequest } from "./account-api"
import { SCAN_SERVICES } from "./lib/scan-preferences"
import "./admin-overview.css"

type Provider = { id: string; name: string; currency: string; balance: string | null; status: string; message: string | null; checked_at: string; topup_url: string; details: { label: string; amount: string; currency?: string; expires_at?: string }[] }
type User = { id: string; email: string; is_admin: boolean; created_at: string; wallet: { balance_kopeks: number; reserved_kopeks: number; available_kopeks: number } }
type Service = { service: string; paused: boolean }
const serviceName = (id: string) => SCAN_SERVICES.find(service => service.id === id)?.label || id
export const balanceLabel = (value: string | null, currency: string) => value === null ? "Недоступен" : currency === "CREDITS" ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 6 }).format(Number(value)) + " credits" : new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: 4 }).format(Number(value))
const rubles = (value: number) => balanceLabel(String(value / 100), "RUB")

export function AdminOverview({ token, userId, walletChanged }: { token: string; userId: string; walletChanged: () => void }) {
  const [email, setEmail] = useState("")
  const [rub, setRub] = useState("")
  const [topupPending, setTopupPending] = useState(false)
  const [topupError, setTopupError] = useState("")
  const [topupSuccess, setTopupSuccess] = useState("")
  async function topup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedEmail = email.trim().toLowerCase()
    const match = /^(\d+)(?:[.,](\d{1,2}))?$/.exec(rub.trim())
    const kopeks = match ? Number(match[1]) * 100 + Number((match[2] || "").padEnd(2, "0")) : 0
    setTopupError("")
    setTopupSuccess("")
    if (!normalizedEmail || !Number.isSafeInteger(kopeks) || kopeks <= 0 || kopeks > 2_147_483_647) {
      setTopupError("Укажите email и сумму больше нуля с точностью до копеек.")
      return
    }
    if (!window.confirm(`Пополнить баланс ${normalizedEmail} на ${rubles(kopeks)}?`)) return
    const storageKey = `admin-topup:${JSON.stringify([userId, normalizedEmail, kopeks])}`
    let requestId: string
    try {
      requestId = sessionStorage.getItem(storageKey) || crypto.randomUUID()
      sessionStorage.setItem(storageKey, requestId)
    } catch {
      setTopupError("Не удалось сохранить идентификатор операции. Проверьте настройки браузера.")
      return
    }
    setTopupPending(true)
    try {
      const result = await accountRequest<{email: string; amount_kopeks: number}>("/admin/users/topup", token, {
        email: normalizedEmail, amount_kopeks: kopeks, request_id: requestId,
      })
      if (result?.email !== normalizedEmail || result?.amount_kopeks !== kopeks) {
        throw new Error("Получен неожиданный ответ сервера")
      }
      try {
        if (sessionStorage.getItem(storageKey) === requestId) sessionStorage.removeItem(storageKey)
      } catch { /* The stored ID still protects retries. */ }
      setRub("")
      setTopupSuccess(`Баланс ${normalizedEmail} пополнен на ${rubles(kopeks)}.`)
      setTick(n => n + 1)
      walletChanged()
    } catch (e) {
      setTopupError(e instanceof AccountError && e.status < 500 ? e.message :
        "Результат неизвестен. Повторите с теми же данными в этой вкладке, чтобы проверить операцию.")
    } finally {
      setTopupPending(false)
    }
  }
  const [providers, setProviders] = useState<Provider[] | null>(null), [balanceError, setBalanceError] = useState("")
  const [users, setUsers] = useState<{ total: number; users: User[] } | null>(null), [error, setError] = useState("")
  const [search, setSearch] = useState(""), [offset, setOffset] = useState(0), [tick, setTick] = useState(0)
  const [balanceTick, setBalanceTick] = useState(0), [loading, setLoading] = useState(true), [balanceLoading, setBalanceLoading] = useState(true)
  const [services, setServices] = useState<Service[] | null>(null), [serviceError, setServiceError] = useState(""), [serviceLoading, setServiceLoading] = useState(true), [changing, setChanging] = useState<Set<string>>(new Set())
  useEffect(() => {
    let alive = true
    setBalanceLoading(true); setBalanceError("")
    accountRequest<{ providers: Provider[] }>("/admin/provider-balances", token)
      .then(d => { if (alive) setProviders(d.providers) }).catch(e => { if (alive) setBalanceError(e.message) })
      .finally(() => { if (alive) setBalanceLoading(false) })
    return () => { alive = false }
  }, [token, balanceTick])
  const loadServices = useCallback(() => { setServiceLoading(true); setServiceError(""); accountRequest<{providers: Service[]}>("/admin/providers", token).then(data => setServices(data.providers)).catch(e => setServiceError(e instanceof Error ? e.message : "Не удалось загрузить ИИ-системы")).finally(() => setServiceLoading(false)) }, [token])
  useEffect(() => { loadServices() }, [loadServices])
  async function toggle(row: Service) { setChanging(current => new Set(current).add(row.service)); setServiceError(""); try { const result = await accountRequest<Service>(`/admin/providers/${row.service}`, token, {paused: !row.paused}, "PUT"); setServices(rows => rows?.map(item => item.service === row.service ? result : item) || null) } catch (e) { setServiceError(e instanceof Error ? e.message : "Не удалось изменить состояние") } finally { setChanging(current => { const next = new Set(current); next.delete(row.service); return next }) } }
  useEffect(() => {
    let alive = true
    const timer = setTimeout(() => {
      setLoading(true); setError(""); setUsers(null)
      accountRequest<{ total: number; users: User[] }>(`/admin/users?${new URLSearchParams({ search, offset: String(offset) })}`, token)
        .then(d => { if (alive) setUsers(d) }).catch(e => { if (alive) setError(e.message) })
        .finally(() => { if (alive) setLoading(false) })
    }, 180)
    return () => { alive = false; clearTimeout(timer) }
  }, [search, offset, tick, token])
  return <>
    <section className="cab-panel admin-overview"><div className="cab-section-head"><div><h2>ИИ-системы</h2><p>Пауза пропускает ещё не отправленные проверки. Уже отправленные ответы сохраняются и списываются один раз.</p></div></div>{serviceLoading && <p role="status">Загружаем ИИ-системы…</p>}{serviceError && <p role="alert">{serviceError} <button className="cc-button" onClick={loadServices}>Повторить</button></p>}{services && <div className="admin-provider-switches">{services.map(row => <label key={row.service}><span>{serviceName(row.service)}</span><input type="checkbox" role="switch" checked={!row.paused} disabled={changing.has(row.service)} onChange={() => void toggle(row)}/><b>{row.paused ? "Приостановлена" : "Включена"}</b></label>)}</div>}</section>
    <section className="cab-panel admin-overview"><div className="cab-section-head"><div><h2>Балансы поставщиков</h2><p>Остатки средств у поставщиков.</p></div><button className="cc-button" disabled={balanceLoading} onClick={() => setBalanceTick(n => n + 1)}>Обновить балансы</button></div>
      {balanceLoading && <p role="status">Получаем актуальные балансы…</p>}{balanceError && <p role="alert">{balanceError}</p>}
      {providers && <ul className="admin-balances">{providers.map(p => <li key={p.id}><div><h2>{p.name}</h2><strong>{balanceLabel(p.balance, p.currency)}</strong>
        {p.details.filter(d => d.label !== "Credits").map(d => <p key={d.label}>{d.label}: {balanceLabel(d.amount, d.currency || p.currency)}{d.expires_at && <small>До {new Date(d.expires_at).toLocaleString("ru-RU")}</small>}</p>)}
        {p.message && <p role="status">{p.message}</p>}<small>Проверено {new Date(p.checked_at).toLocaleString("ru-RU")}</small></div><a className="cc-button" href={p.topup_url} target="_blank" rel="noopener noreferrer">Открыть {p.name} <ExternalLink size={14} aria-hidden="true"/></a></li>)}</ul>}
    </section>
    <section className="cab-panel admin-overview"><div className="cab-section-head"><h2>Все пользователи{users && ` · ${users.total}`}</h2><button className="cc-button" disabled={loading} onClick={() => setTick(n => n + 1)}>Обновить список</button></div>
      <form onSubmit={topup}>
        <h3>Ручное пополнение</h3>
        <label>Email получателя<input inputMode="email" required maxLength={190} value={email} disabled={topupPending} onChange={e => setEmail(e.target.value)}/></label>
        <label>Сумма, ₽<input inputMode="decimal" required value={rub} disabled={topupPending} onChange={e => setRub(e.target.value)}/></label>
        <button className="cc-button primary" disabled={topupPending}>{topupPending ? "Пополняем…" : "Пополнить баланс"}</button>
        {topupError && <p role="alert">{topupError}</p>}
        {topupSuccess && <p role="status">{topupSuccess}</p>}
      </form>
      <label>Email пользователя<input value={search} onChange={e => { setSearch(e.target.value); setOffset(0) }}/></label>
      {loading && <p role="status">Загружаем пользователей…</p>}{error && <p role="alert">{error}</p>}
      {users && <><div className="admin-users-scroll" role="region" aria-label="Пользователи и балансы" tabIndex={0}><table><thead><tr><th>Email</th><th>Регистрация</th><th>Роль</th><th>Баланс</th><th>Резерв</th><th>Доступно</th></tr></thead><tbody>{users.users.map(u => <tr key={u.id}><td>{u.email}</td><td>{new Date(u.created_at).toLocaleDateString("ru-RU")}</td><td>{u.is_admin ? "Администратор" : "Пользователь"}</td><td>{rubles(u.wallet.balance_kopeks)}</td><td>{rubles(u.wallet.reserved_kopeks)}</td><td>{rubles(u.wallet.available_kopeks)}</td></tr>)}</tbody></table></div>
        {!users.users.length && <p>Пользователей по этому запросу нет.</p>}<div className="cc-actions"><button className="cc-button" disabled={loading || offset === 0} onClick={() => setOffset(n => Math.max(0, n - 50))}>Назад</button><button className="cc-button" disabled={loading || offset + 50 >= users.total} onClick={() => setOffset(n => n + 50)}>Далее</button></div></>}
    </section>
  </>
}
