/** Настройки: проект и бренд, браузер с аккаунтами, скорость скана, LLM. */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { Download, LogIn, Save, Trash2 } from "lucide-react"
import { cn } from "cn"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import { ConfirmButton } from "@/components/confirm-button"
import { AgentSettingsPanel } from "@/components/agent-settings-panel"
import { Panel, PanelFoot, PanelHead, ServiceDot } from "@/components/bits"
import { useResource } from "@/hooks/use-resource"
import { api, errText } from "@/lib/api"
import { fmtWhen, splitLines } from "@/lib/format"
import type { BrowserStatus, Project, ServiceAuth } from "@/lib/types"
import { useApp } from "@/store/app-store"

/* --- мелкие обёртки формы ---------------------------------------------- */

function Field({
  label,
  hint,
  htmlFor,
  className,
  children,
}: {
  label: ReactNode
  hint?: ReactNode
  htmlFor?: string
  className?: string
  children: ReactNode
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
    </div>
  )
}

/* --- статус входа в сервис --------------------------------------------- */

/** Две половины правды: кука на диске и то, что сервис ответил в последний
 *  реальный прогон. Кука может лежать, а сервис её уже не принимать —
 *  поэтому «нужен вход» важнее, чем «есть на диске», и показывается первым. */
function authBadge(a: ServiceAuth | undefined): {
  tone: "ok" | "warn" | "off" | "busy"
  label: string
  sub: string
} {
  if (!a) return { tone: "off", label: "вход не выполнен", sub: "" }
  if (a.login_open) return { tone: "busy", label: "окно входа открыто", sub: "" }

  const checked = a.last_scan_at ? `последняя проверка: ${fmtWhen(a.last_scan_at)}` : ""

  if (a.last_scan_state === "auth_required")
    return {
      tone: "warn",
      label: "нужен вход",
      sub: ["Сервис не принял сохранённую сессию", checked].filter(Boolean).join(" · "),
    }
  if (a.cookie_state === "ok") {
    const until = a.expires_at
      ? `действует до ${fmtWhen(new Date(a.expires_at * 1000).toISOString())}`
      : ""
    return { tone: "ok", label: "вход выполнен", sub: [until, checked].filter(Boolean).join(" · ") }
  }
  if (a.cookie_state === "expired") return { tone: "warn", label: "сессия истекла", sub: checked }
  return { tone: "off", label: "вход не выполнен", sub: "" }
}

const TONE: Record<string, { color: string; bg: string }> = {
  ok: { color: "var(--ok)", bg: "var(--ok-soft)" },
  warn: { color: "var(--warn)", bg: "var(--warn-soft)" },
  busy: { color: "var(--primary)", bg: "var(--accent)" },
  off: { color: "var(--muted-foreground)", bg: "var(--muted)" },
}

/* --- экран -------------------------------------------------------------- */

export function SettingsScreen() {
  const { project, services, applyProject, removeProject, reloadProjects } = useApp()

  const { data: browser, reload: reloadBrowser } = useResource<BrowserStatus>(
    () => api.get<BrowserStatus>("/api/browser/status"),
    [],
  )

  if (!project) {
    return (
      <div className="space-y-4"><AgentSettingsPanel /><Panel>
        <div className="text-muted-foreground p-6 text-sm">Создайте проект, чтобы настроить запросы и ИИ-сервисы.</div>
      </Panel></div>
    )
  }

  return (
    <div className="space-y-4">
      <AgentSettingsPanel />
      <ProjectForm
        key={project.id}
        project={project}
        onSaved={applyProject}
        onDeleted={async () => {
          removeProject(project.id)
          await reloadProjects()
        }}
      />
      <BrowserPanel
        browser={browser}
        services={services}
        onChanged={reloadBrowser}
      />
      <Panel>
        <PanelHead title="Анализ упоминаний" hint="Модели и арбитр работают на сервере aiParser" />
        <p className="text-muted-foreground p-4 text-sm">
          Настраивать ключи и выбирать модели на этом компьютере не требуется.
          Спорные результаты проверяет серверный арбитр в рамках стоимости проверки.
        </p>
      </Panel>
    </div>
  )
}

/* --- проект и бренд ----------------------------------------------------- */

