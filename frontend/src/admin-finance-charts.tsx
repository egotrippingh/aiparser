import { useRef, useState, type ReactNode } from "react"
import { CalendarDays, ChevronLeft, ChevronRight, X } from "lucide-react"
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { useAdminData } from "./admin-data"
import {
  defaultFinancePeriod,
  financePresetRange,
  financeRangeLabel,
  isValidFinanceRange,
  matchFinancePreset,
  moscowToday,
  seriesQueryPath,
  shortFinanceDate,
  type FinancePeriod,
  type FinancePresetId,
} from "./admin-finance-period"
import { CabinetSkeleton } from "./cabinet-loading"
import { iso, monthTitle, parse } from "./lib/dates"

type SeriesPoint = {
  bucket: string
  revenue_kopeks: number
  charges_kopeks: number
  api_cost_kopeks: number | null
  api_cost_complete: boolean
  margin_kopeks: number | null
  cloud_results: number
  queries_distinct: number
  new_users: number
}

type SeriesResponse = {
  from: string
  to: string
  granularity: "day" | "week"
  timezone: string
  points: SeriesPoint[]
  totals?: Partial<SeriesPoint>
}

const rubles = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 })
const counts = new Intl.NumberFormat("ru-RU")
const money = (kopeks: number | null | undefined) => kopeks == null ? "—" : rubles.format(kopeks / 100)
const moneyAxis = (kopeks: number) => rubles.format(kopeks / 100)
const PRESETS: { id: Exclude<FinancePresetId, "custom">; label: string }[] = [
  { id: "7", label: "7 дней" },
  { id: "30", label: "30 дней" },
  { id: "90", label: "90 дней" },
  { id: "month", label: "Этот месяц" },
]

const chartStroke = {
  grid: "color-mix(in srgb, var(--air-line) 85%, transparent)",
  muted: "var(--air-muted)",
  revenue: "var(--air-accent)",
  charges: "var(--info)",
  margin: "var(--ok)",
  checks: "var(--air-accent)",
  queries: "var(--info)",
  users: "var(--air-accent)",
  cumulative: "var(--ok)",
}

function tipMoney(label: string, value: number | null | undefined, note?: string) {
  return <div key={label}><span>{label}</span><strong>{money(value)}{note ? ` · ${note}` : ""}</strong></div>
}

function tipCount(label: string, value: number) {
  return <div key={label}><span>{label}</span><strong>{counts.format(value)}</strong></div>
}

function ChartTip({ title, children }: { title: string; children: ReactNode }) {
  return <div className="admin-finance__tip"><p>{title}</p>{children}</div>
}

function emptySeries(points: SeriesPoint[] | undefined) {
  if (!points?.length) return true
  return points.every(point =>
    !point.revenue_kopeks && !point.charges_kopeks && !(point.margin_kopeks ?? 0) &&
    !point.cloud_results && !point.queries_distinct && !point.new_users)
}

