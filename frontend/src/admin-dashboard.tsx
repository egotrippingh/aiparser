import { useRef, useState, type FormEvent } from "react"
import { balanceLabel } from "./admin-overview"
import { adminRunStatuses, budgetBuffer, calibratedRate, collectors, defaultBuffer, forecastRates, rateFields, recommendedRefill, useAdminData } from "./admin-data"
import { CabinetSkeleton } from "./cabinet-loading"
import { addDays, dmy, monthTitle } from "./lib/dates"
import { serviceName } from "./service-mark"

import "./admin-dashboard.scss"

type ServiceForecast = {
  service: string
  currency: "USD" | "RUB"
  rate_minor: number | null
  observed_checks: number
  recent_checks: number
  remaining_checks: number
  next_month_checks: number
  remaining_manual_checks: number
  next_month_manual_checks: number
  backlog_checks: number
  observed_cost: number | null
  remaining_cost: number | null
  next_month_cost: number | null
  openrouter_rate_source: "service" | "pooled" | "scenario" | "unknown"
  openrouter_rate_usd: number | null
  openrouter_recent_usage_checks: number
}

type ProviderForecast = {
  provider: string
  currency: string
  remaining_cost: number | null
  next_month_cost: number | null
}

type ProviderBalance = {
  id: string
  name: string
  currency: string
  balance: string | null
  status: string
  message: string | null
  checked_at: string
  usage_monthly_usd?: string
  topup_url: string
  details?: { label: string; amount: string; expires_at?: string }[]
}

type Dashboard = {
  month: string
  next_month: string
  lookback_start: string
  lookback_end: string
  users: number
  active_projects: number
  scheduled_projects: number
  balance_kopeks: number
  reserved_kopeks: number
  available_kopeks: number
  free_scans: number
  reserved_free_scans: number
  paid_topups_kopeks: number
  check_charges_kopeks: number
  recompute_charges_kopeks: number
  api_cost_kopeks: number | null
  margin_kopeks: number | null
  current_month_api_cost_kopeks: number | null
  next_month_api_cost_kopeks: number | null
  current_month_scheduled_runs: number
  next_month_scheduled_runs: number
  backlog_runs: number
  runs_this_month: number
  recent_run_states: Record<string, number>
  services: ServiceForecast[]
  observed_recomputes: number
  recompute_cost_kopeks: number | null
  remaining_recomputes: number
  next_month_recomputes: number
  remaining_recompute_cost_kopeks: number | null
  next_month_recompute_cost_kopeks: number | null
  openrouter_recorded_cost_usd: number
  openrouter_usage_checks: number
  openrouter_missing_usage_checks: number
  providers: ProviderForecast[]
}

const ratesKey = "airate.admin.forecast-rates-v2"
const providerNames: Record<string, string> = { openrouter: "OpenRouter", scrapeless: "Scrapeless", xmlriver: "XMLRiver" }
const rubles = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB" })
const count = new Intl.NumberFormat("ru-RU")
const percent = new Intl.NumberFormat("ru-RU", { style: "percent", maximumFractionDigits: 1 })
const amount = (kopeks: number | null) => kopeks === null ? "Нет оценки" : rubles.format(kopeks / 100)
const providerAmount = (value: number | null, currency: string) => value === null ? "Нет оценки" : balanceLabel(String(value), currency)
const costRate = (value: number, currency: string) => new Intl.NumberFormat("ru-RU", {
  currency, style: "currency", maximumFractionDigits: currency === "USD" ? 6 : 4,
}).format(value)
const balanceTime = new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Moscow" })

function calendarMonth(period: string) {
  const [year, month] = period.split("-").map(Number)
  return monthTitle(year, month - 1)
}

function savedRates(): Record<string, string> {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(ratesKey) ?? "{}")
    if (typeof stored === "object" && stored !== null) {
      const values = Object.fromEntries(Object.entries(stored).filter(([id, value]) =>
        (id === "buffer" || rateFields.some(field => field.id === id)) && typeof value === "string")) as Record<string, string>
      if (forecastRates(values) && budgetBuffer(values.buffer) !== null) return values
    }
  } catch { /* Rates are optional when browser storage is unavailable. */ }
  return {}
}

function WorkloadCell({ checks, cost, currency }: { checks: number; cost: number | null; currency: string }) {
  return <td>{count.format(checks)}<small>{cost === null ? "Требуется ставка" : costRate(cost, currency)}</small></td>
}

