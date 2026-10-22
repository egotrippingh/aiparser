import { useRef, useState } from "react"
import { CalendarDays, ChevronLeft, ChevronRight, X } from "lucide-react"
import { iso, today } from "./lib/dates"
import { AppChoice } from "./app-choice"

export const shortDate = (value: string) => new Date(value + "T12:00:00").toLocaleDateString("ru-RU", {day:"2-digit",month:"2-digit"})
export type ReportDateSelection = { mode: "period" | "two" | "monthly" | "custom" | "day" | "from"; picked: string[]; maxDates: number }
export const defaultDateSelection: ReportDateSelection = {mode:"period",picked:[],maxDates:30}
const modes = [{value:"period",label:"Период"},{value:"two",label:"Две даты"},{value:"monthly",label:"Последняя проверка месяца"},{value:"custom",label:"Произвольные даты"}] as const
const monthNames = Array.from({length:12},(_,i)=>new Date(2026,i,1).toLocaleDateString("ru-RU",{month:"long"}).replace(/^./,letter=>letter.toLocaleUpperCase("ru-RU")))

export function restoreDateSelection(saved: unknown, from: string, to: string): ReportDateSelection {
  if (!saved || typeof saved!=="object") return defaultDateSelection
  const {mode,picked,maxDates} = saved as ReportDateSelection
  if (!modes.some(item=>item.value===mode) || ![10,15,30].includes(maxDates) || !Array.isArray(picked) || picked.length>maxDates) return defaultDateSelection
  if (!picked.every(day=>typeof day==="string" && /^\d{4}-\d{2}-\d{2}$/.test(day) && iso(new Date(day+"T12:00:00"))===day && day>=from && day<=to)) return defaultDateSelection
  if ((mode==="custom" || mode==="monthly") && !picked.length) return defaultDateSelection
  return {mode,picked:[...new Set(picked)].sort(),maxDates}
}

export function calendarDates(from: string, to: string, available: string[], selection: ReportDateSelection) {
  if (selection.mode === "custom") return [...new Set(selection.picked)].sort()
  if (selection.mode === "two") return [...new Set([from,to])]
  const days = [...new Set(available)].filter(day=>day>=from && day<=to).sort()
  if (selection.mode === "monthly") {
    const last = new Map<string,string>()
    for (const day of days) last.set(day.slice(0,7),day)
    return [...last.values()].slice(-selection.maxDates)
  }
  return days.slice(-selection.maxDates)
}

