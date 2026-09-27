export type ServiceSession = {
  cookie_state: string
  last_scan_state: string | null
  last_scan_at?: string | null
  last_login_at?: string | null
  login_open?: boolean
  login_state?: string
  login_error?: string | null
}

export function sessionLabel(s?: ServiceSession): string {
  if (!s) return "Состояние ещё не получено"
  if (s.login_state === "starting") return "Открываем браузер…"
  if (s.login_open) return "Окно входа открыто"
  if (s.login_state === "error") return "Не удалось открыть окно"
  if (s.cookie_state === "expired") return "Сессия истекла — войдите снова"
  const freshLogin = !!s.last_login_at && (!s.last_scan_at || Date.parse(s.last_login_at) > Date.parse(s.last_scan_at))
  if (s.cookie_state === "ok" && freshLogin) return "Сессия сохранена — готово к проверке"
  if (s.last_scan_state === "auth_required") return s.cookie_state === "ok" ? "Сессия есть, но сервис запрашивал вход" : "Нужен вход"
  if (s.last_scan_state === "ok") return "Последняя проверка прошла"
  if (s.cookie_state === "ok") return "Сессия сохранена"
  return s.login_state === "closed" ? "Сессия не найдена — повторите вход" : "Вход ещё не выполнен"
}
