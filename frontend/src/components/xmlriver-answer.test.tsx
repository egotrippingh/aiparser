import { expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { XMLRiverAnswer, HighlightedSources, brandLink, safeProductImage } from "./xmlriver-answer"

const brand = {names:["Tuvio","Тувио"],domains:["tuvio.test"]}
it("renders XML structure and red brand accents without injecting provider markup", () => {
  const html = renderToStaticMarkup(<XMLRiverAnswer brand={brand} evidence={{content:[{tag:"h2",children:["TUVIO и Тувио"]},{tag:"p",children:["Не tuvioshop. ",{tag:"a",href:"https://shop.tuvio.test/a",children:["Официальный сайт"]},{tag:"script",children:["alert(1)"]},{tag:"a",href:"javascript:alert(1)",children:["плохая ссылка"]}]}],products:[],source_cards:[]}}/> )
  expect(html).toContain('<h2><mark class="answer-brand">TUVIO</mark>')
  expect(html).toContain('class="answer-brand-link"')
  expect(html).not.toContain('<script')
  expect(html).not.toContain('href="javascript:')
  expect(html).toContain('Не tuvioshop.')
  expect(brandLink("https://tuvio.test.evil.test",brand)).toBe(false)
  expect(brandLink("https://evil.test/?next=tuvio.test",brand)).toBe(false)
})
it("shows photo products in a labelled carousel and source cards with safe links", () => {
  const html = renderToStaticMarkup(<XMLRiverAnswer brand={brand} evidence={{content:["Совет"],products:[{title:"Tuvio робот",url:"https://shop.test/product",image_url:"https://photos.test/robot.jpg",price:"23 455 ₽"}],source_cards:[{title:"Источник Tuvio",url:"https://source.test",text:"Описание товара"}]}}/> )
  expect(html).toContain('src="https://photos.test/robot.jpg"')
  expect(html).toContain('loading="lazy"')
  expect(html).toContain('referrerPolicy="no-referrer"')
  expect(html).toContain('aria-label="Следующие товары"')
  expect(html).toContain('class="answer-brand">Tuvio</mark> робот')
  expect(html).toContain('23 455 ₽')
  expect(html).toContain('Карточки ответа')
})
it("displays organization cards without a link or photo instead of dropping them", () => {
  const html=renderToStaticMarkup(<XMLRiverAnswer brand={brand} evidence={{content:["Совет"],products:[],source_cards:[{title:"Клиника Tuvio",text:"",url:""}]}}/> )
  expect(html).toContain('Клиника <mark class="answer-brand">Tuvio</mark>')
  expect(html).not.toContain('href=""')
})
it("keeps unusable image URLs out of the browser and accents matching source domains", () => {
  for (const value of ["javascript:bad()","data:image/svg+xml,bad","https://127.0.0.1/a","https://localhost/a","http://photos.test/a"]) expect(safeProductImage(value)).toBe("")
  const html=renderToStaticMarkup(<HighlightedSources brand={brand} sources={["https://tuvio.test/product","https://source.test","javascript:bad()"]}/> )
  expect(html).toContain('class="answer-brand-link"')
  expect(html).not.toContain('javascript:')
})
