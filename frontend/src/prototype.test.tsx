import { afterEach, expect, it, vi } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { ControlCenter, RunProgress, runStatus } from "./control-center"
import { ProjectIcon, projectFavicon } from "./project-icon"
import { choiceIndex } from "./app-choice"
import { ReportChart, chartDays, chartIndex, linePath } from "./report-chart"
import { reportRange, reportRows, reportSelection, trendText, trendTone, type Trend } from "./report-view"
import { isCurrentService } from "./service-mark"
import { LandingPage } from "./landing-page"

afterEach(() => vi.unstubAllGlobals())

it("restores only valid calendar ranges within the report limit", () => {
  expect(reportRange({from:"2026-09-01",to:"2026-09-30"})).toEqual({from:"2026-09-01",to:"2026-09-30"})
  expect(reportRange({from:"2024-02-29",to:"2024-02-29"})).toEqual({from:"2024-02-29",to:"2024-02-29"})
  for (const value of [null, [], "bad", {from:"2026-02-30",to:"2026-03-01"}, {from:"2026-10-02",to:"2026-10-01"}, {from:"2025-01-01",to:"2026-01-02"}, {from:"0000-01-01",to:"0000-01-01"}, {from:3,to:"2026-01-01"}]) expect(reportRange(value)).toBeNull()
})

it("uses the Gemini logo on the homepage", () => {
  vi.stubGlobal("window", {matchMedia:()=>({matches:true})})
  expect(renderToStaticMarkup(<LandingPage/>)).toMatch(/<img[^>]+src="\/assets\/services\/gemini\.png"[^>]+alt="Gemini"/)
})

it("shows automatic retries as processing but preserves explicit pauses and terminal states", () => {
  expect(runStatus({state:"paused",desired_state:"running",phase:"cloud"})).toBe("В процессе")
  expect(runStatus({state:"running",desired_state:"running",phase:"cloud"})).toBe("В процессе")
  expect(runStatus({state:"paused",desired_state:"paused",phase:"cloud"})).toBe("На паузе")
  expect(runStatus({state:"paused",desired_state:"running",phase:"agent"})).toBe("На паузе")
  expect(runStatus({state:"running",desired_state:"cancelled",phase:"cloud"})).toBe("Останавливается")
  expect(runStatus({state:"done",desired_state:"paused",phase:"cloud"})).toBe("Завершено")
})

it("renders current project progress including zero and safe totals", () => {
  const run = {state:"paused",desired_state:"running",phase:"cloud",project_name:"Test",total:20,progress:{done:7},error:null}
  const html = renderToStaticMarkup(<RunProgress run={run} details={()=>{}}/>)
  expect(html).toContain("В процессе")
  expect(html).toContain("7 / 20")
  expect(html).toMatch(/<progress[^>]*max="20"[^>]*value="7"/)
  expect(html).toContain('aria-label="Прогресс Test"')
  expect(renderToStaticMarkup(<RunProgress run={{...run,total:0,progress:{done:0}}} details={()=>{}}/>)).toContain('max="1" value="0"')
})

it("loads project icons only from the first brand domain with safe fallback", () => {
  expect(projectFavicon(["example.ru","second.test"])).toBe("https://example.ru/favicon.ico")
  expect(projectFavicon(["https://пример.рф/path?q=1"])).toBe("https://xn--e1afmkfd.xn--p1ai/favicon.ico")
  for (const domain of ["javascript:alert(1)","data:image/svg+xml,x","https://user:pass@example.ru","", "bad domain"]) expect(projectFavicon([domain,"second.test"])).toBeNull()
  expect(projectFavicon([])).toBeNull()
  expect(renderToStaticMarkup(<ProjectIcon name="Test" domains={[]}/>)).toContain(">T</span>")
  const html = renderToStaticMarkup(<ProjectIcon name="Test" domains={["example.ru"]}/> )
  expect(html).toContain('src="https://example.ru/favicon.ico"')
  expect(html).toContain('referrerPolicy="no-referrer"')
})

