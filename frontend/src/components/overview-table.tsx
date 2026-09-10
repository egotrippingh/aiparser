/** Таблица как в Топвизоре: запросы в строках, даты в столбцах.
 *
 * Вкладки сверху — как поисковики в Топвизоре: «Все» показывает под каждой
 * датой по колонке на сервис, вкладка сервиса — одну колонку на дату.
 * Колонка Δ сразу за текстом запроса — изменение к прошлому срезу, а ячейки,
 * где упоминание появилось или пропало, обведены. Первая колонка липкая:
 * при прокрутке вправо текст запроса остаётся на виду.
 */

import { useMemo, useState } from "react"
import { motion } from "motion/react"
import { ArrowDownUp, Search, X } from "lucide-react"
import { cn } from "cn"

import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { PanelFoot, PanelHead, ServiceDot } from "@/components/bits"
import { cellChange, rowChanges, type Change } from "@/lib/changes"
import { plural, pct, shortDate, weekday } from "@/lib/format"
import { FAILED, statusMeta } from "@/lib/status"
import type { Cell, Overview, OverviewRow, ServiceMeta } from "@/lib/types"
import { useApp } from "@/store/app-store"
import type { QueryTarget } from "@/components/query-sheet"

type Filter = "all" | "found" | "not_found" | "changed" | "review" | "problem"
type Sort = "text" | "visibility" | "change"

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Все" },
  { id: "found", label: "Есть упоминание" },
  { id: "not_found", label: "Без упоминаний" },
  { id: "changed", label: "Изменились" },
  { id: "review", label: "Требуют проверки" },
  { id: "problem", label: "Сбои проверки" },
]

const SORT_LABEL: Record<Sort, string> = {
  text: "По алфавиту",
  visibility: "По видимости",
  change: "По изменениям",
}
const NEXT_SORT: Record<Sort, Sort> = { text: "visibility", visibility: "change", change: "text" }

const CHANGE: Record<Change, { color: string; sign: string; word: string }> = {
  gained: { color: "var(--ok)", sign: "▲", word: "упоминание появилось" },
  lost: { color: "var(--bad)", sign: "▼", word: "упоминание пропало" },
}

const ALL = "all"
const PAGE = 100

