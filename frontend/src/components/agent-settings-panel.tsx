import { useCallback, useEffect, useState, type FormEvent } from "react"
import { CalendarClock, ExternalLink, Wallet } from "lucide-react"
import { toast } from "sonner"

import { Panel, PanelHead } from "@/components/bits"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, errText } from "@/lib/api"
import { DEFAULT_SCAN_PREFERENCES, MONTH_DAYS, SCAN_SERVICES, type ScanPreferences } from "@/lib/scan-preferences"

type AccountStatus = {
  enabled: boolean
  connected: boolean
  is_admin?: boolean
  email?: string
  cabinet_url?: string
  wallet?: { available_kopeks: number; reserved_kopeks: number }
}
type Autostart = { available: boolean; enabled: boolean }
const rub = (kopeks: number) => new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB" }).format(kopeks / 100)

export function AgentSettingsPanel() {
  const [account, setAccount] = useState<AccountStatus | null>(null)
  const [preferences, setPreferences] = useState<ScanPreferences>(DEFAULT_SCAN_PREFERENCES)
  const [autostart, setAutostart] = useState<Autostart | null>(null)
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const refresh = useCallback(async () => {
    const status = await api.get<AccountStatus>("/api/account/status")
    setAccount(status)
    if (status.connected) setPreferences(await api.get<ScanPreferences>("/api/agent/preferences"))
    setAutostart(await api.get<Autostart>("/api/agent/autostart"))
  }, [])

  useEffect(() => { void refresh().catch((cause) => setError(errText(cause))) }, [refresh])

  async function connect(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError("")
    try {
      await api.post("/api/account/login-code", { code: code.trim() })
      setCode("")
      await refresh()
      toast.success("Аккаунт подключён")
    } catch (cause) { setError(errText(cause)) }
    finally { setBusy(false) }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!preferences.month_days.length || !preferences.services.length) {
      setError("Выберите хотя бы одно число месяца и один ИИ-сервис")
      return
    }
    setBusy(true)
    setError("")
    try {
      const saved = await api.put<ScanPreferences>("/api/agent/preferences", preferences)
      setPreferences(saved)
      toast.success("Настройки синхронизированы с личным кабинетом")
    } catch (cause) {
      setError(errText(cause))
      await api.get<ScanPreferences>("/api/agent/preferences").then(setPreferences).catch(() => undefined)
    } finally { setBusy(false) }
  }

  async function changeAutostart(enabled: boolean) {
    try {
      setAutostart(await api.put<Autostart>("/api/agent/autostart", { enabled }))
      toast.success(enabled ? "Агент запустится вместе с Windows" : "Автозапуск отключён")
    } catch (cause) { setError(errText(cause)) }
  }

  if (!account?.enabled && !error) return null

  return <div className="space-y-4">
    <Panel>
      <PanelHead title="Агент и баланс" hint="Проверки выполняются на этом компьютере, отчёты появляются в личном кабинете" />
      <div className="space-y-4 p-4">
        {account?.connected ? <div className="flex flex-wrap items-center gap-3">
          <Wallet className="text-primary size-5" aria-hidden="true" />
          <div className="min-w-40 flex-1"><strong className="text-sm">{account.email}</strong><p className="text-muted-foreground text-xs">{account.is_admin ? "Безлимитные проверки · бесплатно" : `Доступно: ${rub(account.wallet?.available_kopeks ?? 0)} · В резерве: ${rub(account.wallet?.reserved_kopeks ?? 0)}`}</p></div>
          <Button type="button" size="sm" variant="outline" onClick={() => void refresh().catch((cause) => setError(errText(cause)))}>Обновить баланс</Button>
        </div> : <form onSubmit={connect} className="flex flex-wrap items-end gap-3">
          <label className="min-w-56 flex-1 text-xs">Одноразовый код из кабинета<Input className="mt-1" value={code} onChange={(event) => setCode(event.target.value)} required autoComplete="off" /></label>
          <Button size="sm" disabled={busy}>Подключить</Button>
          <p className="text-muted-foreground w-full text-xs">Войдите через Яндекс на сайте и создайте код в разделе «Аккаунт».</p>
        </form>}
        {account?.cabinet_url && <a href={account.cabinet_url} target="_blank" rel="noreferrer" className="text-primary inline-flex items-center gap-1 text-xs underline">{account.is_admin ? "Личный кабинет" : "Личный кабинет и пополнение"} <ExternalLink size={13} /></a>}
        {autostart && <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="accent-primary size-4" checked={autostart.enabled} disabled={!autostart.available} onChange={(event) => void changeAutostart(event.target.checked)} /> Запускать агент вместе с Windows</label>}
        {autostart && !autostart.available && <p className="text-muted-foreground text-xs">Автозапуск доступен в собранном EXE.</p>}
      </div>
    </Panel>
    {account?.connected && <Panel>
      <PanelHead title="Проверки по расписанию" hint="Одно или несколько чисел месяца, в указанное время этого компьютера" ><CalendarClock size={18} /></PanelHead>
      <form onSubmit={save} className="space-y-5 p-4">
        <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="accent-primary size-4" checked={preferences.enabled} onChange={(event) => setPreferences({ ...preferences, enabled: event.target.checked })} /> Проверять автоматически</label>
        <label className="block text-sm">Время запуска<input type="time" className="bg-card border-input mt-1 block h-9 rounded-lg border px-3" value={preferences.local_time} onChange={(event) => setPreferences({ ...preferences, local_time: event.target.value })} /></label>
        <fieldset><legend className="mb-2 text-sm font-medium">Числа месяца</legend><div className="grid grid-cols-7 gap-1.5 sm:grid-cols-10">{MONTH_DAYS.map((day) => <label key={day} className="cursor-pointer"><input type="checkbox" className="peer sr-only" checked={preferences.month_days.includes(day)} onChange={(event) => setPreferences({ ...preferences, month_days: event.target.checked ? [...preferences.month_days, day].sort((a, b) => a - b) : preferences.month_days.filter((value) => value !== day) })} /><span className="border-input bg-card peer-checked:border-primary peer-checked:bg-primary/20 peer-focus-visible:outline-primary grid h-9 place-items-center rounded-lg border text-xs peer-focus-visible:outline-2">{day}</span></label>)}</div><p className="text-muted-foreground mt-2 text-xs">Если в месяце нет выбранного числа, запуск пропускается. Пропущенная из-за выключенного ПК проверка начнётся при запуске агента в тот же день.</p></fieldset>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Браузер<select className="border-input bg-card mt-1 block h-9 w-full rounded-lg border px-2" value={preferences.browser_mode} onChange={(event) => setPreferences({ ...preferences, browser_mode: event.target.value as ScanPreferences["browser_mode"] })}><option value="headless">Без окон</option><option value="headful">С видимыми окнами</option></select></label><label className="text-sm">Скорость<select className="border-input bg-card mt-1 block h-9 w-full rounded-lg border px-2" value={preferences.speed_profile} onChange={(event) => setPreferences({ ...preferences, speed_profile: event.target.value as ScanPreferences["speed_profile"] })}><option value="careful">Осторожная</option><option value="balanced">Сбалансированная</option><option value="fast">Быстрая</option></select></label></div>
        <fieldset><legend className="mb-2 text-sm font-medium">ИИ-сервисы</legend><div className="flex flex-wrap gap-x-5 gap-y-2">{SCAN_SERVICES.map((service) => <label key={service.id} className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-primary size-4" disabled={"available" in service && !service.available} checked={preferences.services.includes(service.id)} onChange={(event) => setPreferences({ ...preferences, services: event.target.checked ? [...preferences.services, service.id] : preferences.services.filter((id) => id !== service.id) })} />{service.label}</label>)}</div></fieldset>
        <Button disabled={busy}>{busy ? "Сохраняем…" : "Сохранить настройки"}</Button>
      </form>
    </Panel>}
    {error && <p className="text-destructive text-sm" role="alert">{error}</p>}
  </div>
}
