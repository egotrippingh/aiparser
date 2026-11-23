import { CabinetSkeleton } from "../cabinet-loading"
import { useEffect, useState } from "react"
import { Eye, EyeOff } from "lucide-react"
import { AccountError, accountRequest } from "../account-api"

type KeyStatus = { suffix: string | null; created_at: string | null; revealable: boolean }

async function copyKey(key: Promise<string>) {
  if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
    // Safari needs the clipboard request to start during the click, before fetching the key.
    const text = key.then(value => new Blob([value], { type: "text/plain" }))
    // A denied clipboard request may never consume the item.
    void text.catch(() => {})
    await navigator.clipboard.write([new ClipboardItem({ "text/plain": text })])
  } else {
    const value = await key
    await navigator.clipboard.writeText(value)
  }
}

export function ApiKeySettings({ token }: { token: string }) {
  const [status, setStatus] = useState<KeyStatus | null>(null)
  const [key, setKey] = useState("")
  const [pending, setPending] = useState(true)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [loadAttempt, setLoadAttempt] = useState(0)

  useEffect(() => {
    let active = true
    accountRequest<KeyStatus>("/api-key", token).then(result => {
      if (active) setStatus(result)
    }).catch((e: Error) => {
      if (active) setError(e.message)
    }).finally(() => {
      if (active) setPending(false)
    })
    return () => { active = false }
  }, [token, loadAttempt])

  async function change(method: "PUT" | "DELETE") {
    if (pending || !status) return
    if (status.suffix && !window.confirm(method === "PUT"
      ? "Заменить API-ключ? Подключённые интеграции перестанут работать со старым ключом."
      : "Отозвать API-ключ? Подключённые интеграции потеряют доступ.")) return
    setPending(true); setError(""); setMessage(""); setKey("")
    try {
      const updated = await accountRequest<KeyStatus>("/api-key", token, { created_at: status.created_at }, method)
      setStatus({ suffix: updated.suffix, created_at: updated.created_at, revealable: updated.revealable })
      if (method === "DELETE") setMessage("API-ключ отозван.")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось изменить API-ключ")
      if (e instanceof AccountError && e.status === 409) {
        setStatus(null)
        setLoadAttempt(attempt => attempt + 1)
        return
      }
    }
    setPending(false)
  }

  async function toggleKey() {
    if (pending || !status?.revealable) return
    setError(""); setMessage("")
    if (key) {
      setKey("")
      return
    }
    setPending(true)
    const revealed = accountRequest<{ key: string }>("/api-key/reveal", token, { created_at: status.created_at })
      .then(result => result.key)
    const copied = copyKey(revealed).then(() => true, () => false)
    try {
      setKey(await revealed)
      setMessage(await copied ? "API-ключ скопирован." : "Не удалось скопировать ключ. Выделите его и скопируйте вручную.")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось показать API-ключ")
      if (e instanceof AccountError && (e.status === 409 || e.status === 404)) {
        setStatus(null)
        setLoadAttempt(attempt => attempt + 1)
        return
      }
    }
    setPending(false)
  }

  return <section className="cab-panel cab-api-key" aria-labelledby="api-key-heading">
    <h2 id="api-key-heading">REST API</h2>
    <p>Запускайте проверки и получайте ответы из своих интеграций. <a href="/docs/api/">Документация API</a></p>
    {!status && pending && <CabinetSkeleton label="Загружаем сведения о ключе…"/>}
    {status && pending && <p role="status">Обновляем сведения о ключе…</p>}
    {status?.suffix ? <>
      <div className="cab-api-key-row">
        <code id="api-key-value" data-sentry-mask>{key || ("*".repeat(12) + status.suffix)}</code>
        {status.revealable && <button type="button" className="btn" disabled={pending}
          aria-controls="api-key-value" aria-expanded={!!key} aria-label={key ? "Скрыть API-ключ" : "Показать и скопировать API-ключ"}
          title={key ? "Скрыть API-ключ" : "Показать и скопировать API-ключ"} onClick={() => void toggleKey()}>
          {key ? <EyeOff size={18} aria-hidden="true"/> : <Eye size={18} aria-hidden="true"/>}
        </button>}
      </div>
      {!status.revealable && <p className="cab-payment-note">Для этого ключа доступно только окончание. Чтобы показывать и копировать полный ключ, выпустите новый.</p>}
    </> : status && <p>API-ключ ещё не создан.</p>}
    {error && <p className="cab-payment-error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    <div className="cc-actions" aria-busy={pending}>
      {status ? <>
        <button className="btn" disabled={pending} onClick={() => void change("PUT")}>{status.suffix ? "Заменить ключ" : "Создать ключ"}</button>
        {status.suffix && <button className="btn danger" disabled={pending} onClick={() => void change("DELETE")}>Отозвать ключ</button>}
      </> : !pending && <button className="btn" onClick={() => { setPending(true); setError(""); setLoadAttempt(loadAttempt + 1) }}>Повторить</button>}
    </div>
  </section>
}
