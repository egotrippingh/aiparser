import { SCAN_SERVICES } from "./lib/scan-preferences"
import { useEffect, useState } from "react"
import { accountRequest } from "./account-api"

type AdminResponse<T> = { path: string; token: string; refresh: number; data: T | null; error: string }

export function useAdminData<T>(path: string, token: string, refresh: number, fallbackError: string) {
  const [result, setResult] = useState<AdminResponse<T> | null>(null)
  useEffect(() => {
    let alive = true
    accountRequest<T>(path, token)
      .then(data => { if (alive) setResult({ path, token, refresh, data, error: "" }) })
      .catch(error => {
        if (alive) setResult({ path, token, refresh, data: null, error: error instanceof Error ? error.message : fallbackError })
      })
    return () => { alive = false }
  }, [path, token, refresh, fallbackError])
  const current = result?.path === path && result.token === token && result.refresh === refresh ? result : null
  return { data: current?.data ?? null, error: current?.error ?? "", loading: current === null }
}

export const adminRunStatuses: Record<string, string> = {
  queued: "В очереди",
  running: "В процессе",
  paused: "На паузе",
  done: "Завершён",
  failed: "Сбой",
  cancelled: "Остановлен",
  missed: "Пропущен",
}

export function runJournalLabel(run: { state: string; desired_state: string; phase: string; retry_at: string | null }) {
  const label = adminRunStatuses[run.state] ?? run.state
  if (!["queued", "running", "paused"].includes(run.state)) return label
  if (run.desired_state === "cancelled") return "Останавливается"
  if (run.desired_state === "paused") return adminRunStatuses.paused
  if (run.retry_at) return "Ожидает повтора"
  return run.state === "paused" && run.phase === "cloud" ? adminRunStatuses.running : label
}

export const collectors = [
  { name: "Scrapeless", currency: "USD", currencyLabel: "$", decimals: 6 as const, services: ["chatgpt", "gemini", "perplexity"] },
  { name: "XMLRiver", currency: "RUB", currencyLabel: "₽", decimals: 4 as const, services: ["google_aio", "yandex_neuro"] },
]

export const rateFields = [
  ...SCAN_SERVICES.map(({ id, label }) => {
    const collector = collectors.find(collector => collector.services.includes(id))
    return { id, label: `Сбор · ${label} · ${collector?.currencyLabel ?? "₽"}`, decimals: collector?.decimals ?? 4 as const }
  }),
  { id: "analysis", label: "OpenRouter · анализ проверки · ₽", decimals: 4 as const },
  { id: "recompute", label: "OpenRouter · пересчёт ответа · ₽", decimals: 4 as const },
  { id: "usd_rub_kopeks", label: "Курс доллара · ₽ за $1", decimals: 2 as const },
]

export const defaultBuffer = 15

export function budgetBuffer(value = "") {
  const input = value.trim()
  if (!input) return defaultBuffer
  return /^\d{1,3}$/.test(input) && Number(input) <= 100 ? Number(input) : null
}

function fixedUnits(value: string, decimals: 2 | 4 | 6): number | null {
  const match = /^(\d+)(?:[.,](\d{1,6}))?$/.exec(value.trim())
  if (!match || (match[2]?.length ?? 0) > decimals) return null
  const units = Number(match[1]) * 10 ** decimals + Number((match[2] ?? "").padEnd(decimals, "0"))
  return Number.isSafeInteger(units) ? units : null
}

export function forecastRates(values: Record<string, string>) {
  const params = new URLSearchParams()
  for (const { id, decimals } of rateFields) {
    const value = values[id]?.trim()
    if (!value) continue
    const units = fixedUnits(value, decimals)
    if (units === null) return null
    const minor = units / 10 ** (decimals - 2)
    if (minor > 1_000_000 || (id === "usd_rub_kopeks" && minor === 0)) return null
    params.set(id, String(minor))
  }
  return params
}

export function recommendedRefill(budget: number | null, balance: string | null, buffer: number): number | null {
  if (budget === null || !balance?.trim()) return null
  const cents = (budget * (1 + buffer / 100) - Number(balance)) * 100
  // Round up to the payment unit. Remove floating-point noise at exact cents.
  return Number.isFinite(cents) ? Math.max(0, Math.ceil(Number(cents.toFixed(8))) / 100) : null
}

export function calibratedRate(spend: string, checks: number, decimals: 4 | 6): string | null {
  const units = fixedUnits(spend, decimals)
  if (units === null || checks <= 0) return null
  const rate = Math.ceil(units / checks) / 10 ** decimals
  return rate <= 10_000 ? String(rate) : null
}
