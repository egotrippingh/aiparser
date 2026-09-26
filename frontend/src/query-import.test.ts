import { describe, expect, it } from "vitest"
import { parseQueryImport } from "./query-import"

describe("query imports", () => {
  it("preserves punctuation in plain text and the chosen group", () => {
    expect(parseQueryImport("Где купить ESTUS, оригинал?\n\nОфициальный сайт?", "Общие")).toEqual([
      { text: "Где купить ESTUS, оригинал?", group_tag: "Общие" },
      { text: "Официальный сайт?", group_tag: "Общие" },
    ])
  })
  it("reads quoted multiline CSV and header column order", () => {
    expect(parseQueryImport('\uFEFFГруппа;Запрос\r\nОбщие;"Где купить; ESTUS?"\r\nБренд;"Сайт\nESTUS"')).toEqual([
      { text: "Где купить; ESTUS?", group_tag: "Общие" },
      { text: "Сайт\nESTUS", group_tag: "Бренд" },
    ])
  })
  it("rejects malformed quoted input", () => {
    expect(() => parseQueryImport('Запрос;Группа\n"не закрыто;Общие')).toThrow()
  })
})
