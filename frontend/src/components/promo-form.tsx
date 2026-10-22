import { useState, type FormEvent } from "react"
import { accountRequest } from "../account-api"
import { SCAN_SERVICES } from "../lib/scan-preferences"

export type FreeScans = Record<string, { available: number; reserved: number }>

export function PromoForm({ token, freeScans, applied }: { token: string; freeScans?: FreeScans; applied: () => void }) {
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!code.trim() || busy) return
    setBusy(true); setError(""); setMessage("")
    try {
      const result = await accountRequest<{ code: string; already_redeemed: boolean; scans: Record<string, number> }>("/wallet/promo", token, { code })
      const grants = SCAN_SERVICES.filter(s => result.scans[s.id] > 0).map(s => `${s.label}: ${result.scans[s.id]}`).join("; ")
      setMessage(result.already_redeemed ? `Промокод ${result.code} уже применён к вашему аккаунту. Повторного начисления нет.` : `Промокод ${result.code} применён. ${grants ? `Начислены бесплатные сканы — ${grants}.` : "В этом промокоде нет бесплатных сканов."}`)
      setCode(""); applied()
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось применить промокод") }
    finally { setBusy(false) }
  }
  return <section className="cab-panel cab-promo">
    <h2>Промокод и бесплатные сканы</h2>
    <p>Один промокод можно применить один раз на аккаунт. Бесплатные сканы используются первыми и только в указанной системе. Промокод не применяется к пересчёту сохранённых ответов.</p>
    <form onSubmit={submit} aria-busy={busy} className="cab-promo-form">
      <label htmlFor="promo-code">Промокод<input id="promo-code" autoComplete="off" maxLength={64} disabled={busy} value={code} onChange={e => { setCode(e.target.value); setError(""); setMessage("") }} required /></label>
      <button className="cab-primary" disabled={busy || !code.trim()}>{busy ? "Применяем…" : "Применить промокод"}</button>
    </form>
    {error && <p className="cab-payment-error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {freeScans ? <dl className="cab-free-scans">{SCAN_SERVICES.map(s => <div key={s.id}><dt>{s.label}</dt><dd><b>{freeScans[s.id]?.available || 0}</b> доступно{(freeScans[s.id]?.reserved || 0) > 0 && ` · ${freeScans[s.id].reserved} в резерве`}</dd></div>)}</dl> : <p role="status">Обновляем остатки бесплатных сканов…</p>}
  </section>
}
