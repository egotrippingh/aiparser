import { useEffect, useState } from "react"
import { MotionConfig } from "motion/react"
import { ThemeProvider } from "next-themes"
import { FolderPlus, LogIn, Play } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Toaster } from "@/components/ui/sonner"
import { AppShell } from "@/components/app-shell"
import { EmptyState, Panel } from "@/components/bits"
import { NewProjectDialog } from "@/components/new-project-dialog"
import { useHashRoute, type View } from "@/hooks/use-hash-route"
import { api } from "@/lib/api"
import { DashboardScreen } from "@/screens/dashboard"
import { QueriesScreen } from "@/screens/queries"
import { ScanScreen } from "@/screens/scan"
import { SettingsScreen } from "@/screens/settings"
import { AppProvider, useApp } from "@/store/app-store"

const TITLES: Record<View, string> = {
  dashboard: "Дашборд",
  queries: "Запросы",
  scan: "Скан",
  settings: "Настройки",
}

function Workspace() {
  const { project, projects, meta, applyProject, selectProject } = useApp()
  const [view, go] = useHashRoute()
  const [newProject, setNewProject] = useState(false)
  const [needsAccount, setNeedsAccount] = useState(false)

  useEffect(() => {
    let active = true
    api.get<{ enabled: boolean; connected: boolean }>("/api/account/status")
      .then((account) => { if (active) setNeedsAccount(account.enabled && !account.connected) })
      .catch(() => undefined)
    return () => { active = false }
  }, [view])

  const subtitle = project
    ? [project.brand_domains?.[0] || project.brand_name, project.region_code && `регион ${project.region_code}`]
        .filter(Boolean)
        .join(" · ")
    : undefined

  return (
    <>
      <AppShell
        view={view}
        onView={go}
        onCreateProject={() => setNewProject(true)}
        title={project ? `${TITLES[view]} — ${project.name}` : TITLES[view]}
        subtitle={view === "dashboard" ? subtitle : undefined}
        actions={
          project && view !== "scan" ? (
            <Button size="sm" onClick={() => go("scan")}>
              <Play />
              Запустить скан
            </Button>
          ) : null
        }
      >
        {needsAccount && view !== "settings" && <div className="bg-primary/10 border-primary/30 mb-4 flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3">
          <LogIn className="text-primary size-5 shrink-0" aria-hidden="true" />
          <div className="min-w-56 flex-1"><strong className="text-sm">Подключите аккаунт к агенту</strong><p className="text-muted-foreground text-xs">В кабинете откройте «Аккаунт», получите код и введите его в настройках агента.</p></div>
          <Button size="sm" onClick={() => go("settings")}>Войти в агент</Button>
        </div>}
        {!project && view !== "settings" ? (
          <Panel>
            <EmptyState
              icon={<FolderPlus />}
              title={meta && projects.length === 0 ? "Проектов пока нет" : "Загрузка…"}
              text={
                meta && projects.length === 0
                  ? "Создайте первый проект, чтобы начать отслеживать, как ИИ-поисковики упоминают ваш бренд."
                  : undefined
              }
              action={
                meta && projects.length === 0 ? (
                  <Button onClick={() => setNewProject(true)}>Создать проект</Button>
                ) : null
              }
            />
          </Panel>
        ) : view === "dashboard" ? (
          <DashboardScreen onView={go} />
        ) : view === "queries" ? (
          <QueriesScreen />
        ) : view === "scan" ? (
          <ScanScreen onView={go} />
        ) : (
          <SettingsScreen />
        )}
      </AppShell>

      <NewProjectDialog
        open={newProject}
        onOpenChange={setNewProject}
        onCreated={(p) => {
          applyProject(p)
          selectProject(p.id)
          go("settings")
        }}
      />
    </>
  )
}

export default function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      {/* reducedMotion="user": при включённом в системе «уменьшении движения»
          Motion сам выключает сдвиги и layout-анимации, оставляя прозрачность. */}
      <MotionConfig reducedMotion="user">
        <AppProvider>
          <Workspace />
          <Toaster position="bottom-right" richColors closeButton />
        </AppProvider>
      </MotionConfig>
    </ThemeProvider>
  )
}
