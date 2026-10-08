/** TXT: one query per line; CSV/TSV: query and optional group columns. */
export function parseQueryImport(text: string, fallbackGroup = "") {
  const first = text.replace(/^\uFEFF/, "").split(/\r?\n/)[0] || ""
  const delimiter = first.includes("\t") ? "\t" : first.includes(";") ? ";" : /^(?:"?(?:query|запрос|group|группа)"?,)/i.test(first) ? "," : null
  if (!delimiter) return text.split(/\r?\n/).map(line => ({ text: line.trim(), group_tag: fallbackGroup })).filter(q => q.text)
  const rows: string[][] = []; let row: string[] = [], field = "", quoted = false
  const value = text.replace(/^\uFEFF/, "")
  for (let i = 0; i <= value.length; i++) {
    const c = value[i]
    if (c === '"') {
      if (quoted && value[i + 1] === '"') { field += '"'; i++ } else quoted = !quoted
    } else if (!quoted && (c === delimiter || c === "\n" || c === undefined)) {
      row.push(field.trim()); field = ""
      if (c !== delimiter) { if (row.some(Boolean)) rows.push(row); row = [] }
    } else if (c !== "\r" && c !== undefined) field += c
  }
  if (quoted) throw new Error("В файле не закрыты кавычки")
  const header = rows[0]?.map(s => s.toLowerCase()) || []
  const queryColumn = header.findIndex(s => ["query", "запрос", "промпт"].includes(s))
  const groupColumn = header.findIndex(s => ["group", "группа"].includes(s))
  return (queryColumn >= 0 ? rows.slice(1) : rows).map(r => ({
    text: r[queryColumn >= 0 ? queryColumn : 0] || "",
    group_tag: r[groupColumn >= 0 ? groupColumn : 1] || fallbackGroup,
  })).filter(q => q.text)
}