it("keeps Yandex Search with Alice while hiding the retired standalone Alice", () => {
  expect(["alice","yandex_neuro","chatgpt","perplexity"].filter(isCurrentService)).toEqual(["yandex_neuro","chatgpt","perplexity"])
})

it("preserves current saved report choices while removing retired or invalid choices", () => {
  expect(reportSelection(["alice","chatgpt","chatgpt"])).toEqual(["chatgpt"])
  expect(reportSelection(["alice"])).toBeNull()
  expect(reportSelection([])).toBeNull()
  expect(reportSelection(["chatgpt",{}])).toBeNull()
})

it("limits saved report choices to the project's configured systems", () => {
  const configured = ["chatgpt", "perplexity"]
  expect(reportSelection(["google_aio", "chatgpt", "perplexity", "gemini"], configured)).toEqual(configured)
  expect(reportSelection(["perplexity"], configured)).toEqual(["perplexity"])
  expect(reportSelection(["gemini"], configured)).toBeNull()
  expect(reportSelection(["chatgpt"], [])).toBeNull()
  expect(reportSelection(null, configured)).toBeNull()
})

it("keeps all nine app sections and hides administration for an ordinary account", () => {
  vi.stubGlobal("location", {hash:"#/projects"})
  const props = {token:"test",email:"owner@example.test",balance:"0 ₽",admin:false,account:<p>Wallet</p>,administration:<p>Private admin</p>,message:"",brandClarificationsEnabled:false,onDirtyChange:()=>{},logout:()=>{},walletChanged:()=>{}}
  const html = renderToStaticMarkup(<ControlCenter {...props}/>)
  for (const label of ["Обзор видимости","Проекты","Запросы","Источники","Настройки проекта","Расписание","История проверок","Аккаунт и оплата","Помощь"]) expect(html).toContain(label)
  expect(html).not.toMatch(/Администрирование|Компьютеры|Скачать агент|Private admin/)
  expect(renderToStaticMarkup(<ControlCenter {...props} admin/>)).toContain("Администрирование")
})

it("opens searchable choices at the correct end and wraps keyboard selection", () => {
  expect(choiceIndex(-1,"ArrowDown",3)).toBe(0)
  expect(choiceIndex(-1,"ArrowUp",3)).toBe(2)
  expect(choiceIndex(0,"ArrowUp",3)).toBe(2)
  expect(choiceIndex(2,"ArrowDown",3)).toBe(0)
  expect(choiceIndex(1,"Home",3)).toBe(0)
  expect(choiceIndex(1,"End",3)).toBe(2)
  expect(choiceIndex(-1,"ArrowDown",0)).toBe(-1)
})

it("supports chart keyboard boundaries, empty days and Escape", () => {
  expect(chartIndex(null,"ArrowLeft",3)).toBe(2)
  expect(chartIndex(null,"ArrowRight",3)).toBe(0)
  expect(chartIndex(0,"ArrowLeft",3)).toBe(0)
  expect(chartIndex(2,"ArrowRight",3)).toBe(2)
  expect(chartIndex(1,"Home",3)).toBe(0)
  expect(chartIndex(1,"End",3)).toBe(2)
  expect(chartIndex(1,"Escape",3)).toBeNull()
  expect(chartIndex(null,"End",0)).toBeNull()
  expect(linePath([10,20,null,30], i=>i,v=>v)).toBe("M0.0,10.0 L1.0,20.0  M3.0,30.0")
})

it("shows isolated measurements even when surrounding dates have no answers", () => {
  const html = renderToStaticMarkup(<ReportChart days={[
    {date:"2026-09-01",checked:1,issues:0,skipped:0,services:{chatgpt:{visibility_pct:75}}},
    {date:"2026-09-02",checked:0,issues:0,skipped:0,services:{chatgpt:{visibility_pct:null}}},
    {date:"2026-09-03",checked:1,issues:0,skipped:0,services:{chatgpt:{visibility_pct:0}}},
  ]} services={["chatgpt"]} available={["chatgpt"]} choose={()=>{}}/> )
  expect(html.match(/<circle /g)).toHaveLength(2)
})

