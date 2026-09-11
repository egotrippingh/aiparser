/** Оболочка окна: список проектов, вкладки, шапка и прогресс скана. */

import {
  LayoutGrid,
  ListOrdered,
  Monitor,
  Moon,
  Plus,
  Radar,
  Settings2,
  Sun,
} from "lucide-react"
import { useTheme } from "next-themes"
import { cn } from "cn"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScanBar } from "@/components/scan-bar"
import { useApp } from "@/store/app-store"
import type { View } from "@/hooks/use-hash-route"

const NAV: { id: View; label: string; icon: typeof LayoutGrid }[] = [
  { id: "dashboard", label: "Дашборд", icon: LayoutGrid },
  { id: "queries", label: "Запросы", icon: ListOrdered },
  { id: "scan", label: "Скан", icon: Radar },
  { id: "settings", label: "Настройки", icon: Settings2 },
]

function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const order = ["system", "light", "dark"] as const
  const icons = { system: Monitor, light: Sun, dark: Moon }
  const labels = { system: "как в системе", light: "светлая", dark: "тёмная" }
  const current = (order.includes(theme as (typeof order)[number]) ? theme : "system") as
    | "system"
    | "light"
    | "dark"
  const Icon = icons[current]

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      title={`Тема: ${labels[current]}`}
      aria-label={`Тема: ${labels[current]}. Переключить`}
      onClick={() => setTheme(order[(order.indexOf(current) + 1) % order.length])}
    >
      <Icon />
    </Button>
  )
}

export function AppShell({
  view,
  onView,
  onCreateProject,
  title,
  subtitle,
  actions,
  children,
}: {
  view: View
  onView: (v: View) => void
  onCreateProject: () => void
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  const { meta, projects, projectId, selectProject, scan } = useApp()

  return (
    <div className="flex h-full min-h-0">
      <aside className="bg-card hidden w-56 shrink-0 flex-col border-r md:flex">
        <div className="flex items-center gap-2.5 border-b px-4 py-3">
          <div className="min-w-0 leading-tight">
            <div className="truncate text-[14px] font-bold">AI Mentions</div>
            <div className="text-muted-foreground truncate text-[11px]">
              {meta ? `${meta.portable ? "portable" : "установлено"} · v${meta.version}` : "…"}
            </div>
          </div>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </div>

        {/* Разделы — сверху, а не прижаты к низу: низ окна у пользователя
            перекрывался (панель задач, панель загрузок браузера), и
            «Скан» с «Настройками» уходили за край. Длинный список проектов
            прокручивается ниже и разделы не выталкивает. */}
        <nav className="flex shrink-0 flex-col gap-0.5 border-b p-2" aria-label="Разделы">
          {NAV.map(({ id, label, icon: Icon }) => {
            const active = id === view
            return (
              <button
                key={id}
                type="button"
                onClick={() => onView(id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex h-9 cursor-pointer items-center gap-2.5 rounded-sm px-2.5 text-[13px] transition-colors",
                  active
                    ? "bg-muted text-foreground before:bg-primary font-semibold before:absolute before:inset-y-2 before:left-0 before:w-0.5"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                {label}
                {id === "scan" && scan && scan.state !== "finished" ? (
                  <Badge variant="secondary" className="tnum ml-auto">
                    {scan.percent}%
                  </Badge>
                ) : null}
              </button>
            )
          })}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          <div className="text-muted-foreground px-2 py-1.5 text-[10px] font-semibold tracking-[0.08em] uppercase">
            Проекты
          </div>
          <div className="flex flex-col gap-0.5">
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => selectProject(p.id)}
                aria-current={p.id === projectId ? "true" : undefined}
                className={cn(
                  "flex h-8 w-full cursor-pointer items-center gap-2 rounded-sm px-2 text-left text-[13px] transition-colors",
                  p.id === projectId
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <span
                  aria-hidden="true"
                  className="size-1.5 shrink-0 rounded-full"
                  style={{
                    background: p.id === projectId ? "var(--primary)" : "var(--muted-foreground)",
                  }}
                />
                <span className="truncate">{p.name}</span>
              </button>
            ))}
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground justify-start"
              onClick={onCreateProject}
            >
              <Plus />
              Новый проект
            </Button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-card flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-4 py-2.5 md:px-6">
          <div className="min-w-0">
            <h1 className="truncate text-[15px] leading-tight font-semibold tracking-tight">
              {title}
            </h1>
            {subtitle ? (
              <div className="text-muted-foreground truncate text-xs">{subtitle}</div>
            ) : null}
          </div>
          {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
        </header>

        <ScanBar />

        {/* Вкладки снизу — на узком окне сайдбар скрыт, но переключаться надо. */}
        <nav
          className="bg-card order-last flex shrink-0 border-t md:hidden"
          aria-label="Разделы"
        >
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => onView(id)}
              aria-current={id === view ? "page" : undefined}
              className={cn(
                "flex min-h-12 flex-1 cursor-pointer flex-col items-center justify-center gap-0.5 py-1.5 text-[11px] transition-colors",
                id === view ? "text-primary font-medium" : "text-muted-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              {label}
            </button>
          ))}
        </nav>

        <main className="min-h-0 flex-1 overflow-y-auto px-4 py-4 md:px-6 md:py-5">
          {children}
        </main>
      </div>
    </div>
  )
}