export function ReportCalendar({ from, to, available, selection, change, context = "report", disabled = false }: {
  from: string; to: string; available: string[]; selection: ReportDateSelection; context?: "report" | "recompute"; disabled?: boolean
  change: (from: string, to: string, selection: ReportDateSelection) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [start,setStart] = useState(from), [end,setEnd] = useState(to)
  const [draft,setDraft] = useState(selection)
  const [month,setMonth] = useState(new Date(from+"T12:00:00"))
  const [pickingEnd,setPickingEnd] = useState(false)
  const [activePreset,setActivePreset] = useState("Произвольный")
  const single = context === "recompute" && (draft.mode === "day" || draft.mode === "from")
  const chosen = single ? [start] : calendarDates(start,end,available,draft)
  const rangeValid = !!start && !!end && start<=end && (Date.parse(end)-Date.parse(start))/86400000<=365
  const valid = rangeValid && (draft.mode!=="custom" || draft.picked.length>0 && draft.picked.length<=draft.maxDates) && (draft.mode!=="monthly" || chosen.length>0)
  function pick(day: string) {
    setActivePreset("Произвольный")
    if (single) {setStart(day);setEnd(day);setPickingEnd(false)}
    else if (draft.mode === "custom") {
      const picked = draft.picked.includes(day) ? draft.picked.filter(d=>d!==day) : [...draft.picked,day].sort()
      if (picked.length>draft.maxDates) return
      setDraft({...draft,picked})
      if (picked.length) {setStart(picked[0]);setEnd(picked.at(-1)!)}
    } else if (!pickingEnd || day<start) {setStart(day);setEnd(day);setPickingEnd(true)}
    else {setEnd(day);setPickingEnd(false)}
  }
  function preset(label: string) {
    setActivePreset(label);setPickingEnd(false)
    if (label === "Произвольный") return
    const last = new Date(today()+"T12:00:00"), first = new Date(last)
    if (label === "1 Год") first.setDate(first.getDate()-364)
    if (label === "1 Месяц") first.setDate(first.getDate()-29)
    if (label === "1 Неделя") first.setDate(first.getDate()-6)
    if (label === "Текущий месяц") first.setDate(1)
    if (label === "Прошлый месяц") {first.setDate(1);first.setMonth(first.getMonth()-1);last.setDate(0)}
    setStart(iso(first));setEnd(iso(last));setMonth(new Date(first.getFullYear(),first.getMonth(),1))
    setDraft({...draft,mode:draft.mode==="custom"?"period":draft.mode})
  }
  return <><button className="btn report-calendar-trigger" aria-haspopup="dialog" disabled={disabled} onClick={()=>{
    setStart(from);setEnd(to);setDraft(selection);setMonth(new Date(from+"T12:00:00"));setPickingEnd(false);setActivePreset("Произвольный");dialog.current?.showModal()
  }}><CalendarDays size={16}/>{selection.mode==="custom" ? `Выбрано дат: ${selection.picked.length}` : selection.mode==="from" ? `С ${shortDate(from)}.${from.slice(0,4)}` : selection.mode==="day" ? `${shortDate(from)}.${from.slice(0,4)}` : `${shortDate(from)}.${from.slice(0,4)} — ${shortDate(to)}.${to.slice(0,4)}`}</button>
    <dialog ref={dialog} className="ws-dialog calendar-dialog" aria-labelledby="calendar-title">
      <div className="ws-dialog-head"><h2 id="calendar-title">{context === "recompute" ? "Даты пересчёта" : "Даты отчёта"}</h2><button className="btn icon-only" aria-label="Закрыть календарь" onClick={()=>dialog.current?.close()}><X size={18}/></button></div>
      <div className="calendar-layout"><div className="calendar-main">
        {!single && <div className="calendar-presets" aria-label="Быстрый период">{["1 Год","Прошлый месяц","Текущий месяц","1 Месяц","1 Неделя","Произвольный"].map(label=><button key={label} type="button" aria-pressed={activePreset===label} onClick={()=>preset(label)}>{label}</button>)}</div>}
        <div className="calendar-nav"><button className="btn icon-only" aria-label="Предыдущий месяц" onClick={()=>setMonth(new Date(month.getFullYear(),month.getMonth()-1,1))}><ChevronLeft size={16}/></button><span>{single ? "Выберите дату" : draft.mode==="custom" ? "Отметьте нужные даты" : pickingEnd ? "Выберите последнюю дату" : "Выберите первую и последнюю дату"}</span><button className="btn icon-only" aria-label="Следующий месяц" onClick={()=>setMonth(new Date(month.getFullYear(),month.getMonth()+1,1))}><ChevronRight size={16}/></button></div>
        <div className="calendar-months">{[0,1,2].map(shift=>{
          const first=new Date(month.getFullYear(),month.getMonth()+shift,1), offset=(first.getDay()+6)%7
          const days=new Date(first.getFullYear(),first.getMonth()+1,0).getDate()
          return <div key={shift} className="calendar-month"><div className="calendar-month-title">{shift===0 ? <>
            <AppChoice label="Первый месяц" value={String(month.getMonth())} options={monthNames.map((label,i)=>({value:String(i),label}))} change={value=>setMonth(new Date(month.getFullYear(),Number(value),1))}/>
            <input aria-label="Год первого месяца" type="number" min="1900" max="9998" key={month.getFullYear()} defaultValue={month.getFullYear()} onKeyDown={e=>{if(e.key==="Enter")e.currentTarget.blur()}} onBlur={e=>{const year=Number(e.target.value);if(year>=1900 && year<=9998)setMonth(new Date(year,month.getMonth(),1));else e.target.value=String(month.getFullYear())}}/>
          </> : <><span className="calendar-month-name">{monthNames[first.getMonth()]}</span><span className="calendar-month-year">{first.getFullYear()}</span></>}</div>
          <div className="calendar-grid">{["Пн","Вт","Ср","Чт","Пт","Сб","Вс"].map(day=><small key={day}>{day}</small>)}{Array.from({length:offset},(_,i)=><span key={`blank-${i}`}/>)}{Array.from({length:days},(_,i)=>{
            const day=iso(new Date(first.getFullYear(),first.getMonth(),i+1))
            const selected=single ? day===start : draft.mode==="custom" ? draft.picked.includes(day) : draft.mode==="monthly" ? chosen.includes(day) : draft.mode==="two" ? day===start||day===end : day>=start&&day<=end
            return <button type="button" key={day} className={`${selected?"in-range":""} ${selected&&(draft.mode==="custom"||draft.mode==="monthly"||day===start||day===end)?"endpoint":""}`} disabled={draft.mode==="custom" && !selected && draft.picked.length>=draft.maxDates} aria-label={`${day}${available.includes(day)?", есть проверки":""}`} aria-pressed={selected} onClick={()=>pick(day)}>{i+1}{available.includes(day)&&<i/>}</button>
          })}</div></div>
        })}</div>
        <p className="calendar-key"><i aria-hidden="true"/>Выполнялась проверка</p>
      </div><div className="calendar-options">
        <div className="calendar-mode"><AppChoice label="Режим выбора дат" value={draft.mode} options={context === "recompute" ? [{value:"from",label:"С выбранной даты"},{value:"day",label:"Один день"},...modes] : [...modes]} change={value=>{setDraft({...draft,mode:value as ReportDateSelection["mode"]});if(value==="day"||value==="from")setEnd(start);setPickingEnd(false)}}/></div>
        {draft.mode==="custom" ? <div className="calendar-picked" aria-label="Выбранные даты">{draft.picked.length ? draft.picked.map(day=><button key={day} onClick={()=>pick(day)} aria-label={`Убрать ${day}`}>{shortDate(day)}.{day.slice(0,4)}<X size={13}/></button>) : <p>Выберите даты в календаре</p>}</div> : <>
          <label>{single ? "Дата" : "Первая дата"}<input type="date" value={start} onChange={e=>{setStart(e.target.value);if(single)setEnd(e.target.value);setPickingEnd(false);setActivePreset("Произвольный")}}/></label>
          {!single && <label>Последняя дата<input type="date" value={end} onChange={e=>{setEnd(e.target.value);setPickingEnd(false);setActivePreset("Произвольный")}}/></label>}
        </>}
        <div className="calendar-options-bottom">{(context === "report" || ["monthly","custom"].includes(draft.mode)) && <div className="calendar-limit"><span>Максимально дат</span><AppChoice label="Максимально дат" value={String(draft.maxDates)} options={[10,15,30].map(n=>({value:String(n),label:String(n)}))} change={value=>setDraft({...draft,maxDates:Number(value)})}/></div>}
          <p className="calendar-count" role="status">{context === "recompute" ? draft.mode==="from" ? "Все ответы с выбранной даты включительно" : draft.mode==="day" ? "Ответы только за выбранный день" : draft.mode==="period" ? "Все ответы внутри периода включительно" : `Выбрано дат для пересчёта: ${chosen.length}` : draft.mode==="two" ? "Сравнение двух дат" : `В отчёте до ${draft.maxDates} дат`}</p>
          {!valid && <p className="calendar-error" role="alert">{!rangeValid ? "Выберите период до 366 дней, начало не позже конца." : draft.mode==="monthly" ? "В этом периоде нет проверок." : `Выберите от 1 до ${draft.maxDates} дат.`}</p>}
          <button className="btn primary" disabled={!valid} onClick={()=>{change(start,end,{...draft,picked:chosen});dialog.current?.close()}}>Применить</button>
        </div>
      </div></div>
    </dialog></>
}
