export const ACCOUNT_API = (import.meta.env.VITE_ACCOUNT_API_URL || "").replace(/\/$/, "")
import { capture } from "./telemetry"
import { publicError } from "./lib/public-error"

export const COOKIE_SESSION = "cookie-session"
export class AccountError extends Error {
  status: number
  constructor(message: string, status: number) { super(publicError(message)); this.status = status }
}

type SessionExpiryListener = { token: string; expire: () => void }
const sessionExpiryListeners = new Set<SessionExpiryListener>()

export function onSessionExpired(token: string, expire: () => void) {
  const listener = { token, expire }
  if (token) sessionExpiryListeners.add(listener)
  return () => { sessionExpiryListeners.delete(listener) }
}

function notifySessionExpired(status: number, listeners: SessionExpiryListener[]) {
  if (status !== 401) return
  for (const listener of listeners) {
    // One owner handles concurrent failures; removed listeners also reject stale responses.
    if (sessionExpiryListeners.delete(listener)) listener.expire()
  }
}

export async function accountDownload(path: string, token: string, filename: string) { try {
  const listeners = [...sessionExpiryListeners].filter(listener => listener.token === token)
  const response = await fetch(`${ACCOUNT_API}/api/v1${path}`, { credentials: "include", headers: {
    "X-AI-Client": "browser", ...(token !== COOKIE_SESSION ? { Authorization: `Bearer ${token}` } : {}),
  } })
  if (!response.ok) { const data = await response.json().catch(() => ({})); notifySessionExpired(response.status, listeners); throw new AccountError(typeof data.detail === "string" ? data.detail : "Не удалось выгрузить отчёт", response.status) }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
} catch (error) { capture(error, "account_download"); throw error }
}

export async function accountRequest<T>(path: string, token?: string, body?: unknown, method?: string): Promise<T> { try {
  const listeners = [...sessionExpiryListeners].filter(listener => listener.token === token)
  const response = await fetch(`${ACCOUNT_API}/api/v1${path}`, {
    method: method || (body === undefined ? "GET" : "POST"),
    credentials: "include",
    headers: {
      "X-AI-Client": "browser",
      ...(token && token !== COOKIE_SESSION ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    notifySessionExpired(response.status, listeners)
    const detail = data.detail
    throw new AccountError(Array.isArray(detail) ? detail.map((item: {msg?: string}) => item.msg || "Проверьте поля формы").join(". ") : typeof detail === "string" ? detail : `Ошибка ${response.status}`, response.status)
  }
  return data as T
} catch (error) { capture(error, "account_request"); throw error }
}
