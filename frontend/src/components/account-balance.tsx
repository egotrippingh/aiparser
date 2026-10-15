export function AccountBalance({available, balance, reserved, admin, paidRecompute}: {
  available: string; balance: string; reserved?: string; admin: boolean; paidRecompute: boolean
}) {
  return <div className="cab-available">
    <span>{admin ? "Доступный баланс" : "Доступно для проверок"}</span>
    <strong>{available}</strong>
    <small>На балансе {balance}{reserved ? ` · В резерве ${reserved}` : ""}</small>
    {admin && <small>Обычные проверки бесплатны.{paidRecompute && " Пересчёт сохранённых ответов — 0,80 ₽ за ответ."}</small>}
  </div>
}
