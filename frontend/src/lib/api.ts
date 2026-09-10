/** Тонкая обёртка над fetch: всё общение с сервером идёт отсюда.
 *
 * Сервер локальный и без авторизации, поэтому здесь нет ни токенов, ни
 * повторов — единственная забота обёртки в том, чтобы вытащить из ответа
 * FastAPI поле `detail` и показать пользователю человеческую причину сбоя,
 * а не «HTTP 500».
 */

async function call<T>(path: string, method: string, body?: unknown): Promise<T> {
  const opts: RequestInit = { method, headers: {} }
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" }
    opts.body = JSON.stringify(body)
  }

  const resp = await fetch(path, opts)
  if (!resp.ok) {
    let msg = resp.statusText
    try {
      const j = await resp.json()
      msg = j.detail || msg
    } catch {
      /* тело не json — оставляем statusText */
    }
    throw new Error(msg || `HTTP ${resp.status}`)
  }
  if (resp.status === 204) return null as T
  const ct = resp.headers.get("content-type") || ""
  return (ct.includes("application/json") ? resp.json() : resp.text()) as Promise<T>
}

export const api = {
  get: <T>(path: string) => call<T>(path, "GET"),
  post: <T>(path: string, body?: unknown) => call<T>(path, "POST", body),
  patch: <T>(path: string, body?: unknown) => call<T>(path, "PATCH", body),
  put: <T>(path: string, body?: unknown) => call<T>(path, "PUT", body),
  del: <T>(path: string) => call<T>(path, "DELETE"),

  async upload<T>(path: string, file: File, query?: Record<string, string>): Promise<T> {
    const fd = new FormData()
    fd.append("file", file)
    const qs = query ? "?" + new URLSearchParams(query) : ""
    const resp = await fetch(path + qs, { method: "POST", body: fd })
    if (!resp.ok) {
      const j = await resp.json().catch(() => ({}) as { detail?: string })
      throw new Error(j.detail || resp.statusText)
    }
    return resp.json() as Promise<T>
  },
}

export function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
