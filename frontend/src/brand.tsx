import "./brand.scss"

export function Brand({ href = "/", className = "" }: { href?: string; className?: string }) {
  return <a className={`air-brand ${className}`} href={href} aria-label="Аирейт — на главную">
    <img src="/assets/brand/aireyt-quote.svg" alt="" width={26} height={26} className="air-brand__mark"/>
    <img src="/assets/brand/aireyt-wordmark.svg" alt="" width={119} height={34} className="air-brand__wordmark"/>
  </a>
}
