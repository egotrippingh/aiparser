import { afterEach, expect, it, vi } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { ControlCenter, ProjectRegistry, scanPercent, ScanProgress, ScheduleDays, runStatus } from "./control-center"
import { QueryLibrary } from "./query-library"
import { ProjectIcon, projectFavicon } from "./project-icon"
import { choiceIndex } from "./app-choice"
import { ReportChart, chartDays, chartIndex, chartTooltipPosition, linePath } from "./report-chart"
import { reportDisplayRows, reportRange, reportRows, reportSelection, trendText, trendTone, type Trend } from "./report-view"
import { isCurrentService } from "./service-mark"
import { LandingPage } from "./landing-page"

afterEach(() => vi.unstubAllGlobals())

it("opens the project list without project context or an icon rail", () => {
  vi.stubGlobal("location", {hash:"#/projects"})
  const html = renderToStaticMarkup(<ControlCenter token="test" email="owner@example.test" balance="0 ₽" admin={false} account={null} message="" brandClarificationsEnabled={false} onDirtyChange={()=>{}} logout={()=>{}} walletChanged={()=>{}}/>)
  expect(html).toContain('air-app projects-page')
  expect(html).not.toContain('<aside class="sidebar">')
  expect(html).toContain('<span>Выбрать проект</span>')
  expect(html).toContain('aria-label="Поиск проекта"')
})

it("shows real registry progress and filters without exposing viewer scheduling", () => {
  const project: Parameters<typeof ProjectRegistry>[0]["projects"][number] = {
    id: "alpha", revision: 0, name: "Альфа", brand_name: "Север", device_id: null,
    config: { brand_aliases: [], brand_domains: [], region_code: "213", services: ["chatgpt", "perplexity", "gemini", "google_aio", "yandex_neuro"], browser_mode: "headless", speed_profile: "fast", parallel: true },
    schedule: { enabled: true, device_id: null, month_days: [15], last_day: true, time: "09:00", timezone: "Europe/Moscow" },
    queries: [], query_count: 100, active_queries: 64,
  }
  const projects = [project, { ...project, id: "shared", name: "Общий", brand_name: "Доступный", shared: true, role: "viewer" as const }]
  const run = {
    id: "run-alpha", project_id: project.id, project_name: project.name, device_id: null, device_name: "", phase: "cloud",
    state: "running", desired_state: "running", error: null, total: 100, created_at: "", scheduled_for: null, progress: { done: 64 },
  }
  const render = (search = "", filter: Parameters<typeof ProjectRegistry>[0]["filter"] = "all") =>
    renderToStaticMarkup(<ProjectRegistry projects={projects} activeRuns={[run]} loading={false} loadFailed={false} openRun={()=>{}} search={search} filter={filter} onSearch={()=>{}} onFilter={()=>{}}/>)
  const all = render()
  expect(all).toContain('aria-label="Идёт проверка 64% — Альфа"')
  expect(all).toContain('<progress max="100" value="64"')
  expect(all).toContain('15-го и в последний день месяца')
  expect(all).toContain('href="#/project/alpha/schedule"')
  expect(all).not.toContain('href="#/project/shared/schedule"')
  expect(all).toContain("только просмотр")
  for (const mode of ["scheduled", "active"] as const) expect(render("", mode)).not.toContain('href="#/project/shared/report"')
  expect(render("  АЛЬфа ")).toContain('href="#/project/alpha/report"')
  expect(render("shared")).toContain('href="#/project/shared/report"')
  expect(render("Пропуск")).toContain("Проекты не найдены")
  expect(render("Пропуск")).toContain("Сбросить фильтры")
})

it("keeps a failed registry load distinct from an empty account", () => {
  const render = (loading: boolean, loadFailed: boolean) => renderToStaticMarkup(<ProjectRegistry projects={[]} activeRuns={[]} loading={loading} loadFailed={loadFailed} openRun={()=>{}} search="" filter="all" onSearch={()=>{}} onFilter={()=>{}}/>)
  expect(render(true, false)).toContain("Загрузка проектов")
  expect(render(false, false)).toContain("Начните с первого проекта")
  expect(render(false, true)).not.toContain("Начните с первого проекта")
})

