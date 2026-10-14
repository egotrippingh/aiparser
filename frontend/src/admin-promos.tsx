import { useCallback, useEffect, useState, type FormEvent } from "react"
import { accountRequest } from "./account-api"
import { SCAN_SERVICES } from "./lib/scan-preferences"

type Promo = { code: string; scans: Record<string, number>; created_at: string; redemptions: number;
  is_active: boolean; max_redemptions: number | null; expires_at: string | null; revision: number; status: string }
const emptyScans = () => Object.fromEntries(SCAN_SERVICES.map(s => [s.id, "0"]))
const statuses: Record<string, string> = {active: "Активен", inactive: "Отключён", expired: "Срок истёк", exhausted: "Лимит исчерпан"}
function localExpiry(value: string | null) {
  if (!value) return ""
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

export function AdminPromos({ token }: { token: string }) {
  const [code, setCode] = useState("")
  const [editing, setEditing] = useState<Promo | null>(null)
  const [active, setActive] = useState(true), [limit, setLimit] = useState(""), [expiry, setExpiry] = useState("")
  const [scans, setScans] = useState<Record<string, string>>(emptyScans)
  const [page, setPage] = useState<{ total: number; promos: Promo[] } | null>(null)
  const [offset, setOffset] = useState(0), [tick, setTick] = useState(0)
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false)
  const [error, setError] = useState(""), [loadError, setLoadError] = useState(""), [message, setMessage] = useState("")
  const reload = useCallback(() => setTick(n => n + 1), [])
  function clearForm() {
    setEditing(null); setCode(""); setScans(emptyScans()); setActive(true); setLimit(""); setExpiry(""); setError("")
  }
  function edit(promo: Promo) {
    setEditing(promo); setCode(promo.code); setScans(Object.fromEntries(Object.entries(promo.scans).map(([id, n]) => [id, String(n)])))
    setActive(promo.is_active); setLimit(promo.max_redemptions === null ? "" : String(promo.max_redemptions)); setExpiry(localExpiry(promo.expires_at)); setError(""); setMessage("")
  }
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
    if (limit && (!/^\d+$/.test(limit) || Number(limit) < Math.max(1, editing?.redemptions || 0) || Number(limit) > 1_000_000)) {setError("Укажите лимит от 1 до 1 000 000, не меньше числа выполненных активаций."); return}
    if (expiry && Number.isNaN(new Date(expiry).getTime())) {setError("Укажите корректный срок действия."); return}
    setBusy(true); setError(""); setMessage("")
    try {
      const conditions = {is_active: active, max_redemptions: limit ? Number(limit) : null, expires_at: expiry ? new Date(expiry).toISOString() : null}
      const promo = editing
        ? await accountRequest<Promo>(`/admin/promos/${encodeURIComponent(editing.code)}`, token, {...conditions, revision: editing.revision}, "PUT")
        : await accountRequest<Promo>("/admin/promos", token, { code, scans: counts, ...conditions })
      setMessage(`Промокод ${promo.code}: ${editing ? "условия сохранены" : "создан"}.`); clearForm(); if (!editing) setOffset(0); reload()
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось создать промокод") }
    finally { setBusy(false) }
  }
  return <section className="cab-panel admin-overview">
    <div className="cab-section-head"><div><h2>Промокоды</h2><p>Задайте бесплатные сканы по каждой системе. Ноль — без начисления. Каждый код применяется один раз на аккаунт, к пересчёту ответов он не относится.</p></div><button className="cc-button" disabled={loading} onClick={reload}>Обновить промокоды</button></div>
    <form onSubmit={submit} aria-busy={busy} className="admin-promo-form">
      <h3>{editing ? `Условия промокода ${editing.code}` : "Создать промокод"}</h3>
      <label>{editing ? "Промокод" : "Новый промокод"}<input required disabled={busy || !!editing} autoComplete="off" minLength={3} maxLength={64} pattern="[A-Za-z0-9_-]{3,64}" value={code} onChange={e => { setCode(e.target.value); setError(""); setMessage("") }} aria-describedby="admin-promo-hint" /></label>
      <small id="admin-promo-hint">3–64 латинские буквы, цифры, дефис или подчёркивание. Регистр букв не важен.</small>
      <fieldset disabled={busy || !!editing}><legend>Количество бесплатных сканов{editing ? " (не меняется после создания)" : ""}</legend><div className="admin-promo-counts">{SCAN_SERVICES.map(s => <label key={s.id}>{s.label}<input type="number" min={0} max={1_000_000} step={1} required value={scans[s.id]} onChange={e => { setScans(values => ({ ...values, [s.id]: e.target.value })); setError("") }} /></label>)}</div></fieldset>
      <fieldset disabled={busy}><legend>Условия активации</legend><div className="admin-promo-counts">
        <label>Состояние<select value={active ? "active" : "inactive"} onChange={e => setActive(e.target.value === "active")}><option value="active">Активен</option><option value="inactive">Отключён</option></select></label>
        <label>Лимит активаций<input type="number" min={Math.max(1, editing?.redemptions || 0)} max={1_000_000} step={1} placeholder="Без ограничения" value={limit} onChange={e => setLimit(e.target.value)}/><small>Общее число аккаунтов; пусто — без лимита.</small></label>
        <label>Действует до<input type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)}/><small>Ваше местное время. Пусто — бессрочно.</small></label>
      </div></fieldset>
      <p>Отключение и срок действия влияют на новые активации. Уже начисленные сканы сохраняются.</p>
      <div className="cc-actions"><button className="cab-primary" disabled={busy || !code.trim()}>{busy ? "Сохраняем…" : editing ? "Сохранить условия" : "Создать промокод"}</button>{editing && <button className="cc-button" type="button" disabled={busy} onClick={clearForm}>Отменить редактирование</button>}</div>
      {error && <p className="cab-payment-error" role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    </form>
    {loading && <p role="status">Загружаем промокоды…</p>}{loadError && <p role="alert">{loadError} <button className="cc-button" onClick={reload}>Повторить</button></p>}
    {page && !loadError && <><div className="admin-users-scroll" role="region" aria-label="Созданные промокоды" tabIndex={0}><table><thead><tr><th>Промокод</th>{SCAN_SERVICES.map(s => <th key={s.id}>{s.label}</th>)}<th>Активаций / лимит</th><th>Состояние</th><th>Действует до</th><th>Создан</th><th>Условия</th></tr></thead><tbody>{page.promos.map(p => <tr key={p.code}><td><b>{p.code}</b></td>{SCAN_SERVICES.map(s => <td key={s.id}>{p.scans[s.id] || 0}</td>)}<td>{p.redemptions} / {p.max_redemptions ?? "∞"}</td><td>{statuses[p.status] || p.status}</td><td>{p.expires_at ? new Date(p.expires_at).toLocaleString("ru-RU") : "Бессрочно"}</td><td>{new Date(p.created_at).toLocaleDateString("ru-RU")}</td><td><button className="cc-button" disabled={busy} onClick={() => edit(p)} aria-label={`Изменить условия ${p.code}`}>Изменить</button></td></tr>)}</tbody></table></div>{!page.promos.length && <p>Промокодов пока нет.</p>}<div className="cc-actions"><button className="cc-button" disabled={loading || offset === 0} onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущие промокоды</button><button className="cc-button" disabled={loading || offset + 50 >= page.total} onClick={() => setOffset(n => n + 50)}>Следующие промокоды</button></div></>}
  </section>
}
