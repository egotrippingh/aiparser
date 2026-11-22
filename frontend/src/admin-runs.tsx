import { useState, type FormEvent } from "react"
import { adminRunStatuses, runJournalLabel, useAdminData } from "./admin-data"
import { AppChoice } from "./app-choice"
import { CabinetSkeleton } from "./cabinet-loading"

import "./admin-dashboard.scss"

type Run = {
  id: string
  email: string
  project_name: string
  state: string
  desired_state: string
  connection_lost: boolean
  phase: string
  planned_checks: number
  done_checks: number
  scheduled_for: string | null
  created_at: string
  updated_at: string
  retry_at: string | null
}

const statusOptions = [{ value: "", label: "Все статусы" }, ...Object.entries(adminRunStatuses).map(([value, label]) => ({
  value, label: value === "paused" ? "Пауза или ожидание повтора" : label,
}))]
const statusColors: Record<string, string> = { done: "green", failed: "red", paused: "warn", missed: "warn", running: "blue" }
const pageSize = 20
const dateTime = new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "short",
  timeStyle: "short",
  timeZone: "Europe/Moscow",
})

export function AdminRuns({ token, resultsHref }: { token: string; resultsHref?: (runId: string) => string }) {
  const [search, setSearch] = useState("")
  const [query, setQuery] = useState("")
  const [status, setStatus] = useState("")
  const [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const params = new URLSearchParams({ search: query, status, offset: String(offset), limit: String(pageSize) })
  const { data: page, error, loading } = useAdminData<{ total: number; runs: Run[] }>(
    `/admin/runs?${params}`, token, refresh, "Не удалось загрузить запуски.",
  )

  function applySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setQuery(search.trim())
    setOffset(0)
    setRefresh(n => n + 1)
  }

  return <section className="cab-panel admin-overview admin-data" aria-labelledby="admin-runs-heading" aria-busy={loading}>
    <div className="cab-section-head admin-data__heading">
      <div>
        <h2 id="admin-runs-heading">Запуски сканов</h2>
        <p>Очередь, прогресс и история сканов по всем проектам. Время московское.</p>
      </div>
      <button className="cc-button" disabled={loading} onClick={() => setRefresh(n => n + 1)}>Обновить</button>
    </div>
    <div className="admin-data__toolbar">
      <form className="admin-data__search" onSubmit={applySearch}>
        <label>Пользователь или запуск
          <input type="search" placeholder="Email, проект или ID запуска" maxLength={200} value={search} onChange={event => setSearch(event.target.value)}/>
        </label>
        <button className="cc-button" disabled={loading}>Найти</button>
      </form>
      <div className="admin-data__filter">
        <span aria-hidden="true">Статус</span>
        <AppChoice label="Статус запуска" options={statusOptions} value={status} disabled={loading} change={value => { setOffset(0); setStatus(value) }}/>
      </div>
    </div>
    {error && <p className="admin-data__error" role="alert">{error}</p>}
    {loading && <CabinetSkeleton label="Загружаем журнал запусков…"/>}
    {page && !loading && <>
      {page.runs.length > 0 ? <div className="admin-users-scroll admin-data__scroll" role="region" aria-label="Журнал запусков" tabIndex={0}>
        <table className="admin-data__runs">
          <thead>
            <tr>{["Проект и пользователь", "Запуск", "Статус", "Проверено", "Обновлён", ...(resultsHref ? ["Результаты"] : [])].map(heading =>
              <th key={heading} scope="col">{heading}</th>)}
            </tr>
          </thead>
          <tbody>
            {page.runs.map(run => <tr key={run.id}>
              <td><strong>{run.project_name}</strong><small>{run.email}</small></td>
              <td>
                <time dateTime={run.created_at}>{dateTime.format(new Date(run.created_at))}</time>
                <small>{run.scheduled_for ? `По расписанию · ${dateTime.format(new Date(run.scheduled_for))}` : "Вручную"}</small>
              </td>
              <td>
                <span className={`badge ${statusColors[run.state] || ""}`}>{runJournalLabel(run)}</span>
                {run.connection_lost && <small>Нет связи с исполнителем</small>}
                {run.retry_at && <small>Повтор · {dateTime.format(new Date(run.retry_at))}</small>}
              </td>
              <td>
                <span>{run.done_checks} / {run.planned_checks}</span>
                {run.planned_checks > 0 && <progress max={run.planned_checks} value={Math.min(run.done_checks, run.planned_checks)} aria-label={`Прогресс проекта ${run.project_name}`}/>}
              </td>
              <td><time dateTime={run.updated_at}>{dateTime.format(new Date(run.updated_at))}</time></td>
              {resultsHref && <td><a className="cc-button" href={resultsHref(run.id)} aria-label={`Результаты запуска проекта ${run.project_name}`}>Открыть</a></td>}
            </tr>)}
          </tbody>
        </table>
      </div> : <p role="status">Запусков по выбранным фильтрам нет.</p>}
      {page.total > 0 && <div className="cc-actions admin-data__pagination">
        <span>{page.runs.length ? `${offset + 1}–${offset + page.runs.length} из ${page.total}` : `Всего ${page.total}`}</span>
        <button className="cc-button" disabled={offset === 0} onClick={() => setOffset(n => n - pageSize)}>Назад</button>
        <button className="cc-button" disabled={offset + pageSize >= page.total} onClick={() => setOffset(n => n + pageSize)}>Далее</button>
      </div>}
    </>}
  </section>
}
