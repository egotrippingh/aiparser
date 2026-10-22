import { useEffect, useState } from "react"
import { ExternalLink } from "lucide-react"
import { accountRequest } from "./account-api"
import "./admin-overview.css"

type Provider = { id: string; name: string; currency: string; balance: string | null; status: string; message: string | null; checked_at: string; topup_url: string; details: { label: string; amount: string; currency?: string; expires_at?: string }[] }
type User = { id: string; email: string; is_admin: boolean; created_at: string; wallet: { balance_kopeks: number; reserved_kopeks: number; available_kopeks: number } }
type CloudQueue = {
  checked_at: string
  runs: { queued: number; running: number; paused: number; lease_expired: number; oldest_created_at: string | null }
  provider_tasks: { submitting: number; submitted: number; uncertain: number; expired: number; rejected: number }
  provider_accounts: { service: string; active_tasks: number; cooldown_until: string | null; cooling_down: boolean }[]
}
export const balanceLabel = (value: string | null, currency: string) => value === null ? "Недоступен" : currency === "CREDITS" ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 6 }).format(Number(value)) + " credits" : new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: 4 }).format(Number(value))
const rubles = (value: number) => balanceLabel(String(value / 100), "RUB")
const serviceLabel: Record<string, string> = {
  google_aio: "Google AI Overview", yandex_neuro: "Яндекс Нейро", chatgpt: "ChatGPT",
  perplexity: "Perplexity", gemini: "Gemini",
}

