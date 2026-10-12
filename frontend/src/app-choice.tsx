import { useId, useRef, useState } from "react"
import { Check, ChevronDown, Search } from "lucide-react"

export type Choice = { value: string; label: string }
export function choiceIndex(index: number, key: string, length: number) {
  if (!length) return -1
  if (key === "Home") return 0
  if (key === "End") return length - 1
  return (index + (key === "ArrowUp" ? -1 : 1) + length) % length
}

export function AppChoice({ label, value, options, change, searchable = false, disabled = false }: {
  label: string; value: string; options: Choice[]; change: (value: string) => void; searchable?: boolean; disabled?: boolean
}) {
  const id = useId(), menu = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false), [search, setSearch] = useState("")
  const shown = options.filter(option => option.label.toLocaleLowerCase().includes(search.toLocaleLowerCase()))
  function move(key: string) {
    const buttons = [...menu.current!.querySelectorAll<HTMLButtonElement>("[role=option]")]
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
    buttons[choiceIndex(index, key, buttons.length)]?.focus()
  }
  return <div className="custom-select app-choice">
    <button ref={trigger} className="choice-trigger" disabled={disabled} popoverTarget={id} aria-label={label}
      aria-haspopup="listbox" aria-expanded={open} onKeyDown={event => {
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault(); menu.current?.showPopover(); move(event.key)
        }
      }}><span>{options.find(option => option.value === value)?.label || label}</span><ChevronDown size={13}/></button>
    <div id={id} ref={menu} popover="auto" className="choice-menu" onToggle={event => {
      const expanded = event.newState === "open"; setOpen(expanded); if (!expanded) setSearch("")
    }} onKeyDown={event => {
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) && !(event.target instanceof HTMLInputElement && ["Home", "End"].includes(event.key))) {
        event.preventDefault(); move(event.key)
      }
    }} style={{left: trigger.current?.getBoundingClientRect().left, top: trigger.current?.getBoundingClientRect().bottom}}>
      {searchable && <label className="choice-search"><Search size={14}/><input aria-label={`Поиск: ${label}`} placeholder="Найти группу" value={search} onChange={event => setSearch(event.target.value)}/></label>}
      <div className="choice-options" role="listbox" aria-label={label}>{shown.map(option => <button type="button" key={option.value}
        role="option" aria-selected={value === option.value} onClick={() => { change(option.value); menu.current?.hidePopover(); trigger.current?.focus() }}>
        <span>{option.label}</span>{option.value === value && <Check size={13}/>}</button>)}</div>
      {!shown.length && <p className="choice-empty">Ничего не найдено</p>}
    </div>
  </div>
}
