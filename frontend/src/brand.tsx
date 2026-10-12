import "./brand.css"

export function Brand({ href = "/", className = "" }: { href?: string; className?: string }) {
  return <a className={`air-brand ${className}`} href={href} aria-label="AIRate — на главную">
    <img src="/assets/brand/airate.svg" alt="" width={31} height={31} fetchPriority="high" />
    <span><b>ai</b>rate</span>
  </a>
}
