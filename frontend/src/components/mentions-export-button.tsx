/** «Упоминаемость → Excel»: запросы в строках, ИИ-системы в столбцах.
 *
 * Выгружается ровно то, что сейчас на экране: тот же период из календаря и те
 * же знаки в ячейках. Файл собирает сервер — он и так знает срез, а браузеру
 * незачем перекладывать таблицу во второй раз.
 */

import { useState } from "react"
import { Loader2, Table2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { errText } from "@/lib/api"
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

export function MentionsExportButton({ params }: { params: string }) {
  const { projectId } = useApp()
  const [busy, setBusy] = useState(false)

  async function run() {
    if (!projectId) return
    setBusy(true)
    try {
      const resp = await fetch(`/api/projects/${projectId}/mentions.xlsx?${params}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Не удалось собрать Excel (HTTP ${resp.status})`)
      }
      const blob = await resp.blob()
      const href = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = href
      a.download = fileName(resp, "упоминаемость.xlsx")
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(href), 5000)
      toast.success("Таблица упоминаемости выгружена")
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
      title="Запросы в строках, ИИ-системы в столбцах, в ячейках те же знаки, что в таблице. Период — как выбран в календаре."
    >
      {busy ? <Loader2 className="animate-spin" /> : <Table2 />}
      {busy ? "Собираю таблицу…" : "Упоминаемость → Excel"}
    </Button>
  )
}
