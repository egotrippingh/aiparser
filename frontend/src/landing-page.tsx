import { useEffect, useState, type ReactNode } from "react"
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleHelp,
  ExternalLink,
  Link2,
  ListFilter,
  MessageSquareText,
  ScanSearch,
} from "lucide-react"

import "./landing.css"
import Scanner from "./components/reactbits/Scanner"
import SpotlightCard from "./components/reactbits/SpotlightCard"
import { ProcessFlow } from "./components/process-flow"

const APP_URL = "/app/"

function Brand() {
  return (
    <a className="brand" href="#top" aria-label="AI Mentions, к началу страницы">
      <span className="brand-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span>AI Mentions</span>
    </a>
  )
}

const services = ["ChatGPT", "Perplexity", "Алиса AI", "Google AI Overview"]

function ScannerLayer() {
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)")
    const update = () => setReduced(media.matches)
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [])
  return <div className="hero-scanner" aria-hidden="true">{!reduced && <Scanner color1="#5b2dce" color2="#d66edb" color3="#8eeaff" speed={0.18} sweepSpeed={0.14} sweepWidth={1.8} scale={1.2} frequency={1.5} ripple={0.26} bandDensity={8} glow={0.24} brightness={1.2} opacity={1} mouseInteraction={false} scanline={false} grain={false} />}</div>
}

// Set either source when demo GIFs are ready. Until then, each slot renders
// an animated product illustration in the same rounded frame.
const GIF_SOURCES = { interface: "", parsing: "" }

function GifWindow({ slot, title, children }: { slot: keyof typeof GIF_SOURCES; title: string; children: ReactNode }) {
  const source = GIF_SOURCES[slot]
  return (
    <div className="gif-window" data-gif-slot={slot}>
      <div className="gif-window-bar"><span className="window-dots"><i /><i /><i /></span><span>{title}</span><span className="window-bar-action">AI Mentions</span></div>
      {source ? <img src={source} alt={title} loading="lazy" /> : <div className="gif-window-preview">{children}</div>}
    </div>
  )
}

function InterfaceDemo() {
  return <div className="interface-demo"><div className="demo-sidebar"><b>AI<br />Mentions</b><span>Обзор</span><span>Запросы</span><span>Скан</span><span>Настройки</span></div><div className="demo-content"><div className="demo-breadcrumb">ПРОЕКТ / СЕВЕР</div><h4>Видимость бренда</h4><div className="demo-chart"><div className="demo-chart-line" /></div><div className="demo-query"><span>Лучшие средства для сухой кожи</span><strong>Найдено</strong></div><div className="demo-query"><span>Уход за чувствительной кожей</span><strong>Найдено</strong></div><div className="demo-query"><span>Что выбрать на каждый день?</span><em>Не найдено</em></div></div></div>
}

function ParsingDemo() {
  return <div className="parsing-demo"><div className="parsing-head"><div><span>СКАН / В ПРОЦЕССЕ</span><h4>Проверяем запросы</h4></div><strong>03 / 04</strong></div><div className="parsing-progress"><span /></div><div className="parsing-events"><div><span className="parsing-dot is-done" /><span>ChatGPT</span><em>Ответ сохранён</em><Check size={15} /></div><div><span className="parsing-dot is-done" /><span>Perplexity</span><em>Источник найден</em><Check size={15} /></div><div className="is-current"><span className="parsing-dot" /><span>Алиса AI</span><em>Читаем ответ…</em><span className="typing-dots"><i /><i /><i /></span></div><div><span className="parsing-dot" /><span>Google AI Overview</span><em>Ожидает</em></div></div></div>
}

