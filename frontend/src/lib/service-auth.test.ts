import { expect, it } from "vitest"
import { sessionLabel } from "./service-auth"
it("shows fresh login instead of yesterday's rejected session without claiming verified auth", () => {
  expect(sessionLabel({cookie_state:"ok",last_scan_state:"auth_required",last_scan_at:"2026-09-26T10:00:00",last_login_at:"2026-09-27T10:00:00"})).toBe("Сессия сохранена — готово к проверке")
})
it("does not hide a newer rejection or expiration", () => {
  expect(sessionLabel({cookie_state:"ok",last_scan_state:"auth_required",last_scan_at:"2026-09-27T11:00:00",last_login_at:"2026-09-27T10:00:00"})).toContain("запрашивал вход")
  expect(sessionLabel({cookie_state:"expired",last_scan_state:"ok"})).toContain("истекла")
})
it("distinguishes starting, opened, and failed launch", () => {
  const base={cookie_state:"ok",last_scan_state:null}
  expect(sessionLabel({...base,login_open:true,login_state:"starting"})).toBe("Открываем браузер…")
  expect(sessionLabel({...base,login_open:true,login_state:"open"})).toBe("Окно входа открыто")
  expect(sessionLabel({...base,login_state:"error"})).toBe("Не удалось открыть окно")
})
