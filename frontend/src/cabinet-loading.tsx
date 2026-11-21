import "./cabinet-loading.scss"

export function CabinetSkeleton({ label, format = "rows" }: {
  label: string
  format?: "screen" | "report" | "rows"
}) {
  return <div className={`cab-skeleton cab-skeleton--${format}`} role="status" aria-label={label}>
    {format === "screen" && <div className="cab-skeleton__header" aria-hidden="true"><span/><span/><span/></div>}
    <div className="cab-skeleton__content" aria-hidden="true">
      <div className="cab-skeleton__heading"/>
      {format !== "rows" && <><div className="cab-skeleton__meta"><span/><span/><span/></div><div className="cab-skeleton__chart"/></>}
      <div className="cab-skeleton__rows"><span/><span/><span/></div>
    </div>
  </div>
}
