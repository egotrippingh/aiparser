import { Fragment, useEffect, useState } from "react"
import { ArrowUpRight, ChevronDown, ChevronLeft, ChevronRight, Plus, Search, Settings2 } from "lucide-react"
import { accountRequest } from "./account-api"
import { AppChoice } from "./app-choice"
import { CabinetSkeleton } from "./cabinet-loading"
import { CompetitorSettings, type DomainSuggestion } from "./competitor-settings"
import { addDays, dmy, today } from "./lib/dates"
import { plural } from "./lib/format"
import { useReportAnswer } from "./report-answer"
import { defaultDateSelection, ReportCalendar } from "./report-calendar"
import { ServiceMark, serviceName } from "./service-mark"

type Mode = "competitors" | "citations"
type Evidence = { id: number; query_text: string; date: string; service: string; brand_found: boolean }
type CitationKind = "own" | "competitor" | "external"
type CommonRow = { queries: number; services: string[]; results: Evidence[] }
type Competitor = CommonRow & { name: string; mentions: number; gaps: number }
type Citation = CommonRow & { url: string; domain: string; kind: CitationKind; count: number }
type Report = {
  date_from: string; date_to: string; available_dates: string[]; groups: string[];
  checked: number; total: number; services: string[]; available_services: string[];
} & ({ rows: Competitor[]; suggested_domains: DomainSuggestion[] } | { rows: Citation[] })
type Props = { token: string; projectId: string; mode: Mode; canEdit: boolean; lastFinishedRunId?: string }

const pageSize = 30
const integer = new Intl.NumberFormat("ru-RU")
const percentage = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1, style: "percent" })
const kinds = { own: "Сайт бренда", competitor: "Сайт конкурента", external: "Внешний источник" }

export function SourceNavigation({ projectId, pages }: { projectId: string; pages: boolean }) {
  const base = `#/project/${projectId}`
  return <nav className="source-navigation" aria-label="Отчёты об источниках">
    <a className="btn" href={`${base}/sources`} aria-current={pages ? "page" : undefined}>Страницы</a>
    <a className="btn" href={`${base}/source-domains`} aria-current={pages ? undefined : "page"}>Домены с упоминанием бренда</a>
  </nav>
}

function SearchField({ label, value, change, placeholder }: { label: string; value: string; change: (value: string) => void; placeholder: string }) {
  return <label className="search-box">
    <Search size={16} aria-hidden="true"/>
    <input type="search" aria-label={label} placeholder={placeholder} value={value} maxLength={254} onChange={event => change(event.target.value)}/>
  </label>
}

function ServiceMarks({ services }: { services: string[] }) {
  return services.length ? <div className="system-marks">
    {services.map(service => <span key={service} title={serviceName(service)}><ServiceMark id={service}/></span>)}
  </div> : <span aria-label="Нет упоминаний">—</span>
}

function AnswerList({ items, open }: { items: Evidence[]; open: (id: number) => void }) {
  return <div className="project-analysis__answers">
    <p>{items.length === 1 ? "Сохранённый ответ" : "Последние сохранённые ответы"}</p>
    <ul>{items.map(item => <li key={item.id}>
      <button type="button" className="btn project-analysis__answer" onClick={() => open(item.id)}>
        <ServiceMark id={item.service}/>
        <span><strong>{item.query_text}</strong><small>{dmy(item.date)} · {serviceName(item.service)}</small></span>
        <ChevronRight size={16} aria-hidden="true"/>
      </button>
    </li>)}</ul>
  </div>
}

