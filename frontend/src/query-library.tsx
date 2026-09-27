import { useRef, useState } from "react"
import { FolderOpen, Plus, Search, Trash2, Upload, X } from "lucide-react"
import { parseQueryImport } from "./query-import"

type Query = { id: string; text: string; group_tag: string; active: boolean }
export function QueryLibrary({ queries, onChange }: { queries: Query[]; onChange: (queries: Query[]) => void }) {
  const [group, setGroup] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [limit, setLimit] = useState(100)
  const [text, setText] = useState("")
  const [newGroup, setNewGroup] = useState("")
  const [error, setError] = useState("")
  const dialog = useRef<HTMLDialogElement>(null)
  const groups = [...new Set(queries.map(q => q.group_tag).filter(Boolean))].sort((a,b) => a.localeCompare(b, "ru"))
  const filtered = queries.filter(q => (group === null || q.group_tag === group) && `${q.text} ${q.group_tag}`.toLowerCase().includes(search.toLowerCase()))
  function edit(id: string, patch: Partial<Query>) { onChange(queries.map(q => q.id === id ? { ...q, ...patch } : q)) }
  function add() {
    try {
      const known = new Set(queries.map(q => q.text.replace(/\s+/g, " ").trim()))
      const added: Query[] = []
      for (const row of parseQueryImport(text, newGroup.trim())) {
        const value = row.text.replace(/\s+/g, " ").trim()
        if (value.length > 2000 || row.group_tag.length > 120) throw new Error("Запрос — до 2 000 символов, название группы — до 120.")
        if (value && !known.has(value)) { known.add(value); added.push({ id: crypto.randomUUID().replaceAll("-", ""), text: value, group_tag: row.group_tag.trim(), active: true }) }
      }
      if (!added.length) throw new Error("Новых запросов нет: список пуст или все запросы уже добавлены.")
      if (queries.length + added.length > 5000) throw new Error("В проекте может быть до 5 000 запросов.")
      onChange([...queries, ...added]); setGroup(null); setSearch(""); setText(""); dialog.current?.close()
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось добавить запросы") }
  }
  return <>
    <div className="ql-heading"><div><h2>Промптовая база</h2><p>{queries.length} запросов · {queries.filter(q => q.active).length} включено в проверки</p></div><button className="cc-button primary" onClick={() => { setNewGroup(group || ""); setError(""); dialog.current?.showModal() }}><Plus size={16}/>Добавить запросы</button></div>
    <div className="ql-layout"><aside className="ql-groups" aria-label="Группы запросов"><span className="cc-eyebrow">Группы</span>{[null, "", ...groups].map(g => <button key={g ?? "all"} aria-pressed={group === g} onClick={() => { setGroup(g); setLimit(100) }}><FolderOpen size={15}/><span>{g === null ? "Все запросы" : g || "Без группы"}</span><small>{g === null ? queries.length : queries.filter(q => q.group_tag === g).length}</small></button>)}</aside>
      <div className="ql-main"><label className="cc-search"><Search size={16}/><span className="sr-only">Поиск по промптовой базе</span><input placeholder="Найти запрос" value={search} onChange={e => {setSearch(e.target.value); setLimit(100)}}/></label>
        <div className="cc-table-scroll"><table className="cc-table cc-query-table"><thead><tr><th><span className="sr-only">Включён</span></th><th>Запрос · {filtered.length}</th><th>Группа</th><th><span className="sr-only">Удалить</span></th></tr></thead><tbody>{filtered.slice(0,limit).map(q => <tr key={q.id}><td><input type="checkbox" aria-label={`Проверять: ${q.text}`} checked={q.active} onChange={e=>edit(q.id,{active:e.target.checked})}/></td><td><input aria-label="Текст запроса" maxLength={2000} value={q.text} onChange={e=>edit(q.id,{text:e.target.value})}/></td><td><input aria-label={`Группа запроса ${q.text}`} list="query-groups" maxLength={120} placeholder="Без группы" defaultValue={q.group_tag} onBlur={e=>{if(e.target.value!==q.group_tag)edit(q.id,{group_tag:e.target.value})}}/></td><td><button className="cc-button icon" aria-label={`Удалить запрос: ${q.text}`} onClick={()=>onChange(queries.filter(item=>item.id!==q.id))}><Trash2 size={15}/></button></td></tr>)}</tbody></table></div>
        {!filtered.length && <div className="cc-empty"><h3>{queries.length ? "Запросы не найдены" : "Добавьте первые запросы"}</h3><p>Можно вставить список, загрузить файл и объединить запросы в группы.</p></div>}
        {filtered.length>limit && <button className="cc-button" onClick={()=>setLimit(n=>n+100)}>Показать ещё 100</button>}
      </div></div>
    <datalist id="query-groups">{groups.map(g=><option key={g} value={g}/>)}</datalist>
    <dialog className="ws-dialog" ref={dialog} aria-labelledby="add-queries-title"><div className="ws-dialog-head"><h2 id="add-queries-title">Добавить запросы</h2><button className="cc-button icon" aria-label="Закрыть" onClick={()=>dialog.current?.close()}><X size={18}/></button></div><p>По одному запросу в строке. Повторы пропустим. В CSV и TSV можно указать столбцы «Запрос» и «Группа».</p><label>Группа<input list="query-groups" maxLength={120} placeholder="Без группы или название новой группы" value={newGroup} onChange={e=>setNewGroup(e.target.value)}/></label><label>Запросы<textarea rows={9} value={text} onChange={e=>setText(e.target.value)} placeholder="Где купить оригинальное оборудование?"/></label>{error && <p className="cc-alert" role="alert">{error}</p>}<div className="cc-actions"><label className="cc-button cc-upload"><Upload size={16}/>Из файла<input type="file" accept=".txt,.csv,.tsv" onChange={async e=>{const file=e.target.files?.[0];e.target.value="";if(!file)return;try{if(file.size>4000000)throw new Error("Файл больше 4 МБ");setText(await file.text());setError("")}catch(e){setError(e instanceof Error?e.message:"Не удалось прочитать файл")}}}/></label><button className="cc-button primary" disabled={!text.trim()} onClick={add}>Добавить в базу</button></div><small>После добавления сохраните изменения в проекте.</small></dialog>
  </>
}
