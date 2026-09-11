/** Полоса прогресса скана — видна с любой вкладки.
 *
 * Живёт в оболочке, а не во вкладке «Скан», потому что скан идёт часами:
 * пользователь уходит смотреть дашборд и должен видеть, где сейчас прогон.
 */

import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { Pause, Play, Square } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { ServiceDot } from "@/components/bits"
import { api, errText } from "@/lib/api"
import { fmtDur } from "@/lib/format"
import { useApp } from "@/store/app-store"
import { ConfirmButton } from "@/components/confirm-button"

export function ScanBar() {
  const { scan, serviceById, refreshScan } = useApp()
  const reduce = useReducedMotion()

  const paused = scan?.state === "paused"
  const svc = serviceById(scan?.current_service)
  // При параллельном скане идут сразу несколько систем — показываем все.
  const running = (scan?.running_services ?? []).map((id) => serviceById(id)).filter(Boolean)

  async function send(action: "pause" | "resume" | "stop") {
    if (!scan) return
    try {
      await api.post(`/api/scans/${scan.scan_id}/${action}`)
      await refreshScan()
    } catch (e) {
      toast.error(errText(e))
    }
  }

  return (
    <AnimatePresence initial={false}>
      {scan && scan.state !== "finished" ? (
        <motion.div
          initial={reduce ? false : { height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
          transition={{ duration: 0.25, ease: [0.22, 0.61, 0.36, 1] }}
          className="overflow-hidden border-b"
          style={{ background: paused ? "var(--warn-soft)" : "var(--card)" }}
        >
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 md:px-6">
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] font-medium">
              {running.length > 1 ? (
                <>
                  <span className="text-muted-foreground font-normal">параллельно:</span>
                  {running.map((s) => {
                    const p = scan.services?.[s!.id]
                    return (
                      <span key={s!.id} className="flex items-center gap-1.5">
                        <ServiceDot service={s} />
                        {s!.name}
                        {p ? (
                          <span className="tnum text-muted-foreground text-xs font-normal">
                            {p.done}/{p.total}
                          </span>
                        ) : null}
                      </span>
                    )
                  })}
                </>
              ) : (
                <span className="flex items-center gap-2">
                  <ServiceDot service={svc} />
                  {svc ? svc.name : "Скан"}
                </span>
              )}
              {paused ? <span className="text-muted-foreground">· на паузе</span> : null}
            </span>

            <div
              className="bg-muted relative h-1.5 min-w-32 flex-1 overflow-hidden rounded-full"
              role="progressbar"
              aria-valuenow={scan.percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Прогресс скана"
            >
              <motion.i
                className="absolute inset-y-0 left-0 block rounded-full"
                style={{ background: paused ? "var(--warn)" : "var(--primary)" }}
                animate={{ width: `${scan.percent}%` }}
                transition={{ duration: reduce ? 0 : 0.4, ease: "easeOut" }}
              />
            </div>

            <span className="tnum text-muted-foreground text-xs">
              {scan.done} / {scan.total} · {scan.percent}%
            </span>
            <span className="tnum text-muted-foreground hidden text-xs sm:inline">
              осталось ~{fmtDur(scan.eta_sec)}
            </span>

            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => send(paused ? "resume" : "pause")}
                title={paused ? "Продолжить скан" : "Пауза начнётся после текущего запроса"}
              >
                {paused ? <Play /> : <Pause />}
                {paused ? "Продолжить" : "Пауза"}
              </Button>
              <ConfirmButton
                size="sm"
                variant="destructive"
                title="Остановить скан?"
                description="Уже проверенные запросы останутся в базе — скан можно будет продолжить дозапуском."
                confirmLabel="Остановить"
                onConfirm={() => send("stop")}
              >
                <Square />
                Стоп
              </ConfirmButton>
            </div>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
