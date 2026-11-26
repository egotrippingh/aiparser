import { useId, useLayoutEffect, useRef, useState, type FormEvent, type RefObject } from "react"
import { CircleHelp, Folder, FolderInput, FolderOpen, FolderPlus, List, Pencil, Plus, Search, Trash2, Upload, X } from "lucide-react"
import { parseQueryImport, QUERY_IMPORT_EXAMPLE } from "./query-import"
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "./components/ui/popover"
import { plural } from "./lib/format"
import "./query-library.scss"


export function QueryImportHelp({ container }: { container?: RefObject<HTMLDialogElement | null> }) {
  return <Popover><PopoverTrigger openOnHover delay={150} closeDelay={150} className="cc-button" aria-label="Как подготовить файл CSV"><CircleHelp size={17} aria-hidden="true" />CSV UTF-8</PopoverTrigger>
    <PopoverContent portalContainer={container} className="ql-import-help" align="start">
      <PopoverTitle>Формат файла для импорта</PopoverTitle>
      <p>В Excel выберите «CSV UTF-8», не «CSV (MS-DOS)». Кодировка — UTF-8, расширение — .csv.</p>
      <p>Первая строка: «Запрос» и необязательная «Группа». Подойдут разделители: точка с запятой или запятая; для TSV — табуляция. В TXT — один запрос в строке.</p>
      <pre>{QUERY_IMPORT_EXAMPLE}</pre>
      <p>Если внутри запроса есть разделитель или перенос строки, заключите его в двойные кавычки. Кавычки внутри поля удвойте.</p>
      <a className="cc-button" download="airate-queries.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent('\uFEFF' + QUERY_IMPORT_EXAMPLE)}`}>Скачать шаблон CSV</a>
    </PopoverContent>
  </Popover>
}

type Query = { id: string; text: string; group_tag: string; active: boolean }
type QueryAction =
  | { kind: "add" | "folder" }
  | { kind: "edit"; id: string }
  | { kind: "move" | "delete"; ids: Set<string> }
  | { kind: "unfolder"; group: string }

const PAGE_SIZE = 100
const queryCount = (count: number) => `${count} ${plural(count, "запрос", "запроса", "запросов")}`
const normalizeQuery = (value: string) => value.replace(/\s+/g, " ").trim()

function SelectionBox({ checked, total, label, disabled, onChange }: {
  checked: number; total: number; label: string; disabled: boolean; onChange: (selected: boolean) => void
}) {
  return <input type="checkbox" aria-label={label} disabled={disabled || !total}
    checked={total > 0 && checked === total}
    ref={input => { if (input) input.indeterminate = checked > 0 && checked < total }}
    onChange={event => onChange(event.target.checked)}/>
}

