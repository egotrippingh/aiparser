import { useState, type FormEvent } from "react"
import { accountRequest } from "../account-api"

export function PasswordSettings({ token, hasPassword, email, resetEnabled, saved }: {
  token: string; hasPassword: boolean; email: string; resetEnabled: boolean; saved: (result: {token?: string}) => void
}) {
  const [current, setCurrent] = useState(""), [password, setPassword] = useState(""), [confirmation, setConfirmation] = useState("")
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [message, setMessage] = useState("")
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    if (password !== confirmation) { setError("Пароли не совпадают."); return }
    setBusy(true); setError(""); setMessage("")
    try {
      const result = await accountRequest<{token?: string}>("/auth/password", token, {password, current_password: current}, "PUT")
      setCurrent(""); setPassword(""); setConfirmation(""); saved(result)
      setMessage("Пароль сохранён. Теперь можно входить по email. Другие сеансы завершены.")
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось сохранить пароль") }
    finally { setBusy(false) }
  }
  return <section className="cab-panel cab-promo">
    <h2>{hasPassword ? "Пароль и восстановление доступа" : "Добавить пароль для входа"}</h2>
    <p>Вход по email: <b>{email}</b>. {hasPassword ? "Пароль пригодится, если вход через Яндекс недоступен." : "Создайте пароль, чтобы входить независимо от Яндекса."}</p>
    <form className="cab-password-form" onSubmit={submit} aria-busy={busy}>
      {hasPassword && <label>Текущий пароль<input type="password" autoComplete="current-password" required maxLength={256} disabled={busy} value={current} onChange={e => setCurrent(e.target.value)}/></label>}
      <label>Новый пароль<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} disabled={busy} value={password} onChange={e => setPassword(e.target.value)}/></label>
      <small>Не менее 12 символов. После сохранения другие сеансы входа завершатся.</small>
      <label>Повторите новый пароль<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} disabled={busy} value={confirmation} onChange={e => setConfirmation(e.target.value)}/></label>
      <button className="cab-primary" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить пароль"}</button>
      {error && <p role="alert" className="cab-payment-error">{error}</p>}{message && <p role="status">{message}</p>}
    </form>
    <p>{resetEnabled ? `Если забудете пароль, на странице входа можно запросить ссылку на ${email}.` : "Восстановление по почте станет доступно после подключения отправки писем. Сейчас сохраните пароль в надёжном месте."}</p>
  </section>
}
