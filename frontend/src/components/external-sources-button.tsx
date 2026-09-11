/** «Внешние источники → Excel»: чужие сайты с брендом, на которые ссылался ИИ.
 *
 * Сначала сервер проверяет все сайты-источники среза (уже проверенные берутся
 * из кэша) и засчитывает находки как упоминания, потом отдаёт Excel в два
 * столбца: источник и текст упоминания. Если засчитались новые упоминания —
 * дашборд перечитывается, иначе цифры на экране разошлись бы с базой.
 */

import { useState } from "react"
import { FileSpreadsheet, Loader2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { api, errText } from "@/lib/api"
import { plural } from "@/lib/format"
import type { ExternalCheck } from "@/lib/types"
import { useApp } from "@/store/app-store"

function fileName(resp: Response, fallback: string): string {
  const cd = resp.headers.get("content-disposition") || ""
  const m = /filename\*=UTF-8''([^;]+)/i.exec(cd)
  try {
    return m ? decodeURIComponent(m[1]) : fallback
  } catch {
    return fallback
  }
}

export function ExternalSourcesButton({ date }: { date: string }) {
  const { projectId, refreshData } = useApp()
  const [busy, setBusy] = useState(false)

  async function run() {
    if (!projectId) return
    setBusy(true)
    try {
      const r = await api.post<ExternalCheck>(
        `/api/projects/${projectId}/external-sources/check?date=${date}`,
      )
      const resp = await fetch(`/api/projects/${projectId}/external-sources.xlsx?date=${date}`)
      if (!resp.ok) throw new Error(`Не удалось собрать Excel (HTTP ${resp.status})`)
      const blob = await resp.blob()
      const href = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = href
      a.download = fileName(resp, `внешние-источники-${date}.xlsx`)
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(href), 5000)

      toast.success(
        `Сайтов с брендом: ${r.found_sites} из ${r.urls_total} ${plural(r.urls_total, "источника", "источников", "источников")}`,
        {
          description: [
            r.updated_results
              ? `Засчитано упоминаний на сайтах-источниках: ${r.updated_results}`
              : "",
            r.failed ? `Не открылись: ${r.failed}` : "",
          ]
            .filter(Boolean)
            .join(" · ") || undefined,
        },
      )
      if (r.updated_results) refreshData()
    } catch (e) {
      toast.error(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Button
      size="xs"
      variant="outline"
      onClick={run}
      disabled={busy}
      title="Чужие сайты, на которые сослался ИИ и где есть бренд, — источник и текст упоминания"
    >
      {busy ? <Loader2 className="animate-spin" /> : <FileSpreadsheet />}
      {busy ? "Проверяю сайты…" : "Внешние источники → Excel"}
    </Button>
  )
}
