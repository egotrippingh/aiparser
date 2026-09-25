export const ACCOUNT_API = (import.meta.env.VITE_ACCOUNT_API_URL || "").replace(/\/$/, "")

export async function accountRequest<T>(path: string, token?: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch(`${ACCOUNT_API}/api/v1${path}`, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || `Ошибка ${response.status}`)
  return data as T
}
