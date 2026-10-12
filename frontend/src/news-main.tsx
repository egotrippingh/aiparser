import { useEffect, useState } from "react"
import { createRoot } from "react-dom/client"
import { ArrowUpRight } from "lucide-react"
import { accountRequest } from "./account-api"
import { Brand } from "./brand"
import { SiteFooter } from "./site-footer"
import "./landing.css"

type Post = { id: number; body: string; created_at: string }

function NewsFeed() {
  const [items, setItems] = useState<Post[]>([]), [cursor, setCursor] = useState<number | null | undefined>(undefined), [error, setError] = useState(""), [loading, setLoading] = useState(true)
  async function load(next?: number) {
    setLoading(true); setError("")
    try { const page = await accountRequest<{items: Post[]; next_cursor: number | null}>(`/news${next ? `?cursor=${next}` : ""}`); setItems(rows => next ? [...rows, ...page.items] : page.items); setCursor(page.next_cursor) }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось загрузить ленту") }
    finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  return <div className="landing"><header className="site-header"><div className="site-container header-inner"><Brand className="brand" href="/"/><nav className="desktop-nav" aria-label="Навигация"><a href="/">Главная</a><a href="/cabinet/">Личный кабинет</a></nav><a className="header-cta" href="/cabinet/">Открыть кабинет <ArrowUpRight size={16}/></a></div></header><main className="site-container news-feed"><p className="eyebrow">AIRATE</p><h1>Лента</h1><p className="section-copy">Новости сервиса и важные изменения.</p>{loading && !items.length && <p role="status">Загружаем ленту…</p>}{error && <p role="alert">{error} <button className="button" onClick={() => void load()}>Повторить</button></p>}{!loading && !items.length && !error && <p role="status">Пока новостей нет.</p>}<div className="news-posts">{items.map(post => <article key={post.id}><time dateTime={post.created_at}>{new Date(post.created_at).toLocaleDateString("ru-RU")}</time><p>{post.body}</p></article>)}</div>{cursor && <button className="button button-primary" disabled={loading} onClick={() => void load(cursor)}>{loading ? "Загружаем…" : "Показать ещё"}</button>}</main><SiteFooter/></div>
}
createRoot(document.getElementById("root")!).render(<NewsFeed />)
