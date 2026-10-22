import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ReportCalendar, restoreDateSelection, defaultDateSelection, type ReportDateSelection } from './report-calendar'
import { recomputeSelection, selectionLabel } from './recompute-selection'

const base: ReportDateSelection = {mode:'period',picked:[],maxDates:30}
const available = ['2026-09-01','2026-09-02','2026-09-04']
it('freezes exact dates for one day, a period, onward and disjoint selection', () => {
  expect(recomputeSelection('2026-09-01','2026-09-04',available,base)).toEqual({from_date:'2026-09-01',to_date:'2026-09-04',dates:null})
  expect(recomputeSelection('2026-09-01','2026-09-04',available,{...base,mode:'day'})).toEqual({from_date:'2026-09-01',to_date:'2026-09-01',dates:null})
  expect(recomputeSelection('2026-09-01','2026-09-04',available,{...base,mode:'from'})).toEqual({from_date:'2026-09-01',to_date:null,dates:null})
  const picked=['2026-09-01','2026-09-04']
  const scope = recomputeSelection(picked[0],picked[1],available,{...base,mode:'custom',picked})
  picked.push('2026-09-02')
  expect(scope.dates).toEqual(['2026-09-01','2026-09-04'])
  expect(selectionLabel(scope)).toBe('01.09.2026, 04.09.2026')
})
it('uses actual scan dates for monthly selection and exact endpoints for two dates', () => {
  expect(recomputeSelection('2026-09-01','2026-09-04',available,{...base,mode:'monthly'}).dates).toEqual(['2026-09-04'])
  expect(recomputeSelection('2026-09-01','2026-09-04',available,{...base,mode:'two'}).dates).toEqual(['2026-09-01','2026-09-04'])
})
it('reuses the calendar with a single day and clear recompute labels', () => {
  const html=renderToStaticMarkup(<ReportCalendar from='2026-09-01' to='2026-09-01' available={available} selection={{...base,mode:'day'}} context='recompute' change={()=>{}}/>)
  expect(html).toContain('Даты пересчёта')
  expect(html).toContain('Один день')
  expect(html).not.toContain('Последняя дата')
  expect(html).not.toContain('В отчёте')
  expect(html).not.toContain('Сравнение двух дат')
})

it('keeps recompute-only modes out of restored report state', () => {
  for(const mode of ['from','day']) expect(restoreDateSelection({...base,mode},'2026-09-01','2026-09-04')).toEqual(defaultDateSelection)
})
