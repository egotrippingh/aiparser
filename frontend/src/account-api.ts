export const ACCOUNT_API = (import.meta.env.VITE_ACCOUNT_API_URL || "").replace(/\/$/, "")
import { capture } from "./telemetry"
import { publicError } from "./lib/public-error"

export const COOKIE_SESSION = "cookie-session"
export class AccountError extends Error {
  status: number
  constructor(message: string, status: number) { super(publicError(message)); this.status = status }
}

export async function accountDownload(path: string, token: string, filename: string) { try {
  const response = await fetch(`${ACCOUNT_API}/api/v1${path}`, { credentials: "include", headers: {
    "X-AI-Client": "browser", ...(token !== COOKIE_SESSION ? { Authorization: `Bearer ${token}` } : {}),
  } })
  if (!response.ok) { const data = await response.json().catch(() => ({})); throw new AccountError(typeof data.detail === "string" ? data.detail : "Не удалось выгрузить отчёт", response.status) }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
} catch (error) { capture(error, "account_download"); throw error }
}

export async function accountRequest<T>(path: string, token?: string, body?: unknown, method?: string): Promise<T> { try {
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
    const detail = data.detail
    throw new AccountError(Array.isArray(detail) ? detail.map((item: {msg?: string}) => item.msg || "Проверьте поля формы").join(". ") : typeof detail === "string" ? detail : `Ошибка ${response.status}`, response.status)
  }
  return data as T
} catch (error) { capture(error, "account_request"); throw error }
}
