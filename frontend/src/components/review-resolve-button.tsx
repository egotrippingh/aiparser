/** «Решить спорные»: вердикт по строкам «требует проверки» выносит вторая модель.
 *
 * Спорная строка — та, где правила молчат, а первая модель сказала «найдено»:
 * именно там она чаще всего выдумывает. Арбитр перерешает их по сохранённым
 * тексту ответа и скриншоту, пометка снимается, и дашборд перечитывается —
 * иначе цифры на экране разошлись бы с базой.
 */

import { useState } from "react"
import { Loader2, ScanEye } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { useResource } from "@/hooks/use-resource"
import { api, errText } from "@/lib/api"
import { plural } from "@/lib/format"
import type { ReviewInfo, ReviewResolved } from "@/lib/types"
import { useApp } from "@/store/app-store"

export function ReviewResolveButton() {
  const { projectId, refreshData, dataVersion } = useApp()
  const [busy, setBusy] = useState(false)
  const { data: info, reload } = useResource<ReviewInfo>(
    projectId ? () => api.get<ReviewInfo>(`/api/projects/${projectId}/review`) : null,
    [projectId, dataVersion],
  )

  if (!info || info.pending === 0) return null

  async function run() {
    if (!projectId) return
    setBusy(true)
    try {
      const r = await api.post<ReviewResolved>(`/api/projects/${projectId}/review/resolve`)
      toast.success(
        `Решено ${r.resolved} ${plural(r.resolved, "строка", "строки", "строк")}: ` +
          `${r.found} с упоминанием, ${r.not_found} без`,
        {
          description:
            [
              r.changed ? `Вердикт изменился у ${r.changed}` : "",
              r.failed ? `Не удалось спросить модель: ${r.failed}` : "",
            ]
              .filter(Boolean)
              .join(" · ") || undefined,
        },
      )
      reload()
      refreshData()
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
      disabled={busy || !info.enabled}
      title={
        info.enabled
          ? `Спорные строки решит ${info.model} — вместо ручной проверки`
          : "Арбитр выключен: укажите модель в настройках OpenRouter"
      }
    >
      {busy ? <Loader2 className="animate-spin" /> : <ScanEye />}
      {busy ? "Решает модель…" : `Решить спорные (${info.pending})`}
    </Button>
  )
}
