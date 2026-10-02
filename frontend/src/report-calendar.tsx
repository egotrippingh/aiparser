import { useRef, useState } from "react"
import { CalendarDays, ChevronLeft, ChevronRight, X } from "lucide-react"

export const shortDate = (value: string) => new Date(value + "T12:00:00").toLocaleDateString("ru-RU", {day:"2-digit",month:"2-digit"})
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`
export function ReportCalendar({ from, to, available, change }: { from: string; to: string; available: string[]; change: (from: string, to: string) => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [start, setStart] = useState(from), [end, setEnd] = useState(to)
  const [month, setMonth] = useState(new Date(to + "T12:00:00"))
  const [pickingEnd, setPickingEnd] = useState(false)
  const valid = !!start && !!end && start <= end && (Date.parse(end)-Date.parse(start))/86400000 <= 365
  function pick(day: string) { if (!pickingEnd || day < start) {setStart(day);setEnd(day);setPickingEnd(true)} else {setEnd(day);setPickingEnd(false)} }
  function preset(days: number) { const last = iso(new Date()); const first = new Date(last+"T12:00:00");first.setDate(first.getDate()-days+1);setStart(iso(first));setEnd(last);setMonth(first) }
  return <><button className="cc-button" onClick={()=>{setStart(from);setEnd(to);setMonth(new Date(from+"T12:00:00"));setPickingEnd(false);dialog.current?.showModal()}}><CalendarDays size={16}/>{shortDate(from)}.{from.slice(0,4)} — {shortDate(to)}.{to.slice(0,4)}</button>
    <dialog ref={dialog} className="ws-dialog calendar-dialog" aria-labelledby="calendar-title"><div className="ws-dialog-head"><h2 id="calendar-title">Период отчёта</h2><button className="cc-button icon" aria-label="Закрыть календарь" onClick={()=>dialog.current?.close()}><X size={18}/></button></div>
      <div className="cc-two"><label>Начало<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>Конец<input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label></div>
      <div className="calendar-nav"><button className="cc-button icon" aria-label="Предыдущий месяц" onClick={()=>setMonth(new Date(month.getFullYear(),month.getMonth()-1,1))}><ChevronLeft size={16}/></button><span>Выберите начальную и конечную дату</span><button className="cc-button icon" aria-label="Следующий месяц" onClick={()=>setMonth(new Date(month.getFullYear(),month.getMonth()+1,1))}><ChevronRight size={16}/></button></div>
      <div className="calendar-months">{[0,1].map(shift=>{const first=new Date(month.getFullYear(),month.getMonth()+shift,1);const offset=(first.getDay()+6)%7;const days=new Date(first.getFullYear(),first.getMonth()+1,0).getDate();return <div key={shift}><h3>{first.toLocaleDateString("ru-RU",{month:"long",year:"numeric"})}</h3><div className="calendar-grid">{["Пн","Вт","Ср","Чт","Пт","Сб","Вс"].map(d=><small key={d}>{d}</small>)}{Array.from({length:offset},(_,i)=><span key={`blank-${i}`}/>)}{Array.from({length:days},(_,i)=>{const day=iso(new Date(first.getFullYear(),first.getMonth(),i+1));return <button key={day} className={`${day>=start&&day<=end?"in-range":""} ${day===start||day===end?"endpoint":""}`} aria-label={`${day}${available.includes(day)?", есть проверки":""}`} aria-pressed={day>=start&&day<=end} onClick={()=>pick(day)}>{i+1}{available.includes(day)&&<i/>}</button>})}</div></div>})}</div>
      <p className="ws-note">Точка под датой — сохранённые проверки. Максимальный период — 366 дней.</p><div className="cc-actions">{[7,30,90].map(days=><button key={days} className="cc-button" onClick={()=>preset(days)}>{days} дней</button>)}<button className="cc-button primary" disabled={!valid} onClick={()=>{change(start,end);dialog.current?.close()}}>Применить</button></div>{!valid&&<p role="alert">Проверьте даты: начало должно быть не позже конца, период — до 366 дней.</p>}
    </dialog></>
}