export function OverviewTable({
  overview,
  onOpen,
}: {
  overview: Overview
  onOpen: (t: QueryTarget) => void
}) {
  const { services, serviceById } = useApp()
  const [mode, setMode] = useState<string>(ALL)
  const [search, setSearch] = useState("")
  const [filter, setFilter] = useState<Filter>("all")
  const [group, setGroup] = useState<string>("")
  const [sort, setSort] = useState<Sort>("text")
  const [limit, setLimit] = useState(PAGE)

  const available = useMemo(
    () => services.filter((s) => overview.services.includes(s.id)),
    [services, overview.services],
  )
  // Вкладка сервиса, которого нет в новом периоде или проекте, — назад на «Все».
  const current = mode !== ALL && available.some((s) => s.id === mode) ? mode : ALL
  const cols = useMemo(
    () => (current === ALL ? available : available.filter((s) => s.id === current)),
    [available, current],
  )
  const colIds = useMemo(() => cols.map((s) => s.id), [cols])
  const statKey = current === ALL ? "_all" : current
  const withSub = current === ALL

  // Даты в обратном порядке: свежий срез — сразу у текста запроса, за старыми
  // нужно прокручивать вправо, а не наоборот.
  const dates = useMemo(() => [...overview.dates].reverse(), [overview.dates])
  const prevOf = useMemo(() => {
    const m: Record<string, string> = {}
    overview.dates.forEach((d, i) => {
      if (i > 0) m[d] = overview.dates[i - 1]
    })
    return m
  }, [overview.dates])
  const latest = overview.summary?.date
  const prevDate = overview.summary?.prev_date ?? null

  const groups = useMemo(() => {
    const set = new Set<string>()
    for (const r of overview.rows) if (r.group_tag) set.add(r.group_tag)
    return [...set].sort()
  }, [overview.rows])

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const lastCells = (r: OverviewRow): Cell[] =>
      latest ? colIds.map((id) => r.cells[latest]?.[id]).filter((c): c is Cell => Boolean(c)) : []
    const change = (r: OverviewRow) => rowChanges(r, latest, prevDate, colIds)

    let out = overview.rows.filter((r) => {
      if (q && !r.text.toLowerCase().includes(q)) return false
      if (group && r.group_tag !== group) return false
      if (filter === "all") return true
      if (filter === "changed") {
        const c = change(r)
        return c.gained + c.lost > 0
      }

      const cells = Object.values(r.cells).flatMap((by) =>
        colIds.map((id) => by[id]).filter((c): c is Cell => Boolean(c)),
      )
      if (filter === "review") return cells.some((c) => c.needs_review)
      if (filter === "problem") return cells.some((c) => FAILED.includes(c.status))

      // «Есть упоминание» и «без упоминаний» — по свежему срезу: вопрос всегда
      // про сегодняшнее положение дел, а не про всю историю.
      const last = lastCells(r)
      const found = last.some((c) => c.status === "found")
      return filter === "found" ? found : last.length > 0 && !found
    })

    const byText = (a: OverviewRow, b: OverviewRow) => a.text.localeCompare(b.text, "ru")
    if (sort === "visibility") {
      const score = (r: OverviewRow) => {
        const checked = lastCells(r).filter((c) => c.status === "found" || c.status === "not_found")
        if (!checked.length) return -1
        return checked.filter((c) => c.status === "found").length / checked.length
      }
      out = [...out].sort((a, b) => score(b) - score(a) || byText(a, b))
    } else if (sort === "change") {
      // Сначала потери — их важнее заметить, потом появления, потом без изменений.
      const score = (r: OverviewRow) => {
        const c = change(r)
        return c.lost * 1000 + c.gained
      }
      out = [...out].sort((a, b) => score(b) - score(a) || byText(a, b))
    } else {
      out = [...out].sort(byText)
    }
    return out
  }, [overview.rows, search, filter, group, sort, latest, prevDate, colIds])

  const visible = rows.slice(0, limit)
  const reset = search || filter !== "all" || group
  const tabs: { id: string; label: string; service?: ServiceMeta }[] = [
    { id: ALL, label: "Все" },
    ...available.map((s) => ({ id: s.id, label: s.name, service: s })),
  ]
  const nameOf = (id: string) => serviceById(id)?.name ?? id

  return (
    <>
      <PanelHead
        title="Запросы по датам"
        hint={`${overview.dates.length} ${plural(overview.dates.length, "срез", "среза", "срезов")} · клик по ячейке открывает ответ`}
      >
        {available.length > 1 ? (
          <div role="tablist" aria-label="ИИ-система" className="-my-2.5 flex flex-wrap">
            {tabs.map((t) => {
              const on = current === t.id
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  onClick={() => {
                    setMode(t.id)
                    setLimit(PAGE)
                  }}
                  className={cn(
                    "relative flex h-10 cursor-pointer items-center px-3 text-xs transition-colors",
                    "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none focus-visible:ring-inset",
                    on ? "text-foreground font-semibold" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {/* Подчёркивание переезжает под выбранную вкладку — единственная
                      анимация здесь, и она показывает, куда переключились. */}
                  {on ? (
                    <motion.span
                      layoutId="overview-service-tab"
                      className="bg-primary absolute inset-x-2 bottom-0 h-0.5"
                      transition={{ duration: 0.18, ease: "easeOut" }}
                    />
                  ) : null}
                  <span className="relative flex items-center gap-1.5">
                    {t.service ? <ServiceDot service={t.service} /> : null}
                    {t.label}
                  </span>
                </button>
              )
            })}
          </div>
        ) : null}
      </PanelHead>

      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
        <div className="relative min-w-48 flex-1 sm:max-w-72">
          <Search
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
            aria-hidden="true"
          />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setLimit(PAGE)
            }}
            placeholder="Поиск по запросам"
            aria-label="Поиск по запросам"
            className="h-7 pl-8 text-[13px]"
          />
        </div>

        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => {
            const disabled = f.id === "changed" && !prevDate
            return (
              <button
                key={f.id}
                type="button"
                aria-pressed={filter === f.id}
                disabled={disabled}
                title={disabled ? "Появится после второго среза" : undefined}
                onClick={() => {
                  setFilter(f.id)
                  setLimit(PAGE)
                }}
                className={cn(
                  "h-7 cursor-pointer rounded-md border px-2 text-xs transition-colors",
                  "focus-visible:ring-ring focus-visible:ring-3 focus-visible:outline-none",
                  "disabled:cursor-not-allowed disabled:opacity-40",
                  filter === f.id
                    ? "border-primary bg-primary text-primary-foreground font-medium"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {f.label}
              </button>
            )
          })}
        </div>

        {groups.length ? (
          <select
            value={group}
            onChange={(e) => {
              setGroup(e.target.value)
              setLimit(PAGE)
            }}
            aria-label="Группа запросов"
            className="border-input bg-card h-7 cursor-pointer rounded-md border px-2 text-xs"
          >
            <option value="">Все группы</option>
            {groups.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        ) : null}

        <Button
          size="xs"
          variant="ghost"
          className="ml-auto"
          onClick={() => setSort((s) => (NEXT_SORT[s] === "change" && !prevDate ? "text" : NEXT_SORT[s]))}
          title="Порядок строк — нажмите, чтобы сменить"
        >
          <ArrowDownUp />
          {SORT_LABEL[sort]}
        </Button>

        {reset ? (
          <Button
            size="xs"
            variant="ghost"
            onClick={() => {
              setSearch("")
              setFilter("all")
              setGroup("")
            }}
          >
            <X />
            Сбросить
          </Button>
        ) : null}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-0 text-[13px]">
          <thead>
            <tr>
              <th
                rowSpan={withSub ? 2 : 1}
                scope="col"
                aria-sort={sort === "text" ? "ascending" : "none"}
                // w-full: свободное место забирает текст запроса, а ячейки дат
                // остаются компактными, как в Топвизоре, даже при двух срезах.
                className="bg-card sticky left-0 z-20 w-full min-w-56 border-r border-b px-3 py-2 text-left align-bottom text-[11px] font-semibold"
              >
                Запрос
              </th>
              <th
                rowSpan={withSub ? 2 : 1}
                scope="col"
                title={
                  prevDate
                    ? `Изменение ${shortDate(latest ?? "")} к ${shortDate(prevDate)}`
                    : "Появится после второго среза"
                }
                className="text-muted-foreground w-12 border-r border-b px-2 py-2 text-center align-bottom text-[11px] font-semibold"
              >
                Δ
              </th>
              {dates.map((d) => {
                const st = overview.stats[d]?.[statKey]
                return (
                  <th
                    key={d}
                    scope="col"
                    colSpan={cols.length}
                    className={cn(
                      "border-b border-l px-2 py-1.5 text-center align-bottom",
                      d === latest && "bg-accent/50",
                    )}
                  >
                    <div className="tnum text-[11px] font-semibold">
                      {shortDate(d)}
                      <span className="text-muted-foreground ml-1 font-normal">{weekday(d)}</span>
                    </div>
                    <div
                      className="tnum text-[15px] leading-tight font-semibold"
                      style={{ color: st?.pct == null ? "var(--muted-foreground)" : undefined }}
                      title={st ? `${st.found} из ${st.checked} с упоминанием` : "нет проверок"}
                    >
                      {pct(st?.pct)}
                      <span className="text-muted-foreground text-[10px]">%</span>
                    </div>
                  </th>
                )
              })}
            </tr>
            {withSub ? (
              <tr>
                {dates.map((d) =>
                  cols.map((s, i) => (
                    <th
                      key={`${d}-${s.id}`}
                      scope="col"
                      title={s.name}
                      className={cn(
                        "bg-muted/40 text-muted-foreground border-b px-1 py-1 text-center text-[10px] font-medium",
                        i === 0 && "border-l",
                        d === latest && "bg-accent/50",
                      )}
                    >
                      {s.short}
                    </th>
                  )),
                )}
              </tr>
            ) : null}
          </thead>

          <tbody>
            {visible.map((r) => {
              const ch = rowChanges(r, latest, prevDate, colIds)
              return (
                <tr key={r.query_id} className="hover:bg-muted/40 group">
                  <th
                    scope="row"
                    className="bg-card group-hover:bg-muted/40 sticky left-0 z-10 max-w-96 border-r border-b px-3 py-1.5 text-left font-normal transition-colors"
                  >
                    <span className="line-clamp-2" title={r.text}>
                      {r.text}
                    </span>
                    {r.group_tag ? (
                      <Badge variant="outline" className="mt-1">
                        {r.group_tag}
                      </Badge>
                    ) : null}
                    {!r.is_active ? (
                      <span className="text-muted-foreground ml-1.5 text-[10px]">выключен</span>
                    ) : null}
                  </th>

                  <td className="tnum border-r border-b px-1 text-center text-[11px] font-semibold">
                    <DeltaCell
                      changes={ch}
                      comparable={Boolean(prevDate)}
                      showCounts={withSub}
                      describe={(x) => `${nameOf(x.service)}: ${CHANGE[x.change].word}`}
                    />
                  </td>

                  {dates.map((d) =>
                    cols.map((s, i) => {
                      const cell = r.cells[d]?.[s.id]
                      const meta = statusMeta(cell?.status)
                      const prev = prevOf[d]
                      const change = prev ? cellChange(r.cells[prev]?.[s.id], cell) : null
                      const label = cell
                        ? [
                            `${s.name}, ${shortDate(d)}: ${meta.title}`,
                            cell.needs_review ? "требует проверки" : "",
                            change && prev ? `${CHANGE[change].word} (к ${shortDate(prev)})` : "",
                          ]
                            .filter(Boolean)
                            .join(", ")
                        : `${s.name}, ${shortDate(d)}: не проверялся`
                      return (
                        <td
                          key={`${d}-${s.id}`}
                          className={cn("border-b p-0 text-center", i === 0 && "border-l")}
                        >
                          {cell ? (
                            <button
                              type="button"
                              onClick={() => onOpen({ queryId: r.query_id, date: d, service: s.id })}
                              title={label}
                              aria-label={label}
                              className={cn(
                                "focus-visible:ring-ring relative grid h-7 w-full cursor-pointer place-items-center text-[11px] font-bold transition-[filter] hover:brightness-95 focus-visible:z-10 focus-visible:ring-3 focus-visible:outline-none dark:hover:brightness-125",
                                withSub ? "min-w-8" : "min-w-14",
                              )}
                              style={{
                                background: meta.soft,
                                color: meta.color,
                                boxShadow: change ? `inset 0 0 0 1.5px ${CHANGE[change].color}` : undefined,
                              }}
                            >
                              {meta.sign}
                              {change ? (
                                <span
                                  aria-hidden="true"
                                  className="absolute right-0.5 bottom-0 text-[8px] leading-none"
                                  style={{ color: CHANGE[change].color }}
                                >
                                  {CHANGE[change].sign}
                                </span>
                              ) : null}
                              {cell.needs_review ? (
                                <span
                                  aria-hidden="true"
                                  className="absolute top-0.5 right-0.5 size-1 rounded-full"
                                  style={{ background: "var(--warn)" }}
                                />
                              ) : null}
                            </button>
                          ) : (
                            <span
                              className={cn(
                                "text-muted-foreground/50 grid h-7 place-items-center text-[11px]",
                                withSub ? "min-w-8" : "min-w-14",
                              )}
                              title={label}
                            >
                              ·
                            </span>
                          )}
                        </td>
                      )
                    }),
                  )}
                </tr>
              )
            })}

            {visible.length === 0 ? (
              <tr>
                <td
                  colSpan={2 + dates.length * cols.length}
                  className="text-muted-foreground px-3 py-10 text-center text-sm"
                >
                  Под фильтр не попал ни один запрос
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <PanelFoot>
        <span>
          Показано {visible.length} из {rows.length}{" "}
          {plural(rows.length, "запроса", "запросов", "запросов")}
          {rows.length !== overview.rows.length ? ` (всего ${overview.rows.length})` : ""}
        </span>
        {visible.length < rows.length ? (
          <Button size="xs" variant="outline" onClick={() => setLimit((l) => l + PAGE)}>
            Показать ещё {Math.min(PAGE, rows.length - visible.length)}
          </Button>
        ) : null}
        <span className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1">
          {(["found", "not_found", "limit_reached", "error"] as const).map((st) => {
            const m = statusMeta(st)
            return (
              <span key={st} className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="grid size-3.5 place-items-center rounded-[3px] text-[9px] font-bold"
                  style={{ background: m.soft, color: m.color }}
                >
                  {m.sign}
                </span>
                {m.title}
              </span>
            )
          })}
          {prevDate
            ? (["gained", "lost"] as const).map((c) => (
                <span key={c} className="flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="grid size-3.5 place-items-center rounded-[3px] text-[8px]"
                    style={{ boxShadow: `inset 0 0 0 1.5px ${CHANGE[c].color}`, color: CHANGE[c].color }}
                  >
                    {CHANGE[c].sign}
                  </span>
                  {CHANGE[c].word}
                </span>
              ))
            : null}
        </span>
      </PanelFoot>
    </>
  )
}

function DeltaCell({
  changes,
  comparable,
  showCounts,
  describe,
}: {
  changes: ReturnType<typeof rowChanges>
  comparable: boolean
  showCounts: boolean
  describe: (x: { service: string; change: Change }) => string
}) {
  if (!comparable) return <span className="text-muted-foreground/50">·</span>
  if (!changes.gained && !changes.lost) return <span className="text-muted-foreground/60">—</span>
  const title = changes.detail.map(describe).join("\n")
  return (
    <span className="inline-flex flex-col items-center leading-tight" title={title}>
      <span className="sr-only">{title}</span>
      {changes.gained ? (
        <span aria-hidden="true" style={{ color: CHANGE.gained.color }}>
          ▲{showCounts ? changes.gained : ""}
        </span>
      ) : null}
      {changes.lost ? (
        <span aria-hidden="true" style={{ color: CHANGE.lost.color }}>
          ▼{showCounts ? changes.lost : ""}
        </span>
      ) : null}
    </span>
  )
}