it("shows only actual scan dates and never adds a dashed interpolation", () => {
  expect(linePath([null,0,null,60,null], i=>i,v=>v).replace(/\s+/g," ").trim()).toBe("M1.0,0.0 M3.0,60.0")
  expect(linePath([null,null], i=>i,v=>v).trim()).toBe("")
  expect(linePath([null,25,null], i=>i,v=>v).trim()).toBe("M1.0,25.0")
  const html = renderToStaticMarkup(<ReportChart days={[0,25,null,75].map((value,i)=>({date:`2026-09-0${i+1}`,checked:value === null ? 0 : 1,issues:0,skipped:0,services:{chatgpt:{visibility_pct:value}}}))} services={["chatgpt"]} available={["chatgpt"]} choose={()=>{}}/> )
  expect(html).not.toContain('stroke-dasharray="4 4"')
  expect(html.match(/<circle /g)).toHaveLength(3)
  expect(html).not.toContain("пунктир")
})

it("keeps failed and skipped scan dates while omitting calendar placeholders", () => {
  const days = chartDays([
    {date:"2026-10-10",checked:1,issues:0,skipped:0,services:{chatgpt:{visibility_pct:0}}},
    {date:"2026-10-11",checked:0,issues:0,skipped:0,services:{chatgpt:{visibility_pct:null}}},
    {date:"2026-10-12",checked:0,issues:1,skipped:1,services:{chatgpt:{visibility_pct:null}}},
  ])
  expect(days.map(day => day.date)).toEqual(["2026-10-10", "2026-10-12"])
  expect(chartIndex(null, "Home", days.length)).toBe(0)
  expect(chartIndex(0, "ArrowRight", days.length)).toBe(1)
})

it("keeps missing/zero baselines neutral and distinguishes points from relative percent", () => {
  expect(trendTone(null)).toBe("neutral")
  expect(trendTone(0)).toBe("neutral")
  expect(trendTone(5)).toBe("positive")
  expect(trendTone(-5)).toBe("negative")
  expect(trendText({delta:null} as Trend)).toBe("Нет полных данных для сравнения")
  expect(trendText({delta:100,relative:null} as Trend)).toBe("Рост: +100 п.п.")
  expect(trendText({delta:-25,relative:-50} as Trend)).toBe("Снижение: -25 п.п. (-50%)")
})

it("filters the observable verdict, without counting excluded product cards as a mention", () => {
  const rows = [
    {latest:{google_aio:{status:"found",found:false}},trend:{current:{visibility_pct:0}}},
    {latest:{chatgpt:{status:"found",found:true}},trend:{current:{visibility_pct:100}}},
    {latest:{google_aio:{status:"not_found",found:false}},trend:{current:{visibility_pct:0}}},
    {latest:{},trend:{current:{visibility_pct:null}}},
  ] as unknown as Parameters<typeof reportRows>[0]
  expect(reportRows(rows,"found",false)).toEqual([rows[1]])
  expect(reportRows(rows,"not_found",false)).toEqual([rows[2]])
  expect(reportRows(rows,"",true)[0]).toBe(rows[1])
  expect(rows[0].trend.current.visibility_pct).toBe(0)
})

it("filters comparison rows only by the two displayed dates", () => {
  const absent = {status:"not_found",found:false}, found = {status:"found",found:true}
  const rows = [
    {latest:{google_aio:found},cells:{"2026-09-01":{google_aio:absent},"2026-09-02":{google_aio:found},"2026-09-03":{google_aio:absent}}},
    {latest:{google_aio:absent},cells:{"2026-09-01":{google_aio:found},"2026-09-03":{google_aio:absent}}},
    {latest:{},cells:{}},
  ] as unknown as Parameters<typeof reportRows>[0]
  const dates = ["2026-09-01","2026-09-03"]
  expect(reportRows(rows,"found",false,dates)).toEqual([rows[1]])
  expect(reportRows(rows,"not_found",false,dates)).toEqual([rows[0],rows[1]])
  expect(reportRows(rows,"found",false)).toEqual([rows[0]])
})
