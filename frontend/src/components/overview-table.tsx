/** Таблица как в Топвизоре: запросы в строках, даты в столбцах.
 *
 * Внутри каждой даты — по колонке на сервис, потому что «упоминание есть»
 * без указания, у кого именно, бесполезно. Первая колонка липкая: при
 * прокрутке вправо текст запроса должен оставаться на виду, иначе ячейки
 * теряют смысл.
 */

import { useMemo, useState } from "react"
import { ArrowDownUp, Search, X } from "lucide-react"
import { cn } from "cn"

import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { PanelFoot, PanelHead, ServiceDot } from "@/components/bits"
import { plural, pct, shortDate, weekday } from "@/lib/format"
import { statusMeta } from "@/lib/status"
import type { Overview, OverviewRow } from "@/lib/types"
import { useApp } from "@/store/app-store"
import type { QueryTarget } from "@/components/query-sheet"

type Filter = "all" | "found" | "not_found" | "review" | "problem"
type Sort = "text" | "visibility"

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Все" },
  { id: "found", label: "Есть упоминание" },
  { id: "not_found", label: "Без упоминаний" },
  { id: "review", label: "Требуют проверки" },
  { id: "problem", label: "Сбои проверки" },
]

const PAGE = 100

export function OverviewTable({
  overview,
  onOpen,
}: {
  overview: Overview
  onOpen: (t: QueryTarget) => void
}) {
  const { services } = useApp()
  const [search, setSearch] = useState("")
  const [filter, setFilter] = useState<Filter>("all")
  const [group, setGroup] = useState<string>("")
  const [sort, setSort] = useState<Sort>("text")
  const [limit, setLimit] = useState(PAGE)
  const [offServices, setOffServices] = useState<Set<string>>(new Set())

  const available = services.filter((s) => overview.services.includes(s.id))
  const cols = available.filter((s) => !offServices.has(s.id))
  // Даты в обратном порядке: свежий срез — сразу у текста запроса, за старыми
  // нужно прокручивать вправо, а не наоборот.
  const dates = useMemo(() => [...overview.dates].reverse(), [overview.dates])
  const latest = overview.summary?.date

  const groups = useMemo(() => {
    const set = new Set<string>()
    for (const r of overview.rows) if (r.group_tag) set.add(r.group_tag)
    return [...set].sort()
  }, [overview.rows])

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const cellsOf = (r: OverviewRow) =>
      Object.values(r.cells).flatMap((byService) => Object.values(byService))

    let out = overview.rows.filter((r) => {
      if (q && !r.text.toLowerCase().includes(q)) return false
      if (group && r.group_tag !== group) return false
      if (filter === "all") return true

      const cells = cellsOf(r)
      if (filter === "review") return cells.some((c) => c.needs_review)
      if (filter === "problem")
        return cells.some((c) => ["error", "captcha", "auth_required"].includes(c.status))

      // «Есть упоминание» и «без упоминаний» считаем по свежему срезу:
      // вопрос всегда про сегодняшнее положение дел, а не про всю историю.
      const last = latest ? Object.values(r.cells[latest] ?? {}) : []
      const found = last.some((c) => c.status === "found")
      return filter === "found" ? found : last.length > 0 && !found
    })

    if (sort === "visibility") {
      const score = (r: OverviewRow) => {
        const last = latest ? Object.values(r.cells[latest] ?? {}) : []
        const checked = last.filter((c) => c.status === "found" || c.status === "not_found")
        if (!checked.length) return -1
        return checked.filter((c) => c.status === "found").length / checked.length
      }
      out = [...out].sort((a, b) => score(b) - score(a) || a.text.localeCompare(b.text, "ru"))
    } else {
      out = [...out].sort((a, b) => a.text.localeCompare(b.text, "ru"))
    }
    return out
  }, [overview.rows, search, filter, group, sort, latest])

  const visible = rows.slice(0, limit)
  const reset = search || filter !== "all" || group

  return (
    <>
      <PanelHead
        title="Запросы по датам"
        hint={`${overview.dates.length} ${plural(overview.dates.length, "срез", "среза", "срезов")} · клик по ячейке открывает ответ`}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          {available.map((s) => {
            const off = offServices.has(s.id)
            return (
              <button
                key={s.id}
                type="button"
                aria-pressed={!off}
                onClick={() =>
                  setOffServices((prev) => {
                    const next = new Set(prev)
                    if (next.has(s.id)) next.delete(s.id)
                    else if (cols.length > 1) next.add(s.id)
                    return next
                  })
                }
                title={off ? `Показать колонку ${s.name}` : `Скрыть колонку ${s.name}`}
                className={cn(
                  "flex h-6 cursor-pointer items-center gap-1.5 rounded-md border px-1.5 text-[11px] transition-opacity",
                  "hover:bg-muted focus-visible:ring-ring focus-visible:ring-3 focus-visible:outline-none",
                  off && "opacity-40",
                )}
              >
                <ServiceDot service={s} />
                {s.short}
              </button>
            )
          })}
        </div>
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
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              aria-pressed={filter === f.id}
              onClick={() => {
                setFilter(f.id)
                setLimit(PAGE)
              }}
              className={cn(
                "h-7 cursor-pointer rounded-md border px-2 text-xs transition-colors",
                "focus-visible:ring-ring focus-visible:ring-3 focus-visible:outline-none",
                filter === f.id
                  ? "border-primary bg-primary text-primary-foreground font-medium"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
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
          onClick={() => setSort((s) => (s === "text" ? "visibility" : "text"))}
          title="Порядок строк"
        >
          <ArrowDownUp />
          {sort === "text" ? "По алфавиту" : "По видимости"}
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
                rowSpan={2}
                scope="col"
                aria-sort={sort === "text" ? "ascending" : "none"}
                className="bg-card sticky left-0 z-20 min-w-56 border-r border-b px-3 py-2 text-left align-bottom text-[11px] font-semibold"
              >
                Запрос
              </th>
              {dates.map((d) => {
                const total = overview.stats[d]?.["_all"]
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
                      style={{ color: total?.pct === null ? "var(--muted-foreground)" : undefined }}
                    >
                      {pct(total?.pct)}
                      <span className="text-muted-foreground text-[10px]">%</span>
                    </div>
                  </th>
                )
              })}
            </tr>
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
          </thead>

          <tbody>
            {visible.map((r) => (
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

                {dates.map((d) =>
                  cols.map((s, i) => {
                    const cell = r.cells[d]?.[s.id]
                    const meta = statusMeta(cell?.status)
                    const label = cell
                      ? `${s.name}, ${shortDate(d)}: ${meta.title}${cell.needs_review ? ", требует проверки" : ""}`
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
                            className="focus-visible:ring-ring relative grid h-7 w-full min-w-8 cursor-pointer place-items-center text-[11px] font-bold transition-[filter] hover:brightness-95 focus-visible:z-10 focus-visible:ring-3 focus-visible:outline-none dark:hover:brightness-125"
                            style={{ background: meta.soft, color: meta.color }}
                          >
                            {meta.sign}
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
                            className="text-muted-foreground/50 grid h-7 min-w-8 place-items-center text-[11px]"
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
            ))}

            {visible.length === 0 ? (
              <tr>
                <td
                  colSpan={1 + dates.length * cols.length}
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
        </span>
      </PanelFoot>
    </>
  )
}
