export const ACCOUNT_API = (import.meta.env.VITE_ACCOUNT_API_URL || "").replace(/\/$/, "")

export const COOKIE_SESSION = "cookie-session"

export async function accountDownload(path: string, token: string, filename: string) {
  const response = await fetch(`${ACCOUNT_API}/api/v1${path}`, { credentials: "include", headers: {
    "X-AI-Client": "browser", ...(token !== COOKIE_SESSION ? { Authorization: `Bearer ${token}` } : {}),
  } })
  if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(typeof data.detail === "string" ? data.detail : "Не удалось выгрузить отчёт") }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function accountRequest<T>(path: string, token?: string, body?: unknown, method?: string): Promise<T> {
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
    throw new Error(Array.isArray(detail) ? detail.map((item: {msg?: string}) => item.msg || "Проверьте поля формы").join(". ") : typeof detail === "string" ? detail : `Ошибка ${response.status}`)
  }
  return data as T
}