export function ProjectAnalysis({ token, projectId, mode, canEdit, lastFinishedRunId }: Props) {
  const citations = mode === "citations"
  const base = `/control/projects/${encodeURIComponent(projectId)}/mentions`
  const [range, setRange] = useState(() => ({ from: addDays(today(), -29), to: today() }))
  const [service, setService] = useState("")
  const [group, setGroup] = useState<string | null>(null)
  const [querySearch, setQuerySearch] = useState("")
  const [pageSearch, setPageSearch] = useState("")
  const [sourceKind, setSourceKind] = useState("all")
  const [gapsOnly, setGapsOnly] = useState(false)
  const [openRow, setOpenRow] = useState("")
  const [page, setPage] = useState({ filters: "", offset: 0 })
  const [refresh, setRefresh] = useState(0)
  const [settings, setSettings] = useState<{ domain?: string; label?: string } | null>(null)
  const [loaded, setLoaded] = useState<{ report: Report; key: string } | null>(null)
  const [failure, setFailure] = useState<{ message: string; key: string } | null>(null)
  const params = new URLSearchParams({ date_from: range.from, date_to: range.to, gap_only: String(gapsOnly), limit: String(pageSize) })
  if (service) params.set("services", service)
  if (group !== null) params.set("group", group)
  if (querySearch.trim()) params.set("search", querySearch.trim())
  if (citations) {
    params.set("source_kind", sourceKind)
    if (pageSearch.trim()) params.set("page_search", pageSearch.trim())
  }
  const filters = params.toString()
  const offset = page.filters === filters ? page.offset : 0
  params.set("offset", String(offset))
  const path = `${base}/${mode}?${params}`
  const requestKey = JSON.stringify([path, refresh, lastFinishedRunId])
  const report = loaded?.key === requestKey ? loaded.report : null
  const error = failure?.key === requestKey ? failure.message : ""
  const reloading = !report && !error
  const metadata = loaded?.report
  const { openResult, answerDialog } = useReportAnswer(base, token, canEdit, reload)

  function reload() { setRefresh(value => value + 1) }
  function changePage(next: number) {
    setOpenRow("")
    setPage({ filters, offset: next })
  }

  useEffect(() => {
    let active = true
    const timer = setTimeout(() => {
      accountRequest<Report>(path, token).then(data => {
        if (!active) return
        setLoaded({ report: data, key: requestKey })
        setFailure(null)
      }).catch((cause: unknown) => {
        if (active) setFailure({ message: cause instanceof Error ? cause.message : "Не удалось загрузить отчёт", key: requestKey })
      })
    }, 180)
    return () => { active = false; clearTimeout(timer) }
  }, [path, requestKey, token])

  const suggestions = report && "suggested_domains" in report ? report.suggested_domains : []
  const serviceOptions = metadata?.available_services || metadata?.services || []
  const groups = (metadata?.groups || []).filter(Boolean)
  const showSettings = !citations && canEdit
  const groupOptions = [{ value: "*", label: "Все группы" }, { value: "group:", label: "Без группы" },
    ...groups.map(item => ({ value: `group:${item}`, label: item }))]
  if (group && !groups.includes(group)) groupOptions.push({ value: `group:${group}`, label: group })

  return <section className="project-analysis" aria-label={citations ? "Карта цитируемых страниц" : "Анализ конкурентов"}>
    <div className="filterbar project-analysis__filters">
      <ReportCalendar from={range.from} to={range.to} available={metadata?.available_dates || []}
        selection={defaultDateSelection} context="analysis" change={(from, to) => setRange({ from, to })}/>
      <AppChoice label="ИИ-система" value={service} options={[{ value: "", label: "Все ИИ-системы" },
        ...serviceOptions.map(id => ({ value: id, label: serviceName(id) }))]} change={setService}/>
      <AppChoice label="Группа запросов" value={group === null ? "*" : `group:${group}`} searchable
        options={groupOptions} change={value => setGroup(value === "*" ? null : value.slice(6))}/>
      <label className="report-switch">
        <input type="checkbox" role="switch" checked={gapsOnly} onChange={event => setGapsOnly(event.target.checked)}/>
        Только где нас обходят
      </label>
      {showSettings && <button type="button" className="btn project-analysis__settings-trigger" onClick={() => setSettings({})}>
        <Settings2 size={16} aria-hidden="true"/>Настроить конкурентов
      </button>}
    </div>

    <section className="panel project-analysis__panel" aria-label={citations ? "Страницы по числу ссылок" : "Конкуренты по частоте упоминаний"} aria-busy={reloading}>
      <div className="table-toolbar project-analysis__toolbar">
        <SearchField label="Поиск по запросам" placeholder="Запрос" value={querySearch} change={setQuerySearch}/>
        {citations && <>
          <SearchField label="Поиск по URL" placeholder="URL или домен" value={pageSearch} change={setPageSearch}/>
          <AppChoice label="Тип источника" value={sourceKind} options={[
            { value: "all", label: "Все источники" }, { value: "own", label: "Сайт бренда" },
            { value: "competitor", label: "Сайты конкурентов" }, { value: "external", label: "Внешние источники" },
          ]} change={setSourceKind}/>
        </>}
        <span className="project-analysis__total" role="status">{report && <>
          {integer.format(report.checked)} {plural(report.checked, "проверка", "проверки", "проверок")} в выборке
        </>}</span>
      </div>

      {error ? <div className="project-analysis__empty" role="alert"><p>{error}</p><button type="button" className="btn" onClick={reload}>Повторить</button></div>
        : reloading ? <CabinetSkeleton label="Загружаем отчёт…" format="rows"/>
        : report && (report.rows.length ? <div className="table-wrap project-analysis__table-region" role="region" aria-label={citations ? "Таблица цитируемых страниц" : "Таблица конкурентов"} tabIndex={0}>
          <table className="project-analysis__table">
            <thead><tr>
              <th scope="col">{citations ? "Страница" : "Конкурент"}</th>
              <th scope="col">{citations ? "Ответов со ссылкой" : "Упоминания"}</th>
              {!citations && <th scope="col">Обошёл бренд</th>}
              <th className="project-analysis__secondary" scope="col">Запросы</th>
              <th className="project-analysis__secondary" scope="col">ИИ-системы</th>
              <th scope="col"><span className="sr-only">Сохранённые ответы</span></th>
            </tr></thead>
            <tbody>{report.rows.map(row => {
              const isCitation = "url" in row
              const id = isCitation ? row.url : row.name
              const expanded = id === openRow
              const count = isCitation ? row.count : row.mentions
              return <Fragment key={id}>
                <tr>
                  <th scope="row" className="project-analysis__row-label">{isCitation ? <>
                    <a className="project-analysis__url" href={row.url} target="_blank" rel="noopener noreferrer">
                      <span>{row.url}</span><ArrowUpRight size={16} aria-hidden="true"/>
                    </a><span className={`badge ${row.kind === "own" ? "blue" : ""}`}>{kinds[row.kind]}</span>
                  </> : row.name}</th>
                  <td className="project-analysis__number"><strong>{integer.format(count)}</strong>{!isCitation && report.checked > 0 && <small>{percentage.format(count / report.checked)}</small>}</td>
                  {!isCitation && <td className="project-analysis__number">{integer.format(row.gaps)}</td>}
                  <td className="project-analysis__secondary project-analysis__number">{integer.format(row.queries)}</td>
                  <td className="project-analysis__secondary"><ServiceMarks services={row.services}/></td>
                  <td className="project-analysis__action-cell"><button type="button" className="btn project-analysis__row-action" disabled={!row.results.length}
                    aria-label={`Ответы · ${id}`} aria-expanded={expanded} onClick={() => setOpenRow(expanded ? "" : id)}>
                    <span>Ответы</span><ChevronDown size={16} aria-hidden="true"/>
                  </button></td>
                </tr>
                {expanded && row.results.length > 0 && <tr className="project-analysis__evidence-row"><td colSpan={citations ? 5 : 6}>
                  <div className="project-analysis__evidence-meta"><span>{integer.format(row.queries)} {plural(row.queries, "запрос", "запроса", "запросов")}</span><ServiceMarks services={row.services}/></div>
                  <AnswerList items={row.results} open={openResult}/>
                </td></tr>}
              </Fragment>
            })}</tbody>
          </table>
        </div> : <p className="empty-state project-analysis__empty" role="status">{citations
          ? report.checked ? "Страниц по выбранным фильтрам нет." : "За выбранный период нет завершённых проверок."
          : gapsOnly || querySearch.trim() ? "По выбранным фильтрам совпадений нет."
            : "Список конкурентов пока пуст."}</p>)}
      {report && (offset > 0 || report.total > pageSize) && <div className="project-analysis__pagination" aria-label="Страницы результатов">
        <span>{offset < report.total ? `${integer.format(offset + 1)}–${integer.format(Math.min(offset + pageSize, report.total))} из ${integer.format(report.total)}` : `Всего ${integer.format(report.total)}`}</span>
        <button type="button" className="btn icon-only" disabled={offset === 0} onClick={() => changePage(Math.max(0, offset - pageSize))} aria-label="Предыдущая страница"><ChevronLeft size={16}/></button>
        <button type="button" className="btn icon-only" disabled={offset + pageSize >= report.total} onClick={() => changePage(offset + pageSize)} aria-label="Следующая страница"><ChevronRight size={16}/></button>
      </div>}
    </section>

    <p className="page-note project-analysis__note">{citations
      ? "В отчёт входят сохранённые ссылки из всех ответов. Одна страница учитывается один раз в каждом ответе."
      : "Учитываем совпадения по названию, вариантам написания и указанным доменам. Доля считается от завершённых проверок, включая случаи без ИИ-блока."}</p>
    {!citations && suggestions.length > 0 && <section className="panel project-analysis__suggestions" aria-labelledby="competitor-suggestions">
      <h2 id="competitor-suggestions">Домены для проверки</h2>
      <p>Эти домены встречаются в тексте нескольких ответов. Добавьте те, которые принадлежат конкурентам.</p>
      <ul>{suggestions.map(({ domain, mentions, label }) => <li key={domain}>
        <span><strong>{label || domain}</strong>{label && <small>{domain}</small>}</span><span>Ответов: {integer.format(mentions)}</span>
        {showSettings && <button type="button" className="btn icon-only" aria-label={`Добавить домен ${domain}`} onClick={() => setSettings({ domain, label })}><Plus size={16}/></button>}
      </li>)}</ul>
    </section>}
    {settings && <CompetitorSettings base={base} token={token} suggestedDomain={settings.domain} suggestedName={settings.label} onClose={() => setSettings(null)} onSaved={() => {
      changePage(0)
      reload()
      setSettings(null)
    }}/>}
    {answerDialog}
  </section>
}
