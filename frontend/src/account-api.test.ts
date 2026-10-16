import { afterEach, expect, it, vi } from "vitest"
import { AccountError, COOKIE_SESSION, accountDownload, accountRequest, onSessionExpired } from "./account-api"

afterEach(() => vi.unstubAllGlobals())
const unauthorized = () => new Response(JSON.stringify({ detail: "Недействительная сессия" }), { status: 401 })

it("handles simultaneous session failures once while each request still rejects", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => unauthorized()))
  const expire = vi.fn(), unsubscribe = onSessionExpired(COOKIE_SESSION, expire)
  try {
    const results = await Promise.allSettled([
      accountRequest("/wallet", COOKIE_SESSION), accountRequest("/control/projects", COOKIE_SESSION),
      accountDownload("/report.xlsx", COOKIE_SESSION, "report.xlsx"),
    ])
    expect(results.every(result => result.status === "rejected" && result.reason instanceof AccountError)).toBe(true)
    expect(expire).toHaveBeenCalledTimes(1)
  } finally { unsubscribe() }
})

it("keeps login failures and forbidden requests out of session-expiry handling", async () => {
  const expire = vi.fn(), unsubscribe = onSessionExpired(COOKIE_SESSION, expire)
  try {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()))
    await expect(accountRequest("/auth/login", undefined, { email: "test@example.test", password: "wrong" })).rejects.toMatchObject({ status: 401 })
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 403 })))
    await expect(accountRequest("/admin", COOKIE_SESSION)).rejects.toMatchObject({ status: 403 })
    expect(expire).not.toHaveBeenCalled()
  } finally { unsubscribe() }
})

it("ignores a late 401 after a new login even when both sessions use cookies", async () => {
  let finish!: (response: Response) => void
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(resolve => { finish = resolve })))
  const oldExpiry = vi.fn(), unsubscribeOld = onSessionExpired(COOKIE_SESSION, oldExpiry)
  const pending = accountRequest("/wallet", COOKIE_SESSION)
  unsubscribeOld()
  const newExpiry = vi.fn(), unsubscribeNew = onSessionExpired(COOKIE_SESSION, newExpiry)
  try {
    finish(unauthorized())
    await expect(pending).rejects.toMatchObject({ status: 401 })
    expect(oldExpiry).not.toHaveBeenCalled()
    expect(newExpiry).not.toHaveBeenCalled()
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()))
    await expect(accountRequest("/wallet", COOKIE_SESSION)).rejects.toMatchObject({ status: 401 })
    expect(newExpiry).toHaveBeenCalledTimes(1)
  } finally { unsubscribeNew() }
})

it("does not invalidate a different bearer session", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => unauthorized()))
  const expire = vi.fn(), unsubscribe = onSessionExpired("new-token", expire)
  try {
    await expect(accountRequest("/wallet", "old-token")).rejects.toMatchObject({ status: 401 })
    expect(expire).not.toHaveBeenCalled()
  } finally { unsubscribe() }
})