function AdminPeriodCalendar({ period, onChange }: {
  period: FinancePeriod
  onChange: (next: FinancePeriod) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [start, setStart] = useState(period.from)
  const [end, setEnd] = useState(period.to)
  const [month, setMonth] = useState(() => parse(period.from))
  const [pickingEnd, setPickingEnd] = useState(false)
  const [activePreset, setActivePreset] = useState<FinancePresetId>(period.preset)
  const valid = isValidFinanceRange(start, end)

  function open() {
    setStart(period.from)
    setEnd(period.to)
    setMonth(parse(period.from))
    setPickingEnd(false)
    setActivePreset(period.preset)
    dialog.current?.showModal()
  }

  function applyPreset(id: Exclude<FinancePresetId, "custom">) {
    const range = financePresetRange(id)
    setActivePreset(id)
    setStart(range.from)
    setEnd(range.to)
    setMonth(parse(range.from))
    setPickingEnd(false)
  }

  function pick(day: string) {
    setActivePreset("custom")
    if (!pickingEnd || day < start) {
      setStart(day)
      setEnd(day)
      setPickingEnd(true)
      return
    }
    setEnd(day)
    setPickingEnd(false)
  }

  function apply() {
    if (!valid) return
    onChange({ from: start, to: end, preset: matchFinancePreset(start, end) })
    dialog.current?.close()
  }

  return <>
    <button type="button" className="cc-button admin-finance__calendar-trigger" aria-haspopup="dialog" onClick={open}>
      <CalendarDays size={16} aria-hidden="true"/>
      {financeRangeLabel(period.from, period.to)}
    </button>
    <dialog ref={dialog} className="admin-finance__dialog" aria-labelledby="admin-finance-calendar-title">
      <div className="admin-finance__dialog-head">
        <h3 id="admin-finance-calendar-title">Период графиков</h3>
        <button type="button" className="cc-button icon" aria-label="Закрыть календарь" onClick={() => dialog.current?.close()}>
          <X size={18}/>
        </button>
      </div>
      <div className="admin-finance__presets" aria-label="Быстрый период">
        {PRESETS.map(item =>
          <button key={item.id} type="button" aria-pressed={activePreset === item.id} onClick={() => applyPreset(item.id)}>{item.label}</button>)}
      </div>
      <div className="admin-finance__nav">
        <button type="button" className="cc-button icon" aria-label="Предыдущий месяц" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>
          <ChevronLeft size={16}/>
        </button>
        <span>{pickingEnd ? "Выберите последнюю дату" : "Выберите первую и последнюю дату"}</span>
        <button type="button" className="cc-button icon" aria-label="Следующий месяц" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>
          <ChevronRight size={16}/>
        </button>
      </div>
      <div className="admin-finance__months">
        {[0, 1].map(shift => {
          const first = new Date(month.getFullYear(), month.getMonth() + shift, 1)
          const offset = (first.getDay() + 6) % 7
          const days = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
          return <div key={shift} className="admin-finance__month">
            <p className="admin-finance__month-title">{monthTitle(first.getFullYear(), first.getMonth())}</p>
            <div className="admin-finance__grid">
              {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map(day => <small key={day}>{day}</small>)}
              {Array.from({ length: offset }, (_, index) => <span key={`blank-${index}`}/>)}
              {Array.from({ length: days }, (_, index) => {
                const day = iso(new Date(first.getFullYear(), first.getMonth(), index + 1))
                const selected = day >= start && day <= end
                const endpoint = day === start || day === end
                return <button
                  type="button"
                  key={day}
                  className={`${selected ? "in-range" : ""}${endpoint ? " endpoint" : ""}`}
                  aria-label={day}
                  aria-pressed={selected}
                  onClick={() => pick(day)}
                >{index + 1}</button>
              })}
            </div>
          </div>
        })}
      </div>
      <div className="admin-finance__dates">
        <label>Первая дата
          <input type="date" value={start} onChange={event => {
            setStart(event.target.value)
            setActivePreset("custom")
            setPickingEnd(false)
          }}/>
        </label>
        <label>Последняя дата
          <input type="date" value={end} onChange={event => {
            setEnd(event.target.value)
            setActivePreset("custom")
            setPickingEnd(false)
          }}/>
        </label>
      </div>
      <p className="admin-finance__hint" role="status">До {366} дней включительно · часовой пояс Europe/Moscow</p>
      {!valid && <p className="admin-data__error" role="alert">Выберите период до 366 дней, начало не позже конца.</p>}
      <button type="button" className="cc-button primary" disabled={!valid} onClick={apply}>Применить</button>
    </dialog>
  </>
}

export function AdminFinanceCharts({ token, rates = "" }: { token: string; rates?: string }) {
  const [period, setPeriod] = useState<FinancePeriod>(() => defaultFinancePeriod())
  const [refresh, setRefresh] = useState(0)
  const path = seriesQueryPath(period, rates)
  const { data, error, loading } = useAdminData<SeriesResponse>(path, token, refresh, "Не удалось загрузить ряды для графиков.")

  function choosePreset(id: Exclude<FinancePresetId, "custom">) {
    const range = financePresetRange(id)
    setPeriod({ ...range, preset: id })
  }

  const points = data?.points ?? []
  let runningUsers = 0
  const chartRows = points.map(point => {
    runningUsers += point.new_users
    return {
      ...point,
      revenue: point.revenue_kopeks,
      charges: point.charges_kopeks,
      margin: point.margin_kopeks,
      cumulative_users: runningUsers,
    }
  })
  const blank = !loading && !error && emptySeries(points)
  const incompleteCost = points.some(point => !point.api_cost_complete)

  return <section className="cab-panel admin-overview admin-finance" aria-labelledby="admin-finance-charts-heading" aria-busy={loading}>
    <div className="cab-section-head admin-data__heading">
      <div>
        <h2 id="admin-finance-charts-heading">Динамика</h2>
        <p>Выручка, объём проверок и рост пользователей · МСК{data ? ` · ${data.granularity === "week" ? "по неделям" : "по дням"}` : ""}</p>
      </div>
      <div className="cc-actions admin-finance__toolbar">
        <div className="admin-finance__preset-row" role="group" aria-label="Пресеты периода">
          {PRESETS.map(item =>
            <button
              key={item.id}
              type="button"
              className="cc-button"
              aria-pressed={period.preset === item.id}
              onClick={() => choosePreset(item.id)}
            >{item.label}</button>)}
        </div>
        <AdminPeriodCalendar period={period} onChange={setPeriod}/>
        <button type="button" className="cc-button" disabled={loading} onClick={() => setRefresh(n => n + 1)}>Обновить</button>
      </div>
    </div>

    {error && <p className="admin-data__error" role="alert">{error}</p>}
    {loading && <CabinetSkeleton label="Загружаем графики…"/>}
    {blank && <p className="admin-finance__empty" role="status">За выбранный период пока нет движений — графики появятся после первых пополнений, проверок или регистраций.</p>}

    {data && !loading && !blank && <>
      {incompleteCost && <p className="admin-data__status admin-data__status--warn" role="status">
        Оценка API-cost за часть дней неполная — маржа считается без недостающих ставок сбора.
      </p>}

      <div className="admin-finance__panels">
        <article className="admin-finance__panel" aria-labelledby="admin-finance-money-heading">
          <header>
            <h3 id="admin-finance-money-heading">Деньги</h3>
            <p>Пополнения, списания и расчётная маржа</p>
          </header>
          <div className="admin-finance__chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartRows} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                <CartesianGrid stroke={chartStroke.grid} strokeDasharray="2 4" vertical={false}/>
                <XAxis dataKey="bucket" tickFormatter={shortFinanceDate} tick={{ fontSize: 11, fill: chartStroke.muted }} tickLine={false} axisLine={false} minTickGap={28}/>
                <YAxis tickFormatter={moneyAxis} width={72} tick={{ fontSize: 11, fill: chartStroke.muted }} tickLine={false} axisLine={false}/>
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length || typeof label !== "string") return null
                    const row = payload[0]?.payload as SeriesPoint
                    return <ChartTip title={shortFinanceDate(label)}>
                      {tipMoney("Пополнения", row.revenue_kopeks)}
                      {tipMoney("Списания", row.charges_kopeks)}
                      {tipMoney("Маржа", row.margin_kopeks, row.api_cost_complete ? undefined : "частично")}
                    </ChartTip>
                  }}
                />
                <Line type="monotone" dataKey="revenue" name="Пополнения" stroke={chartStroke.revenue} strokeWidth={2.2} dot={false} isAnimationActive={false}/>
                <Line type="monotone" dataKey="charges" name="Списания" stroke={chartStroke.charges} strokeWidth={2} dot={false} isAnimationActive={false}/>
                <Line type="monotone" dataKey="margin" name="Маржа" stroke={chartStroke.margin} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false}/>
              </LineChart>
            </ResponsiveContainer>
          </div>
          <ul className="admin-finance__legend" aria-hidden="true">
            <li><i style={{ background: chartStroke.revenue }}/>Пополнения</li>
            <li><i style={{ background: chartStroke.charges }}/>Списания</li>
            <li><i style={{ background: chartStroke.margin }}/>Маржа</li>
          </ul>
        </article>

        <article className="admin-finance__panel" aria-labelledby="admin-finance-volume-heading">
          <header>
            <h3 id="admin-finance-volume-heading">Объём</h3>
            <p>Выполненные проверки и уникальные запросы</p>
          </header>
          <div className="admin-finance__chart">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartRows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={chartStroke.grid} strokeDasharray="2 4" vertical={false}/>
                <XAxis dataKey="bucket" tickFormatter={shortFinanceDate} tick={{ fontSize: 11, fill: chartStroke.muted }} tickLine={false} axisLine={false} minTickGap={28}/>
                <YAxis allowDecimals={false} width={44} tick={{ fontSize: 11, fill: chartStroke.muted }} tickLine={false} axisLine={false}/>
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length || typeof label !== "string") return null
                    const row = payload[0]?.payload as SeriesPoint
                    return <ChartTip title={shortFinanceDate(label)}>
                      {tipCount("Проверки", row.cloud_results)}
                      {tipCount("Уникальные запросы", row.queries_distinct)}
                    </ChartTip>
                  }}
                />
                <Bar dataKey="cloud_results" name="Проверки" fill={chartStroke.checks} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false}/>
                <Line type="monotone" dataKey="queries_distinct" name="Запросы" stroke={chartStroke.queries} strokeWidth={2} dot={false} isAnimationActive={false}/>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <ul className="admin-finance__legend" aria-hidden="true">
            <li><i style={{ background: chartStroke.checks }}/>Проверки</li>
            <li><i style={{ background: chartStroke.queries }}/>Уникальные запросы</li>
          </ul>
        </article>

        <article className="admin-finance__panel" aria-labelledby="admin-finance-users-heading">
          <header>
            <h3 id="admin-finance-users-heading">Рост</h3>
            <p>Новые пользователи за период</p>
          </header>
          <div className="admin-finance__chart">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartRows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={chartStroke.grid} strokeDasharray="2 4" vertical={false}/>
                <XAxis dataKey="bucket" tickFormatter={shortFinanceDate} tick={{ fontSize: 11, fill: chartStroke.muted }} tickLine={false} axisLine={false} minTickGap={28}/>
                <YAxis allowDecimals={false} width={44} tick={{ fontSize: 11, fill: chartStroke.muted }} tickLine={false} axisLine={false}/>
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length || typeof label !== "string") return null
                    const row = payload[0]?.payload as typeof chartRows[number]
                    return <ChartTip title={shortFinanceDate(label)}>
                      {tipCount("Новые", row.new_users)}
                      {tipCount("Накоплено за период", row.cumulative_users)}
                    </ChartTip>
                  }}
                />
                <Area type="monotone" dataKey="new_users" name="Новые" stroke={chartStroke.users} fill="color-mix(in srgb, var(--air-accent) 22%, transparent)" strokeWidth={2} isAnimationActive={false}/>
                <Line type="monotone" dataKey="cumulative_users" name="Накоплено" stroke={chartStroke.cumulative} strokeWidth={1.8} strokeDasharray="4 4" dot={false} isAnimationActive={false}/>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <ul className="admin-finance__legend" aria-hidden="true">
            <li><i style={{ background: chartStroke.users }}/>Новые</li>
            <li><i style={{ background: chartStroke.cumulative }}/>Накоплено за период</li>
          </ul>
        </article>
      </div>
      <p className="admin-data__note">Сегодня по Москве · {shortFinanceDate(moscowToday())}. KPI сверху остаются за текущий месяц.</p>
    </>}
  </section>
}