function ProjectForm({
  project,
  onSaved,
  onDeleted,
}: {
  project: Project
  onSaved: (p: Project) => void
  onDeleted: () => void | Promise<void>
}) {
  const [form, setForm] = useState({
    name: project.name,
    brand_name: project.brand_name,
    aliases: (project.brand_aliases || []).join("\n"),
    domains: (project.brand_domains || []).join("\n"),
    region_code: project.region_code ?? "",
    deep_check_depth: String(project.deep_check_depth ?? 0),
    parallel: Boolean(project.parallel_scan),
  })
  const [busy, setBusy] = useState(false)
  const [savingParallel, setSavingParallel] = useState(false)

  const invalid = !form.name.trim() || !form.brand_name.trim()

  // Переключатель сохраняется сразу, как «Активен» у запросов. 10.09.2026 он
  // ждал общей кнопки «Сохранить»: пользователь включил, ушёл со страницы —
  // и флаг пропал. Переключатель читается как мгновенное действие.
  async function toggleParallel(on: boolean) {
    setForm((f) => ({ ...f, parallel: on }))
    setSavingParallel(true)
    try {
      const updated = await api.patch<Project>(`/api/projects/${project.id}`, { parallel_scan: on })
      onSaved(updated)
      toast.success(on ? "Параллельный скан включён" : "Параллельный скан выключен")
    } catch (e) {
      setForm((f) => ({ ...f, parallel: !on }))
      toast.error(errText(e))
    } finally {
      setSavingParallel(false)
    }
  }

  async function save() {
    if (invalid) return
    setBusy(true)
    try {
      const updated = await api.patch<Project>(`/api/projects/${project.id}`, {
        name: form.name.trim(),
        brand_name: form.brand_name.trim(),
        brand_aliases: splitLines(form.aliases),
        brand_domains: splitLines(form.domains),
        region_code: form.region_code.trim() || null,
        deep_check_depth: Number(form.deep_check_depth) || 0,
        parallel_scan: form.parallel,
      })
      onSaved(updated)
      toast.success("Проект сохранён")
    } catch (e) {
      toast.error(errText(e))
    } finally {
      setBusy(false)
    }
  }

  async function del() {
    try {
      await api.del(`/api/projects/${project.id}`)
      await onDeleted()
      toast.success("Проект удалён")
    } catch (e) {
      toast.error(errText(e))
    }
  }

  return (
    <Panel>
      <PanelHead title="Проект и бренд" hint="формы бренда используются для поиска в ответах" />
      <div className="grid gap-4 p-4 sm:grid-cols-2">
        <Field label="Название проекта" htmlFor="f_name">
          <Input
            id="f_name"
            value={form.name}
            aria-invalid={!form.name.trim()}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
        </Field>
        <Field label="Название бренда" htmlFor="f_brand">
          <Input
            id="f_brand"
            value={form.brand_name}
            aria-invalid={!form.brand_name.trim()}
            onChange={(e) => setForm((f) => ({ ...f, brand_name: e.target.value }))}
          />
        </Field>

        <Field
          className="sm:col-span-2"
          label="Алиасы бренда"
          htmlFor="f_aliases"
          hint="По одному в строке: другие написания, латиница, старое название."
        >
          <Textarea
            id="f_aliases"
            rows={3}
            value={form.aliases}
            onChange={(e) => setForm((f) => ({ ...f, aliases: e.target.value }))}
          />
        </Field>

        <Field
          className="sm:col-span-2"
          label="Домены бренда"
          htmlFor="f_domains"
          hint="По одному в строке, без https://. По ним ловятся упоминания ссылкой, без названия."
        >
          <Textarea
            id="f_domains"
            rows={3}
            value={form.domains}
            onChange={(e) => setForm((f) => ({ ...f, domains: e.target.value }))}
          />
        </Field>

        <Field label="Регион для Яндекса" htmlFor="f_region" hint="Код lr, например 213 — Москва.">
          <Input
            id="f_region"
            inputMode="numeric"
            placeholder="213"
            value={form.region_code}
            onChange={(e) => setForm((f) => ({ ...f, region_code: e.target.value }))}
          />
        </Field>

        <Field
          label="Глубокая проверка источников"
          htmlFor="f_deep"
          hint="Сколько процитированных страниц открывать, 0 — выключено. Если бренда нет в самом ответе, программа заглянет в источники и поищет его там: так ловятся упоминания на сайтах партнёров и перекупщиков. Добавляет около 5 секунд на каждый запрос без упоминания — на базе в 100 запросов это примерно полчаса к прогону."
        >
          <Input
            id="f_deep"
            type="number"
            min={0}
            max={5}
            value={form.deep_check_depth}
            onChange={(e) => setForm((f) => ({ ...f, deep_check_depth: e.target.value }))}
          />
        </Field>

        <div className="flex items-start gap-3 sm:col-span-2">
          <Switch
            id="f_parallel"
            // id у Base UI достаётся скрытому input, а видимый переключатель
            // без своей подписи оставался бы безымянным для скринридера.
            aria-label="Проверять ИИ-системы параллельно"
            checked={form.parallel}
            disabled={savingParallel}
            onCheckedChange={(v) => void toggleParallel(Boolean(v))}
            className="mt-0.5"
          />
          <div className="space-y-0.5">
            <Label htmlFor="f_parallel">Проверять ИИ-системы параллельно</Label>
            <p className="text-muted-foreground text-xs">
              Выбранные системы сканируются одновременно, каждая в своём окне браузера со своим
              аккаунтом, — скан идёт во столько раз быстрее, сколько систем выбрано. Внутри одной
              системы запросы по-прежнему идут по одному. Нужно больше памяти: примерно 0,5–1 ГБ на
              каждое окно.
            </p>
          </div>
        </div>
      </div>

      <PanelFoot className="justify-end">
        <ConfirmButton
          variant="ghost"
          size="sm"
          className="text-destructive mr-auto"
          title={`Удалить проект «${project.name}»?`}
          confirmLabel="Удалить проект"
          description="Вместе с проектом удалятся все его запросы и вся история проверок. Это необратимо."
          onConfirm={del}
        >
          <Trash2 />
          Удалить проект
        </ConfirmButton>
        <Button size="sm" onClick={save} disabled={busy || invalid}>
          <Save />
          Сохранить
        </Button>
      </PanelFoot>
    </Panel>
  )
}

