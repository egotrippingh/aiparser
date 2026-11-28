import { useEffect, useRef, useState, type FormEvent } from "react"
import { Plus, Trash2, X } from "lucide-react"
import { accountRequest, AccountError } from "./account-api"
import { CabinetSkeleton } from "./cabinet-loading"

type CompetitorInput = { name: string; aliases: string[]; domains: string[] }
type Settings = { revision: number; competitors: CompetitorInput[] }
type Draft = { id: number; name: string; aliases: string; domains: string }
export type DomainSuggestion = { domain: string; mentions: number; label?: string }

const splitLines = (value: string) => value.split(/\r?\n/).map(line => line.trim()).filter(Boolean)

export function CompetitorSettings({ base, token, suggestedDomain, suggestedName, onClose, onSaved }: {
  base: string; token: string; suggestedDomain?: string; suggestedName?: string; onClose: () => void; onSaved: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const nextId = useRef(0)
  const [revision, setRevision] = useState<number | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState("")
  const [conflict, setConflict] = useState(false)
  const path = `${base}/competitor-settings`

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal()
  }, [])

  useEffect(() => {
    let active = true
    accountRequest<Settings>(path, token).then(data => {
      if (!active) return
      const rows = data.competitors.map(({ name, aliases, domains }) => ({
        id: nextId.current++, name, aliases: aliases.join("\n"), domains: domains.join("\n"),
      }))
      const addSuggestion = suggestedDomain && rows.length < 20 && !rows.some(row => splitLines(row.domains).includes(suggestedDomain))
      if (addSuggestion || rows.length === 0) rows.push({
        id: nextId.current++, name: suggestedName || "", aliases: "", domains: suggestedDomain || "",
      })
      setRevision(data.revision)
      setDrafts(rows)
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : "Не удалось загрузить конкурентов")
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [path, refresh, suggestedDomain, suggestedName, token])

  function update(id: number, field: "name" | "aliases" | "domains", value: string) {
    setDrafts(rows => rows.map(row => row.id === id ? { ...row, [field]: value } : row))
  }

  function retry() {
    setLoading(true)
    setError("")
    setConflict(false)
    setRevision(null)
    setRefresh(value => value + 1)
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (revision === null || saving || loading || conflict || drafts.some(row => !row.name.trim())) return
    setSaving(true)
    setError("")
    try {
      await accountRequest<Settings>(path, token, {
        revision,
        competitors: drafts.map(({ name, aliases, domains }) => ({ name: name.trim(), aliases: splitLines(aliases), domains: splitLines(domains) })),
      }, "PUT")
      dialog.current?.close()
      onSaved()
    } catch (cause) {
      setConflict(cause instanceof AccountError && cause.status === 409)
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить конкурентов")
      setSaving(false)
    }
  }

  function addRow() {
    const id = nextId.current++
    setDrafts(rows => [...rows, { id, name: "", aliases: "", domains: "" }])
  }

  return <dialog ref={dialog} className="ws-dialog analysis-editor" aria-labelledby="analysis-editor-title" onClose={onClose}
    onCancel={event => { if (saving) event.preventDefault() }}>
    <div className="ws-dialog-head">
      <h2 id="analysis-editor-title">Настроить конкурентов</h2>
      <button type="button" className="btn icon-only" aria-label="Закрыть настройки конкурентов" disabled={saving} onClick={() => dialog.current?.close()}>
        <X size={16} aria-hidden="true"/>
      </button>
    </div>
    <form onSubmit={save}>
      <div className="analysis-editor-body">
        {loading ? <CabinetSkeleton label="Загружаем конкурентов…" format="rows"/> : revision !== null && <>
          <p>Укажите название. Варианты написания и домены можно добавить по одному на строку.</p>
          {drafts.map((row, index) => <fieldset key={row.id} className="analysis-editor-row" disabled={saving}>
            <legend>Конкурент {index + 1}</legend>
            <div className="analysis-editor-name">
              <label>Название<input required maxLength={120} value={row.name} onChange={event => update(row.id, "name", event.target.value)}/></label>
              <button type="button" className="btn icon-only" aria-label={`Убрать конкурента ${row.name || index + 1}`}
                onClick={() => setDrafts(items => items.filter(item => item.id !== row.id))}><Trash2 size={16} aria-hidden="true"/></button>
            </div>
            <div className="analysis-editor-fields">
              <label>Варианты написания<textarea rows={2} maxLength={1500} value={row.aliases} onChange={event => update(row.id, "aliases", event.target.value)}/></label>
              <label>Домены<textarea rows={2} maxLength={2000} value={row.domains} onChange={event => update(row.id, "domains", event.target.value)}/></label>
            </div>
          </fieldset>)}
          <button type="button" className="btn" disabled={saving || drafts.length >= 20} onClick={addRow}>
            <Plus size={16} aria-hidden="true"/>Добавить конкурента
          </button>
        </>}
        {error && <div className="cc-alert analysis-editor-error" role="alert">
          <span>{error}</span>
          {(revision === null || conflict) && <button type="button" className="btn" onClick={retry}>{conflict ? "Загрузить текущий список" : "Повторить"}</button>}
        </div>}
      </div>
      <div className="analysis-editor-actions">
        <button type="button" className="btn" disabled={saving} onClick={() => dialog.current?.close()}>Отмена</button>
        <button type="submit" className="btn primary" disabled={loading || saving || conflict || revision === null || drafts.some(row => !row.name.trim())}>
          {saving ? "Сохраняем…" : "Сохранить"}
        </button>
      </div>
    </form>
  </dialog>
}

