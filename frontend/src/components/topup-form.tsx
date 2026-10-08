import { useEffect, useState, type FormEvent } from "react"
import { CreditCard, LoaderCircle } from "lucide-react"
import { accountRequest } from "../account-api"
import { parseRubles, type Payment } from "../lib/payment"

type Method = "sbp" | "crypto"
type Options = { configured: boolean; testing: boolean; methods: { method: Method; min_kopeks: number; max_kopeks: number; available: boolean }[] }
const rubles = (value: number) => new Intl.NumberFormat("ru-RU").format(value / 100) + " ₽"

export function TopupForm({ token, minimum }: { token: string; minimum: number }) {
  const [amount, setAmount] = useState(String(minimum / 100))
  const [method, setMethod] = useState<Method>("sbp")
  const [options, setOptions] = useState<Options | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    setOptions(null); setError("")
    accountRequest<Options>("/payments/options", token).then(data => {
      if (!active) return
      setOptions(data)
      const first = data.methods.find(row => row.available)
      if (first) { setMethod(first.method); setAmount(String(first.min_kopeks / 100)) }
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [token, retry])
  const selected = options?.methods.find(row => row.method === method && row.available)
  const total = parseRubles(amount)
  const valid = !!selected && total !== null && total >= selected.min_kopeks && total <= selected.max_kopeks
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!valid || busy) return
    setBusy(true); setError("")
    try {
      const payment = await accountRequest<Payment>("/payments", token, { amount_kopeks: total, method })
      if (!payment.payment_url) throw new Error("Платёжная ссылка не получена")
      location.assign(payment.payment_url)
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось создать счёт"); setBusy(false) }
  }
  return <form id="topup" className="cab-panel cab-topup" onSubmit={submit} aria-busy={busy}>
    <span className="cab-kicker">ПОПОЛНЕНИЕ</span><h2>Добавить средства</h2>
    {options?.testing && <p className="cab-payment-note">Тестовый режим. Оплата имитируется и не меняет баланс.</p>}
    {options && !options.configured ? <p>Оплата пока настраивается. Напишите <a href="https://t.me/egotrippintg" target="_blank" rel="noreferrer">в поддержку</a>.</p> : <>
      <fieldset disabled={busy || !options}><legend>Способ оплаты</legend>{(["sbp", "crypto"] as Method[]).map(value => <label className="cab-payment-method" key={value}><input type="radio" name="payment-method" checked={method === value} disabled={!options?.methods.some(row => row.method === value && row.available)} onChange={() => {setMethod(value); setError("")}} />{value === "sbp" ? "СБП" : "Криптовалюта"}</label>)}</fieldset>
      <label htmlFor="topup-amount">Сумма пополнения, ₽<input id="topup-amount" type="text" inputMode="decimal" autoComplete="off" maxLength={9} value={amount} disabled={busy || !selected} aria-describedby="topup-hint" aria-invalid={!!selected && !valid} onChange={event => {setAmount(event.target.value); setError("")}} /></label>
      <div className="cab-amount-presets" aria-label="Готовые суммы">{[30000, 100000, 300000, 1000000].filter(value => selected && value >= selected.min_kopeks && value <= selected.max_kopeks).map(value => <button key={value} type="button" aria-pressed={total === value} disabled={busy} onClick={() => setAmount(String(value / 100))}>{rubles(value)}</button>)}</div>
      <small id="topup-hint">{selected ? `От ${rubles(selected.min_kopeks)} до ${rubles(selected.max_kopeks)}. На баланс зачисляется указанная сумма.` : options ? "Для этого проекта пока нет доступных способов оплаты." : "Получаем доступные способы оплаты…"}</small>
      {selected && !valid && <p className="cab-payment-error" role="status">Введите сумму в указанном диапазоне, не более двух знаков после запятой.</p>}
      <button className="cab-primary" disabled={!valid || busy}>{busy ? <LoaderCircle size={17} className="cab-payment-spinner" /> : <CreditCard size={17} />}{busy ? "Создаём счёт…" : "Перейти к оплате"}</button>
      <small>Coinso может добавить комиссию к оплате. Итоговая сумма показывается на его странице до подтверждения платежа; на баланс AIRate поступит выбранная вами сумма.</small>
      <small>{method === "crypto" ? "Валюту и сеть выберите на защищённой странице Coinso. Сумма счёта указана в рублях." : "Оплатите через приложение своего банка на странице Coinso."} Баланс обновится после подтверждения платежа.</small>
    </>}
    {error && <div className="cab-payment-error" role="alert">{error}{!options && <button type="button" className="cab-refresh" onClick={() => setRetry(value => value + 1)}>Повторить</button>}</div>}
  </form>
}
