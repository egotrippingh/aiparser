/** Как называть типы упоминаний в интерфейсе — одно место на всё приложение. */

export const MENTION_LABEL: Record<string, { label: string; hint: string }> = {
  text: { label: "в тексте", hint: "ИИ назвал бренд в самом ответе" },
  link: { label: "ссылка на сайт", hint: "в ответе ссылка на сайт бренда" },
  marketplace: { label: "маркетплейс", hint: "карточка бренда на маркетплейсе" },
  card: {
    label: "в карточке",
    hint: "бренд в карточке внутри ответа: источник, товар, организация — не в словах ИИ",
  },
  source: {
    label: "на сайте-источнике",
    hint: "бренд на чужом сайте, на который сослался ИИ",
  },
  indirect: { label: "косвенно", hint: "бренд узнаётся по описанию, без названия (оценка LLM)" },
}

export function mentionLabel(type: string): string {
  return MENTION_LABEL[type]?.label ?? type
}

export function mentionHint(type: string): string | undefined {
  return MENTION_LABEL[type]?.hint
}
