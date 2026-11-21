import { useEffect, useRef, type CSSProperties, type PointerEvent } from "react"
import { Brand } from "./brand"
import { PublicSiteHeader } from "./site-header"
import { SUPPORT_URL } from "./site-footer"
import { LandingHeroAnimation } from "./components/landing-hero-animation"
import { mountApiDemo } from "../design-system/landing/api-demo"
import "./site-theme.scss"
import "../design-system/stand.scss"
import "../design-system/landing/landing.scss"

const registerUrl = `${import.meta.env.VITE_APP_URL || "/cabinet/"}?register=1`

function moveSpotlight(event: PointerEvent<HTMLDivElement>) {
  if (event.pointerType === "touch" || !(event.target instanceof Element)) return
  const card = event.target.closest<HTMLElement>(".task-card")
  if (!card) return
  const rect = card.getBoundingClientRect()
  card.style.setProperty("--mouse-x", `${event.clientX - rect.left}px`)
  card.style.setProperty("--mouse-y", `${event.clientY - rect.top}px`)
}

export function LandingPage() {
  const page = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (page.current) return mountApiDemo(page.current)
  }, [])
  return <div className="landing-page" ref={page}>
    <a href="#main" className="skip">К содержанию</a>
    <PublicSiteHeader/>
    <main id="main" tabIndex={-1}>
      <section className="home-hero container" aria-labelledby="hero-title">
        <div className="home-hero__message">
          <h1 id="hero-title">Узнайте, что ИИ говорит<br/> о вашем бренде<span>.</span></h1>
          <p>Добавьте вопросы, которые задают ваши покупатели. Аирейт проверит их в пяти ИИ-сервисах, сохранит ответы и покажет, где назвали ваш бренд.</p>
          <div className="home-hero__actions">
            <a className="btn primary" href={registerUrl}>Начать проверку <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M7 17 17 7M7 7h10v10"/></svg></a>
            <a className="btn quiet" href="#tasks">Для каких задач <span aria-hidden="true">↓</span></a>
          </div>
        </div>
        <LandingHeroAnimation/>
      </section>

      <section className="home-audience" id="audience" aria-labelledby="audience-title">
        <div className="container home-audience__layout">
          <div className="home-audience__intro">
            <h2 id="audience-title">Для кого</h2>
            <p>Проверьте, по каким запросам ИИ уже упоминает ваш бренд. Найдите темы, где вас пока не называют.</p>
            <figure className="home-audience__report">
              <div className="report-sample">
                <div className="report-sample__heading"><span>Отчёт по бренду</span><code>ПРИМЕР</code></div>
                <div className="report-sample__stats">
                  <div><span>Видимость</span><strong>52,1<span>%</span></strong></div>
                  <div><span>С упоминанием</span><strong>609<span> / 1170</span></strong></div>
                </div>
                <ol className="report-sample__bars" aria-label="Пример видимости по сервисам">
                  <li><img src="/assets/services/chatgpt.svg" width="18" height="18" alt=""/><span>ChatGPT</span><i style={{"--value": "68%"} as CSSProperties} aria-hidden="true"></i><b>68%</b></li>
                  <li><img src="/assets/services/perplexity.svg" width="18" height="18" alt=""/><span>Perplexity</span><i style={{"--value": "54%"} as CSSProperties} aria-hidden="true"></i><b>54%</b></li>
                  <li><img src="/assets/services/gemini.png" width="18" height="18" alt=""/><span>Gemini</span><i style={{"--value": "46%"} as CSSProperties} aria-hidden="true"></i><b>46%</b></li>
                </ol>
              </div>
            </figure>
          </div>
          <ul className="home-audience__list">
            <li><svg className="home-audience__icon" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6"><path d="M11 6a13 13 0 0 0 8.4-2.8A1 1 0 0 1 21 4v12a1 1 0 0 1-1.6.8A13 13 0 0 0 11 14H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z"/><path d="M6 14a12 12 0 0 0 2.4 7.2a2 2 0 0 0 3.2-2.4A8 8 0 0 1 10 14M8 6v8"/></g></svg><div><h3>Маркетинговые агентства</h3><p>Добавьте в отчёт для клиента долю ответов с упоминанием бренда и покажите, как она изменилась с прошлой проверки.</p></div></li>
            <li><svg className="home-audience__icon" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6"><path d="m8 11l2 2l4-4"/><circle cx="11" cy="11" r="8"/><path d="m21 21l-4.3-4.3"/></g></svg><div><h3>Агентства поискового продвижения</h3><p>Проверьте запросы из семантики и найдите темы, в которых ИИ отвечает без упоминания клиента.</p></div></li>
            <li><svg className="home-audience__icon" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6"><path d="M10 12h4m-4-4h4m0 13v-3a2 2 0 0 0-4 0v3"/><path d="M6 10H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-2"/><path d="M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16"/></g></svg><div><h3>Владельцы бизнеса</h3><p>Посмотрите, что ИИ советует покупателям, когда они выбирают товар или услугу в вашей категории.</p></div></li>
            <li><svg className="home-audience__icon" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" d="M18 5a2 2 0 0 1 2 2v8.526a2 2 0 0 0 .212.897l1.068 2.127a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45l1.068-2.127A2 2 0 0 0 4 15.526V7a2 2 0 0 1 2-2zm2.054 10.987H3.946"/></svg><div><h3>Специалисты на фрилансе</h3><p>Ведите проверку каждого бренда в отдельном проекте. Дайте клиенту доступ к отчёту с ответами.</p></div></li>
          </ul>
        </div>
      </section>

      <section className="home-tasks container" id="tasks" aria-labelledby="tasks-title">
        <div className="home-tasks__heading"><h2 id="tasks-title">Для каких задач</h2><p>Откройте сам ответ, посмотрите его источники и сравните с прошлой проверкой.</p></div>
        <div className="home-tasks__grid" onPointerMove={moveSpotlight}>
          <article className="task-card task-card--featured">
            <div>
              <div className="task-card__heading"><svg className="task-card__icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 18h18M4 13l5-4 4 3 6-7m-4 0h4v4"/></svg><h3>Измерить видимость бренда</h3></div>
              <p>Сравните долю ответов с вашим брендом в разных ИИ-сервисах. Посмотрите, где она выросла или снизилась.</p>
            </div>
            <div className="task-card__chart" role="img" aria-label="Иллюстрация роста видимости между проверками">
              <svg viewBox="0 0 280 94" preserveAspectRatio="none" aria-hidden="true">
                <defs><linearGradient id="trend-fill" x2="0" y2="1"><stop stopColor="var(--accent)" stopOpacity=".22"/><stop offset="1" stopColor="var(--accent)" stopOpacity="0"/></linearGradient></defs>
                <path d="M0 75 46 69 91 73 135 46 181 53 229 28 280 17V94H0Z" fill="url(#trend-fill)"/>
                <path d="M0 75 46 69 91 73 135 46 181 53 229 28 280 17" stroke="var(--accent)" strokeWidth="2" vector-effect="non-scaling-stroke" fill="none"/>
                <circle cx="276" cy="18" r="3" fill="var(--accent)"/>
              </svg>
            </div>
          </article>
          <article className="task-card">
            <div className="task-card__heading"><svg className="task-card__icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="5.5"/><path d="m14 14 5 5M8 10h4"/></svg><h3>Найти запросы без упоминаний</h3></div>
            <p>Найдите вопросы, на которые ИИ дал ответ без вашего бренда. С них можно начать разбор тем.</p>
          </article>
          <article className="task-card">
            <div className="task-card__heading"><svg className="task-card__icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 5h16v11H9l-5 4zM8 9h8m-8 3h5"/></svg><h3>Увидеть контекст упоминания</h3></div>
            <p>Прочитайте ответ целиком. Проверьте, появился ли бренд в тексте, в ссылке или в карточке товара.</p>
          </article>
          <article className="task-card">
            <div className="task-card__heading"><svg className="task-card__icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m10 14 4-4m-5-1 3-3a4 4 0 0 1 6 6l-3 3m-6-6-3 3a4 4 0 0 0 6 6l3-3"/></svg><h3>Посмотреть источники ответов</h3></div>
            <p>Посмотрите, какие сайты ИИ приводит в ответах с вашим брендом. Список доменов можно выгрузить в Excel.</p>
          </article>
          <article className="task-card">
            <div className="task-card__heading"><svg className="task-card__icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4m8-4v4M4 10h16m-11 5 2 2 4-4"/></svg><h3>Следить за изменениями</h3></div>
            <p>Поставьте проверки на расписание. Команда или клиент смогут открыть отчёт и сравнить результаты за разные даты.</p>
          </article>
        </div>
        <div className="home-tasks__action">
          <div><h2>Начните с запросов покупателей</h2><p>Добавьте запросы в проект и выберите, где их проверить.</p></div>
          <a className="btn primary" href={registerUrl}>Начать проверку <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M7 17 17 7M7 7h10v10"/></svg></a>
        </div>
      </section>
      <section className="home-chapter container" id="how" aria-labelledby="how-title">
        <div className="home-chapter__heading"><h2 id="how-title">Как работает</h2><p>От вопросов покупателей до отчёта с ответами ИИ.</p></div>
        <ol className="home-chapter__steps">
          <li><h3>Добавьте запросы</h3><p>Укажите бренд и вопросы, которые хотите проверить.</p></li>
          <li><h3>Запустите проверку</h3><p>Аирейт отправит запросы в выбранные ИИ-сервисы и сохранит ответы.</p></li>
          <li><h3>Откройте отчёт</h3><p>Сравните видимость по датам и откройте ответ за любым упоминанием.</p></li>
        </ol>
      </section>
      <section className="home-chapter home-chapter--api" id="api" aria-labelledby="api-title">
        <div className="container">
          <div className="api-demo__intro">
            <h2 id="api-title">Встройте Аирейт в свои инструменты</h2>
            <div><p>Используйте REST API в скриптах, внутренних сервисах и клиентских отчётах. Запускайте проверки по списку брендов, забирайте ответы со ссылками и собирайте данные в своём дашборде.</p><a className="btn" href="/docs/api/">Документация REST API <span aria-hidden="true">↗</span></a></div>
          </div>
          <div className="api-demo" aria-label="Пример запроса и ответа REST API">
            <section className="api-panel" aria-labelledby="api-request-title">
              <div className="api-panel__heading"><h3 id="api-request-title">answers.sh</h3><button type="button" className="btn compact" id="copy-api" hidden>Скопировать</button></div>
              <pre tabIndex={0} aria-label="Команда cURL"><code id="api-request">
                <span className="code-verb">curl</span>{" -fsS --get \\\n  "}
                <span className="code-string">"https://airate.tech/api/v1/public/projects/$PROJECT_ID/answers"</span>{" \\\n  -H "}
                <span className="code-string">"Authorization: Bearer $AIRATE_API_KEY"</span>{" \\\n  --data-urlencode "}
                <span className="code-string">"date_from=2026-11-01"</span>{" \\\n  --data-urlencode "}
                <span className="code-string">"date_to=2026-11-19"</span>{" \\\n  --data-urlencode "}
                <span className="code-string">"limit=1"</span>
              </code></pre>

            </section>
            <section className="api-panel" aria-labelledby="api-response-title">
              <div className="api-panel__heading"><h3 id="api-response-title"><span className="api-panel__indicator" aria-hidden="true"></span>Пример ответа</h3><span className="api-panel__format">JSON</span></div>
              <pre tabIndex={0} aria-label="Пример ответа JSON"><code id="api-response">{"{\n  "}
                <span className="code-property">"items"</span>{": [{\n    "}
                <span className="code-property">"id"</span>{": 42,\n    "}
                <span className="code-property">"service"</span>: <span className="code-string">"chatgpt"</span>{",\n    "}
                <span className="code-property">"scan_date"</span>: <span className="code-string">"2026-11-18"</span>{",\n    "}
                <span className="code-property">"answer_text"</span>: <span className="code-string">"Например, «Север» предлагает…"</span>{",\n    "}
                <span className="code-property">"sources"</span>: [<span className="code-string">"https://example.com"</span>{"]\n  }],\n  "}
                <span className="code-property">"next_after_id"</span>: <span className="code-verb">null</span>{"\n}"}
              </code></pre>

            </section>
          </div>
          <p className="api-demo__status" id="api-demo__status" role="status"></p>
        </div>
      </section>
      <section className="home-chapter home-chapter--mcp" id="mcp" aria-labelledby="mcp-title">
        <div className="container">
          <div className="api-demo__intro">
            <h2 id="mcp-title">Подключите Аирейт к ИИ-агенту через MCP</h2>
            <div>
              <p>Попросите агента собрать сохранённые ответы по нужным проектам, сравнить даты и приложить ссылки на источники. Для новой проверки агент рассчитает стоимость, а вы подтвердите запуск.</p>
              <a className="btn primary" href="/docs/mcp/">Как подключить MCP <span aria-hidden="true">↗</span></a>
            </div>
          </div>
          <div className="mcp-example">
            <figure className="api-panel mcp-example__prompt">
              <figcaption className="api-panel__heading">Запрос агенту</figcaption>
              <blockquote>«Сравни последние две недели в проекте „Север“. Покажи, в каких ответах ChatGPT упомянул бренд, и приложи ссылки на источники».</blockquote>
            </figure>
            <div className="mcp-example__setup">
              <h3>Подключение</h3>
              <p>Скачайте файл MCP, добавьте его в настройки Claude Desktop, Codex или Google Antigravity и укажите ключ Аирейт. При первом запуске uv установит всё необходимое.</p>
            </div>
          </div>
        </div>
      </section>
    </main>
    <footer className="home-footer">
      <div className="container home-footer__inner">
        <Brand/>
        <nav aria-label="Документы и поддержка"><a href="/terms/">Условия использования</a><a href="/privacy/">Политика конфиденциальности</a><a href={SUPPORT_URL}>Поддержка</a></nav>
      </div>
    </footer>
  </div>
}
