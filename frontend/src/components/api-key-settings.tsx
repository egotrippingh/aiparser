import { CabinetSkeleton } from "../cabinet-loading"
import { useEffect, useState } from "react"
import { AccountError, accountRequest } from "../account-api"

type KeyStatus = { suffix: string | null; created_at: string | null }
type IssuedKey = KeyStatus & { key: string }

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
    setPending(true); setError(""); setMessage("")
    const expected = { created_at: status.created_at }
    try {
      if (method === "PUT") {
        const { key: newKey, ...metadata } = await accountRequest<IssuedKey>("/api-key", token, expected, method)
        setStatus(metadata)
        setKey(newKey)
      } else {
        setStatus(await accountRequest<KeyStatus>("/api-key", token, expected, method))
        setKey("")
        setMessage("API-ключ отозван.")
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось изменить API-ключ")
      if (e instanceof AccountError && e.status === 409) {
        setStatus(null)
        setKey("")
        setLoadAttempt(attempt => attempt + 1)
        return
      }
    }
    setPending(false)
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(key)
      setMessage("API-ключ скопирован.")
    } catch {
      setMessage("Не удалось скопировать ключ. Выделите его и скопируйте вручную.")
    }
  }

  return <section className="cab-panel cab-api-key" aria-labelledby="api-key-heading">
    <h2 id="api-key-heading">REST API</h2>
    <p>Запускайте проверки и получайте ответы из своих интеграций. <a href="/docs/api/">Документация API</a></p>
    {!status && pending && <CabinetSkeleton label="Загружаем сведения о ключе…"/>}
    {status && pending && <p role="status">Обновляем сведения о ключе…</p>}
    {status && <p>{status.suffix ? <>Ключ оканчивается на <code>{status.suffix}</code></> : "API-ключ ещё не создан."}</p>}
    {key && <div>
      <p className="cab-payment-note">Скопируйте ключ сейчас. Полностью он показывается только после выпуска.</p>
      <p><code style={{ overflowWrap: "anywhere" }}>{key}</code></p>
      <div className="cc-actions">
        <button className="btn" disabled={pending} onClick={copy}>Копировать ключ</button>
        <button className="btn" disabled={pending} onClick={() => { setKey(""); setMessage("") }}>Скрыть ключ</button>
      </div>
    </div>}
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
