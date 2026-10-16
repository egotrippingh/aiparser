import { useId, useState, type ReactNode } from "react"
import { Tooltip } from "@base-ui/react/tooltip"
import "./icon-nav-link.css"

export function IconNavLink({ href, label, current, children, className, side = "right" }: {
  href: string; label: string; current?: boolean; children: ReactNode; className: string; side?: "right" | "bottom"
}) {
  const id = useId(), [open, setOpen] = useState(false)
  return <Tooltip.Root onOpenChange={setOpen}>
    <Tooltip.Trigger delay={180} render={<a href={href} className={className} aria-label={label} aria-describedby={open ? id : undefined} aria-current={current ? "page" : undefined}/>}>{children}</Tooltip.Trigger>
    <Tooltip.Portal><Tooltip.Positioner side={side} sideOffset={12} className="air-nav-tip-positioner">
      <Tooltip.Popup className="air-nav-tip" id={id} role="tooltip"><Tooltip.Arrow className="air-nav-tip-arrow"/>{label}</Tooltip.Popup>
    </Tooltip.Positioner></Tooltip.Portal>
  </Tooltip.Root>
}
