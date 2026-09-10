/** Карточка запроса: что именно ответил каждый сервис в выбранный день. */

import { useEffect, useState } from "react"
import { ExternalLink, ImageOff } from "lucide-react"

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { ServiceDot } from "@/components/bits"
import { api, errText } from "@/lib/api"
import { longDate, shortDate } from "@/lib/format"
import { statusMeta } from "@/lib/status"
import type { QueryDetail } from "@/lib/types"
import { useApp } from "@/store/app-store"

export interface QueryTarget {
  queryId: number
  date: string
  /** Сервис, по ячейке которого кликнули: с него и открываем карточку. */
  service?: string
}

export function QuerySheet({
  target,
  onClose,
}: {
  target: QueryTarget | null
  onClose: () => void
}) {
  const { services, project } = useApp()
  const [detail, setDetail] = useState<QueryDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<string>("")

  useEffect(() => {
    if (!target) return
    let alive = true
    setDetail(null)
    setError(null)
    api
      .get<QueryDetail>(`/api/queries/${target.queryId}/detail?date=${target.date}`)
      .then((d) => {
        if (!alive) return
        setDetail(d)
        const first = services.find((s) => d.by_service[s.id])?.id
        setTab(target.service && d.by_service[target.service] ? target.service : (first ?? ""))
      })
      .catch((e) => alive && setError(errText(e)))
    return () => {
      alive = false
    }
  }, [target, services])

  const present = services.filter((s) => detail?.by_service[s.id])

  return (
    <Sheet open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-[42rem]">
        <SheetHeader className="border-b">
          <SheetTitle className="pr-8 text-[15px] leading-snug">
            {detail?.text ?? "Загрузка…"}
          </SheetTitle>
          <SheetDescription>
            {project ? `${project.name} · ` : ""}
            срез за {target ? longDate(target.date) : "—"}
          </SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {error ? (
            <p className="text-destructive p-4 text-sm">{error}</p>
          ) : !detail ? (
            <div className="space-y-3 p-4">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-40 w-full" />
            </div>
          ) : present.length === 0 ? (
            <p className="text-muted-foreground p-4 text-sm">
              В этом срезе по запросу нет ни одного результата.
            </p>
          ) : (
            <Tabs value={tab} onValueChange={(v) => setTab(v as string)}>
              <div className="bg-card sticky top-0 z-10 border-b px-4 py-2.5">
                <TabsList variant="line" className="w-full">
                  {present.map((s) => {
                    const info = detail.by_service[s.id]
                    const meta = statusMeta(info.status)
                    return (
                      <TabsTrigger key={s.id} value={s.id} className="gap-1.5">
                        <span
                          aria-hidden="true"
                          className="grid size-4 place-items-center rounded text-[10px] font-bold"
                          style={{ background: meta.soft, color: meta.color }}
                        >
                          {meta.sign}
                        </span>
                        {s.short}
                      </TabsTrigger>
                    )
                  })}
                </TabsList>
              </div>

              {present.map((s) => {
                const info = detail.by_service[s.id]
                const meta = statusMeta(info.status)
                return (
                  <TabsContent key={s.id} value={s.id} className="space-y-4 p-4">
                    <div
                      className="rounded-xl border p-3"
                      style={{ background: meta.soft, borderColor: "transparent" }}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className="grid size-5 place-items-center rounded-md text-xs font-bold"
                          style={{ background: "var(--card)", color: meta.color }}
                          aria-hidden="true"
                        >
                          {meta.sign}
                        </span>
                        <span className="text-sm font-semibold" style={{ color: meta.color }}>
                          {meta.title}
                        </span>
                        {info.confidence !== null && info.confidence !== undefined ? (
                          <Badge variant="outline" className="ml-auto">
                            {info.detected_by || "детекция"} · {Math.round(info.confidence * 100)}%
                          </Badge>
                        ) : null}
                        {info.needs_review ? (
                          <Badge variant="secondary">требует проверки</Badge>
                        ) : null}
                      </div>
                      {info.evidence_quote ? (
                        <blockquote className="mt-2.5 border-l-2 pl-3 text-sm italic">
                          {info.evidence_quote}
                        </blockquote>
                      ) : null}
                      {info.error_message ? (
                        <p className="mt-2.5 font-mono text-xs break-words">{info.error_message}</p>
                      ) : null}
                      {info.mention_types?.length ? (
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {info.mention_types.map((t) => (
                            <Badge key={t} variant="outline">
                              {t}
                            </Badge>
                          ))}
                        </div>
                      ) : null}
                    </div>

                    <Section title="Скриншот выдачи">
                      {info.screenshot ? (
                        <a
                          href={info.screenshot}
                          target="_blank"
                          rel="noopener"
                          className="focus-visible:ring-ring block overflow-hidden rounded-lg border focus-visible:ring-3 focus-visible:outline-none"
                        >
                          <img
                            src={info.screenshot}
                            alt={`Скриншот ответа ${s.name} на запрос «${detail.text}»`}
                            loading="lazy"
                            className="w-full"
                          />
                        </a>
                      ) : (
                        <Muted icon={<ImageOff className="size-3.5" />}>
                          Скриншот не сохранён
                        </Muted>
                      )}
                    </Section>

                    {info.answer_text ? (
                      <Section title="Текст ответа">
                        <p className="bg-muted/60 max-h-72 overflow-y-auto rounded-lg p-3 text-sm whitespace-pre-wrap">
                          {info.answer_text}
                        </p>
                      </Section>
                    ) : null}

                    <Section title={`Источники${info.sources?.length ? ` (${info.sources.length})` : ""}`}>
                      {info.sources?.length ? (
                        <ul className="space-y-1">
                          {info.sources.map((u) => (
                            <li key={u}>
                              <a
                                href={u}
                                target="_blank"
                                rel="noopener"
                                className="text-primary inline-flex max-w-full items-center gap-1.5 text-xs hover:underline"
                                style={{ overflowWrap: "anywhere" }}
                              >
                                <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
                                <span className="min-w-0">{u}</span>
                              </a>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <Muted>Ссылок в ответе нет</Muted>
                      )}
                    </Section>

                    {info.history?.length ? (
                      <Section title="История по дням">
                        <div className="flex items-end gap-1 overflow-x-auto pb-1">
                          {info.history.map((h) => {
                            const hm = statusMeta(h.status)
                            return (
                              <div key={h.scan_date} className="min-w-9 flex-1 text-center">
                                <div
                                  className="grid h-7 place-items-center rounded-md text-[11px] font-bold"
                                  style={{ background: hm.soft, color: hm.color }}
                                  title={`${h.scan_date}: ${hm.title}`}
                                >
                                  {hm.sign}
                                </div>
                                <div className="text-muted-foreground tnum mt-1 text-[10px]">
                                  {shortDate(h.scan_date)}
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </Section>
                    ) : null}
                  </TabsContent>
                )
              })}
            </Tabs>
          )}
        </div>

        {detail ? (
          <div className="text-muted-foreground flex items-center gap-2 border-t px-4 py-2.5 text-xs">
            {present.map((s) => (
              <span key={s.id} className="flex items-center gap-1.5">
                <ServiceDot service={s} />
                {s.name}
              </span>
            ))}
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-muted-foreground mb-1.5 text-[10px] font-semibold tracking-[0.08em] uppercase">
        {title}
      </h3>
      {children}
    </div>
  )
}

function Muted({ icon, children }: { icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
      {icon}
      {children}
    </p>
  )
}
