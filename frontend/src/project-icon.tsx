import { useState } from "react"

export function projectFavicon(domains: string[]) {
  const domain = domains[0]?.trim()
  if (!domain) return null
  try {
    const url = new URL(domain.includes(":") ? domain : `https://${domain}`)
    if (!["http:","https:"].includes(url.protocol) || url.username || url.password) return null
    return `${url.origin}/favicon.ico`
  } catch { return null }
}

export function ProjectIcon({ name, domains }: { name: string; domains: string[] }) {
  const src = projectFavicon(domains)
  const [failed, setFailed] = useState<string | null>(null)
  return <span className="project-initial">{src && failed !== src ? <img key={src} src={src} alt="" width={20} height={20} referrerPolicy="no-referrer" decoding="async" onError={()=>setFailed(src)}/> : name.slice(0,1) || "—"}</span>
}
