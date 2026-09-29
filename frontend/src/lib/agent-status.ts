export function agentStatus(paused: boolean, scan?: {state?: string}|null, job?: {desired_state?: string}|null) {
  if (paused) return ["Агент на паузе", "Новые задания будут ждать в очереди."]
  if (job?.desired_state === "paused") return ["Проверка на паузе", "Пауза задана на сайте управления."]
  if (scan?.state === "paused") return ["Проверка на паузе", job?.desired_state === "paused" ? "Пауза задана на сайте управления." : "Ожидается возобновление или синхронизация."]
  if (scan) return ["Проверка выполняется", ""]
  return ["Готов к заданиям сайта", "Можно закрыть окно. Агент продолжит работать в трее."]
}
