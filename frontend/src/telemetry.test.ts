import { afterEach, expect, test, vi } from "vitest"
import * as Sentry from "@sentry/react"
import { privacyTransport, sanitizeEvent } from "./telemetry"

afterEach(async () => { await Sentry.close(1000); vi.unstubAllGlobals() })

test("actual SDK serialization sends only a sanitized error and forbids IP inference", async () => {
  const bodies: string[] = []
  const fetcher: typeof fetch = async (_url, init) => { bodies.push(String(init?.body)); expect(init?.credentials).toBe("omit"); expect(init?.referrerPolicy).toBe("no-referrer"); return new Response("", { status: 200 }) }
  Sentry.init({ dsn: "https://public@example.invalid/1", defaultIntegrations: false,
    dataCollection: { userInfo: false }, sendClientReports: false, beforeSend: sanitizeEvent,
    transport: options => privacyTransport(options, fetcher) })
  Sentry.setUser({ email: "SEEDED-SECRET", ip_address: "SEEDED-SECRET" })
  Sentry.setExtra("prompt", "SEEDED-SECRET")
  const error = new TypeError("SEEDED-SECRET")
  error.stack = "TypeError: SEEDED-SECRET\n    at secret (https://example.invalid/assets/cabinet-ABC123.js?token=SEEDED-SECRET:12:8)"
  Sentry.captureException(error)
  await Sentry.flush(1000)
  expect(bodies).toHaveLength(1)
  expect(bodies[0]).not.toContain("SEEDED-SECRET")
  const lines = bodies[0].split("\n")
  expect(lines).toHaveLength(3)
  expect(JSON.parse(lines[1]).type).toBe("event")
  expect(JSON.parse(lines[2]).sdk.settings.infer_ip).toBe("never")
  expect(JSON.parse(lines[2]).exception.values[0].type).toBe("TypeError")
  const transport = Sentry.getClient()!.getTransport()!
  const event: Sentry.ErrorEvent = { type: undefined, event_id: "a".repeat(32), release: "SEEDED-SECRET", environment: "SEEDED-SECRET", exception: { values: [{ type: "SEEDED-SECRET", value: "SEEDED-SECRET", stacktrace: { frames: [{ filename: "https://host/assets/app-ABC.js?secret=SEEDED-SECRET", function: "SEEDED-SECRET", lineno: 12 }] } }] }, tags: { operation: "SEEDED-SECRET" } }
  await transport.send([{ event_id: "a".repeat(32), sent_at: "now", trace: { transaction: "SEEDED-SECRET" } }, [[{ type: "event" }, event]]])
  // The same transport gate rejects non-error envelopes independently of beforeSend.
  await transport.send([{ sent_at: "now" }, [[{ type: "session" }, { sid: "a".repeat(32), init: true, started: "now", timestamp: "now", status: "ok", errors: 0, attrs: { user_agent: "SEEDED-SECRET" } }]]])
  await Sentry.flush(1000)
  expect(bodies).toHaveLength(2)
  expect(bodies.join("")).not.toContain("SEEDED-SECRET")
  expect(JSON.parse(bodies[1].split("\n")[2]).exception.values[0].stacktrace.frames).toEqual([{ filename: "/assets/app-ABC.js", lineno: 12 }])
})

test("runtime config enables typed API errors, expected filtering and duplicate suppression", async () => {
  vi.resetModules()
  const bodies: string[] = []
  vi.stubGlobal("fetch", vi.fn(async (url, options) => {
    if (url === "/api/v1/telemetry") return Response.json({ dsn: "https://public@example.invalid/1", release: "2026.10.1.3", environment: "test" })
    if (String(url).includes("example.invalid")) { bodies.push(String(options?.body)); return new Response("", { status: 200 }) }
    return Response.json({ detail: "SEEDED-SECRET" }, { status: String(url).includes("unauthorized") ? 401 : 500 })
  }))
  const telemetry = await import("./telemetry")
  await telemetry.initTelemetry()
  const { api } = await import("./lib/api")
  const { accountDownload, accountRequest } = await import("./account-api")
  await expect(api.get("/unauthorized")).rejects.toMatchObject({ status: 401 })
  await expect(accountDownload("/unauthorized", "secret", "private.csv")).rejects.toMatchObject({ status: 401 })
  await expect(api.get("/error")).rejects.toMatchObject({ status: 500 })
  await expect(accountRequest("/error")).rejects.toMatchObject({ status: 500 })
  const error = new Error("SEEDED-SECRET")
  telemetry.rootOptions.onCaughtError(error)
  telemetry.capture(error, "react_uncaught")
  Sentry.captureException(Object.assign(new Error("SEEDED-SECRET"), { status: 401 }))
  Sentry.captureException(new DOMException("SEEDED-SECRET", "AbortError"))
  await Sentry.flush(1000)
  expect(bodies).toHaveLength(3)
  expect(bodies.join("")).not.toContain("SEEDED-SECRET")
})

test("missing, malformed and failed configuration leave rendering unblocked", async () => {
  for (const config of [{}, { dsn: "broken" }, null]) {
    vi.resetModules()
    vi.stubGlobal("fetch", vi.fn(async () => { if (config === null) throw new DOMException("timeout", "TimeoutError"); return Response.json(config) }))
    const telemetry = await import("./telemetry")
    await expect(telemetry.initTelemetry()).resolves.toBeUndefined()
    expect(Sentry.isEnabled()).toBeFalsy()
  }
})