it("offers days 1–28 and a last-day flag without converting legacy dates", () => {
  const html = renderToStaticMarkup(<ScheduleDays days={[]} lastDay={true} change={()=>{}}/> )
  expect(html.match(/aria-pressed=/g)).toHaveLength(29)
  expect(html).toContain('aria-label="Последний день месяца" aria-pressed="true"')
  expect(html).toContain(">28</button>")
  expect(html).not.toContain(">29</button>")
  const legacy = renderToStaticMarkup(<ScheduleDays days={[15,29,31]} lastDay={false} change={()=>{}}/> )
  expect(legacy).toContain('aria-label="Убрать число 29"')
  expect(legacy).toContain('aria-label="Убрать число 31"')
  expect(legacy).toContain('aria-label="Последний день месяца" aria-pressed="false"')
})

it("restores only valid calendar ranges within the report limit", () => {
  expect(reportRange({from:"2026-09-01",to:"2026-09-30"})).toEqual({from:"2026-09-01",to:"2026-09-30"})
  expect(reportRange({from:"2024-02-29",to:"2024-02-29"})).toEqual({from:"2024-02-29",to:"2024-02-29"})
  for (const value of [null, [], "bad", {from:"2026-02-30",to:"2026-03-01"}, {from:"2026-10-02",to:"2026-10-01"}, {from:"2025-01-01",to:"2026-01-02"}, {from:"0000-01-01",to:"0000-01-01"}, {from:3,to:"2026-01-01"}]) expect(reportRange(value)).toBeNull()
})

it("describes all five providers and keeps a responsive still before animation loads", () => {
  vi.stubGlobal("window", {matchMedia:()=>({matches:true})})
  const html = renderToStaticMarkup(<LandingPage/>).split('</section>')[0]
  for (const name of ["Google", "Яндекса", "Gemini", "ChatGPT", "Perplexity"]) expect(html).toContain(name)
  expect(html).toContain('<picture class="home-hero__still"')
  expect(html).toContain('media="(max-aspect-ratio: 1/1)"')
  expect(html).toContain('Начать проверку')
  expect(html).not.toContain('Войти в кабинет')
})

it("describes the REST API without directing visitors to a desktop installer", () => {
  vi.stubGlobal("window", {matchMedia:()=>({matches:true})})
  const html = renderToStaticMarkup(<LandingPage/>)
  expect(html).not.toMatch(/на вашем ПК|компьютер выполняет|\/app\/|\.exe|Windows\.zip/)
  expect(html).toContain('href="/docs/api/"')
})

it("shows automatic retries as processing but preserves explicit pauses and terminal states", () => {
  expect(runStatus({state:"paused",desired_state:"running",phase:"cloud"})).toBe("В процессе")
  expect(runStatus({state:"running",desired_state:"running",phase:"cloud"})).toBe("В процессе")
  expect(runStatus({state:"paused",desired_state:"paused",phase:"cloud"})).toBe("На паузе")
  expect(runStatus({state:"paused",desired_state:"running",phase:"agent"})).toBe("На паузе")
  expect(runStatus({state:"running",desired_state:"cancelled",phase:"cloud"})).toBe("Останавливается")
  expect(runStatus({state:"done",desired_state:"paused",phase:"cloud"})).toBe("Завершено")
})

it("reports real scan progress in bounded five-percent steps", () => {
  expect(scanPercent(7,20)).toBe(35)
  expect(scanPercent(14,99)).toBe(10)
  expect(scanPercent(0,0)).toBe(0)
  expect(scanPercent(-1,20)).toBe(0)
  expect(scanPercent(100,99)).toBe(100)
  expect(scanPercent(29,100,1)).toBe(29)
})

