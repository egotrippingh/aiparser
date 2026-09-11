/** Общее состояние приложения: мета, проекты и живой скан.
 *
 * Скан живёт здесь, а не во вкладке «Скан», по той же причине, что и в
 * прежнем интерфейсе: подписка на события одна на всё приложение, а прогресс
 * и лог должны переживать переключение вкладок. Поверх этого добавлено
 * восстановление после перезапуска — состояние подтягивается из
 * /api/scans/active, потому что SSE рассказывает только о новых событиях.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { toast } from "sonner"

import { api, errText } from "@/lib/api"
import type { Meta, Project, ScanSnapshot, ServiceMeta, Status } from "@/lib/types"
import { statusMeta } from "@/lib/status"

export interface LogLine {
  id: number
  text: string
  kind?: "ok" | "err"
}

interface AppValue {
  meta: Meta | null
  services: ServiceMeta[]
  serviceById: (id: string | null | undefined) => ServiceMeta | undefined
  projects: Project[]
  project: Project | null
  projectId: number | null
  selectProject: (id: number) => void
  reloadProjects: () => Promise<Project[]>
  applyProject: (p: Project) => void
  removeProject: (id: number) => void

  scan: ScanSnapshot | null
  scanLog: LogLine[]
  clearScanLog: () => void
  watchScan: (scanId: number) => void
  refreshScan: () => Promise<ScanSnapshot | null>
  /** Растёт после каждого завершённого скана — экраны перечитывают данные. */
  dataVersion: number
  /** Данные в базе поменялись не сканом (например, засчитаны сайты-источники). */
  refreshData: () => void
}

const AppContext = createContext<AppValue | null>(null)

const LAST_PROJECT_KEY = "aimt.lastProject"

