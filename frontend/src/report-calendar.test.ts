import { expect, it } from "vitest"
import { calendarDates, restoreDateSelection, defaultDateSelection, type ReportDateSelection } from "./report-calendar"
const selection: ReportDateSelection = {mode:"period",picked:[],maxDates:30}
const available = ["2026-08-01","2026-08-30","2026-09-03","2026-09-15","2026-10-01"]
it("restores the complete filter after reload and rejects invalid saved choices", () => {
  const custom = {...selection,mode:"custom" as const,picked:["2026-08-01","2026-09-15"],maxDates:15}
  expect(restoreDateSelection(JSON.parse(JSON.stringify(custom)),"2026-08-01","2026-10-01")).toEqual(custom)
  for (const value of [null,{...custom,maxDates:50},{...custom,picked:["2026-08-32"]},{...custom,picked:["2026-10-02"]},{...custom,mode:"yandex_updates"}]) expect(restoreDateSelection(value,"2026-08-01","2026-10-01")).toEqual(defaultDateSelection)
})
it("selects the last actual check in each month inside the chosen range", () => {
  expect(calendarDates("2026-08-01","2026-09-10",available,{...selection,mode:"monthly"})).toEqual(["2026-08-30","2026-09-03"])
  expect(calendarDates("2026-08-01","2026-10-01",available,{...selection,mode:"monthly",maxDates:2})).toEqual(["2026-09-15","2026-10-01"])
})
it("keeps exactly the two boundaries, and deduplicates arbitrary dates", () => {
  expect(calendarDates("2026-08-05","2026-09-10",available,{...selection,mode:"two"})).toEqual(["2026-08-05","2026-09-10"])
  expect(calendarDates("2026-08-05","2026-08-05",available,{...selection,mode:"two"})).toEqual(["2026-08-05"])
  expect(calendarDates("2026-08-01","2026-10-01",available,{...selection,mode:"custom",picked:["2026-09-15","2026-08-01","2026-09-15"]})).toEqual(["2026-08-01","2026-09-15"])
})