function analysisBasis(row: ServiceForecast) {
  const name = serviceName(row.service)
  const checks = count.format(row.openrouter_recent_usage_checks)
  const rate = row.openrouter_rate_usd === null ? "" : `${costRate(row.openrouter_rate_usd, "USD")} · `
  switch (row.openrouter_rate_source) {
    case "service": return `${name} · ${rate}средняя по системе, проверок с данными ${checks}`
    case "pooled": return `${name} · ${rate}общая средняя, проверок с данными по системе ${checks}`
    case "scenario": return `${name} · ${rate}${rate ? "ручная ставка" : "ручная ставка, нужен курс"}`
    case "unknown": return `${name} · недостаточно данных, нужна ставка`
  }
}

export function AdminDashboard({ token }: { token: string }) {
  const settings = useRef<HTMLDetailsElement>(null)
  const [draft, setDraft] = useState(savedRates)
  const [rates, setRates] = useState(() => forecastRates(draft)?.toString() ?? "")
  const [buffer, setBuffer] = useState(() => budgetBuffer(draft.buffer) ?? defaultBuffer)
  const [refresh, setRefresh] = useState(0)
  const [rateError, setRateError] = useState("")
  const [balanceRefresh, setBalanceRefresh] = useState(0)
  const [billing, setBilling] = useState<Record<string, string>>({})
  const [billingMessage, setBillingMessage] = useState<{ text: string; error?: boolean }>()
  const { data, error, loading } = useAdminData<Dashboard>(
    `/admin/dashboard${rates ? `?${rates}` : ""}`, token, refresh, "Не удалось загрузить финансовую сводку.",
  )
  const { data: balances, error: balanceError, loading: balanceLoading } = useAdminData<{ providers: ProviderBalance[] }>(
    "/admin/provider-balances", token, balanceRefresh, "Не удалось загрузить балансы поставщиков.",
  )

  function applyRates(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const params = forecastRates(draft)
    if (!params) {
      setRateError("Укажите ставку от 0 до 10 000 в валюте поля. Для ставок в долларах допустимо шесть знаков после запятой, в рублях — четыре, для курса — два.")
      return
    }
    const nextBuffer = budgetBuffer(draft.buffer)
    if (nextBuffer === null) {
      setRateError("Укажите запас целым числом от 0 до 100%.")
      return
    }
    setRateError("")
    try { localStorage.setItem(ratesKey, JSON.stringify(draft)) } catch { /* Recalculation also works without storage. */ }
    setRates(params.toString())
    setBuffer(nextBuffer)
    setRefresh(n => n + 1)
  }

  function fillCollectionRates(collector: typeof collectors[number], checks: number) {
    const rate = calibratedRate(billing[collector.name] ?? "", checks, collector.decimals)
    if (rate === null) {
      setBillingMessage({text: `Укажите расходы за период в валюте поля. Средняя ставка должна быть не выше ${balanceLabel("10000", collector.currency)}.`, error: true})
      return
    }
    setRateError("")
    setDraft(current => ({ ...current, ...Object.fromEntries(collector.services.map(service => [service, rate])) }))
    setBillingMessage({text: `Подставлена ставка ${collector.name} — ${costRate(Number(rate), collector.currency)} за сбор. Можно уточнить её перед пересчётом.`})
  }

  function openSettings() {
    if (!settings.current) return
    settings.current.open = true
    settings.current.querySelector("summary")?.focus()
  }

  const charged = data ? data.check_charges_kopeks + data.recompute_charges_kopeks : 0
  const analysisBasisNotes = data?.services.filter(row =>
    row.backlog_checks + row.remaining_checks + row.remaining_manual_checks + row.next_month_checks + row.next_month_manual_checks > 0,
  ).map(analysisBasis) ?? []
  return <div className="admin-data" aria-busy={loading}>
    <section className="cab-panel admin-overview" aria-labelledby="admin-finance-heading">
      <div className="cab-section-head admin-data__heading">
        <div>
          <h2 id="admin-finance-heading">Финансовая сводка</h2>
          <p>{data ? `С начала месяца · ${calendarMonth(data.month)} · МСК` : "С начала месяца по московскому времени"}</p>
        </div>
        <button className="cc-button" disabled={loading} onClick={() => setRefresh(n => n + 1)}>Обновить</button>
      </div>
      {error && <p className="admin-data__error" role="alert">{error}</p>}
      {loading && <CabinetSkeleton label="Загружаем финансовую сводку…"/>}
      {data && !loading && <>
        <dl className="admin-data__figures admin-data__figures--summary">
          <div>
            <dt>Оплаченные пополнения</dt><dd>{amount(data.paid_topups_kopeks)}</dd>
            <dd className="admin-data__note">Поступления от реальных платежей</dd>
          </div>
          <div>
            <dt>Списания за услуги</dt><dd>{amount(charged)}</dd>
            <dd className="admin-data__note">Проверки {amount(data.check_charges_kopeks)} · пересчёты {amount(data.recompute_charges_kopeks)}</dd>
          </div>
          <div>
            <dt>Расходы API</dt><dd>{amount(data.api_cost_kopeks)}</dd>
            <dd className="admin-data__note">Данные OpenRouter и оценка по сохранённым результатам</dd>
          </div>
          <div>
            <dt>Расчётная маржа</dt>
            <dd className={data.margin_kopeks === null ? undefined : data.margin_kopeks < 0 ? "admin-data__loss" : "admin-data__gain"}>{amount(data.margin_kopeks)}</dd>
            <dd className="admin-data__note">{data.margin_kopeks !== null && charged > 0 ? `${percent.format(data.margin_kopeks / charged)} от списаний` : "Списания за услуги за вычетом расходов API"}</dd>
          </div>
        </dl>
        {data.api_cost_kopeks === null && <p className="admin-data__note">Для расчёта расходов и маржи заполните недостающие ставки и курс.</p>}
      </>}
    </section>
    {data && !loading && <>
      <section className="cab-panel admin-overview" aria-labelledby="admin-forecast-heading">
        <h2 id="admin-forecast-heading">Прогноз расходов на API</h2>
        <dl className="admin-data__figures admin-data__figures--forecast">
          <div>
            <dt>Текущий месяц · {calendarMonth(data.month)}</dt>
            <dd>{amount(data.current_month_api_cost_kopeks)}</dd>
            <dd className="admin-data__note">Оценка с начала месяца и прогноз до его конца · по расписанию {count.format(data.current_month_scheduled_runs)} · незавершённых запусков {count.format(data.backlog_runs)}</dd>
          </div>
          <div>
            <dt>Следующий месяц · {calendarMonth(data.next_month)}</dt>
            <dd>{amount(data.next_month_api_cost_kopeks)}</dd>
            <dd className="admin-data__note">Запусков по расписанию · {count.format(data.next_month_scheduled_runs)}</dd>
          </div>
        </dl>
        <div className="cab-section-head admin-data__heading admin-data__subheading">
          <div>
            <h3>Бюджет и пополнения по поставщикам</h3>
            <p>К пополнению — расходы до конца месяца с резервом {buffer}% за вычетом текущего остатка.</p>
          </div>
          <div className="cc-actions">
            <button className="cc-button" onClick={openSettings}>Настроить расчёт</button>
            <button className="cc-button" disabled={balanceLoading} onClick={() => setBalanceRefresh(n => n + 1)}>Обновить балансы</button>
          </div>
        </div>
        {balanceError && <p className="admin-data__error" role="alert">{balanceError}</p>}
        <div className="admin-users-scroll admin-data__scroll" role="region" aria-label="Прогноз по поставщикам" aria-busy={balanceLoading} tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th scope="col">Поставщик</th>
                <th scope="col">Текущий остаток</th>
                <th scope="col">Расходы до конца месяца</th>
                <th scope="col">Пополнить до конца месяца</th>
                <th scope="col">Расходы в следующем месяце</th>
              </tr>
            </thead>
            <tbody>{data.providers.map(provider => {
              const account = balances?.providers.find(row => row.id === provider.provider && row.currency === provider.currency)
              const live = !balanceLoading && account?.status === "ok" ? account.balance : null
              const subscription = account?.details?.find(item => item.label === "Остаток подписки" && Number(item.amount) > 0)
              const expiry = subscription?.expires_at ? Date.parse(subscription.expires_at) : NaN
              const uncertainBalance = subscription !== undefined &&
                (!Number.isFinite(expiry) || expiry < Date.parse(`${data.next_month}-01T00:00:00+03:00`))
              const refill = recommendedRefill(provider.remaining_cost, uncertainBalance ? null : live, buffer)
              return <tr key={provider.provider}>
                <th scope="row">
                  {account ? <a href={account.topup_url} target="_blank" rel="noopener noreferrer">{account.name}</a> : providerNames[provider.provider] ?? provider.provider}
                </th>
                <td>
                  {balanceLoading ? "Загружаем…" : balanceLabel(live, provider.currency)}
                  {live !== null && account?.checked_at && <small>{balanceTime.format(new Date(account.checked_at))} МСК</small>}
                  {account?.usage_monthly_usd && <small>Расход ключа за месяц (UTC) {balanceLabel(account.usage_monthly_usd, "USD")}</small>}
                  {live !== null && Number.isFinite(expiry) && <small>Подписка до {balanceTime.format(expiry)} МСК</small>}
                  {live === null && !balanceLoading && account?.message && <small>{account.message}</small>}
                </td>
                <td>{providerAmount(provider.remaining_cost, provider.currency)}</td>
                <td><strong>{providerAmount(refill, provider.currency)}</strong>
                  {uncertainBalance && <small>Уточните доступность кредитов подписки до конца месяца.</small>}
                </td>
                <td>{providerAmount(provider.next_month_cost, provider.currency)}</td>
              </tr>
            })}</tbody>
          </table>
        </div>
        <p className="admin-data__note">Сумма пополнения появляется, когда известны прогноз расходов и доступный остаток. Оценка бюджета следующего месяца приведена без учёта текущего остатка.</p>
        {analysisBasisNotes.length > 0 && <p className="admin-data__note">
          <strong>Ставки анализа OpenRouter за проверку.</strong> {analysisBasisNotes.join(". ")}.
        </p>}
        <h3 className="admin-data__subheading">Проверки и стоимость сбора</h3>
        <div className="admin-users-scroll admin-data__scroll" role="region" aria-label="Нагрузка и расходы по ИИ-системам" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th scope="col">ИИ-система</th>
                <th scope="col">Ставка за сбор</th>
                <th scope="col">С начала месяца</th>
                <th scope="col">До конца месяца</th>
                <th scope="col">Следующий месяц</th>
              </tr>
            </thead>
            <tbody>
              {data.services.map(row => <tr key={row.service}>
                <th scope="row">{serviceName(row.service)}</th>
                <td>{row.rate_minor === null ? "Не задана" : costRate(row.rate_minor / 100, row.currency)}</td>
                <WorkloadCell checks={row.observed_checks} cost={row.observed_cost} currency={row.currency}/>
                <WorkloadCell checks={row.backlog_checks + row.remaining_checks + row.remaining_manual_checks} cost={row.remaining_cost} currency={row.currency}/>
                <WorkloadCell checks={row.next_month_checks + row.next_month_manual_checks} cost={row.next_month_cost} currency={row.currency}/>
              </tr>)}
            </tbody>
          </table>
        </div>
        <p className="admin-data__note">Сохранённый расход OpenRouter по проверкам этого месяца: {providerAmount(data.openrouter_recorded_cost_usd, "USD")}. Данные есть по {count.format(data.openrouter_usage_checks)} проверкам, отсутствуют полностью или частично по {count.format(data.openrouter_missing_usage_checks)}. Биллинг ключа может включать незаписанные попытки и учитывать другую дату списания.</p>
        <p className="admin-data__note">Пересчёты с начала месяца · {count.format(data.observed_recomputes)} / {amount(data.recompute_cost_kopeks)}. До конца месяца · {count.format(data.remaining_recomputes)} / {amount(data.remaining_recompute_cost_kopeks)}. Следующий месяц · {count.format(data.next_month_recomputes)} / {amount(data.next_month_recompute_cost_kopeks)}.</p>
        <p className="admin-data__note">Прогноз учитывает очередь проверок, активные запросы в расписаниях и темп ручных проверок и пересчётов за 28 полных дней. В объём входят бесплатные проверки. Возможность запуска зависит от баланса и очереди.</p>
      </section>
      <section className="cab-panel admin-overview" aria-labelledby="admin-workload-heading">
        <h2 id="admin-workload-heading">Кошельки и нагрузка</h2>
        <dl className="admin-data__figures admin-data__figures--compact">
          <div><dt>Баланс пользователей</dt><dd>{amount(data.balance_kopeks)}</dd></div>
          <div><dt>Зарезервировано</dt><dd>{amount(data.reserved_kopeks)}</dd></div>
          <div><dt>Доступно</dt><dd>{amount(data.available_kopeks)}</dd></div>
          <div><dt>Промопроверки</dt><dd>{count.format(data.free_scans)}</dd><dd className="admin-data__note">В резерве {count.format(data.reserved_free_scans)}</dd></div>
          <div><dt>Пользователи</dt><dd>{count.format(data.users)}</dd></div>
          <div><dt>Активные проекты</dt><dd>{count.format(data.active_projects)}</dd><dd className="admin-data__note">С расписанием {count.format(data.scheduled_projects)}</dd></div>
        </dl>
        <p className="admin-data__note">
          Запуски за этот месяц · {count.format(data.runs_this_month)}
          {Object.entries(data.recent_run_states).filter(([, total]) => total > 0)
            .map(([state, total]) => ` · ${adminRunStatuses[state] ?? state} ${count.format(total)}`).join("")}
        </p>
      </section>
    </>}
    <details ref={settings} className="cab-panel admin-overview admin-data__rates">
      <summary>Настройки расчёта</summary>
      <p>Укажите среднюю цену сбора одного ответа с учётом повторов. Scrapeless учитывается в долларах, XMLRiver — в рублях. Курс применяется при пересчёте между валютами. Пустое поле означает, что ставка неизвестна. Для прогноза OpenRouter можно использовать средний расход по данным API или задать свою ставку.</p>
      <p className="admin-data__note">Оценка учитывает сохранённые данные OpenRouter и средние ставки. Комиссии, инфраструктура и налоги находятся за пределами расчёта. Настройки сохраняются в этом браузере.</p>
      <form onSubmit={applyRates}>
        <div className="admin-data__rate-fields">
          {rateFields.map(({ id, label }) => <label key={id}>{label}
            <input inputMode="decimal" autoComplete="off" maxLength={12} placeholder="Не задана" value={draft[id] ?? ""}
              onChange={event => { setRateError(""); setDraft(current => ({ ...current, [id]: event.target.value })) }}/>
          </label>)}
          <label>Резерв на пополнение · %
            <input inputMode="numeric" autoComplete="off" maxLength={3} placeholder={String(defaultBuffer)}
              aria-describedby="admin-budget-buffer" value={draft.buffer ?? ""}
              onChange={event => { setRateError(""); setDraft(current => ({ ...current, buffer: event.target.value })) }}/>
          </label>
        </div>
        <p className="admin-data__note" id="admin-budget-buffer">Резерв применяется к сумме на пополнение. Прогноз расходов рассчитывается по ставкам.</p>
        {rateError && <p className="admin-data__error" role="alert">{rateError}</p>}
        <button className="cc-button primary" disabled={loading}>{loading ? "Рассчитываем…" : "Пересчитать"}</button>
      </form>
      {data && !loading && <details className="admin-data__calibration">
        <summary>Подставить ставки по недавним расходам</summary>
        <p>Введите расходы именно на сбор с {dmy(data.lookback_start)} по {dmy(addDays(data.lookback_end, -1))} включительно по Москве. Расход за период делится на число сохранённых проверок. Одинаковая средняя ставка подставляется для всех ИИ-систем поставщика. Перед пересчётом её можно уточнить.</p>
        <div className="admin-data__rate-fields">
          {collectors.map(collector => {
            const checks = data.services.filter(row => collector.services.includes(row.service)).reduce((sum, row) => sum + row.recent_checks, 0)
            return <div key={collector.name}>
              <label>{collector.name} · расходы, {collector.currencyLabel}
                <input inputMode="decimal" autoComplete="off" maxLength={16} disabled={checks === 0} value={billing[collector.name] ?? ""}
                  onChange={event => { setBillingMessage(undefined); setBilling(current => ({ ...current, [collector.name]: event.target.value })) }}/>
              </label>
              <p className="admin-data__note">Проверок за период · {count.format(checks)}</p>
              <button className="cc-button" disabled={checks === 0} onClick={() => fillCollectionRates(collector, checks)}>Подставить ставку {collector.name}</button>
            </div>
          })}
        </div>
        {billingMessage && <p className={billingMessage.error ? "admin-data__error" : undefined} role={billingMessage.error ? "alert" : "status"}>{billingMessage.text}</p>}
      </details>}
    </details>
  </div>
}