export function QueryLibrary({ queries, saving, onChange }: { queries: Query[]; saving: boolean; onChange: (queries: Query[]) => void }) {
  const id = useId()
  const [group, setGroup] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [limit, setLimit] = useState(PAGE_SIZE)
  const [selected, setSelected] = useState(new Set<string>())
  const [operation, setOperation] = useState<QueryAction | null>(null)
  const [text, setText] = useState("")
  const [destination, setDestination] = useState("")
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const dialog = useRef<HTMLDialogElement>(null)
  const searchInput = useRef<HTMLInputElement>(null)
  const fileRead = useRef(0)
  const addDraft = useRef("")

  useLayoutEffect(() => {
    if (!operation) return
    const modal = dialog.current
    modal?.showModal()
    modal?.querySelector<HTMLElement>("[data-initial-focus]")?.focus()
  }, [operation])
  const groups = new Map<string, Query[]>()
  for (const query of queries) {
    const items = groups.get(query.group_tag)
    if (items) items.push(query)
    else groups.set(query.group_tag, [query])
  }
  const folderNames = [...groups.keys()].filter(Boolean).sort((a, b) => a.localeCompare(b, "ru"))
  const currentGroup = group !== null && group !== "" && !groups.has(group) ? null : group
  const scope = currentGroup === null ? queries : groups.get(currentGroup) ?? []
  const term = search.trim().toLocaleLowerCase("ru-RU")
  const filtered = term ? scope.filter(query => `${query.text} ${query.group_tag}`.toLocaleLowerCase("ru-RU").includes(term)) : scope
  const selection = queries.filter(query => selected.has(query.id))
  const activeCount = queries.filter(query => query.active).length

  function chooseFolder(next: string | null) {
    setGroup(next)
    setSearch("")
    setLimit(PAGE_SIZE)
  }

  function select(items: Query[], checked: boolean) {
    setSelected(previous => {
      const next = new Set(previous)
      for (const query of items) {
        if (checked) next.add(query.id)
        else next.delete(query.id)
      }
      return next
    })
  }

  function open(next: QueryAction) {
    fileRead.current++
    setOperation(next)
    const editing = next.kind === "edit" ? queries.find(query => query.id === next.id) : undefined
    setText(next.kind === "add" ? addDraft.current : editing?.text ?? "")
    setDestination(editing?.group_tag ?? (next.kind === "add" ? currentGroup ?? "" : ""))
    setError("")
  }

  function updateText(next: string) {
    setText(next)
    if (operation?.kind === "add") addDraft.current = next
  }

  function finish(next: Query[], message: string) {
    onChange(next)
    setNotice(message)
    dialog.current?.close()
    searchInput.current?.focus()
  }

  function add(folder: string, createFolder: boolean) {
    const known = new Set(queries.map(query => normalizeQuery(query.text)))
    const added: Query[] = []
    for (const row of parseQueryImport(text, folder)) {
      const value = normalizeQuery(row.text)
      const groupTag = createFolder ? folder : row.group_tag
      if (value.length > 2000 || groupTag.length > 120) throw new Error("Запрос — до 2 000 символов, название папки — до 120.")
      if (value && !known.has(value)) {
        known.add(value)
        added.push({ id: crypto.randomUUID().replaceAll("-", ""), text: value, group_tag: groupTag, active: true })
      }
    }
    if (!added.length) throw new Error("Новых запросов нет: список пуст или все запросы уже добавлены.")
    if (queries.length + added.length > 5000) throw new Error("В проекте может быть до 5 000 запросов.")
    if (!createFolder) addDraft.current = ""
    chooseFolder(added.every(query => query.group_tag === added[0].group_tag) ? added[0].group_tag : null)
    finish([...queries, ...added], `Добавлено: ${queryCount(added.length)}.`)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!operation || saving) return
    const folder = groups.has(destination) ? destination : destination.trim()
    try {
      switch (operation.kind) {
        case "folder":
          if (!folder) throw new Error("Укажите название папки.")
          if (groups.has(folder)) throw new Error("Такая папка уже есть. Откройте её, чтобы добавить запросы.")
          break
        case "edit": {
          const current = queries.find(query => query.id === operation.id)
          if (!current) throw new Error("Запрос больше не доступен.")
          const value = text === current.text ? current.text : normalizeQuery(text)
          if (!value) throw new Error("Введите текст запроса.")
          if (value !== current.text && queries.some(query => query.id !== current.id && normalizeQuery(query.text) === value)) throw new Error("Такой запрос уже есть.")
          finish(queries.map(query => query.id === operation.id ? { ...query, text: value, group_tag: folder } : query), "Запрос изменён.")
          return
        }
        case "move":
          chooseFolder(folder)
          setSelected(new Set())
          finish(queries.map(query => operation.ids.has(query.id) ? { ...query, group_tag: folder } : query), `Перемещено: ${queryCount(operation.ids.size)}.`)
          return
        case "delete":
          setSelected(previous => new Set([...previous].filter(queryId => !operation.ids.has(queryId))))
          finish(queries.filter(query => !operation.ids.has(query.id)), `Удалено: ${queryCount(operation.ids.size)}.`)
          return
        case "unfolder":
          chooseFolder("")
          finish(queries.map(query => query.group_tag === operation.group ? { ...query, group_tag: "" } : query), "Папка удалена. Запросы перемещены в «Без папки».")
          return
      }
      add(folder, operation.kind === "folder")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось обновить запросы")
    }
  }

  const adding = operation?.kind === "add" || operation?.kind === "folder"
  const editing = operation?.kind === "edit"
  const removing = operation?.kind === "delete" || operation?.kind === "unfolder"
  const titles = { add: "Добавить запросы", folder: "Новая папка", edit: "Редактировать запрос", move: "Переместить запросы", delete: "Удалить запросы?", unfolder: "Удалить папку?" }
  const actions = { add: "Добавить в базу", folder: "Создать папку", edit: "Применить", move: "Переместить", delete: "Удалить запросы", unfolder: "Удалить папку" }
  const selectedIds = () => new Set(selection.map(query => query.id))

  return <section className="query-library project-registry" aria-label="Запросы проекта">
    <div className="project-registry__toolbar query-library__heading">
      <p className="project-registry__summary"><strong>{queryCount(queries.length)}</strong><span aria-hidden="true">·</span>{activeCount} в проверках</p>
      <button type="button" className="btn primary" disabled={saving} aria-haspopup="dialog" onClick={() => open({ kind: "add" })}><Plus size={17} aria-hidden="true"/>Добавить запросы</button>
    </div>

    <div className="query-library__layout">
      <aside className="panel query-library__folders" aria-label="Папки запросов">
        <div className="query-library__folder-heading"><h2>Папки</h2>
          <button type="button" className="btn icon-only" disabled={saving} aria-label="Новая папка" title="Новая папка" aria-haspopup="dialog" onClick={() => open({ kind: "folder" })}><FolderPlus size={18} aria-hidden="true"/></button>
        </div>
        <ul>
          {[null, "", ...folderNames].map(name => {
            const items = name === null ? queries : groups.get(name) ?? []
            const label = name === null ? "Все запросы" : name || "Без папки"
            const Icon = name === null ? List : currentGroup === name ? FolderOpen : Folder
            return <li key={name === null ? "all" : `folder:${name}`}>
              <button type="button" className="query-library__folder" aria-pressed={currentGroup === name} title={label} disabled={saving} onClick={() => chooseFolder(name)}>
                <Icon size={17} aria-hidden="true"/><span>{label}</span><small>{items.length}</small>
              </button>
              {name !== null && items.length > 0 && <SelectionBox label={`Выбрать запросы в «${label}»`} total={items.length} checked={items.filter(query => selected.has(query.id)).length} disabled={saving} onChange={checked => select(items, checked)}/>}
            </li>
          })}
        </ul>
      </aside>

      <div className="query-library__main">
        <div className="project-registry__toolbar query-library__toolbar">
          <label className="search-box project-registry__search"><Search size={17} aria-hidden="true"/>
            <input type="search" ref={searchInput} aria-label="Поиск запросов" placeholder="Найти запрос" value={search} onChange={event => { setSearch(event.target.value); setLimit(PAGE_SIZE) }}/>
          </label>
          {currentGroup && <button type="button" className="btn query-library__delete" disabled={saving} aria-haspopup="dialog" onClick={() => open({ kind: "unfolder", group: currentGroup })}><Trash2 size={16} aria-hidden="true"/>Удалить папку</button>}
        </div>

        {selection.length > 0 && <div className="query-library__selection">
          <strong role="status">Выбрано: {selection.length}</strong>
          <div className="cc-actions">
            <button type="button" className="btn" disabled={saving} aria-haspopup="dialog" onClick={() => open({ kind: "move", ids: selectedIds() })}><FolderInput size={16} aria-hidden="true"/>Переместить</button>
            <button type="button" className="btn query-library__delete" disabled={saving} aria-haspopup="dialog" onClick={() => open({ kind: "delete", ids: selectedIds() })}><Trash2 size={16} aria-hidden="true"/>Удалить выбранные</button>
            <button type="button" className="btn icon-only" disabled={saving} aria-label="Снять выделение" title="Снять выделение" onClick={() => { setSelected(new Set()); searchInput.current?.focus() }}><X size={16} aria-hidden="true"/></button>
          </div>
        </div>}

        {filtered.length > 0 ? <div className="panel table-scroll project-registry__table-wrap query-library__list" role="region" tabIndex={0} aria-label="Список запросов">
          <table className="query-library__table" aria-label="Запросы">
            <thead><tr>
              <th scope="col"><SelectionBox label="Выбрать все запросы по текущему фильтру" total={filtered.length} checked={filtered.filter(query => selected.has(query.id)).length} disabled={saving} onChange={checked => select(filtered, checked)}/></th>
              <th scope="col">Запрос</th><th scope="col">Папка</th><th scope="col">Проверять</th>
              <th scope="col"><span className="sr-only">Действия</span></th>
            </tr></thead>
            <tbody>{filtered.slice(0, limit).map(query => <tr key={query.id} data-selected={selected.has(query.id)}>
              <td><input type="checkbox" aria-label={`Выбрать запрос: ${query.text}`} disabled={saving} checked={selected.has(query.id)} onChange={event => select([query], event.target.checked)}/></td>
              <td><button type="button" className="query-library__edit" disabled={saving} aria-label={`Редактировать: ${query.text}`} title={query.text} aria-haspopup="dialog" onClick={() => open({ kind: "edit", id: query.id })}><span>{query.text}</span><Pencil size={14} aria-hidden="true"/></button>
                {currentGroup === null && query.group_tag && <small className="query-library__mobile-tag">{query.group_tag}</small>}
              </td>
              <td>{query.group_tag && <span className="query-library__tag" title={query.group_tag}>{query.group_tag}</span>}</td>
              <td><input type="checkbox" aria-label={`Проверять: ${query.text}`} disabled={saving} checked={query.active} onChange={event => {
                const active = event.target.checked
                onChange(queries.map(item => item.id === query.id ? { ...item, active } : item))
              }}/></td>
              <td><button type="button" className="btn icon-only query-library__delete" disabled={saving} aria-label={`Удалить запрос: ${query.text}`} aria-haspopup="dialog" onClick={() => open({ kind: "delete", ids: new Set([query.id]) })}><Trash2 size={16} aria-hidden="true"/></button></td>
            </tr>)}</tbody>
          </table></div> : <div className="panel empty-state project-registry__empty">
            <h2>{search.trim() ? "Запросы не найдены" : queries.length ? "В этой папке пока пусто" : "Запросов пока нет"}</h2>
            {search.trim() ? <button type="button" className="btn" onClick={() => { setSearch(""); searchInput.current?.focus() }}>Очистить поиск</button> : <p>Добавьте список запросов или загрузите файл.</p>}
          </div>}

        {filtered.length > 0 && <div className="query-library__footer">
          <span role="status">Показано {Math.min(limit, filtered.length)} из {filtered.length}</span>
          {filtered.length > limit && <button type="button" className="btn" onClick={() => setLimit(limit + PAGE_SIZE)}>Показать ещё {Math.min(PAGE_SIZE, filtered.length - limit)}</button>}
        </div>}
        <p className="query-library__notice" role="status">{notice}</p>
      </div>
    </div>

    <datalist id={`${id}-folders`}>{folderNames.map(name => <option key={name} value={name}/>)}</datalist>
    <dialog className="ws-dialog query-library__dialog" ref={dialog} aria-labelledby={`${id}-title`} onClose={() => setOperation(null)}>
      {operation && <form onSubmit={submit}>
        <div className="ws-dialog-head"><h2 id={`${id}-title`}>{titles[operation.kind]}</h2>
          <button type="button" className="btn icon-only" aria-label="Закрыть" onClick={() => dialog.current?.close()}><X size={18} aria-hidden="true"/></button>
        </div>
        {operation.kind === "delete" && <p>Из базы проекта будут удалены выбранные запросы ({operation.ids.size}). Сохранённые ответы останутся в отчётах.</p>}
        {operation.kind === "unfolder" && <p>Папка «{operation.group}» исчезнет. Её запросы переместятся в «Без папки».</p>}
        {operation.kind === "move" && <p>Будет перемещено: {queryCount(operation.ids.size)}. Можно выбрать существующую папку или ввести новое название.</p>}
        {adding && <p>{operation.kind === "folder" ? "Добавьте первые запросы в папку." : "Вставьте запросы по одному в строке или загрузите файл."}</p>}
        {!removing && <label>{operation.kind === "folder" ? "Название папки" : "Папка"}
          <input data-initial-focus={!editing && operation.kind !== "add" ? "" : undefined} list={operation.kind === "folder" ? undefined : `${id}-folders`} maxLength={120} required={operation.kind === "folder"} placeholder="Без папки" value={destination} onChange={event => setDestination(event.target.value)}/>
        </label>}
        {(adding || editing) && <label>{editing ? "Текст запроса" : "Запросы"}
          <textarea data-initial-focus={operation.kind !== "folder" ? "" : undefined} rows={editing ? 4 : 7} maxLength={editing ? 2000 : undefined} value={text} onChange={event => updateText(event.target.value)} placeholder="Где купить оригинальное оборудование?"/>
        </label>}
        {error && <p className="cc-alert" role="alert">{error}</p>}
        <div className="query-library__dialog-actions">
          {adding && <div className="cc-actions"><label className="btn cc-upload"><Upload size={16} aria-hidden="true"/>Из файла<input type="file" accept=".txt,.csv,.tsv" aria-label="Загрузить запросы из файла" onChange={async event => {
            const file = event.target.files?.[0]
            event.target.value = ""
            if (!file) return
            try {
              if (file.size > 4_000_000) throw new Error("Файл больше 4 МБ")
              const reading = ++fileRead.current
              const contents = await file.text()
              if (reading !== fileRead.current || !dialog.current?.open) return
              updateText(contents)
              setError("")
            } catch (e) { setError(e instanceof Error ? e.message : "Не удалось прочитать файл") }
          }}/></label><QueryImportHelp container={dialog}/></div>}
          <div className="cc-actions">
            <button type="button" className="btn" data-initial-focus={removing ? "" : undefined} onClick={() => dialog.current?.close()}>Отмена</button>
            <button type="submit" className={`btn ${removing ? "danger" : "primary"}`} disabled={saving || ((adding || editing) && !text.trim())}>{actions[operation.kind]}</button>
          </div>
        </div>
        {adding && <small>TXT, CSV UTF-8 или TSV · до 4 МБ.</small>}
      </form>}
    </dialog>
  </section>
}
