import { useRef, useState, type KeyboardEvent } from "react"
import "./product-principles.css"

const features = [
  { id: "browser", title: "Смотрим на выдачу в браузере", text: "Агент открывает ИИ-сервисы на вашем ПК и задаёт запросы в их веб-интерфейсах. Сохраняет ответ, ссылки на источники и скриншот." },
  { id: "models", title: "Две модели разбирают спорные случаи", text: "Основная модель ищет бренд в ответе. Если её вывод расходится с правилами точного поиска, арбитр перепроверяет текст, ссылки и скриншот." },
  { id: "price", title: "Понятно, за что вы платите", text: "В цену входят работа ИИ, облако для скриншотов и сервер сервиса. Сканирование на вашем ПК сокращает затраты на серверные мощности." },
  { id: "support", title: "Быстрая поддержка", text: "Помогаем с настройкой агента, подключением компьютеров и результатами проверок. Разбираем проблему на конкретном запросе." },
  { id: "updates", title: "Приложение становится лучше", text: "Учитываем обратную связь, исправляем ошибки и обновляем сбор ответов, когда ИИ-сервисы меняют свои интерфейсы." },
] as const

function Illustration({ id }: { id: string }) {
  if (id === "browser") return <div className="principle-browser">
    <div className="principle-window-bar"><span>● ● ●</span><span>Браузер на вашем компьютере</span></div>
    <div className="principle-browser-body"><span className="principle-label">ВАШ ЗАПРОС</span><div className="principle-question">Какой уход выбрать для сухой кожи?</div><span className="principle-label">ОТВЕТ ИИ</span><div className="principle-answer"><p>Обратите внимание на средства с мягкой формулой. Например, <mark>«Север»</mark> предлагает…</p><div className="principle-source">↗ example.com / catalogue</div></div><div className="principle-evidence"><span>Текст ответа</span><span>Внешние источники</span><span>Скриншот</span></div></div><p className="principle-caption">Пример ответа с вымышленным брендом</p>
  </div>
  if (id === "models") return <div className="principle-models"><span className="principle-label">ПЕРЕПРОВЕРКА РЕЗУЛЬТАТА</span><div className="model-note"><span>01</span><div><strong>Основная модель</strong><p>Упоминание бренда найдено.</p></div></div><div className="model-connector">Сверяем вывод с правилами точного поиска ↓</div><div className="model-note arbiter"><span>02</span><div><strong>Арбитр</strong><p>Бренд есть только в вопросе. В самом ответе упоминания нет.</p></div></div><div className="model-verdict"><span>Результат проверки</span><strong>Нет упоминания</strong><small>Вывод уточнён после перепроверки</small></div><p className="principle-caption">Пример спорного случая. Арбитр подключается при расхождении.</p></div>
  if (id === "price") return <div className="principle-price"><span className="principle-label">ЕДИНИЦА РАСЧЁТА</span><div className="price-equation"><strong>1 запрос</strong><span>×</span><strong>1 ИИ-система</strong><span>=</span><strong className="price-unit">1 проверка</strong></div><div className="price-included"><span>В стоимость входят</span><div><b>01</b><strong>Анализ ответа моделями</strong><small>Основная модель и арбитр</small></div><div><b>02</b><strong>Облачное хранилище</strong><small>Скриншоты доступны 90 дней</small></div><div><b>03</b><strong>Сервер сервиса</strong><small>Кабинет, очередь и синхронизация</small></div></div><div className="price-local"><span>Ваш компьютер выполняет сканирование</span><p>Меньше расходов на серверный браузер в цене проверки.</p></div></div>
  if (id === "support") return <div className="principle-support"><span className="principle-label">ОТ ВОПРОСА К РЕШЕНИЮ</span><h3>Разберёмся вместе.</h3><div className="support-step"><span>01</span><div><strong>Опишите, что произошло</strong><p>Укажите проект, ИИ-систему и запрос.</p></div></div><div className="support-step"><span>02</span><div><strong>Посмотрим на контекст</strong><p>Ответ, скриншот и состояние агента помогают найти причину.</p></div></div><div className="support-step"><span>03</span><div><strong>Поможем продолжить работу</strong><p>Подскажем настройку или возьмём ошибку в исправление.</p></div></div><p className="principle-caption">Так мы разбираем обращения по проверкам</p></div>
  return <div className="principle-updates"><span className="principle-label">ОБРАТНАЯ СВЯЗЬ СТАНОВИТСЯ ИЗМЕНЕНИЕМ</span><h3>Развиваем то,<br/>чем вы пользуетесь.</h3><div className="update-cycle">{["Ваше наблюдение", "Исправление", "Проверка", "Обновление"].map((step,i)=><div key={step}><span>{String(i+1).padStart(2,"0")}</span><strong>{step}</strong>{i<3&&<i aria-hidden="true">↓</i>}</div>)}</div><p className="principle-caption">Сбор ответов · Удобство кабинета · Стабильность агента</p></div>
}

export function ProductPrinciples() {
  const [active, setActive] = useState(0)
  const tabs = useRef<(HTMLButtonElement|null)[]>([])
  function navigate(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index
    if(event.key === "ArrowDown" || event.key === "ArrowRight") next = (index+1)%features.length
    else if(event.key === "ArrowUp" || event.key === "ArrowLeft") next = (index+features.length-1)%features.length
    else if(event.key === "Home") next = 0
    else if(event.key === "End") next = features.length-1
    else return
    event.preventDefault(); setActive(next); tabs.current[next]?.focus()
  }
  return <section className="principles-section" id="approach" aria-labelledby="principles-title"><div className="site-container">
    <div className="principles-heading"><span className="section-index">КАК МЫ ПРОВЕРЯЕМ</span><h2 id="principles-title">Ответы, которые<br/>можно проверить.</h2><p>Мы сохраняем контекст, разбираем спорные упоминания и показываем, из чего складывается стоимость проверки.</p></div>
    <div className="principles-layout"><div className="principles-tabs" role="tablist" aria-label="Принципы работы AIRvision" aria-orientation="vertical">{features.map((feature,index)=><button key={feature.id} ref={element=>{tabs.current[index]=element}} type="button" role="tab" id={`principle-tab-${feature.id}`} aria-controls={`principle-panel-${feature.id}`} aria-selected={active===index} tabIndex={active===index?0:-1} onClick={()=>setActive(index)} onKeyDown={event=>navigate(event,index)}><span className="principle-tab-number">0{index+1}</span><span><strong>{feature.title}</strong><span className="principle-tab-text">{feature.text}</span></span></button>)}</div>
      <div className="principles-stage">{features.map((feature,index)=><div key={feature.id} role="tabpanel" id={`principle-panel-${feature.id}`} aria-labelledby={`principle-tab-${feature.id}`} hidden={index!==active} tabIndex={0}><Illustration id={feature.id}/></div>)}</div>
    </div>
  </div></section>
}
