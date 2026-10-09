export type ServiceSession = {
  cookie_state: string
  api_backend?: boolean
  api_configured?: boolean
  last_scan_state: string | null
  last_scan_at?: string | null
  last_login_at?: string | null
  login_open?: boolean
  login_state?: string
  login_error?: string | null
}

export function sessionReady(s?: ServiceSession): boolean {
  if (!s || s.cookie_state !== "ok" || s.login_open || ["starting", "error"].includes(s.login_state || "")) return false
  const freshLogin = !!s.last_login_at && (!s.last_scan_at || Date.parse(s.last_login_at) > Date.parse(s.last_scan_at))
  return s.last_scan_state !== "auth_required" || freshLogin
}

export function sessionLabel(s?: ServiceSession): string {
  if (!s) return "Состояние ещё не получено"
  if (s.api_backend) return s.api_configured
    ? s.last_scan_state === "ok" ? "API настроен · последний запрос успешен" : s.last_scan_state === "error" ? "API настроен · последний запрос завершился ошибкой" : "API настроен · запрос ещё не подтверждён"
    : "Укажите доступ XMLRiver на агенте"
  if (s.login_state === "starting") return "Открываем браузер…"
  if (s.login_open) return "Окно входа открыто"
  if (s.login_state === "error") return "Не удалось открыть окно"
  if (s.cookie_state === "unknown") return "Не удалось проверить сохранённую сессию"
  if (s.cookie_state === "expired") return "Сессия истекла — войдите снова"
  if (s.cookie_state !== "ok") return "Сессия не найдена — повторите вход"
  const freshLogin = !!s.last_login_at && (!s.last_scan_at || Date.parse(s.last_login_at) > Date.parse(s.last_scan_at))
  if (s.cookie_state === "ok" && freshLogin) return "Сохранённые cookies проверены — готово к проверке"
  if (s.last_scan_state === "auth_required") return s.cookie_state === "ok" ? "Сессия есть, но сервис запрашивал вход" : "Нужен вход"
  if (s.last_scan_state === "ok") return "Последняя проверка прошла"
  return "Сессия сохранена"
}
