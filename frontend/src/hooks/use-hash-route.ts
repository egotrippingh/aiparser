import { useCallback, useEffect, useState } from "react"

export const VIEWS = ["dashboard", "queries", "scan", "settings"] as const
export type View = (typeof VIEWS)[number]

function read(): View {
  const raw = window.location.hash.replace(/^#\/?/, "")
  return (VIEWS as readonly string[]).includes(raw) ? (raw as View) : "dashboard"
}

/** Вкладка в адресе окна.
 *
 * Полноценный роутер здесь избыточен — экранов четыре и вложенности нет.
 * Но хеш нужен: он возвращает пользователя на ту же вкладку после
 * перезагрузки окна и переживает пересборку фронта при разработке.
 */
export function useHashRoute(): [View, (v: View) => void] {
  const [view, setView] = useState<View>(read)

  useEffect(() => {
    const onHash = () => setView(read())
    window.addEventListener("hashchange", onHash)
    return () => window.removeEventListener("hashchange", onHash)
  }, [])

  const go = useCallback((v: View) => {
    window.location.hash = `/${v}`
    setView(v)
  }, [])

  return [view, go]
}