/* --- браузер и аккаунты ------------------------------------------------- */

function BrowserPanel({
  browser,
  services,
  onChanged,
}: {
  browser: BrowserStatus | null
  services: ReturnType<typeof useApp>["services"]
  onChanged: () => void
}) {
  const timers = useRef<number[]>([])

  useEffect(
    () => () => {
      timers.current.forEach(clearInterval)
    },
    [],
  )

  const poll = useCallback(
    (done: (st: BrowserStatus) => boolean, onDone: (st: BrowserStatus) => void) => {
      const id = window.setInterval(async () => {
        try {
          const st = await api.get<BrowserStatus>("/api/browser/status")
          if (done(st)) {
            clearInterval(id)
            onDone(st)
          }
        } catch {
          clearInterval(id)
        }
      }, 2500)
      timers.current.push(id)
    },
    [],
  )

  async function login(serviceId: string, name: string) {
    try {
      await api.post(`/api/browser/services/${serviceId}/login`, {})
      toast.info(`Открываю окно входа в ${name}`, {
        description: "Залогиньтесь и просто закройте окно — сессия сохранится сама.",
        duration: 6000,
      })
      onChanged()
      // Понять «вошёл ли» можно только по факту закрытия окна: оно живёт
      // своей жизнью и о результате не сообщает.
      poll(
        (st) => !st.logins_in_progress.includes(serviceId),
        () => onChanged(),
      )
    } catch (e) {
      toast.error(errText(e))
    }
  }

  async function install() {
    try {
      await api.post("/api/browser/install", {})
      onChanged()
      poll(
        (st) => !st.installing,
        (st) => {
          if (st.install_error) toast.error("Не удалось скачать браузер: " + st.install_error)
          else toast.success("Браузер установлен")
          onChanged()
        },
      )
    } catch (e) {
      toast.error(errText(e))
    }
  }

  if (!browser) {
    return (
      <Panel>
        <PanelHead title="Браузер и аккаунты" />
        <div className="space-y-2 p-4">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      </Panel>
    )
  }

  return (
    <Panel>
      <PanelHead
        title="Браузер и аккаунты"
        hint={browser.installed ? "Camoufox установлен" : "Camoufox не установлен"}
      >
        {!browser.installed ? (
          <Button size="sm" onClick={install} disabled={browser.installing}>
            <Download />
            {browser.installing ? "Скачивается…" : "Скачать браузер"}
          </Button>
        ) : null}
      </PanelHead>

      {!browser.installed ? (
        <p className="text-muted-foreground border-b px-4 py-2.5 text-xs">
          Браузер скачивается один раз при первом запуске — дальше он уже не потребуется. Без
          него ни сканировать, ни входить в аккаунты нельзя.
        </p>
      ) : null}
      {browser.install_error ? (
        <p className="text-destructive border-b px-4 py-2.5 text-xs">{browser.install_error}</p>
      ) : null}

      <div className="divide-y">
        {services.map((s) => {
          const st = authBadge(browser.services?.[s.id])
          const tone = TONE[st.tone]
          return (
            <div key={s.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
              <ServiceDot service={s} className="size-2.5" />
              <div className="min-w-48 flex-1">
                <div className="flex items-center gap-2 text-[13px] font-medium">
                  {s.name}
                  {!s.has_adapter ? <Badge variant="outline">нет адаптера</Badge> : null}
                </div>
                <p className="text-muted-foreground text-xs">{s.note}</p>
                {st.sub ? <p className="text-muted-foreground mt-0.5 text-[11px]">{st.sub}</p> : null}
              </div>
              <span
                className="rounded-md px-2 py-1 text-[11px] font-medium"
                style={{ background: tone.bg, color: tone.color }}
              >
                {st.label}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={!browser.installed || st.tone === "busy"}
                onClick={() => login(s.id, s.name)}
              >
                <LogIn />
                {st.tone === "ok" ? "Перевойти" : "Войти"}
              </Button>
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
