import { Brand } from "./brand"
import "./site-footer.css"

export const SUPPORT_URL = "https://t.me/egotrippintg"

export function SiteFooter() {
  return <footer className="air-footer">
    <div className="air-footer-inner">
      <div><Brand /><p>Мониторинг упоминаний бренда в ответах ИИ.</p></div>
      <nav aria-label="Документы и поддержка">
        <a href="/terms/">Пользовательское соглашение</a>
        <a href="/privacy/">Политика конфиденциальности</a>
        <a href={SUPPORT_URL} target="_blank" rel="noopener noreferrer">Поддержка в Telegram ↗</a>
      </nav>
    </div>
  </footer>
}