export function AppProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<number | null>(null)
  const [scan, setScan] = useState<ScanSnapshot | null>(null)
  const [scanLog, setScanLog] = useState<LogLine[]>([])
  const [dataVersion, setDataVersion] = useState(0)

  const esRef = useRef<EventSource | null>(null)
  const lineId = useRef(0)
  const servicesRef = useRef<ServiceMeta[]>([])

  const services = meta?.services ?? []
  servicesRef.current = services

  const serviceById = useCallback(
    (id: string | null | undefined) => servicesRef.current.find((s) => s.id === id),
    [],
  )

  const pushLog = useCallback((text: string, kind?: "ok" | "err") => {
    setScanLog((prev) => {
      const next = [...prev, { id: lineId.current++, text, kind }]
      // Лог живёт всю сессию; без потолка длинный скан вырастает в тысячи
      // узлов и вкладка начинает тормозить на каждой перерисовке.
      return next.length > 400 ? next.slice(-400) : next
    })
  }, [])

  const clearScanLog = useCallback(() => setScanLog([]), [])
  const refreshData = useCallback(() => setDataVersion((v) => v + 1), [])

  const refreshScan = useCallback(async () => {
    try {
      const s = await api.get<ScanSnapshot | null>("/api/scans/active")
      setScan(s)
      return s
    } catch {
      // Сервер ещё поднимается — молчим, а не пугаем тостом на старте.
      return null
    }
  }, [])

  const watchScan = useCallback(
    (scanId: number) => {
      if (esRef.current) return // подписка уже есть, вторая только дублирует события
      const es = new EventSource(`/api/scans/${scanId}/stream`)
      esRef.current = es

      const on = <T,>(name: string, fn: (data: T) => void) =>
        es.addEventListener(name, (ev) => {
          try {
            fn(JSON.parse((ev as MessageEvent).data))
          } catch {
            fn({} as T)
          }
        })

      const progress = (e: ScanSnapshot) => setScan(e)

      on<ScanSnapshot & { total: number }>("scan_started", (e) => {
        progress(e)
        pushLog(`Скан запущен · проверок: ${e.total}`)
      })
      on<ScanSnapshot>("progress", progress)
      on<ScanSnapshot>("paused", (e) => {
        progress(e)
        pushLog("Пауза — остановится после текущего запроса")
      })
      on<ScanSnapshot>("resumed", (e) => {
        progress(e)
        pushLog("Продолжено")
      })
      on<ScanSnapshot>("stopping", (e) => {
        progress(e)
        pushLog("Останавливается…")
      })
      on<{ name: string; pending: number }>("service_started", (e) =>
        pushLog(`→ сервис ${e.name} · запросов: ${e.pending}`),
      )
      on<{ service: string }>("service_finished", (e) => pushLog(`← сервис ${e.service} завершён`))
      on<{ service: string; error: string }>("service_error", (e) =>
        pushLog(`сервис ${e.service} упал: ${e.error}`, "err"),
      )
      on<{ service: string; reason: string }>("service_blocked", (e) =>
        pushLog(`сервис ${e.service} недоступен: ${e.reason}`, "err"),
      )
      on<{ service: string; skipped: number }>("service_limit", (e) =>
        pushLog(
          `${e.service}: лимит тарифа — пропущено ${e.skipped} запросов, их возьмёт дозапуск`,
          "err",
        ),
      )
      on<{ service: string; query_id: number; status: Status }>("query_result", (e) => {
        const svc = servicesRef.current.find((s) => s.id === e.service)
        const kind =
          e.status === "found"
            ? "ok"
            : ["error", "captcha", "auth_required", "limit_reached"].includes(e.status)
              ? "err"
              : undefined
        pushLog(
          `${statusMeta(e.status).sign} ${svc?.name || e.service} — #${e.query_id}: ${statusMeta(e.status).title}`,
          kind,
        )
      })
      on<{ status: string }>("scan_finished", (e) => {
        pushLog(
          e.status === "done" ? "Скан завершён" : `Скан остановлен (${e.status})`,
          e.status === "done" ? "ok" : undefined,
        )
        setScan(null)
        es.close()
        esRef.current = null
        setDataVersion((v) => v + 1)
        toast.success(e.status === "done" ? "Скан завершён" : "Скан остановлен")
      })

      // Кратковременный обрыв EventSource переживает сам — переподключается.
      // Но если сервер перезапустили посреди скана, поток отвечает 404 и
      // закрывается навсегда. Держать такую подписку нельзя: watchScan видит
      // «подписка уже есть» и молча игнорирует следующий скан, а полоса
      // прогресса застывает. Сбрасываем и перечитываем, что идёт на самом
      // деле, — переподпишет эффект ниже.
      es.onerror = () => {
        if (es.readyState !== EventSource.CLOSED) return
        if (esRef.current === es) esRef.current = null
        void refreshScan()
      }
    },
    [pushLog, refreshScan],
  )

  // Пока скан идёт, подписка на его события должна быть. Сюда сходятся все
  // пути: старт программы посреди скана, запуск с вкладки «Скан», обрыв
  // потока. watchScan сам не создаёт вторую подписку, если первая жива.
  useEffect(() => {
    if (scan && scan.state !== "finished") watchScan(scan.scan_id)
  }, [scan, watchScan])

  const reloadProjects = useCallback(async () => {
    const list = await api.get<Project[]>("/api/projects")
    setProjects(list)
    setProjectId((cur) => {
      if (cur && list.some((p) => p.id === cur)) return cur
      const saved = Number(localStorage.getItem(LAST_PROJECT_KEY))
      if (saved && list.some((p) => p.id === saved)) return saved
      return list[0]?.id ?? null
    })
    return list
  }, [])

  const selectProject = useCallback((id: number) => {
    setProjectId(id)
    localStorage.setItem(LAST_PROJECT_KEY, String(id))
  }, [])

  const applyProject = useCallback((p: Project) => {
    setProjects((prev) => {
      const known = prev.some((x) => x.id === p.id)
      return known ? prev.map((x) => (x.id === p.id ? p : x)) : [...prev, p]
    })
  }, [])

  const removeProject = useCallback((id: number) => {
    setProjects((prev) => {
      const next = prev.filter((p) => p.id !== id)
      setProjectId((cur) => (cur === id ? (next[0]?.id ?? null) : cur))
      return next
    })
  }, [])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const m = await api.get<Meta>("/api/meta")
        if (!alive) return
        setMeta(m)
        await reloadProjects()
      } catch (e) {
        toast.error(errText(e))
      }
      // Скан мог идти ещё до открытия окна — подхватываем его, а не делаем
      // вид, что ничего не происходит.
      const active = await refreshScan()
      if (alive && active) watchScan(active.scan_id)
    })()
    return () => {
      alive = false
    }
  }, [reloadProjects, refreshScan, watchScan])

  useEffect(() => () => esRef.current?.close(), [])

  const project = useMemo(
    () => projects.find((p) => p.id === projectId) ?? null,
    [projects, projectId],
  )

  const value: AppValue = {
    meta,
    services,
    serviceById,
    projects,
    project,
    projectId,
    selectProject,
    reloadProjects,
    applyProject,
    removeProject,
    scan,
    scanLog,
    clearScanLog,
    watchScan,
    refreshScan,
    dataVersion,
    refreshData,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp(): AppValue {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error("useApp вызван вне AppProvider")
  return ctx
}