it("exposes the progress pie value without displaying a number", () => {
  for (const percent of [0,35,100]) {
    const html=renderToStaticMarkup(<ScanProgress percent={percent}/>)
    expect(html).toContain(`aria-valuenow="${percent}"`)
    expect(html).toContain(`--scan-target:${percent}%`)
    expect(html).toMatch(/><\/span>$/)
    expect(html).not.toMatch(/NaN|Infinity/)
  }
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

it("keeps project tools in an accessible icon rail and account navigation in the header", () => {
  vi.stubGlobal("location", {hash:"#/project/one/report"})
  const props = {token:"test",email:"owner@example.test",balance:"0 ₽",admin:false,account:<p>Wallet</p>,message:"",brandClarificationsEnabled:false,onDirtyChange:()=>{},logout:()=>{},walletChanged:()=>{}}
  const html = renderToStaticMarkup(<ControlCenter {...props}/>)
  const sidebar = html.match(/<aside class="sidebar">([\s\S]*?)<\/aside>/)![1]
  for (const label of ["Обзор видимости","Запросы","Источники","Настройки проекта","Расписание","История проверок"]) expect(sidebar).toContain(`aria-label="${label}"`)
  expect(sidebar).not.toMatch(/Проекты|Аккаунт|Помощь|owner@example|sidebar-account|title=/)
  expect(sidebar).not.toContain(">Запросы")
  expect(html).toContain("Меню аккаунта")
  expect(html).not.toMatch(/Администрирование|Компьютеры|Скачать агент|Private admin/)
  expect(renderToStaticMarkup(<ControlCenter {...props} admin/>)).not.toContain('href="/cabinet/?admin=1"')
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

it("keeps the tooltip within the chart at each corner", () => {
  expect(chartTooltipPosition(4, 3, 320, 240, 180, 90)).toEqual({ left: 16, top: 8 })
  expect(chartTooltipPosition(312, 3, 320, 240, 180, 90)).toEqual({ left: 120, top: 8 })
  expect(chartTooltipPosition(4, 238, 320, 240, 180, 90)).toEqual({ left: 16, top: 142 })
  expect(chartTooltipPosition(312, 238, 320, 240, 180, 90)).toEqual({ left: 120, top: 142 })
  expect(chartTooltipPosition(120, 80, 320, 240, 180, 90)).toEqual({ left: 132, top: 35 })
  expect(chartTooltipPosition(120, 160, 320, 240, 180, 90)).toEqual({ left: 132, top: 115 })
  expect(chartTooltipPosition(130, 95, 320, 140, 200, 112)).toEqual({ left: 8, top: 20 })
})

it("shows isolated measurements even when surrounding dates have no answers", () => {
  const html = renderToStaticMarkup(<ReportChart days={[
    {date:"2026-09-01",checked:1,issues:0,skipped:0,services:{chatgpt:{visibility_pct:75}}},
    {date:"2026-09-02",checked:0,issues:0,skipped:0,services:{chatgpt:{visibility_pct:null}}},
    {date:"2026-09-03",checked:1,issues:0,skipped:0,services:{chatgpt:{visibility_pct:0}}},
  ]} services={["chatgpt"]} available={["chatgpt"]} choose={()=>{}}/> )
  expect(html.match(/<circle /g)).toHaveLength(2)
})

it("uses pressed service buttons and preserves the last selected system", () => {
  const html = renderToStaticMarkup(<ReportChart days={[]} services={["chatgpt"]} available={["chatgpt","google_aio"]} choose={()=>{}}/> )
  expect(html).not.toContain('type="checkbox"')
  expect(html).toMatch(/<button[^>]*aria-pressed="true"[^>]*disabled=""[^>]*aria-label="Показывать ChatGPT"/)
  expect(html).toMatch(/<button[^>]*aria-pressed="false"[^>]*aria-label="Показывать Google AI Overview"/)
})

it("filters by full-period totals even when an earlier mention is outside the loaded date window", () => {
  const rows = [
    {trend:{current:{found:1,checked:2}},latest:{chatgpt:{status:"not_found",found:false}},cells:{"2026-10-14":{chatgpt:{status:"not_found",found:false}},"2026-10-10":{chatgpt:{status:"found",found:true}}}},
    {trend:{current:{found:0,checked:0}},latest:{},cells:{}},
  ] as unknown as Parameters<typeof reportRows>[0]
  expect(reportRows(rows,"found",false,["2026-10-14","2026-10-10"])).toEqual([rows[0]])
  expect(reportRows(rows,"found",false)).toEqual([rows[0]])
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

it("keeps missing/zero baselines neutral and shows share changes as percent", () => {
  expect(trendTone(null)).toBe("neutral")
  expect(trendTone(0)).toBe("neutral")
  expect(trendTone(5)).toBe("positive")
  expect(trendTone(-5)).toBe("negative")
  expect(trendText({delta:null} as Trend)).toBe("Нет полных данных для сравнения")
  expect(trendText({delta:66.7,relative:200} as Trend)).toBe("Рост: +66.7%")
  expect(trendText({delta:-25,relative:-50} as Trend)).toBe("Снижение: -25%")
})

it("filters the observable verdict, without counting excluded product cards as a mention", () => {
  const rows = [
    {latest:{google_aio:{status:"found",found:false}},trend:{current:{visibility_pct:0,found:0,checked:1}}},
    {latest:{chatgpt:{status:"found",found:true}},trend:{current:{visibility_pct:100,found:1,checked:1}}},
    {latest:{google_aio:{status:"not_found",found:false}},trend:{current:{visibility_pct:0,found:0,checked:1}}},
    {latest:{},trend:{current:{visibility_pct:null,found:0,checked:0}}},
  ] as unknown as Parameters<typeof reportRows>[0]
  expect(reportRows(rows,"found",false)).toEqual([rows[1]])
  expect(reportRows(rows,"not_found",false)).toEqual([rows[0],rows[2]])
  expect(reportRows(rows,"",true)[0]).toBe(rows[1])
  expect(rows[0].trend.current.visibility_pct).toBe(0)
})

it("keeps period mentions in the selected-period filter while showing endpoint trends", () => {
  const row = {trend:{current:{found:1,checked:2}},period_trend:{current:{found:0,checked:1}},latest:{}} as unknown as Parameters<typeof reportRows>[0][number]
  expect(reportDisplayRows([row],"found",false,false)).toEqual([{...row,trend:row.period_trend}])
})

it("filters comparison rows only by the two displayed dates", () => {
  const absent = {status:"not_found",found:false}, found = {status:"found",found:true}
  const rows = [
    {trend:{current:{found:1,checked:3}},latest:{google_aio:found},cells:{"2026-09-01":{google_aio:absent},"2026-09-02":{google_aio:found},"2026-09-03":{google_aio:absent}}},
    {trend:{current:{found:1,checked:2}},latest:{google_aio:absent},cells:{"2026-09-01":{google_aio:found},"2026-09-03":{google_aio:absent}}},
    {trend:{current:{found:0,checked:0}},latest:{},cells:{}},
  ] as unknown as Parameters<typeof reportRows>[0]
  const dates = ["2026-09-01","2026-09-03"]
  expect(reportRows(rows,"found",false,dates)).toEqual([rows[1]])
  expect(reportRows(rows,"not_found",false,dates)).toEqual([rows[0],rows[1]])
  expect(reportRows(rows,"found",false)).toEqual([rows[0],rows[1]])
})

it("includes absent AI blocks as no mention in period and comparison filters", () => {
  const rows = [
    {trend:{current:{found:0,checked:1}},latest:{yandex_neuro:{status:"skipped",found:false}},cells:{"2026-10-14":{yandex_neuro:{status:"skipped",found:false}}}},
    {trend:{current:{found:0,checked:0}},latest:{yandex_neuro:{status:"error",found:false}},cells:{"2026-10-14":{yandex_neuro:{status:"error",found:false}}}},
    {trend:{current:{found:0,checked:0}},latest:{},cells:{}},
  ] as unknown as Parameters<typeof reportRows>[0]
  for (const dates of [undefined, ["2026-10-14"]]) {
    expect(reportRows(rows,"not_found",false,dates)).toEqual([rows[0]])
    expect(reportRows(rows,"found",false,dates)).toEqual([])
  }
})

it("opens account-wide run history with the shared status filter", () => {
  vi.stubGlobal("location", { hash: "#/runs" })
  const html = renderToStaticMarkup(<ControlCenter token="test" email="owner@example.test" balance="0 ₽" admin={false} account={null} message="" brandClarificationsEnabled={false} onDirtyChange={()=>{}} logout={()=>{}} walletChanged={()=>{}}/>)
  expect(html).toContain('aria-label="Тип запуска"')
  expect(html).toContain('aria-label="Статус проверки"')
  expect(html).toContain("Загрузка проверок")
})

it("renders legacy query groups as folders without selecting active queries for bulk actions", () => {
  const html = renderToStaticMarkup(<QueryLibrary saving={false} onChange={()=>{}} queries={[
    { id: "first", text: "Активный запрос", group_tag: "Оборудование", active: true },
    { id: "second", text: "Запрос без папки", group_tag: "", active: false },
  ]}/>)
  expect(html).toContain(">Оборудование</span><small>1</small>")
  expect(html).toContain(">Без папки</span><small>1</small>")
  expect(html).toMatch(/aria-label="Выбрать запрос: Активный запрос"\/>/)
  expect(html).toMatch(/aria-label="Проверять: Активный запрос" checked=""/)
  expect(html).not.toContain("Удалить выбранные")
})
