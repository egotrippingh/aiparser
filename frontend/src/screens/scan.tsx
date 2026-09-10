/** Скан: выбор сервисов, запуск/дозапуск и живой лог.
 *
 * Прогресс здесь намеренно не дублируется — он в шапке и виден со всех
 * вкладок. На этом экране остаётся то, чего в шапке нет: чем именно сейчас
 * занят прогон и почему пропущены запросы.
 */

import { useEffect, useMemo, useRef, useState } from "react"
import { motion, useReducedMotion } from "motion/react"
import { History, Play, RotateCcw } from "lucide-react"
import { cn } from "cn"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { ConfirmButton } from "@/components/confirm-button"
import { EmptyState, Panel, PanelFoot, PanelHead, ServiceDot } from "@/components/bits"
import { useResource } from "@/hooks/use-resource"
import { api, errText } from "@/lib/api"
import { plural } from "@/lib/format"
import type { Query, Resumable } from "@/lib/types"
import { useApp } from "@/store/app-store"
import type { View } from "@/hooks/use-hash-route"

export function ScanScreen({ onView }: { onView: (v: View) => void }) {
  const {
    project,
    projectId,
    services,
    scan,
    scanLog,
    clearScanLog,
    watchScan,
    refreshScan,
    dataVersion,
  } = useApp()
  const reduce = useReducedMotion()
  const logRef = useRef<HTMLDivElement>(null)
  const [chosen, setChosen] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)

  const ready = useMemo(() => services.filter((s) => s.has_adapter), [services])
  const notReady = useMemo(() => services.filter((s) => !s.has_adapter), [services])

  // Первичный выбор — все работающие сервисы: обычно сканируют всё сразу,
  // а снять галочку дешевле, чем расставить пять.
  useEffect(() => {
    setChosen((prev) => (prev.size ? prev : new Set(ready.map((s) => s.id))))
  }, [ready])

  const { data: active } = useResource<Query[]>(
    projectId
      ? () => api.get<Query[]>(`/api/projects/${projectId}/queries?only_active=true`)
      : null,
    [projectId, dataVersion],
  )
  const { data: resumable, reload: reloadResumable } = useResource<Resumable | null>(
    projectId ? () => api.get<Resumable | null>(`/api/projects/${projectId}/resumable`) : null,
    [projectId, dataVersion],
  )

  const activeCount = active?.length ?? 0
  const running = scan !== null && scan.state !== "finished"

  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [scanLog])

  async function launch(resume: boolean) {
    if (!projectId) return
    if (!activeCount) {
      toast.error("Нет активных запросов — добавьте их на вкладке «Запросы»")
      return
    }
    if (!chosen.size) {
      toast.error("Выберите хотя бы один сервис")
      return
    }
    setBusy(true)
    try {
      if (!resume) clearScanLog()
      const res = await api.post<{ scan_id: number }>(`/api/projects/${projectId}/scans`, {
        services: [...chosen],
        resume,
      })
      watchScan(res.scan_id)
      await refreshScan()
      reloadResumable()
    } catch (e) {
      toast.error(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {resumable ? (
        <Alert>
          <History />
          <AlertTitle>Незаконченный скан от {resumable.scan_date}</AlertTitle>
          <AlertDescription>
            <p>
              Проверено {resumable.conclusive} из {resumable.expected}, осталось{" "}
              {resumable.remaining}. Бесплатные тарифы упираются в лимит примерно на сороковом
              запросе, поэтому большую базу приходится добирать за несколько заходов. Дозапуск
              продолжит с места остановки и допишет результаты в тот же срез.
            </p>
          </AlertDescription>
        </Alert>
      ) : null}

      <Panel>
        <PanelHead title="Сервисы" hint="выберите, какие проверять" />
        <div className="grid gap-1.5 p-4 sm:grid-cols-2 lg:grid-cols-3">
          {ready.map((s) => {
            const on = chosen.has(s.id)
            return (
              <Label
                key={s.id}
                className={cn(
                  "flex min-h-10 cursor-pointer items-start gap-2.5 rounded-lg border p-2.5 transition-colors",
                  on ? "border-primary/40 bg-accent/40" : "hover:bg-muted/60",
                )}
              >
                <Checkbox
                  checked={on}
                  disabled={running}
                  onCheckedChange={(v) =>
                    setChosen((prev) => {
                      const next = new Set(prev)
                      if (v) next.add(s.id)
                      else next.delete(s.id)
                      return next
                    })
                  }
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-[13px] font-medium">
                    <ServiceDot service={s} />
                    {s.name}
                  </span>
                  <span className="text-muted-foreground mt-0.5 block text-xs font-normal">
                    {s.note}
                  </span>
                </span>
              </Label>
            )
          })}
          {notReady.map((s) => (
            <div
              key={s.id}
              className="flex min-h-10 items-start gap-2.5 rounded-lg border border-dashed p-2.5 opacity-60"
              title="Адаптер для этого сервиса ещё не реализован"
            >
              <Checkbox checked={false} disabled className="mt-0.5" />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-[13px] font-medium">
                  <ServiceDot service={s} />
                  {s.name}
                </span>
                <span className="text-muted-foreground mt-0.5 block text-xs">
                  Адаптер ещё не реализован — сканировать нельзя
                </span>
              </span>
            </div>
          ))}
        </div>

        <PanelFoot>
          <span>
            {activeCount} {plural(activeCount, "активный запрос", "активных запроса", "активных запросов")}{" "}
            × {chosen.size} {plural(chosen.size, "сервис", "сервиса", "сервисов")} ={" "}
            <b className="tnum text-foreground">{activeCount * chosen.size}</b>{" "}
            {plural(activeCount * chosen.size, "проверка", "проверки", "проверок")}
            {chosen.size > 1
              ? project?.parallel_scan
                ? " · системы идут одновременно"
                : " · системы идут по очереди (параллельно — в настройках проекта)"
              : ""}
          </span>
          {!activeCount ? (
            <Button size="xs" variant="ghost" onClick={() => onView("queries")}>
              Добавить запросы
            </Button>
          ) : null}
          <div className="ml-auto flex items-center gap-2">
            {resumable ? (
              <ConfirmButton
                size="sm"
                variant="outline"
                disabled={running || busy}
                title="Начать скан заново?"
                confirmLabel="Начать заново"
                description="Незаконченный скан останется в истории, но продолжить его будет уже нельзя — оставшиеся запросы придётся проверять с нуля."
                onConfirm={() => launch(false)}
              >
                <RotateCcw />
                Начать заново
              </ConfirmButton>
            ) : null}
            <Button size="sm" disabled={running || busy} onClick={() => launch(true)}>
              <Play />
              {running
                ? "Скан уже идёт"
                : resumable
                  ? "Продолжить скан"
                  : "Запустить скан"}
            </Button>
          </div>
        </PanelFoot>
      </Panel>

      <Panel>
        <PanelHead title="Лог" hint="прогресс виден в шапке с любой вкладки">
          {scanLog.length && !running ? (
            <Button size="xs" variant="ghost" onClick={clearScanLog}>
              Очистить
            </Button>
          ) : null}
        </PanelHead>
        {scanLog.length === 0 ? (
          <EmptyState
            icon={<Play />}
            title="Скан ещё не запускался"
            text="Здесь построчно появится, что происходит с каждым запросом: какой сервис отвечает, где нашлось упоминание и на чём прогон споткнулся."
          />
        ) : (
          <div
            ref={logRef}
            role="log"
            aria-live="polite"
            aria-label="Лог скана"
            className="bg-muted/40 max-h-96 overflow-y-auto p-3 font-mono text-xs"
          >
            {scanLog.map((l) => (
              <motion.div
                key={l.id}
                initial={reduce ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.15 }}
                className="py-0.5"
                style={{
                  color:
                    l.kind === "ok"
                      ? "var(--ok)"
                      : l.kind === "err"
                        ? "var(--bad)"
                        : "var(--muted-foreground)",
                }}
              >
                {l.text}
              </motion.div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
