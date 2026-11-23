import { expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { chipLabel, sourceCardLookup, sourcePreviewCopy } from "./answer-content"
import { AnswerDialog } from "./answer-dialog"
import { AnswerEvidenceView, HighlightedSources, SourceChipList, brandLink, evidenceSources, safeProductImage } from "./answer-evidence"

const brand = {names:["Tuvio","Тувио"],domains:["tuvio.test"]}
it("formats supplier Markdown and highlights brand text and links safely", () => {
  const text = "## Tuvio\n\n**Tuvio** [сайт](https://tuvio.test)\n\n| Бренд | Статус |\n| --- | --- |\n| Tuvio | найден |\n\n- Первый\n- Второй\n\n<script>alert(1)</script>"
  const html = renderToStaticMarkup(<AnswerEvidenceView brand={brand} evidence={{format:"markdown",answer_text:text,content:[text],products:[],source_cards:[]}}/>)
  expect(html).toContain('<h2><mark class="answer-brand">Tuvio</mark></h2>')
  expect(html).toContain('<strong><mark class="answer-brand">Tuvio</mark></strong>')
  expect(html).toContain('class="answer-brand-link"')
  expect(html).toContain('<table')
  expect(html).toContain('<ul>')
  expect(html).not.toContain('<script>')
})
it("uses the same saved source context for Markdown evidence links", () => {
  const html = renderToStaticMarkup(<AnswerEvidenceView evidence={{format:"markdown",answer_text:"example.test/path",content:[],products:[],source_cards:[]}} sources={["https://example.test/path"]}/>)
  expect(html).toContain('href="https://example.test/path"')
})
it("keeps structured Yandex sources in the common source block", () => {
  const source = "https://example.test/item#:~:text=fragment"
  const evidence = {content:[{tag:"a",href:source,children:["Источник"]}],products:[],source_cards:[]}
  expect(evidenceSources(evidence,[source],"yandex_neuro")).toEqual([source])
})
it("renders XML structure and red brand accents without injecting provider markup", () => {
  const html = renderToStaticMarkup(<AnswerEvidenceView brand={brand} evidence={{content:[{tag:"h2",children:["TUVIO и Тувио"]},{tag:"p",children:["Не tuvioshop. ",{tag:"a",href:"https://shop.tuvio.test/a",children:["Официальный сайт"]},{tag:"script",children:["alert(1)"]},{tag:"a",href:"javascript:alert(1)",children:["плохая ссылка"]}]}],products:[],source_cards:[]}}/> )
  expect(html).toContain('<h2><mark class="answer-brand">TUVIO</mark>')
  expect(html).toContain('class="answer-brand-link"')
  expect(html).not.toContain('<script')
  expect(html).not.toContain('href="javascript:')
  expect(html).toContain('Не tuvioshop.')
  expect(html).not.toMatch(/xmlriver/i)
  expect(brandLink("https://tuvio.test.evil.test",brand)).toBe(false)
  expect(brandLink("https://evil.test/?next=tuvio.test",brand)).toBe(false)
})
it("shows photo products in a labelled carousel and source cards with safe links", () => {
  const html = renderToStaticMarkup(<AnswerEvidenceView brand={brand} evidence={{content:["Совет"],products:[{title:"Tuvio робот",url:"https://shop.test/product",image_url:"https://photos.test/robot.jpg",price:"23 455 ₽"}],source_cards:[{title:"Источник Tuvio",url:"https://source.test",text:"Описание товара"}]}}/> )
  expect(html).toContain('src="https://photos.test/robot.jpg"')
  expect(html).toContain('loading="lazy"')
  expect(html).toContain('referrerPolicy="no-referrer"')
  expect(html).toContain('aria-label="Следующие товары"')
  expect(html).toContain('class="answer-brand">Tuvio</mark> робот')
  expect(html).toContain('23 455 ₽')
  expect(html).not.toContain('Карточки ответа')
  expect(html).toContain('Описание товара')
})
it("displays organization cards without a link or photo instead of dropping them", () => {
  const html=renderToStaticMarkup(<AnswerEvidenceView brand={brand} evidence={{content:["Совет"],products:[],source_cards:[{title:"Клиника Tuvio",text:"",url:""}]}}/> )
  expect(html).toContain('Клиника <mark class="answer-brand">Tuvio</mark>')
  expect(html).not.toContain('href=""')
})
it("keeps a Yandex link in the shared list until the dialog asks for sources that are not already in the text", () => {
  const linked = "https://example.test/item#:~:text=fragment"
  const extra = "https://extra.example/path"
  const evidence = { content: [{ tag: "a", href: linked, children: ["Источник"] }], products: [{ title: "Торт", url: "https://shop.example/item", image_url: "", price: "" }], source_cards: [{ title: "Карточка", text: "Фрагмент", url: extra }] }
  expect(evidenceSources(evidence, [linked, extra, "https://shop.example/item"], "yandex_neuro")).toEqual([linked, extra, "https://shop.example/item"])
  expect(evidenceSources(evidence, [linked, extra, "https://shop.example/item"], "yandex_neuro", { skipRendered: true })).toEqual([extra])
})

it("builds a source card from a saved title and fragment, and a short chip from the domain", () => {
  expect(sourcePreviewCopy("https://www.retsept.example/tort", { title: "Простой торт", text: "Клубника и сметана" }, "рецепт")).toEqual({ host: "retsept.example", title: "Простой торт", text: "Клубника и сметана" })
  expect(sourcePreviewCopy("https://retsept.example/tort", { title: "Простой торт", text: "Простой торт" }, "рецепт")?.text).toBe("")
  expect(sourcePreviewCopy("https://retsept.example/tort", undefined, "рецепт")?.title).toBe("рецепт")
  expect(sourcePreviewCopy("https://retsept.example/tort", undefined, "https://retsept.example/tort")?.title).toBe("retsept.example/tort")
  expect(sourcePreviewCopy("javascript:bad()", undefined, "плохо")).toBeNull()
  expect(chipLabel("https://sever.example/a", ["https://sever.example/a", "https://retsept.example/b"])).toBe("sever.example")
  expect(chipLabel("https://sever.example/catalog/tort", ["https://sever.example/a", "https://sever.example/catalog/tort"])).toBe("sever.example/catalog/tort")
})

it("distinguishes sources whose links differ by query, including on the home page", () => {
  const sources = ["https://sever.example/?id=1", "https://sever.example/?id=2"]
  const html = renderToStaticMarkup(<SourceChipList sources={sources}/>)
  expect(html).toContain("sever.example/?id=1</span>")
  expect(html).toContain("sever.example/?id=2</span>")
})

it("finds saved source cards through text fragments and www without guessing between cards", () => {
  const first = { url: "https://www.sever.example/item?id=1#:~:text=one", title: "Первый", text: "Фрагмент" }
  const second = { url: "https://www.sever.example/item?id=1#:~:text=two", title: "Второй", text: "Другой фрагмент" }
  const link = new URL("https://sever.example/item?id=1")
  const lookup = sourceCardLookup([first])
  expect(lookup(link)).toEqual({ title: first.title, text: first.text })
  expect(lookup(new URL("https://sever.example/item?id=2"))).toBeUndefined()
  expect(lookup(new URL("https://sever.example/item?id=1#section"))).toBeUndefined()
  const ambiguous = sourceCardLookup([first, second])
  expect(ambiguous(link)).toBeUndefined()
  expect(ambiguous(new URL(second.url))?.title).toBe(second.title)
})

it("uses one dialog shell and chips only for sources that are not already linked in the answer", () => {
  const html = renderToStaticMarkup(<AnswerDialog service="google_aio" scanDate="2026-11-12" status="found" originalStatus="not_found" query="Какой торт испечь?" quote="Крем держит форму" answer="" evidence={{ format: "markdown", answer_text: "Порядок есть в [рецепте](https://retsept.example/a).", content: [], products: [], source_cards: [{ title: "Простой торт", text: "Клубника и сметана", url: "https://retsept.example/a" }, { title: "Кондитерская", text: "Доставка в день заказа", url: "https://sever.example/tort" }, { title: "Клиника без ссылки", text: "", url: "" }] }} sources={["https://retsept.example/a", "https://sever.example/tort"]} mentionTypes={["текст"]} onClose={() => {}}/>)
  expect(html).toContain("Google AI Overview")
  expect(html).toContain("12 ноября 2026")
  expect(html).toContain("Какой торт испечь?")
  expect(html).toContain("Ручное исправление")
  expect(html).toContain('class="source-preview"')
  expect(html).toContain("Клиника без ссылки")
  expect(html).toContain("sever.example")
  expect(html).toContain('aria-label="Источник: sever.example"')
  expect(html).not.toContain('aria-label="Источник: retsept.example"')
  expect(html).not.toContain("Сохранённый ответ")
})

it("marks only the chip whose domain is the tracked brand", () => {
  const html = renderToStaticMarkup(<SourceChipList brand={brand} sources={["https://shop.tuvio.test/product", "https://source.test/page"]}/>)
  expect(html).toContain('class="answer-brand-link source-chip"')
  expect(html).toContain("https://shop.tuvio.test/product")
  expect(html.match(/class="source-chip"/g) || []).toHaveLength(1)
  expect(html).toContain("https://source.test/page")
})

it("keeps unusable image URLs out of the browser and accents matching source domains", () => {
  for (const value of ["javascript:bad()","data:image/svg+xml,bad","https://127.0.0.1/a","https://localhost/a","http://photos.test/a"]) expect(safeProductImage(value)).toBe("")
  const html=renderToStaticMarkup(<HighlightedSources brand={brand} sources={["https://tuvio.test/product","https://source.test","javascript:bad()"]}/> )
  expect(html).toContain('class="answer-brand-link"')
  expect(html).not.toContain('javascript:')
})

it.each(["yandex_neuro", "google_aio", "gemini", "perplexity", "chatgpt"])("renders grouped saved citations in %s and preserves prose links", (service) => {
  const text = "Сводка. ([One][1], [Two][2]) ([сайт производителя](https://factory.test)).\n\n[1]: https://one.test/page\n[2]: https://two.test/page"
  const html = renderToStaticMarkup(<AnswerDialog service={service} scanDate="" status="found" originalStatus="found" query="Сравнение" answer={text} sources={["https://one.test/page", "https://two.test/page", "https://factory.test"]} onClose={() => {}}/>)
  expect(html).toContain('data-citation-service="' + service + '"')
  expect(html).toContain('class="answer-citation')
  expect(html).toContain('href="https://factory.test/"')
  expect(html).not.toContain("[One][1]")
  if (service !== "yandex_neuro") expect(html).toContain(service === "gemini" ? "ещё 1</span>" : "+1")
  if (["yandex_neuro", "perplexity"].includes(service)) expect(html).toContain("Источники")
})

it("renders ChatGPT products as comparison rows with saved descriptions and without an empty shopping block", () => {
  const evidence = { format: "markdown" as const, answer_text: "Сравнение", content: [], products: [{ title: "ESTUS", url: "https://brand.test/estus", image_url: "https://images.test/estus.jpg", price: "", description: "Модульный комплекс" }], source_cards: [] }
  const render = (data: typeof evidence) => renderToStaticMarkup(<AnswerEvidenceView evidence={data} service="chatgpt"/>)
  const html = render(evidence)
  expect(html).toContain("answer-comparison")
  expect(html).toContain("Модульный комплекс")
  expect(html).toContain('src="https://images.test/estus.jpg"')
  expect(render({ ...evidence, products: [] })).not.toContain("answer-comparison")
})
