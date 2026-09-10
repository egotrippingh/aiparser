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
      className={cn("inline-block size-2 shrink-0 rounded-full", className)}
      style={{ background: service ? `var(${service.color})` : "var(--muted-foreground)" }}
    />
  )
}

/** Секция экрана: белый лист с тонкой рамкой — без теней и крупных скруглений. */
export function Panel({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn("bg-card overflow-hidden rounded-md border", className)}>
      {children}
    </section>
  )
}

/** Шапка секции. Пояснение `hint` не занимает строку — оно в подсказке
 *  к заголовку: в рабочем инструменте подписи под каждым блоком мешают. */
export function PanelHead({
  title,
  hint,
  children,
  className,
}: {
  title: ReactNode
  hint?: string
  children?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn("flex min-h-10 flex-wrap items-center gap-x-3 gap-y-2 border-b px-4 py-2", className)}
    >
      <h2 className="text-[13px] font-semibold" title={hint}>
        {title}
      </h2>
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
        "text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-2 border-t px-4 py-2 text-xs",
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
    <div className="flex flex-col items-center px-6 py-10 text-center">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <span className="text-muted-foreground [&_svg]:size-4" aria-hidden="true">
          {icon}
        </span>
        {title}
      </p>
      {text ? <p className="text-muted-foreground mt-1 max-w-md text-[13px]">{text}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}

/** Изменение в п.п. Знак дублируется словом для скринридера, цвет — не
 *  единственный носитель смысла (иначе при дальтонизме рост и падение
 *  неразличимы). */
export function Delta({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return null
  const dir = value > 0 ? "up" : value < 0 ? "down" : "flat"
  const label = dir === "up" ? "рост" : dir === "down" ? "падение" : "без изменений"
  const color =
    dir === "up" ? "var(--ok)" : dir === "down" ? "var(--bad)" : "var(--muted-foreground)"
  const sign = dir === "up" ? "+" : dir === "down" ? "−" : "±"
  return (
    <span className="tnum inline-flex items-center text-xs font-medium" style={{ color }} title={label}>
      <span className="sr-only">{label} на </span>
      {sign}
      {Math.abs(value).toFixed(1).replace(/\.0$/, "")} п.п.
    </span>
  )
}
