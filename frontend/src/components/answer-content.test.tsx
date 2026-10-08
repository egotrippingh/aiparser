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
  expect(renderToStaticMarkup(<AnswerContent text={'1. First\n9. Ninth'}/>)).toContain('<li value="9">Ninth</li>')
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

it("only hides the confirmed ChatGPT map prefix and keeps its saved text available", () => {
  const map = '4.9\nPlace\nUse two fingers to move the map\nPlace\nОставить отзыв\n\nUseful prose\n\n- one\n- two'
  const html = renderToStaticMarkup(<AnswerContent text={map} service="chatgpt"/>)
  expect(html).toContain('Useful prose')
  expect(html).not.toContain('<p>4.9')
  expect(html).toContain('Исходный текст')
  expect(renderToStaticMarkup(<AnswerContent text={'4.9\nBudget 5-7\nUseful prose'} service="chatgpt"/>)).toContain('4.9')
})

it("uses saved source URLs only for unambiguous bare domains and keeps code literal", () => {
  const html = renderToStaticMarkup(<AnswerContent text={'[Named](https://example.test/a?q=(x))\n\nexample.org/path\n\n`https://code.test`'} sources={['https://example.org/path', 'https://else.test/']}/>)
  expect(html).toContain('href="https://example.test/a?q=(x)"')
  expect(html).toContain('href="https://example.org/path"')
  expect(html).not.toContain('href="https://code.test"')
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

it("renders captured structure, nested lists, exact named links and literal fenced code", () => {
  const html = renderToStaticMarkup(<AnswerContent text={'## Heading\n\nIntro\n- One\n  - Nested\n- Two\nEnd\n\n3. Three\n8. Eight\n9. Nine\n\n[A](<https://a.test/path)>) and [B](https://b.test/?q=(x))\n\n```\n  4.9\n\n  https://code.test\n```\n\n•\nBudget 4.9 and 5–7.'}/>)
  expect(html).toContain('<h2>Heading</h2>')
  expect(html).toContain('<p>Intro</p><ul><li>One<ul><li>Nested</li></ul></li><li>Two</li></ul><p>End</p>')
  expect(html).toContain('<li value="8">Eight</li><li value="9">Nine</li>')
  expect(html).toContain('href="https://a.test/path)"')
  expect(html).toContain('href="https://b.test/?q=(x)"')
  expect(html).toContain('<pre><code>  4.9\n\n  https://code.test</code></pre>')
  expect(html).not.toContain('href="https://code.test"')
  expect(html).not.toContain('•')
  expect(html).toContain('Budget 4.9 and 5–7.')
  expect(renderToStaticMarkup(<AnswerContent text={'```inline```'}/>)).toContain('<code>inline</code>')
  expect(renderToStaticMarkup(<AnswerContent text={'- Item\n  ```\n    space\n  ```'}/>)).toContain('<pre><code>  space</code></pre>')
  expect(renderToStaticMarkup(<AnswerContent text={'```\nfirst\nhttps://code.test\n```'}/>)).toContain('<pre><code>first\nhttps://code.test</code></pre>')
  expect(renderToStaticMarkup(<AnswerContent text={'[first second](<https://actual.test/>)'}/>)).toContain('href="https://actual.test/" target="_blank" rel="noopener noreferrer">first second</a>')
  expect(renderToStaticMarkup(<AnswerContent text={'- Parent\n  ```\n    preserve  \n   \n    later \n  ```'}/>)).toContain('<pre><code>  preserve  \n \n  later </code></pre>')
  expect(renderToStaticMarkup(<AnswerContent text={'-\n  ```\n    first\n  https://code.test\n  ```'}/>)).toContain('<ul><li><pre><code>  first\nhttps://code.test</code></pre></li></ul>')
  expect(renderToStaticMarkup(<AnswerContent text={'-\n  - Nested'}/>)).toContain('<ul><li><ul><li>Nested</li></ul></li></ul>')
})

it("never guesses a source path, lowercases its path or links an email", () => {
  const html = renderToStaticMarkup(<AnswerContent text={'example.org/one\nexample.org/Case?q=1\na@example.org\n[Bad](<https://user:secret@example.org/>)'} sources={['https://example.org/Case?q=1']}/>)
  expect(html).not.toContain('href="https://example.org/one"')
  expect(html).not.toContain('>example.org/one</a>')
  expect(html).toContain('href="https://example.org/Case?q=1"')
  expect(html).not.toContain('>example.org</a>')
  expect(html).not.toContain('href="https://user:secret')
})

it.each(['chatgpt', 'perplexity', 'alice', 'google_aio'])("hides standalone source counters for %s without changing prose, code or sources", service => {
  const sources = ['https://example.test/source']
  const text = 'Answer\nexample.test/source\n+1\n\nMore prose\n\u00a0+12\n\n- Item\n  +2\n  Continuation\n\nC++ and 2 + 1; temperature +2 °C.\n\n`+3`\n\n```\n+4\n```\n\n- Code\n  ```\n  +5\n  ```'
  const html = renderToStaticMarkup(<><AnswerContent text={text} service={service} sources={sources}/><SourceList sources={sources}/></>)
  const display = html.split('<details')[0]
  expect(display).not.toContain('<p>+1')
  expect(display).not.toContain('+12')
  expect(display).not.toContain('<br/>  +2')
  expect(display).toContain('C++ and 2 + 1; temperature +2 °C.')
  expect(display).toContain('<code>+3</code>')
  expect(display).toContain('<pre><code>+4</code></pre>')
  expect(display).toContain('<pre><code>+5</code></pre>')
  expect(display).toContain('href="https://example.test/source"')
  expect(display).toContain('Continuation')
  expect(html).toContain('Исходный текст')
  expect(html).toContain('+12')
  expect(html).toContain('class="answer-sources"')
})

it.each(['chatgpt', 'perplexity', 'alice', 'google_aio'])("formats tables and bold nested lists for %s", service => {
  const text = 'Intro\n| Service | Price | Site |\n| :--- | ---: | :---: |\n| **Company** | +2 | [Source](<https://example.test/?q=a\\|b>) |\n| Other | | `a|b` |\nAfter\n\n- **Main option**\n  3. Nested\n  8. Another\n\n-\n  | A | B |\n  | --- | --- |\n  | x | y |'
  const html = renderToStaticMarkup(<AnswerContent text={text} service={service}/>)
  expect(html).toContain('aria-label="Таблица ответа" tabindex="0"')
  expect(html).toContain('<thead><tr><th scope="col" style="text-align:left">Service</th>')
  expect(html).toContain('<td style="text-align:right">+2</td>')
  expect(html).toContain('<strong>Company</strong>')
  expect(html).toContain('<td style="text-align:right"></td>')
  expect(html).toContain('href="https://example.test/?q=a|b"')
  expect(html).toContain('<code>a|b</code>')
  expect(html).toContain('<p>After</p>')
  expect(html).toContain('<strong>Main option</strong><ol start="3">')
  expect(html).toContain('<li value="8">Another</li>')
  expect(html).toContain('<li><div class="answer-table-scroll"')
})

it("keeps malformed tables and code literal; displays TSV and headerless tables safely", () => {
  const html = renderToStaticMarkup(<AnswerContent text={'Name\tPrice\nCompany\t100\n\n| | |\n| --- | --- |\n| x | y |\n\n| A | B |\n| --- | --- |\n| mismatched | row | keep |\n\n```\n| A | B |\n| --- | --- |\n| x | y |\n```\n\n| HTML | URL |\n| --- | --- |\n| <img src=x> | [bad](<javascript:alert(1)>) |'}/>)
  expect(html).toContain('>Company</td>')
  expect(html).toContain('<tbody><tr><td style="text-align:left">x</td>')
  expect(html).toContain('mismatched | row | keep')
  expect(html).toContain('<pre><code>| A | B |')
  expect(html).not.toContain('<img')
  expect(html).not.toContain('href="javascript:')
})

it("preserves one-column tables and escaped backticks, code spaces and bold-code boundaries", () => {
  const html = renderToStaticMarkup(<AnswerContent text={'| Code |\n| --- |\n| `a  b` |\n| `a\\`\\|b` |\n\n**`a**https://code.test/path`**\n\n```\nfirst\n```\n\nOther\nAfter'}/>)
  expect(html).toContain('<th scope="col" style="text-align:left">Code</th>')
  expect(html).toContain('<code>a  b</code>')
  expect(html).toContain('<code>a`|b</code>')
  expect(html).not.toContain('href="https://code.test')
  expect(html).toContain('<code>a**https://code.test/path</code>')
  expect(html).toContain('<p>Other<br/>After</p>')
  const single = renderToStaticMarkup(<AnswerContent text={'| Header |\n| --- |\n| Keep |\nAfter table'}/>)
  expect(single).toContain('</table></div><p>After table</p>')
  expect(single).not.toContain('>After table</td>')
})
