/** Единая расшифровка статусов результата.
 *
 * Одно место на всё приложение: таблица, карточка запроса и лог скана
 * обязаны называть один и тот же статус одинаково, иначе пользователь
 * решит, что это разные вещи.
 */

import type { Status } from "./types"

export interface StatusMeta {
  /** Короткая подпись в ячейке таблицы. */
  sign: string
  /** Полная формулировка для карточки и подсказок. */
  title: string
  /** Основной цвет (знак, текст). */
  color: string
  /** Мягкая заливка ячейки. */
  soft: string
}

export const STATUS: Record<Status, StatusMeta> = {
  found: {
    sign: "✓",
    title: "Упоминание найдено",
    color: "var(--ok)",
    soft: "var(--ok-soft)",
  },
  not_found: {
    sign: "✗",
    title: "Упоминаний нет",
    color: "var(--no)",
    soft: "var(--no-soft)",
  },
  skipped: {
    sign: "—",
    title: "AI-блок не показан",
    color: "var(--muted-foreground)",
    soft: "var(--muted)",
  },
  error: {
    sign: "!",
    title: "Ошибка проверки",
    color: "var(--bad)",
    soft: "var(--bad-soft)",
  },
  auth_required: {
    sign: "!",
    title: "Нужен вход в аккаунт",
    color: "var(--bad)",
    soft: "var(--bad-soft)",
  },
  captcha: {
    sign: "!",
    title: "Остановлено капчей",
    color: "var(--bad)",
    soft: "var(--bad-soft)",
  },
  limit_reached: {
    sign: "◷",
    title: "Лимит тарифа — запрос не проверен",
    color: "var(--warn)",
    soft: "var(--warn-soft)",
  },
}

const UNKNOWN: StatusMeta = {
  sign: "?",
  title: "Неизвестный статус",
  color: "var(--muted-foreground)",
  soft: "var(--muted)",
}

export function statusMeta(status: string | undefined | null): StatusMeta {
  return (status && STATUS[status as Status]) || UNKNOWN
}

/** Статусы, которые означают «проверка не удалась», а не «бренда нет». */
export const FAILED: Status[] = ["error", "captcha", "auth_required"]