export function AdminOverview({ token }: { token: string }) {
  const [providers, setProviders] = useState<Provider[] | null>(null), [balanceError, setBalanceError] = useState("")
  const [queue, setQueue] = useState<CloudQueue | null>(null), [queueError, setQueueError] = useState("")
  const [users, setUsers] = useState<{ total: number; users: User[] } | null>(null), [error, setError] = useState("")
  const [search, setSearch] = useState(""), [offset, setOffset] = useState(0), [tick, setTick] = useState(0)
  const [balanceTick, setBalanceTick] = useState(0), [queueTick, setQueueTick] = useState(0)
  const [loading, setLoading] = useState(true), [balanceLoading, setBalanceLoading] = useState(true), [queueLoading, setQueueLoading] = useState(true)
  useEffect(() => {
    let alive = true
    setBalanceLoading(true); setBalanceError("")
    accountRequest<{ providers: Provider[] }>("/admin/provider-balances", token)
      .then(d => { if (alive) setProviders(d.providers) }).catch(e => { if (alive) setBalanceError(e.message) })
      .finally(() => { if (alive) setBalanceLoading(false) })
    return () => { alive = false }
  }, [token, balanceTick])
  useEffect(() => {
    let alive = true
    setQueueLoading(true); setQueueError("")
    accountRequest<CloudQueue>("/admin/cloud-queue", token)
      .then(d => { if (alive) setQueue(d) }).catch(e => { if (alive) setQueueError(e.message) })
      .finally(() => { if (alive) setQueueLoading(false) })
    return () => { alive = false }
  }, [token, queueTick])
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
    <section className="cab-panel admin-overview"><div className="cab-section-head"><div><h1>Администрирование</h1><p>Пользователи, серверная очередь и остатки у поставщиков.</p></div><button className="cc-button" disabled={balanceLoading} onClick={() => setBalanceTick(n => n + 1)}>Обновить балансы</button></div>
      {balanceLoading && <p role="status">Получаем актуальные балансы…</p>}{balanceError && <p role="alert">{balanceError}</p>}
      {providers && <ul className="admin-balances">{providers.map(p => <li key={p.id}><div><h2>{p.name}</h2><strong>{balanceLabel(p.balance, p.currency)}</strong>
        {p.details.filter(d => d.label !== "Credits").map(d => <p key={d.label}>{d.label}: {balanceLabel(d.amount, d.currency || p.currency)}{d.expires_at && <small>До {new Date(d.expires_at).toLocaleString("ru-RU")}</small>}</p>)}
        {p.message && <p role="status">{p.message}</p>}<small>Проверено {new Date(p.checked_at).toLocaleString("ru-RU")}</small></div><a className="cc-button" href={p.topup_url} target="_blank" rel="noopener noreferrer">Открыть {p.name} <ExternalLink size={14} aria-hidden="true"/></a></li>)}</ul>}
    </section>
    <section className="cab-panel admin-overview" aria-labelledby="admin-queue-heading"><div className="cab-section-head"><div><h2 id="admin-queue-heading">Серверная очередь</h2><p>Глубина заданий и зависшие задачи сбора — без текстов ответов.</p></div><button className="cc-button" disabled={queueLoading} onClick={() => setQueueTick(n => n + 1)}>Обновить очередь</button></div>
      {queueLoading && <p role="status">Считаем очередь…</p>}{queueError && <p role="alert">{queueError}</p>}
      {queue && <><ul className="admin-queue-stats"><li><span>В очереди</span><strong>{queue.runs.queued}</strong></li><li><span>В работе</span><strong>{queue.runs.running}</strong></li><li><span>На паузе</span><strong>{queue.runs.paused}</strong></li><li><span>Просроченный lease</span><strong>{queue.runs.lease_expired}</strong></li></ul>
        <p className="admin-queue-meta">Самое старое открытое: {queue.runs.oldest_created_at ? new Date(queue.runs.oldest_created_at).toLocaleString("ru-RU") : "нет"} · задачи: submitting {queue.provider_tasks.submitting}, submitted {queue.provider_tasks.submitted}, uncertain {queue.provider_tasks.uncertain}, expired {queue.provider_tasks.expired}</p>
        <ul className="admin-queue-accounts">{queue.provider_accounts.map(a => <li key={a.service}><span>{serviceLabel[a.service] || a.service}</span><strong>{a.active_tasks} активн.</strong>{a.cooling_down ? <em>охлаждение до {a.cooldown_until ? new Date(a.cooldown_until).toLocaleString("ru-RU") : "—"}</em> : <em>готово</em>}</li>)}
        </ul><small>Проверено {new Date(queue.checked_at).toLocaleString("ru-RU")}</small></>}
    </section>
    <section className="cab-panel admin-overview"><div className="cab-section-head"><h2>Все пользователи{users && ` · ${users.total}`}</h2><button className="cc-button" disabled={loading} onClick={() => setTick(n => n + 1)}>Обновить список</button></div>
      <label>Email пользователя<input value={search} onChange={e => { setSearch(e.target.value); setOffset(0) }}/></label>
      {loading && <p role="status">Загружаем пользователей…</p>}{error && <p role="alert">{error}</p>}
      {users && <><div className="admin-users-scroll" role="region" aria-label="Пользователи и балансы" tabIndex={0}><table><thead><tr><th>Email</th><th>Регистрация</th><th>Роль</th><th>Баланс</th><th>Резерв</th><th>Доступно</th></tr></thead><tbody>{users.users.map(u => <tr key={u.id}><td>{u.email}</td><td>{new Date(u.created_at).toLocaleDateString("ru-RU")}</td><td>{u.is_admin ? "Администратор" : "Пользователь"}</td><td>{rubles(u.wallet.balance_kopeks)}</td><td>{rubles(u.wallet.reserved_kopeks)}</td><td>{rubles(u.wallet.available_kopeks)}</td></tr>)}</tbody></table></div>
        {!users.users.length && <p>Пользователей по этому запросу нет.</p>}<div className="cc-actions"><button className="cc-button" disabled={loading || offset === 0} onClick={() => setOffset(n => Math.max(0, n - 50))}>Назад</button><button className="cc-button" disabled={loading || offset + 50 >= users.total} onClick={() => setOffset(n => n + 50)}>Далее</button></div></>}
    </section>
  </>
}
