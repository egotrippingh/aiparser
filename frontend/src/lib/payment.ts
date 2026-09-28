export type Payment = { id: string; amount_kopeks: number; method: string; status: string; test_mode: boolean; payment_url: string | null; created_at: string }
export function parseRubles(value: string): number | null {
  const normalized = value.trim().replace(",", ".")
  if (!/^\d{1,6}(\.\d{1,2})?$/.test(normalized)) return null
  const [rubles, cents = ""] = normalized.split(".")
  const total = Number(rubles) * 100 + Number(cents.padEnd(2, "0"))
  return total > 0 && total <= 10_000_000 ? total : null
}
export const paymentLabel = (status: string) => ({ paid: "Зачислено", pending: "Ожидает оплаты", failed: "Не оплачен", expired: "Счёт истёк", test_paid: "Тестовая оплата · без зачисления", test_rejected: "Тестовый счёт отключён" }[status] || "Обрабатывается")
