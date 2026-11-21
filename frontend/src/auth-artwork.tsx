export function AuthArtwork() {
  return <aside className="auth-screen__art" aria-label="Пример отчёта по бренду">
    <img className="auth-screen__quote" src="/assets/brand/aireyt-quote.svg" alt="" width={470} height={470}/>
    <figure className="auth-screen__report">
      <figcaption><strong>Видимость бренда</strong></figcaption>
      <div className="auth-screen__report-body">
        <div className="auth-screen__metric"><strong>52,1<span>%</span></strong><span>ответов с упоминанием</span></div>
        <div className="auth-screen__chart" aria-hidden="true">
          <svg viewBox="0 0 360 105" preserveAspectRatio="none">
            <defs><linearGradient id="auth-area" x2="0" y2="1"><stop stopColor="var(--accent)" stopOpacity=".32"/><stop offset="1" stopColor="var(--accent)" stopOpacity="0"/></linearGradient></defs>
            <path d="M0 85 60 74 120 77 180 54 240 62 300 35 360 20V105H0Z" fill="url(#auth-area)"/>
            <path d="M0 85 60 74 120 77 180 54 240 62 300 35 360 20" stroke="var(--accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" fill="none"/>
          </svg>
        </div>
      </div>
    </figure>
  </aside>
}
