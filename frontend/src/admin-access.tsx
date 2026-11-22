import { useCallback, useEffect, useState, type FormEvent } from "react"
import { accountRequest } from "./account-api"
import { CabinetSkeleton } from "./cabinet-loading"

type Entry = { id: number; cidr: string; label: string | null; created_at: string; created_by: string | null }
type Payload = { client_ip: string; env: string[]; entries: Entry[] }

export function AdminAccess({ token }: { token: string }) {
  const [page, setPage] = useState<Payload | null>(null)
  const [cidr, setCidr] = useState("")
  const [label, setLabel] = useState("")
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)
  const [error, setError] = useState("")
  const [loadError, setLoadError] = useState("")
  const [message, setMessage] = useState("")
  const reload = useCallback(() => setTick(n => n + 1), [])

  useEffect(() => {
    let alive = true
    setLoading(true)
    setLoadError("")
    accountRequest<Payload>("/admin/allowed-ips", token)
      .then(data => { if (alive) setPage(data) })
      .catch(e => { if (alive) setLoadError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [token, tick])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError("")
    setMessage("")
    try {
      const entry = await accountRequest<Entry>("/admin/allowed-ips", token, {
        cidr: cidr.trim(),
        label: label.trim() || null,
      })
      setMessage(`Добавлен адрес ${entry.cidr}.`)
      setCidr("")
      setLabel("")
      reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось добавить адрес")
    } finally {
      setBusy(false)
    }
  }

  async function remove(entry: Entry) {
    if (busy) return
    setBusy(true)
    setError("")
    setMessage("")
    try {
      await accountRequest(`/admin/allowed-ips/${entry.id}`, token, undefined, "DELETE")
      setMessage(`Удалён адрес ${entry.cidr}.`)
      reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось удалить адрес")
    } finally {
      setBusy(false)
    }
  }

  return <section className="cab-panel admin-overview">
    <div className="cab-section-head">
      <div>
        <h2>Разрешённые IP</h2>
        <p>Список проверяется только при входе в админку. Уже открытая сессия продолжит работать при смене VPN.</p>
      </div>
      <button className="cc-button" disabled={loading} onClick={reload}>Обновить</button>
    </div>
    {loading && <CabinetSkeleton label="Загружаем список IP…"/>}
    {loadError && <p role="alert">{loadError} <button className="cc-button" onClick={reload}>Повторить</button></p>}
    {page && !loadError && <>
      <p>Ваш текущий IP: <b>{page.client_ip || "не определён"}</b></p>
      {!!page.env.length && <div className="admin-access-env">
        <h3>Из переменной окружения</h3>
        <ul>{page.env.map(item => <li key={item}><code>{item}</code></li>)}</ul>
        <p>Эти адреса задаются через <code>ADMIN_ALLOWED_IPS</code> и здесь не удаляются.</p>
      </div>}
      <form onSubmit={submit} aria-busy={busy} className="admin-access-form">
        <h3>Добавить адрес</h3>
        <label>IP или CIDR
          <input required disabled={busy} autoComplete="off" maxLength={64} value={cidr}
            placeholder={page.client_ip || "203.0.113.10"}
            onChange={e => { setCidr(e.target.value); setError(""); setMessage("") }}/>
        </label>
        <label>Подпись
          <input disabled={busy} autoComplete="off" maxLength={100} value={label}
            placeholder="Опционально"
            onChange={e => { setLabel(e.target.value); setError("") }}/>
        </label>
        <div className="cc-actions">
          <button className="cab-primary" disabled={busy || !cidr.trim()}>{busy ? "Сохраняем…" : "Добавить"}</button>
          {page.client_ip && <button className="cc-button" type="button" disabled={busy}
            onClick={() => { setCidr(page.client_ip); setError(""); setMessage("") }}>Подставить мой IP</button>}
        </div>
        {error && <p className="cab-payment-error" role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
      </form>
      <div className="admin-users-scroll" role="region" aria-label="Разрешённые IP" tabIndex={0}>
        <table>
          <thead><tr><th>Адрес</th><th>Подпись</th><th>Добавлен</th><th></th></tr></thead>
          <tbody>
            {page.entries.map(entry => <tr key={entry.id}>
              <td><code>{entry.cidr}</code></td>
              <td>{entry.label || "—"}</td>
              <td>{new Date(entry.created_at).toLocaleString("ru-RU")}</td>
              <td><button className="cc-button" disabled={busy} onClick={() => void remove(entry)}
                aria-label={`Удалить ${entry.cidr}`}>Удалить</button></td>
            </tr>)}
          </tbody>
        </table>
      </div>
      {!page.entries.length && <p>В базе пока нет дополнительных адресов. Для первого входа задайте <code>ADMIN_ALLOWED_IPS</code>.</p>}
    </>}
  </section>
}
