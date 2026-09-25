export type ScanPreferences = {
  revision: number
  enabled: boolean
  local_time: string
  month_days: number[]
  browser_mode: "headless" | "headful"
  services: string[]
  speed_profile: "careful" | "balanced" | "fast"
}

export const MONTH_DAYS = Array.from({ length: 31 }, (_, index) => index + 1)
export const SCAN_SERVICES = [
  { id: "perplexity", label: "Perplexity" },
  { id: "chatgpt", label: "ChatGPT" },
  { id: "yandex_neuro", label: "Яндекс Нейро (скоро)", available: false },
  { id: "alice", label: "Алиса AI" },
  { id: "google_aio", label: "Google AI Overview" },
]

export const DEFAULT_SCAN_PREFERENCES: ScanPreferences = {
  revision: 0,
  enabled: false,
  local_time: "09:00",
  month_days: [1],
  browser_mode: "headless",
  services: ["perplexity", "chatgpt"],
  speed_profile: "balanced",
}
