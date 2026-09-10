/** Запросы проекта: массовое добавление, импорт файла, список с переключателями. */

import { useMemo, useRef, useState } from "react"
import { FileUp, Plus, Search, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import { ConfirmButton } from "@/components/confirm-button"
import { EmptyState, Panel, PanelFoot, PanelHead } from "@/components/bits"
import { useResource } from "@/hooks/use-resource"
import { api, errText } from "@/lib/api"
import { plural, splitLines } from "@/lib/format"
import type { Query } from "@/lib/types"
import { useApp } from "@/store/app-store"

interface AddResult {
  added: number
  skipped: number
  total: number
}

export function QueriesScreen() {
  const { projectId } = useApp()
  const [bulk, setBulk] = useState("")
  const [groupTag, setGroupTag] = useState("")
  const [search, setSearch] = useState("")
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const { data, error, loading, reload, set } = useResource<Query[]>(
    projectId ? () => api.get<Query[]>(`/api/projects/${projectId}/queries`) : null,
    [projectId],
  )

  const queries = data ?? []
  const lines = useMemo(() => splitLines(bulk), [bulk])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return q ? queries.filter((x) => x.text.toLowerCase().includes(q)) : queries
  }, [queries, search])

  function report(res: AddResult, verb: string) {
    const parts = [`${verb} ${res.added}`]
    if (res.skipped) parts.push(`пропущено дубликатов ${res.skipped}`)
    toast.success(parts.join(", "))
    reload()
  }

  async function add() {
    if (!projectId || !lines.length) return
    setBusy(true)
    try {
      const res = await api.post<AddResult>(`/api/projects/${projectId}/queries`, {
        text: bulk,
        group_tag: groupTag.trim() || null,
      })
      setBulk("")
      report(res, "Добавлено")
    } catch (e) {
      toast.error(errText(e))
    } finally {
      setBusy(false)
    }
  }

  async function upload(file: File) {
    if (!projectId) return
    setBusy(true)
    try {
      const res = await api.upload<AddResult>(
        `/api/projects/${projectId}/queries/upload`,
        file,
        { group_tag: groupTag.trim() },
      )
      report(res, "Загружено")
    } catch (e) {
      toast.error(errText(e))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  async function toggle(q: Query, active: boolean) {
    if (!projectId) return
    set((prev) => prev.map((x) => (x.id === q.id ? { ...x, is_active: active } : x)))
    try {
      await api.patch(`/api/projects/${projectId}/queries/${q.id}?is_active=${active}`)
    } catch (e) {
      toast.error(errText(e))
      set((prev) => prev.map((x) => (x.id === q.id ? { ...x, is_active: !active } : x)))
    }
  }

  async function remove(q: Query) {
    if (!projectId) return
    try {
      await api.del(`/api/projects/${projectId}/queries/${q.id}`)
      set((prev) => prev.filter((x) => x.id !== q.id))
      toast.success("Запрос удалён")
    } catch (e) {
      toast.error(errText(e))
    }
  }

  const activeCount = queries.filter((q) => q.is_active).length

  return (
    <div className="space-y-4">
      <Panel>
        <PanelHead
          title="Добавить запросы"
          hint="по одному в строке · дубликаты внутри проекта пропускаются"
        />
        <div className="space-y-3 p-4">
          <div className="space-y-1.5">
            <Label htmlFor="bulk">Список запросов</Label>
            <Textarea
              id="bulk"
              value={bulk}
              onChange={(e) => setBulk(e.target.value)}
              rows={5}
              placeholder={"купить крепёж оптом от производителя\nпоставщик метизов оптом в москве"}
              className="font-mono text-[13px]"
            />
            <p className="text-muted-foreground text-xs">
              {lines.length
                ? `${lines.length} ${plural(lines.length, "строка", "строки", "строк")} к добавлению`
                : "Каждая строка станет отдельным запросом."}
            </p>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <div className="w-full space-y-1.5 sm:w-56">
              <Label htmlFor="group">Тег группы</Label>
              <Input
                id="group"
                value={groupTag}
                onChange={(e) => setGroupTag(e.target.value)}
                placeholder="необязательно"
              />
            </div>
            <Button onClick={add} disabled={busy || !lines.length}>
              <Plus />
              Добавить
            </Button>
            <span className="text-muted-foreground text-xs">или</span>
            <Button variant="outline" disabled={busy} onClick={() => fileRef.current?.click()}>
              <FileUp />
              Загрузить .txt / .csv
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.csv"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) upload(f)
              }}
            />
          </div>
          <p className="text-muted-foreground text-xs">
            В csv берётся первая колонка; разделитель определяется сам, так что выгрузки из
            Топвизора и Excel в русской локали загружаются как есть. Тег группы применится ко
            всем добавленным строкам.
          </p>
        </div>
      </Panel>

      <Panel>
        <PanelHead
          title="Список запросов"
          hint={
            queries.length
              ? `${activeCount} из ${queries.length} активны — в скан пойдут только они`
              : undefined
          }
        >
          <div className="relative w-48">
            <Search
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
              aria-hidden="true"
            />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск"
              aria-label="Поиск по запросам"
              className="h-7 pl-8 text-[13px]"
            />
          </div>
        </PanelHead>

        {loading && !data ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : error ? (
          <EmptyState icon={<Search />} title="Не удалось загрузить список" text={error} />
        ) : queries.length === 0 ? (
          <EmptyState
            icon={<Plus />}
            title="Запросов пока нет"
            text="Добавьте их сверху — списком или файлом. Именно эти фразы программа будет задавать ИИ-поисковикам."
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-muted-foreground border-b text-[11px]">
                    <th scope="col" className="px-4 py-2 text-left font-semibold">
                      Запрос
                    </th>
                    <th scope="col" className="px-3 py-2 text-left font-semibold">
                      Группа
                    </th>
                    <th scope="col" className="px-3 py-2 text-center font-semibold">
                      Активен
                    </th>
                    <th scope="col" className="w-12 px-3 py-2 text-right font-semibold">
                      <span className="sr-only">Действия</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((q) => (
                    <tr key={q.id} className="hover:bg-muted/40 border-b last:border-0">
                      <td className="px-4 py-1.5">{q.text}</td>
                      <td className="px-3 py-1.5">
                        {q.group_tag ? (
                          <Badge variant="outline">{q.group_tag}</Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-center">
                        <Switch
                          checked={Boolean(q.is_active)}
                          onCheckedChange={(v) => toggle(q, Boolean(v))}
                          aria-label={`Запрос «${q.text}» участвует в скане`}
                        />
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        <ConfirmButton
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Удалить запрос «${q.text}»`}
                          title="Удалить запрос"
                          confirmLabel="Удалить"
                          onConfirm={() => remove(q)}
                          description={
                            <>
                              Запрос «{q.text}» и вся история его проверок будут удалены. Это
                              необратимо. Если нужно только исключить его из ближайших сканов —
                              выключите переключатель «Активен».
                            </>
                          }
                        >
                          <Trash2 />
                        </ConfirmButton>
                      </td>
                    </tr>
                  ))}
                  {filtered.length === 0 ? (
                    <tr>
                      <td
                        colSpan={4}
                        className="text-muted-foreground px-4 py-8 text-center text-sm"
                      >
                        Ничего не нашлось
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <PanelFoot>
              Показано {filtered.length} из {queries.length}
            </PanelFoot>
          </>
        )}
      </Panel>
    </div>
  )
}