function ReportPreview() {
  return (
    <div className="report-frame" aria-label="Пример отчёта по упоминаниям бренда">
      <div className="report-window">
        <div className="report-topline">
          <div className="report-project">
            <span className="report-project-icon" aria-hidden="true">С</span>
            <span><strong>Север</strong><small>Демонстрационный проект</small></span>
          </div>
          <span className="report-period">Последние 14 дней <ChevronDown size={12} aria-hidden="true" /></span>
        </div>

        <div className="report-heading">
          <div><span className="report-kicker">ОБЗОР ВИДИМОСТИ</span><h3>Где нашли бренд</h3></div>
          <span className="report-scan"><span /> Скан завершён</span>
        </div>

        <div className="report-metrics">
          <div className="report-main-metric">
            <span>Упоминания</span>
            <strong>28 <small>/ 48</small></strong>
            <em><ArrowUpRight size={13} aria-hidden="true" /> +6 к прошлой проверке</em>
          </div>
          <div className="report-chart" aria-hidden="true">
            <div className="chart-grid" />
            <svg viewBox="0 0 260 90" preserveAspectRatio="none">
              <defs>
                <linearGradient id="report-area" x1="0" x2="0" y1="0" y2="1"><stop stopColor="#a879ff" stopOpacity=".24"/><stop offset="1" stopColor="#a879ff" stopOpacity="0"/></linearGradient>
              </defs>
              <path d="M0 76 C28 72 36 68 57 70 S92 48 113 53 S150 38 166 42 S202 20 225 26 S250 11 260 13 V90 H0Z" fill="url(#report-area)" />
              <path d="M0 76 C28 72 36 68 57 70 S92 48 113 53 S150 38 166 42 S202 20 225 26 S250 11 260 13" fill="none" stroke="#a879ff" strokeWidth="3" strokeLinecap="round" />
              <circle cx="260" cy="13" r="4.5" fill="#a879ff" stroke="white" strokeWidth="3" />
            </svg>
          </div>
        </div>

        <div className="report-table-title"><strong>Поисковые запросы</strong><span>Найдено / проверено</span></div>
        <div className="report-table" role="table" aria-label="Пример результатов по запросам">
          <div className="report-row report-row-head" role="row">
            <span role="columnheader">Запрос</span><span role="columnheader">ChatGPT</span><span role="columnheader">Perplexity</span><span role="columnheader">Алиса AI</span>
          </div>
          <div className="report-row" role="row">
            <span role="cell">Как выбрать уход для кожи?</span><span role="cell" className="status-found"><Check size={13} /> Найдено</span><span role="cell" className="status-found"><Check size={13} /> Найдено</span><span role="cell" className="status-empty">—</span>
          </div>
          <div className="report-row" role="row">
            <span role="cell">Средства для сухой кожи</span><span role="cell" className="status-empty">—</span><span role="cell" className="status-found"><Check size={13} /> Найдено</span><span role="cell" className="status-found"><Check size={13} /> Найдено</span>
          </div>
        </div>
      </div>
      <div className="report-note"><span className="note-dot" /> Пример интерфейса. Данные вымышлены.</div>
    </div>
  )
}

