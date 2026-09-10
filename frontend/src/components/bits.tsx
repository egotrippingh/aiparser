/** Мелкие общие элементы: точка сервиса, панель-секция, пустой экран. */

import { cn } from "cn"
import type { ReactNode } from "react"

import type { ServiceMeta } from "@/lib/types"

export function ServiceDot({
  service,
  className,
}: {
  service: ServiceMeta | undefined
  className?: string
}) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block size-2 shrink-0 rounded-[3px]", className)}
      style={{ background: service ? `var(${service.color})` : "var(--muted-foreground)" }}
    />
  )
}

export function Panel({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={cn(
        "bg-card overflow-hidden rounded-xl border shadow-[0_1px_2px_rgb(15_23_42/0.04)]",
        className,
      )}
    >
      {children}
    </section>
  )
}

export function PanelHead({
  title,
  hint,
  children,
  className,
}: {
  title: ReactNode
  hint?: ReactNode
  children?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-2 border-b px-4 py-3",
        className,
      )}
    >
      <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
      {hint ? <span className="text-muted-foreground text-xs">{hint}</span> : null}
      {children ? <div className="ml-auto flex items-center gap-2">{children}</div> : null}
    </div>
  )
}

export function PanelFoot({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-2 border-t px-4 py-3 text-xs",
        className,
      )}
    >
      {children}
    </div>
  )
}

export function EmptyState({
  icon,
  title,
  text,
  action,
}: {
  icon: ReactNode
  title: string
  text?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div
        className="bg-muted text-muted-foreground mb-4 flex size-11 items-center justify-center rounded-xl [&_svg]:size-5"
        aria-hidden="true"
      >
        {icon}
      </div>
      <p className="text-[15px] font-semibold">{title}</p>
      {text ? (
        <p className="text-muted-foreground mt-1.5 max-w-md text-sm text-balance">{text}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}

/** Стрелка изменения в п.п. Знак дублируется словом, цвет — не единственный
 *  носитель смысла (иначе при дальтонизме рост и падение неразличимы). */
export function Delta({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return null
  const dir = value > 0 ? "up" : value < 0 ? "down" : "flat"
  const label = dir === "up" ? "рост" : dir === "down" ? "падение" : "без изменений"
  const color =
    dir === "up" ? "var(--ok)" : dir === "down" ? "var(--bad)" : "var(--muted-foreground)"
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium"
      style={{ color }}
      title={label}
    >
      <span aria-hidden="true">{dir === "up" ? "▲" : dir === "down" ? "▼" : "•"}</span>
      <span className="sr-only">{label} на </span>
      {Math.abs(value).toFixed(1).replace(/\.0$/, "")} п.п.
    </span>
  )
}
