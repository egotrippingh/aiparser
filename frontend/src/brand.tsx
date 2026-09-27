import "./brand.css"

export function Brand({ href = "/", className = "" }: { href?: string; className?: string }) {
  return <a className={`air-brand ${className}`} href={href} aria-label="AIRvision.ru — на главную">
    <img src="/assets/brand/airvision-icon.png" alt="" width={48} height={48} fetchPriority="high" />
    <span>AIRvision.ru</span>
  </a>
}
