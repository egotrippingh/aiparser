import { Fragment, useCallback, useEffect, useState, type FormEvent } from "react"
import { CalendarClock, ChevronDown, Monitor, RefreshCw, ScanSearch } from "lucide-react"

import { accountRequest } from "./account-api"
import { DEFAULT_SCAN_PREFERENCES, MONTH_DAYS, SCAN_SERVICES, type ScanPreferences } from "./lib/scan-preferences"

type CloudProject = { key: string; name: string; brand_name: string; last_scan_date: string; checks: number }
type AgentDevice = { device_id: string; name: string; online: boolean; active_scan: boolean; last_seen_at: string; local_time_zone: string }
type ReportResult = {
  id: number; query_text: string; project_name: string; brand_name: string; group_tag: string | null
  service: string; scan_date: string; status: string; counts_as_found: boolean
  mention_types: string[]; evidence_quote: string | null; answer_text: string | null
  sources: string[]; check_id: string | null
}
type Stats = { found: number; checked: number }
type Report = { summary: Stats & { visibility_pct: number | null; by_service: Record<string, Stats>; by_date: Record<string, Stats> }; total: number; results: ReportResult[] }

const serviceName = (id: string) => SCAN_SERVICES.find((service) => service.id === id)?.label || id
const percent = (stats: Stats) => stats.checked ? Math.round(stats.found * 100 / stats.checked) : 0
const dateLabel = (raw: string) => new Date(`${raw}T12:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })

export function CloudDashboard({ token }: { token: string }) {
  const [projects, setProjects] = useState<CloudProject[]>([])
  const [devices, setDevices] = useState<AgentDevice[]>([])
  const [projectKey, setProjectKey] = useState("")
  const [report, setReport] = useState<Report | null>(null)
  const [days, setDays] = useState(30)
  const [includeCards, setIncludeCards] = useState(true)
  const [preferences, setPreferences] = useState<ScanPreferences>(DEFAULT_SCAN_PREFERENCES)
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [saved, setSaved] = useState("")
  const [expanded, setExpanded] = useState<number | null>(null)
  const [preview, setPreview] = useState("")

  const refreshHeader = useCallback(async (includePreferences = false) => {
    const [nextProjects, nextDevices, nextPreferences] = await Promise.all([
      accountRequest<CloudProject[]>("/reports/projects", token),
      accountRequest<AgentDevice[]>("/agent/devices", token),
      includePreferences ? accountRequest<ScanPreferences>("/scan-preferences", token) : Promise.resolve(null),
    ])
    setProjects(nextProjects)
    setDevices(nextDevices)
    if (nextPreferences) setPreferences(nextPreferences)
    setProjectKey((current) => nextProjects.some((project) => project.key === current)
      ? current : nextProjects[0]?.key || "")
    setLoaded(true)
  }, [token])

  useEffect(() => {
    refreshHeader(true).catch((cause) => { setError(cause instanceof Error ? cause.message : "Не удалось загрузить дашборд"); setLoaded(true) })
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") refreshHeader().catch(() => undefined)
    }, 60_000)
    return () => window.clearInterval(timer)
  }, [refreshHeader])

  const refreshReport = useCallback(async (offset = 0) => {
    if (!projectKey) { setReport(null); return }
    const query = new URLSearchParams({ project: projectKey, days: String(days),
      include_cards: String(includeCards), offset: String(offset), limit: "100" })
    const next = await accountRequest<Report>(`/reports?${query}`, token)
    setReport((current) => offset && current ? { ...next, results: [...current.results, ...next.results] } : next)
  }, [projectKey, days, includeCards, token])

  useEffect(() => {
    setExpanded(null)
    setPreview("")
    refreshReport().catch((cause) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить отчёт"))
  }, [refreshReport])

  async function savePreferences(event: FormEvent) {
    event.preventDefault()
    if (!preferences.month_days.length || !preferences.services.length) {
      setError("Выберите хотя бы одно число месяца и один ИИ-сервис")
      return
    }
    setBusy(true)
    setError("")
    setSaved("")
    try {
      const next = await accountRequest<ScanPreferences>("/scan-preferences", token, preferences, "PUT")
      setPreferences(next)
      setSaved("Расписание сохранено и появится в агенте при следующей синхронизации")
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить настройки")
      await accountRequest<ScanPreferences>("/scan-preferences", token).then(setPreferences).catch(() => undefined)
    } finally { setBusy(false) }
  }

  async function openShot(checkId: string) {
    try {
      const result = await accountRequest<{ url: string }>(`/screenshots/${encodeURIComponent(checkId)}/url`, token)
      setPreview(result.url)
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось открыть снимок") }
  }

  const selected = projects.find((project) => project.key === projectKey)
  const chart = Object.entries(report?.summary.by_date || {}).sort(([a], [b]) => a.localeCompare(b))

  return <div className="cloud-dashboard">
    <div className="cab-title-row"><div><span className="cab-kicker">AI MENTIONS / АНАЛИТИКА</span><h1>Видимость бренда</h1><p>Результаты проверок с вашего компьютера доступны здесь после синхронизации агента.</p></div><button className="cab-refresh cloud-refresh" onClick={() => Promise.all([refreshHeader(true), refreshReport()]).catch(() => setError("Не удалось обновить данные"))}><RefreshCw size={16} /> Обновить</button></div>

    <section className="cloud-devices" aria-label="Состояние агента">
      {devices.length ? devices.map((device) => <div className="cloud-device" key={device.device_id}>
        <span className={`cloud-status ${device.online ? "online" : ""}`} aria-hidden="true" />
        <Monitor size={18} aria-hidden="true" />
        <span><strong>{device.name}</strong><small>{device.active_scan ? "Проверка идёт" : device.online ? "Агент на связи" : `Не в сети с ${new Date(device.last_seen_at).toLocaleString("ru-RU")}`}</small></span>
      </div>) : <div className="cloud-device"><span className="cloud-status" aria-hidden="true" /><Monitor size={18} aria-hidden="true" /><span><strong>Агент пока не подключён</strong><small>Подключите приложение кодом в разделе «Аккаунт».</small></span></div>}
      <span className="cloud-next"><CalendarClock size={17} aria-hidden="true" /> {preferences.enabled ? `${preferences.local_time} по времени компьютера · ${preferences.browser_mode === "headless" ? "без окон" : "с окнами"}` : "Расписание выключено"}</span>
    </section>

    <div className="cloud-main-grid">
      <section className="cab-panel cloud-report">
        <div className="cab-section-head"><div><span className="cab-kicker">ОТЧЁТ</span><h2>{selected?.name || "Проекты пока не синхронизированы"}</h2></div></div>
        {projects.length ? <>
          <div className="cloud-filters"><label>Проект<select value={projectKey} onChange={(event) => setProjectKey(event.target.value)}>{projects.map((project) => <option key={project.key} value={project.key}>{project.name}</option>)}</select></label><label>Период<select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={7}>7 дней</option><option value={30}>30 дней</option><option value={90}>90 дней</option><option value={365}>Год</option></select></label><label className="cloud-checkbox"><input type="checkbox" checked={includeCards} onChange={(event) => setIncludeCards(event.target.checked)} /> Учитывать карточки товаров</label></div>
          <div className="cloud-metrics"><div><span>Упоминаемость</span><strong>{report?.summary.visibility_pct == null ? "—" : `${report.summary.visibility_pct}%`}</strong></div><div><span>Упоминаний</span><strong>{report?.summary.found ?? 0}<small> / {report?.summary.checked ?? 0}</small></strong></div><div><span>Результатов</span><strong>{report?.total ?? 0}</strong></div></div>
          <div className="cloud-chart" role="img" aria-label="Доля упоминаний по датам">{chart.length ? chart.map(([date, stats]) => <div className="cloud-chart-col" key={date}><div className="cloud-chart-track"><span style={{ height: `${percent(stats)}%` }} /></div><b>{percent(stats)}%</b><small>{dateLabel(date)}</small></div>) : <p className="cab-empty">Проверок за выбранный период пока нет.</p>}</div>
          <div className="cloud-service-list">{Object.entries(report?.summary.by_service || {}).map(([service, stats]) => <div key={service}><span>{serviceName(service)}</span><strong>{percent(stats)}%</strong><small>{stats.found} из {stats.checked}</small></div>)}</div>
        </> : <div className="cloud-empty"><ScanSearch size={28} aria-hidden="true" /><strong>{loaded ? "Ожидаем первый отчёт" : "Загружаем проекты…"}</strong><p>Установите агент, подключите аккаунт и выполните первую проверку. Проект появится здесь автоматически.</p></div>}
      </section>

      <form className="cab-panel cloud-preferences" onSubmit={savePreferences}><span className="cab-kicker">АГЕНТ / РАСПИСАНИЕ</span><h2>Проверки по расписанию</h2><p>Агент запускает проекты на вашем компьютере. Если он выключен или спит, проверка начнётся после следующего запуска в выбранный день.</p>
        <label className="cloud-checkbox cloud-enabled"><input type="checkbox" checked={preferences.enabled} onChange={(event) => setPreferences({ ...preferences, enabled: event.target.checked })} /> Проверять автоматически</label>
        <label className="cloud-field">Время на компьютере<input type="time" value={preferences.local_time} onChange={(event) => setPreferences({ ...preferences, local_time: event.target.value })} /></label>
        <fieldset><legend>Числа месяца</legend><div className="cloud-days">{MONTH_DAYS.map((day) => <label key={day}><input type="checkbox" checked={preferences.month_days.includes(day)} onChange={(event) => setPreferences({ ...preferences, month_days: event.target.checked ? [...preferences.month_days, day].sort((a, b) => a - b) : preferences.month_days.filter((value) => value !== day) })} /><span>{day}</span></label>)}</div><small className="cloud-hint">Если в месяце нет выбранного числа, этот запуск пропускается.</small></fieldset>
        <fieldset><legend>Режим браузера</legend><div className="cloud-mode"><label><input type="radio" name="cloud-browser-mode" checked={preferences.browser_mode === "headless"} onChange={() => setPreferences({ ...preferences, browser_mode: "headless" })} /><span><b>Без окон</b><small>Работает в фоне. Для входа и капчи может понадобиться видимое окно.</small></span></label><label><input type="radio" name="cloud-browser-mode" checked={preferences.browser_mode === "headful"} onChange={() => setPreferences({ ...preferences, browser_mode: "headful" })} /><span><b>С окнами</b><small>Видно, как агент проходит проверки.</small></span></label></div></fieldset>
        <fieldset><legend>ИИ-сервисы</legend><div className="cloud-services">{SCAN_SERVICES.map((service) => <label key={service.id}><input type="checkbox" disabled={"available" in service && !service.available} checked={preferences.services.includes(service.id)} onChange={(event) => setPreferences({ ...preferences, services: event.target.checked ? [...preferences.services, service.id] : preferences.services.filter((id) => id !== service.id) })} />{service.label}</label>)}</div></fieldset>
        <label className="cloud-field">Скорость<select value={preferences.speed_profile} onChange={(event) => setPreferences({ ...preferences, speed_profile: event.target.value as ScanPreferences["speed_profile"] })}><option value="careful">Осторожная</option><option value="balanced">Сбалансированная</option><option value="fast">Быстрая</option></select></label>
        <button className="cab-primary" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить расписание"}</button>{saved && <small className="cloud-saved" role="status">{saved}</small>}
      </form>
    </div>

    {projectKey && <section className="cab-panel cloud-results"><div className="cab-section-head"><div><span className="cab-kicker">ПРОВЕРКИ</span><h2>Ответы и источники</h2></div><span className="cloud-result-count">{report?.total ?? 0} результатов</span></div><div className="cloud-table-wrap"><table><thead><tr><th>Дата</th><th>Запрос</th><th>ИИ-сервис</th><th>Результат</th><th><span className="sr-only">Подробности</span></th></tr></thead><tbody>{report?.results.map((row) => <Fragment key={row.id}><tr><td>{dateLabel(row.scan_date)}</td><td className="cloud-query">{row.query_text}</td><td>{serviceName(row.service)}</td><td><span className={`cloud-result-badge ${row.counts_as_found ? "found" : ""}`}>{row.counts_as_found ? "Найден" : row.status === "not_found" || row.status === "found" ? "Не найден" : row.status === "skipped" ? "Нет AI-блока" : "Сбой"}</span></td><td><button className="cloud-detail-button" aria-expanded={expanded === row.id} onClick={() => setExpanded(expanded === row.id ? null : row.id)}>{expanded === row.id ? "Скрыть" : "Ответ"} <ChevronDown size={14} /></button></td></tr>{expanded === row.id && <tr className="cloud-detail-row"><td colSpan={5}><div><b>Ответ ИИ</b><p>{row.answer_text || row.evidence_quote || "Текст ответа не сохранён."}</p>{row.mention_types.length > 0 && <small>Типы упоминания: {row.mention_types.join(", ")}</small>}{row.sources.length > 0 && <ul>{row.sources.map((source) => <li key={source}><a href={source} target="_blank" rel="noreferrer">{source}</a></li>)}</ul>}{row.check_id && <button className="cab-shot-button" onClick={() => openShot(row.check_id!)}>Показать снимок</button>}</div></td></tr>}</Fragment>)}</tbody></table></div>{report && report.results.length < report.total && <button className="cab-refresh" onClick={() => refreshReport(report.results.length)}>Показать ещё</button>}{preview && <div className="cab-shot-preview"><div className="cab-section-head"><b>Снимок ответа</b><button className="cab-refresh" onClick={() => setPreview("")}>Закрыть</button></div><img src={preview} alt="Снимок ответа ИИ" /></div>}</section>}
    {error && <p className="cab-message" role="alert">{error}<button onClick={() => setError("")} aria-label="Закрыть сообщение">×</button></p>}
  </div>
}
