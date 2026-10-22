export function AccountBalance({available, balance, reserved, admin}: {
  available: string; balance: string; reserved?: string; admin: boolean
}) {
  return <div className="cab-available">
    <span>{admin ? "Проверки" : "Доступно для проверок"}</span>
    <strong>{admin ? "Безлимитно" : available}</strong>
    <small>На балансе {balance}{reserved ? ` · В резерве ${reserved}` : ""}</small>
    {admin && <small>Проверки и пересчёт сохранённых ответов бесплатны.</small>}
  </div>
}
