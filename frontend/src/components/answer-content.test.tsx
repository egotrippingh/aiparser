import { expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { AnswerContent, ResultIssue, SourceList, sourcesOf } from "./answer-content"

it("renders paragraphs, real lists and safe links while keeping HTML literal", () => {
  const html = renderToStaticMarkup(<AnswerContent text={'Intro <script>alert(1)</script>\r\n\r\n- One\n- Two https://example.test/a.\n\n3. Three\n4. Four\n\nEnd'}/>)
  expect(html).toContain('&lt;script&gt;')
  expect(html).not.toContain('<script>')
  expect(html).toContain('<ul><li>One</li>')
  expect(html).toContain('<ol start="3">')
  expect(html).toContain('href="https://example.test/a"')
  expect(html).toContain('rel="noopener noreferrer"')
  expect(html).toContain('</a>.')
  expect(renderToStaticMarkup(<AnswerContent text={'1. First\n9. Ninth'}/>)).toContain('9. Ninth')
  expect(renderToStaticMarkup(<AnswerContent text={'https://en.wikipedia.org/wiki/Function_(mathematics)'}/>)).toContain('href="https://en.wikipedia.org/wiki/Function_(mathematics)"')
  expect(renderToStaticMarkup(<AnswerContent text={'(https://example.test/item)'}/>)).toContain('href="https://example.test/item"')
})

it("keeps distinct query-string sources, deduplicates identical URLs and rejects unsafe URLs", () => {
  const sources=['https://example.test/?q=1','https://example.test/?q=2','https://example.test/?q=1','javascript:alert(1)','data:text/html,evil','https://user:secret@example.test','broken']
  expect(sourcesOf(sources)).toEqual(sources.slice(0,2))
  const html=renderToStaticMarkup(<SourceList sources={sources}/>)
  expect(html).toContain('?q=2')
  expect(html).not.toContain('javascript:')
  expect(html).not.toContain('secret')
})

it("shows the saved cause and honest retry guidance; handles old and empty answers", () => {
  const html=renderToStaticMarkup(<ResultIssue status="error" error={'main .prose timeout <img src=x>'}/>)
  expect(html).toContain('&lt;img')
  expect(html).toContain('автоматически не повторяется')
  expect(html).toContain('все запросы заново')
  expect(renderToStaticMarkup(<ResultIssue status="error"/>)).toContain('Обновите агент')
  expect(renderToStaticMarkup(<ResultIssue status="found" answer="Answer"/>)).toBe('')
  expect(renderToStaticMarkup(<SourceList sources={[]}/>)).toContain('Сохранённых ссылок')
})