export function LandingPage() {
  return (
    <div className="landing" id="top">
      <header className="site-header">
        <div className="site-container header-inner">
          <Brand />
          <nav className="desktop-nav" aria-label="Навигация по странице">
            <a href="#how">Как работает</a>
            <a href="#signals">Что видно в отчёте</a>
            <a href="#faq">Вопросы</a>
          </nav>
          <a className="header-cta" href={APP_URL}>Открыть парсер <ArrowUpRight size={16} aria-hidden="true" /></a>
          <details className="mobile-nav">
            <summary>Меню <ChevronDown size={16} aria-hidden="true" /></summary>
            <nav aria-label="Мобильная навигация">
              <a href="#how">Как работает</a>
              <a href="#signals">Что видно в отчёте</a>
              <a href="#faq">Вопросы</a>
              <a href={APP_URL}>Открыть парсер</a>
            </nav>
          </details>
        </div>
      </header>

      <main>
        <section className="hero" aria-labelledby="hero-title">
          <ScannerLayer />
          <div className="site-container hero-inner">
            <div className="hero-copy">
              <div className="eyebrow"><span className="eyebrow-line" /> МОНИТОРИНГ ОТВЕТОВ ИИ</div>
              <h1 id="hero-title">Смотрите, где ИИ упоминает <span>ваш бренд.</span></h1>
              <p>Проверяйте свои запросы в четырёх ИИ-системах. Сохраняйте ответы, смотрите источник каждого упоминания и сравнивайте видимость по датам.</p>
              <div className="hero-actions">
                <a className="button button-primary" href="#how">Как это работает <ArrowRight size={18} aria-hidden="true" /></a>
                <a className="text-link" href={APP_URL}>Открыть парсер <ArrowUpRight size={17} aria-hidden="true" /></a>
              </div>
              <div className="hero-services"><span>ПРОВЕРЯЕМ</span><div>{services.map((name) => <span key={name}>{name}</span>)}</div></div>
            </div>
          </div>
          <div className="site-container hero-foot"><span>ОТ ЗАПРОСА ДО КОНКРЕТНОГО ОТВЕТА</span><span>01 / 04</span></div>
        </section>

        <section className="proof-section" aria-label="Пример интерфейса отчёта"><div className="site-container proof-layout"><div className="proof-copy"><span className="section-index">РЕЗУЛЬТАТ СКАНА</span><h2>Каждое упоминание видно в деталях.</h2><p>Смотрите ответы по каждому запросу и системе. Данные остаются под рукой для сравнения.</p></div><ReportPreview /></div></section>

        <section className="intro-section" id="how" aria-labelledby="how-title">
          <div className="site-container">
            <div className="section-heading"><span className="section-index">01 / КАК РАБОТАЕТ</span><h2 id="how-title">От списка запросов<br />до понятного отчёта.</h2><p>Вы задаёте вопросы, которые задают ваши клиенты. Парсер собирает ответы и показывает, в каком виде появился бренд.</p></div>
            <ProcessFlow />
            <div className="steps-grid">
              <article className="step-card"><span className="step-number">01</span><div className="step-icon"><ListFilter size={23} strokeWidth={1.8} aria-hidden="true" /></div><h3>Добавьте запросы</h3><p>Укажите бренд, его варианты написания и список вопросов для проверки.</p></article>
              <article className="step-card"><span className="step-number">02</span><div className="step-icon"><ScanSearch size={23} strokeWidth={1.8} aria-hidden="true" /></div><h3>Запустите скан</h3><p>Парсер откроет ИИ-сервисы, задаст вопросы и сохранит ответы по каждой системе.</p></article>
              <article className="step-card"><span className="step-number">03</span><div className="step-icon"><MessageSquareText size={23} strokeWidth={1.8} aria-hidden="true" /></div><h3>Проверьте контекст</h3><p>Смотрите, где найден бренд: в тексте ответа, ссылке, карточке или на сайте-источнике.</p></article>
            </div>
          </div>
        </section>

        <section className="showcase-section" aria-labelledby="showcase-title"><div className="site-container"><div className="showcase-heading"><span className="section-index">ВНУТРИ ПРОДУКТА</span><h2 id="showcase-title">Весь путь проверки — перед глазами.</h2><p>Список запросов, ход скана и результаты по каждой ИИ-системе собраны в одном интерфейсе.</p></div><div className="showcase-grid">
          <SpotlightCard className="media-card" spotlightColor="rgba(162, 108, 255, 0.17)"><div className="media-card-heading"><span>01 / ИНТЕРФЕЙС</span><h3>Все запросы и результаты в одном месте.</h3></div><GifWindow slot="interface" title="Обзор проекта"><InterfaceDemo /></GifWindow><p>Дашборд показывает видимость по запросам и датам. Каждый результат можно открыть и проверить.</p></SpotlightCard>
          <SpotlightCard className="media-card" spotlightColor="rgba(162, 108, 255, 0.17)"><div className="media-card-heading"><span>02 / ПРОЦЕСС СКАНИРОВАНИЯ</span><h3>Видно, что происходит во время проверки.</h3></div><GifWindow slot="parsing" title="Ход проверки"><ParsingDemo /></GifWindow><p>Парсер показывает прогресс по сервисам и сохраняет ответы по мере выполнения скана.</p></SpotlightCard>
        </div></div></section>

        <section className="signals-section" id="signals" aria-labelledby="signals-title">
          <div className="site-container signals-layout">
            <div className="signals-copy"><span className="section-index">02 / ЧТО ВИДНО В ОТЧЁТЕ</span><h2 id="signals-title">У каждого упоминания есть источник.</h2><p>Бренд может появиться в словах ИИ, в карточках товаров, в ссылке на ваш сайт или в адресе чужой страницы. Отчёт сохраняет этот контекст, чтобы вы понимали, что именно произошло.</p><a className="text-link" href={APP_URL}>Посмотреть в парсере <ArrowUpRight size={17} aria-hidden="true" /></a></div>
            <div className="signals-list">
              <article><div className="signal-symbol"><MessageSquareText size={22} aria-hidden="true" /></div><div><span>01 / ПРЯМОЕ УПОМИНАНИЕ</span><h3>В словах ИИ</h3><p>Видно, назвал ли сервис бренд в собственном ответе.</p></div><ArrowUpRight className="signal-arrow" size={18} aria-hidden="true" /></article>
              <article><div className="signal-symbol"><Link2 size={22} aria-hidden="true" /></div><div><span>02 / ССЫЛКА</span><h3>На вашем сайте или вне его</h3><p>Отдельно учитываются ссылки на ваш домен и упоминания в адресах сторонних страниц.</p></div><ArrowUpRight className="signal-arrow" size={18} aria-hidden="true" /></article>
              <article><div className="signal-symbol"><ListFilter size={22} aria-hidden="true" /></div><div><span>03 / СПОСОБ ПОДСЧЁТА</span><h3>Сравнимые цифры</h3><p>Считайте все упоминания, исключайте внешние площадки или оставляйте только ссылки на свой сайт.</p></div><ArrowUpRight className="signal-arrow" size={18} aria-hidden="true" /></article>
            </div>
          </div>
        </section>

        <section className="history-section" aria-labelledby="history-title">
          <div className="site-container history-layout">
            <div className="history-visual" aria-hidden="true"><div className="history-axis"><span>ВИДИМОСТЬ</span><span>100%</span><span>50%</span><span>0%</span></div><svg viewBox="0 0 620 270" preserveAspectRatio="none"><path d="M0 232 C72 207 96 210 142 191 S226 206 276 163 S351 168 407 102 S492 133 548 57 S586 47 620 27" fill="none" stroke="#bc91ff" strokeWidth="3"/><path d="M0 232 C72 207 96 210 142 191 S226 206 276 163 S351 168 407 102 S492 133 548 57 S586 47 620 27 V270 H0Z" fill="url(#history-fill)"/><defs><linearGradient id="history-fill" x1="0" x2="0" y1="0" y2="1"><stop stopColor="#9c64fb" stopOpacity=".31"/><stop offset="1" stopColor="#9c64fb" stopOpacity="0"/></linearGradient></defs></svg><div className="history-dates"><span>ПЕРВЫЙ СКАН</span><span>ПОСЛЕДНИЙ СКАН</span></div><div className="history-callout"><ArrowUpRight size={19} /> Изменение видно по датам</div></div>
            <div className="history-copy"><span className="section-index">03 / ДИНАМИКА</span><h2 id="history-title">Сравнивайте ответы между сканами.</h2><p>Смотрите, в каких запросах бренд появился или пропал. При необходимости выгружайте таблицу упоминаний в Excel.</p><a className="button button-light" href={APP_URL}>Открыть отчёт <ArrowUpRight size={17} aria-hidden="true" /></a></div>
          </div>
        </section>

        <section className="faq-section" id="faq" aria-labelledby="faq-title"><div className="site-container faq-layout"><div><span className="section-index">04 / ВОПРОСЫ</span><h2 id="faq-title">Перед первым сканом.</h2><p>Коротко о том, что проверяет текущая версия.</p></div><div className="faq-list">
          <details><summary><span>Какие ИИ-системы доступны?</span><ChevronDown size={18} aria-hidden="true" /></summary><p>Сейчас работают ChatGPT, Perplexity, Алиса AI и Google AI Overview.</p></details>
          <details><summary><span>Что считается упоминанием?</span><ChevronDown size={18} aria-hidden="true" /></summary><p>Отчёт различает бренд в тексте ответа, ссылку на ваш сайт, карточку и упоминания в сторонних источниках. На дашборде можно выбрать, какие типы учитывать.</p></details>
          <details><summary><span>Нужен ли вход в ИИ-сервисы?</span><ChevronDown size={18} aria-hidden="true" /></summary><p>Некоторые сервисы могут запросить вход или показать капчу. Парсер работает через браузерные сессии на вашем компьютере.</p></details>
          <details><summary><span>Где хранятся результаты?</span><ChevronDown size={18} aria-hidden="true" /></summary><p>Текущая версия работает локально. Результаты, снимки и профили браузера хранятся на вашем компьютере.</p></details>
        </div></div></section>

        <section className="bottom-cta" aria-labelledby="cta-title"><div className="site-container cta-inner"><div><span className="section-index">НАЧНИТЕ С ВАШИХ ЗАПРОСОВ</span><h2 id="cta-title">Проверьте, что ИИ уже говорит о вашем бренде.</h2></div><a className="button button-primary" href={APP_URL}>Открыть парсер <ArrowUpRight size={18} aria-hidden="true" /></a><ArrowDownRight className="cta-decoration" size={210} strokeWidth={.5} aria-hidden="true" /></div></section>
      </main>

      <footer className="site-footer"><div className="site-container footer-inner"><Brand /><span>Мониторинг упоминаний бренда в ответах ИИ.</span><a href="https://github.com/egotrippingh/aiparser" target="_blank" rel="noreferrer">GitHub <ExternalLink size={14} aria-hidden="true" /></a><a className="back-to-top" href="#top">Наверх ↑</a></div></footer>
      <a className="floating-help" href="#faq" aria-label="Частые вопросы"><CircleHelp size={22} aria-hidden="true" /></a>
    </div>
  )
}
