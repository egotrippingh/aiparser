/** Формы данных, которые отдаёт FastAPI из app/api. */

export type Status =
  | "found"
  | "not_found"
  | "skipped"
  | "error"
  | "auth_required"
  | "captcha"
  | "limit_reached"

export interface ServiceMeta {
  id: string
  name: string
  short: string
  requires_auth: boolean
  /** Имя CSS-переменной, например «--c1». Приходит из app/services.py. */
  color: string
  note: string
  has_adapter: boolean
}

export interface Meta {
  version: string
  portable: boolean
  data_dir: string
  services: ServiceMeta[]
}

export interface Project {
  id: number
  name: string
  brand_name: string
  brand_aliases: string[]
  brand_domains: string[]
  region_code: string | null
  deep_check_depth: number
  notes: string | null
  /** Сканировать выбранные ИИ-системы одновременно. */
  parallel_scan: boolean
}

export interface Query {
  id: number
  text: string
  group_tag: string | null
  is_active: number | boolean
}

/* --- overview: даты в столбцах, запросы в строках ---------------------- */

export interface Cell {
  status: Status
  needs_review: boolean
  result_id: number
}

export interface OverviewRow {
  query_id: number
  text: string
  group_tag: string | null
  is_active: boolean
  /** дата → сервис → ячейка */
  cells: Record<string, Record<string, Cell>>
}

export interface CellStats {
  found: number
  checked: number
  pct: number | null
}

export interface ServiceSummary extends CellStats {
  id: string
  name: string
  delta: number | null
}

export interface OverviewSummary {
  date: string
  prev_date: string | null
  total: CellStats & { delta: number | null }
  by_service: ServiceSummary[]
  queries: number
  needs_review: number
  errors: number
  not_checked: number
}

/* --- календарь -------------------------------------------------------- */

/** Режимы календаря, как в Топвизоре. */
export type CalendarMode = "period" | "two" | "monthly" | "custom"

export interface ScanDate {
  date: string
  checks: number
  services: string[]
}

export interface Selection {
  mode: CalendarMode
  date_from: string | null
  date_to: string | null
  /** Сколько срезов подходило под выбор до обрезки до 30. */
  available: number
  truncated: boolean
  first_scan: string | null
  last_scan: string | null
}

export interface Overview {
  project: Project
  selection: Selection
  dates: string[]
  services: string[]
  rows: OverviewRow[]
  /** дата → («_all» | id сервиса) → статистика */
  stats: Record<string, Record<string, CellStats>>
  summary: OverviewSummary | null
}

/* --- внешние источники ------------------------------------------------- */

export interface ExternalCheck {
  date: string
  urls_total: number
  checked_now: number
  failed: number
  found_sites: number
  updated_results: number
  sites: { url: string; quote: string }[]
}

/* --- карточка запроса -------------------------------------------------- */

export interface HistoryPoint {
  scan_date: string
  status: Status
}

export interface QueryServiceDetail {
  status: Status
  mention_types: string[]
  confidence: number | null
  evidence_quote: string | null
  answer_text: string | null
  sources: string[]
  screenshot: string | null
  detected_by: string | null
  needs_review: boolean
  llm_model: string | null
  error_message: string | null
  history: HistoryPoint[]
}

export interface QueryDetail {
  query_id: number
  text: string
  by_service: Record<string, QueryServiceDetail>
}

/* --- скан -------------------------------------------------------------- */

export type ScanState = "running" | "paused" | "stopping" | "finished"

export interface ScanSnapshot {
  scan_id: number
  state: ScanState
  done: number
  total: number
  percent: number
  eta_sec: number | null
  current_service: string | null
  /** Все системы, которые идут прямо сейчас (при параллельном скане — несколько). */
  running_services?: string[]
}

export interface Resumable {
  scan_id: number
  scan_date: string
  expected: number
  conclusive: number
  remaining: number
}

/* --- настройки и браузер ---------------------------------------------- */

export interface SpeedProfile {
  delay_min_sec: number
  delay_max_sec: number
  break_every_n: number | null
  break_min_sec?: number
  break_max_sec?: number
}

export interface Settings {
  openrouter_model: string
  llm_mode: "smart" | "always" | "never"
  llm_confidence_threshold: string
  screenshot_retention_days: string
  speed_profile: string
  openrouter_api_key_masked: string
  openrouter_api_key_set: boolean
  secrets_encrypted: boolean
  speed_profiles: Record<string, SpeedProfile>
}

export interface ServiceAuth {
  cookie_state: "ok" | "expired" | "none" | string
  expires_at: number | null
  last_scan_state: string | null
  last_scan_at: string | null
  login_open: boolean
}

export interface BrowserStatus {
  installed: boolean
  installing: boolean
  install_error: string | null
  logins_in_progress: string[]
  services: Record<string, ServiceAuth>
}
