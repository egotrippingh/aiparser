import { useCallback, useEffect, useState } from "react"

import { errText } from "@/lib/api"

interface Resource<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
  /** Локальная правка без похода на сервер — например, после PATCH. */
  set: (updater: T | ((prev: T) => T)) => void
}

/** Загрузка данных экрана: один запрос, состояние загрузки и ошибка.
 *
 * `deps` работает как у useEffect. Ключ здесь — не показывать пустой экран
 * при перезагрузке: старые данные остаются на месте, пока не приедут новые.
 */
export function useResource<T>(
  load: (() => Promise<T>) | null,
  deps: readonly unknown[],
): Resource<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(load !== null)
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    if (!load) {
      setData(null)
      setLoading(false)
      return
    }
    let alive = true
    setLoading(true)
    load()
      .then((res) => {
        if (!alive) return
        setData(res)
        setError(null)
      })
      .catch((e) => {
        if (!alive) return
        setError(errText(e))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  const set = useCallback((updater: T | ((prev: T) => T)) => {
    setData((prev) => {
      if (prev === null) return prev
      return typeof updater === "function" ? (updater as (p: T) => T)(prev) : updater
    })
  }, [])

  return { data, error, loading, reload, set }
}
