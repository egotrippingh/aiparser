/** Даты в виде «ГГГГ-ММ-ДД» без часовых поясов.
 *
 * Срез скана — это календарный день на компьютере пользователя, а не момент
 * времени. Через Date.toISOString() «10 сентября 00:30» по Москве превратилось
 * бы в 9-е по UTC, поэтому строки собираются из локальных полей вручную.
 */

export function iso(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${d.getFullYear()}-${m}-${day}`
}

export function parse(s: string): Date {
  const [y, m, d] = s.split("-").map(Number)
  return new Date(y, m - 1, d)
}

export function addDays(s: string, n: number): string {
  const d = parse(s)
  d.setDate(d.getDate() + n)
  return iso(d)
}

export function today(): string {
  return iso(new Date())
}

export function monthStart(s: string): string {
  return s.slice(0, 8) + "01"
}

export function monthEnd(s: string): string {
  const d = parse(s)
  return iso(new Date(d.getFullYear(), d.getMonth() + 1, 0))
}

/** Ячейки месяца для сетки с понедельника: null — пустые клетки до 1-го числа. */
export function monthGrid(year: number, month: number): (string | null)[] {
  const first = new Date(year, month, 1)
  const offset = (first.getDay() + 6) % 7
  const days = new Date(year, month + 1, 0).getDate()
  const cells: (string | null)[] = Array.from({ length: offset }, () => null)
  for (let d = 1; d <= days; d++) cells.push(iso(new Date(year, month, d)))
  return cells
}

const MONTHS = [
  "январь", "февраль", "март", "апрель", "май", "июнь",
  "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

export function monthTitle(year: number, month: number): string {
  return `${MONTHS[month]} ${year}`
}

/** «10.09.2026» — полная дата для подписей периода. */
export function dmy(s: string): string {
  const [y, m, d] = s.split("-")
  return `${d}.${m}.${y}`
}
