import { afterEach, expect, it, vi } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { ControlCenter } from "./control-center"
import { choiceIndex } from "./app-choice"
import { ReportChart, chartIndex, linePath } from "./report-chart"
import { reportRows, trendText, trendTone, type Trend } from "./report-view"

afterEach(() => vi.unstubAllGlobals())

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
    {date:"2026-09-01",services:{chatgpt:{visibility_pct:75}}},
    {date:"2026-09-02",services:{chatgpt:{visibility_pct:null}}},
    {date:"2026-09-03",services:{chatgpt:{visibility_pct:0}}},
  ]} services={["chatgpt"]} available={["chatgpt"]} choose={()=>{}}/> )
  expect(html.match(/<circle /g)).toHaveLength(2)
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
