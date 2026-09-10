/** Форматирование чисел, дат и длительностей — всё в русской локали. */

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—"
  return v.toFixed(1).replace(/\.0$/, "")
}

export function delta(v: number | null | undefined): string {
  if (v === null || v === undefined) return ""
  return `${Math.abs(v).toFixed(1).replace(/\.0$/, "")} п.п.`
}

/** «2026-09-10» → «10.09» — для плотных заголовков колонок. */
export function shortDate(iso: string): string {
  const [, m, d] = iso.split("-")
  return `${d}.${m}`
}

/** «2026-09-10» → «10 сентября» — для подписей, где есть место. */
export function longDate(iso: string): string {
  const d = new Date(iso + "T00:00:00")
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })
}

export function weekday(iso: string): string {
  const d = new Date(iso + "T00:00:00")
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString("ru-RU", { weekday: "short" })
}

/** Метка времени из SQLite приходит без зоны, но записана в UTC. */
export function relTime(sqlTime: string | null | undefined): string {
  if (!sqlTime) return ""
  const ms = new Date(sqlTime.replace(" ", "T") + "Z").getTime()
  if (isNaN(ms)) return ""
  const diff = (Date.now() - ms) / 1000
  if (diff < 60) return "только что"
  if (diff < 3600) return `${Math.round(diff / 60)} мин назад`
  if (diff < 86400) return `${Math.round(diff / 3600)} ч назад`
  return `${Math.round(diff / 86400)} дн назад`
}

export function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return ""
  const d = new Date(iso)
  return isNaN(d.getTime())
    ? ""
    : d.toLocaleString("ru-RU", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
}

export function fmtDur(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return "—"
  if (sec < 60) return `${sec} сек`
  const m = Math.round(sec / 60)
  if (m < 60) return `${m} мин`
  return `${Math.floor(m / 60)} ч ${m % 60} мин`
}

/** «запрос / запроса / запросов» по числу. */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

export function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean)
}
