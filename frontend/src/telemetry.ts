import * as Sentry from "@sentry/react"

type Config = { dsn?: string; release?: string; environment?: string }
let ready = false
const operations = new Set(["account_request", "account_download", "agent_api", "react_uncaught", "react_caught", "react_recoverable", "local_api", "uncaught"])
const sent = new WeakSet<object>()
const validRelease = (value: unknown) => typeof value === "string" && (value === "local" || /^(?:[0-9]+\.){3}[0-9]+$|^[a-f0-9]{40}$/.test(value))
const validEnvironment = (value: unknown) => typeof value === "string" && ["development", "test", "production"].includes(value)

function expected(error: unknown) {
  return typeof error === "object" && error !== null &&
    (("status" in error && [401, 402, 403, 409, 422, 429].includes(Number(error.status))) ||
      (error instanceof DOMException && error.name === "AbortError"))
}

function safeFrame(frame: Sentry.StackFrame): Sentry.StackFrame | null {
  const raw = typeof frame.filename === "string" ? frame.filename : ""
  const filename = raw.replace(/^https?:\/\/[^/]+\//, "/").replace(/[?#].*$/, "")
  if (!/^\/?(?:assets\/[A-Za-z0-9_-]+\.js|src\/[A-Za-z0-9_/-]+\.(?:ts|tsx|js))$/.test(filename) || filename.includes("..")) return null
  return { filename, lineno: Number.isInteger(frame.lineno) ? frame.lineno : undefined, colno: Number.isInteger(frame.colno) ? frame.colno : undefined }
}

export function sanitizeEvent(event: Sentry.ErrorEvent): Sentry.ErrorEvent | null {
  const value = event.exception?.values?.[0]
  if (!value) return null
  return { type: undefined, event_id: /^[a-f0-9]{32}$/.test(event.event_id || "") ? event.event_id : undefined,
    platform: "javascript", level: "error",
    exception: { values: [{ type: value.type === "TypeError" || value.type === "RangeError" ? value.type : "Error", stacktrace: { frames: (value.stacktrace?.frames || []).map(safeFrame).filter((frame): frame is Sentry.StackFrame => frame !== null) } }] },
    release: validRelease(event.release) ? event.release : undefined,
    environment: validEnvironment(event.environment) ? event.environment : undefined,
    tags: { component: "browser", operation: typeof event.tags?.operation === "string" && operations.has(event.tags.operation) ? event.tags.operation : "uncaught" },
    sdk: { settings: { infer_ip: "never" } },
  }
}

// Gate the final envelope too: the SDK can append data after beforeSend.
export function privacyTransport(options: Parameters<typeof Sentry.makeFetchTransport>[0], nativeFetch?: typeof fetch) {
  const transport = Sentry.makeFetchTransport({ ...options, fetchOptions: { referrerPolicy: "no-referrer", credentials: "omit" } }, nativeFetch)
  return { flush: transport.flush, send(envelope: Parameters<typeof transport.send>[0]) {
    const items: Array<[{ type: "event" }, Sentry.ErrorEvent]> = []
    let eventId: string | undefined
    for (const [header, payload] of envelope[1]) {
      if (header.type !== "event" || typeof payload !== "object" || payload === null) continue
      const event = sanitizeEvent(payload as Sentry.ErrorEvent)
      if (event) { eventId = event.event_id; items.push([{ type: "event" }, event]) }
    }
    return items.length && eventId ? transport.send([{ event_id: eventId, sent_at: new Date().toISOString() }, items]) : Promise.resolve({})
  } }
}

export async function initTelemetry() {
  if (ready) return
  try {
    const response = await fetch("/api/v1/telemetry", { cache: "no-store", signal: AbortSignal.timeout(1500) })
    const config = await response.json() as Config
    if (!response.ok || typeof config.dsn !== "string" || !/^https:\/\/[A-Za-z0-9]+@[A-Za-z0-9.-]+\/\d+$/.test(config.dsn)) return
    Sentry.init({ dsn: config.dsn, release: validRelease(config.release) ? config.release : undefined,
      environment: validEnvironment(config.environment) ? config.environment : undefined,
      tracesSampleRate: 0, defaultIntegrations: false,
      integrations: [Sentry.globalHandlersIntegration()], sendClientReports: false,
      dataCollection: { userInfo: false, cookies: false, httpHeaders: false, httpBodies: [], urlQueryParams: false,
        graphQL: { document: false, variables: false }, genAI: { inputs: false, outputs: false },
        databaseQueryData: false, queues: false, stackFrameVariables: false, frameContextLines: 0 },
      transport: privacyTransport,
      beforeSend: (event, hint) => expected(hint.originalException) ? null : sanitizeEvent(event),
    })
    ready = true
  } catch { /* telemetry must not affect the page */ }
}

export function capture(error: unknown, operation: string) {
  if (!ready || !operations.has(operation) || expected(error)) return
  if (typeof error === "object" && error) { if (sent.has(error)) return; sent.add(error) }
  try { Sentry.withScope(scope => { scope.setTag("operation", operation); Sentry.captureException(error) }) } catch { /* collector failure is nonfatal */ }
}

export const rootOptions = { onUncaughtError: (error: unknown) => capture(error, "react_uncaught"), onCaughtError: (error: unknown) => capture(error, "react_caught"), onRecoverableError: (error: unknown) => capture(error, "react_recoverable") }
