import { useCallback, useEffect, useState, type FormEvent } from "react"
import { accountRequest } from "./account-api"
import { SCAN_SERVICES } from "./lib/scan-preferences"

type Promo = { code: string; scans: Record<string, number>; created_at: string; redemptions: number }
const emptyScans = () => Object.fromEntries(SCAN_SERVICES.map(s => [s.id, "0"]))

export function AdminPromos({ token }: { token: string }) {
  const [code, setCode] = useState("")
  const [scans, setScans] = useState<Record<string, string>>(emptyScans)
  const [page, setPage] = useState<{ total: number; promos: Promo[] } | null>(null)
  const [offset, setOffset] = useState(0), [tick, setTick] = useState(0)
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false)
  const [error, setError] = useState(""), [loadError, setLoadError] = useState(""), [message, setMessage] = useState("")
  const reload = useCallback(() => setTick(n => n + 1), [])
  useEffect(() => {
    let alive = true
    setLoading(true); setLoadError("")
    accountRequest<{ total: number; promos: Promo[] }>(`/admin/promos?offset=${offset}`, token)
      .then(data => { if (alive) setPage(data) }).catch(e => { if (alive) setLoadError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [token, offset, tick])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    const counts = Object.fromEntries(Object.entries(scans).map(([id, value]) => [id, Number(value)]))
    if (Object.values(scans).some(value => !/^\d+$/.test(value)) || Object.values(counts).some(value => value > 1_000_000)) { setError("Укажите целое число от 0 до 1 000 000 для каждой системы."); return }
    setBusy(true); setError(""); setMessage("")
    try {
      const promo = await accountRequest<Promo>("/admin/promos", token, { code, scans: counts })
      setMessage(`Промокод ${promo.code} создан.`); setCode(""); setScans(emptyScans()); setOffset(0); reload()
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось создать промокод") }
    finally { setBusy(false) }
  }
  return <section className="cab-panel admin-overview">
    <div className="cab-section-head"><div><h2>Промокоды</h2><p>Задайте бесплатные сканы по каждой системе. Ноль — без начисления. Каждый код применяется один раз на аккаунт, к пересчёту ответов он не относится.</p></div><button className="cc-button" disabled={loading} onClick={reload}>Обновить промокоды</button></div>
    <form onSubmit={submit} aria-busy={busy} className="admin-promo-form">
      <label>Новый промокод<input required disabled={busy} autoComplete="off" minLength={3} maxLength={64} pattern="[A-Za-z0-9_-]{3,64}" value={code} onChange={e => { setCode(e.target.value); setError(""); setMessage("") }} aria-describedby="admin-promo-hint" /></label>
      <small id="admin-promo-hint">3–64 латинские буквы, цифры, дефис или подчёркивание. Регистр букв не важен.</small>
      <fieldset disabled={busy}><legend>Количество бесплатных сканов</legend><div className="admin-promo-counts">{SCAN_SERVICES.map(s => <label key={s.id}>{s.label}<input type="number" min={0} max={1_000_000} step={1} required value={scans[s.id]} onChange={e => { setScans(values => ({ ...values, [s.id]: e.target.value })); setError("") }} /></label>)}</div></fieldset>
      <button className="cab-primary" disabled={busy || !code.trim()}>{busy ? "Создаём…" : "Создать промокод"}</button>
      {error && <p className="cab-payment-error" role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    </form>
    {loading && <p role="status">Загружаем промокоды…</p>}{loadError && <p role="alert">{loadError} <button className="cc-button" onClick={reload}>Повторить</button></p>}
    {page && !loadError && <><div className="admin-users-scroll" role="region" aria-label="Созданные промокоды" tabIndex={0}><table><thead><tr><th>Промокод</th>{SCAN_SERVICES.map(s => <th key={s.id}>{s.label}</th>)}<th>Активаций</th><th>Создан</th></tr></thead><tbody>{page.promos.map(p => <tr key={p.code}><td><b>{p.code}</b></td>{SCAN_SERVICES.map(s => <td key={s.id}>{p.scans[s.id] || 0}</td>)}<td>{p.redemptions}</td><td>{new Date(p.created_at).toLocaleDateString("ru-RU")}</td></tr>)}</tbody></table></div>{!page.promos.length && <p>Промокодов пока нет.</p>}<div className="cc-actions"><button className="cc-button" disabled={loading || offset === 0} onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущие промокоды</button><button className="cc-button" disabled={loading || offset + 50 >= page.total} onClick={() => setOffset(n => n + 50)}>Следующие промокоды</button></div></>}
  </section>
}
