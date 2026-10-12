import type { ReactNode } from "react"

export type BrandHighlight = { names: string[]; domains: string[] }

function brandPattern(brand?: BrandHighlight) {
  const forms = [...new Set(brand?.names.map(n => n.trim()).filter(Boolean) || [])].sort((a,b) => b.length-a.length)
  return forms.length ? new RegExp(`(?<![\\p{L}\\p{N}_])(${forms.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(?![\\p{L}\\p{N}_])`, "giu") : null
}

export function highlightedText(text: string, brand?: BrandHighlight): ReactNode {
  const pattern = brandPattern(brand)
  if (!pattern) return text
  return text.split(pattern).map((part,i) => i % 2 ? <mark className="answer-brand" key={i}>{part}</mark> : part)
}

export function brandLink(href: string, brand?: BrandHighlight) {
  try {
    const host = new URL(href).hostname.replace(/^www\./, "")
    return brand?.domains.some(domain => {
      try {
        const value = new URL(domain.includes("://") ? domain : `https://${domain}`).hostname.replace(/^www\./, "")
        return host === value || host.endsWith(`.${value}`)
      } catch { return false }
    }) || false
  } catch { return false }
}
