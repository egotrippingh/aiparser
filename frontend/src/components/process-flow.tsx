import { useEffect, useRef } from "react"
import type { AnimationItem } from "lottie-web"

const staticValue = (value: number | number[]) => ({ a: 0, k: value })

function dotLayer(name: string, size: number, color: number[], opacity: number, index: number, start: number[], end: number[]) {
  return {
    ddd: 0, ind: index, ty: 4, nm: name, sr: 1,
    ks: { o: staticValue(opacity), r: staticValue(0), p: { a: 1, k: [
      { t: 0, s: start, e: end, o: { x: 0.45, y: 0 }, i: { x: 0.55, y: 1 } },
      { t: 119, s: end },
    ] }, a: staticValue([0, 0, 0]), s: staticValue([100, 100, 100]) },
    ao: 0,
    shapes: [{ ty: "gr", nm: name, it: [
      { ty: "el", nm: "Circle", d: 1, p: staticValue([0, 0]), s: staticValue([size, size]) },
      { ty: "fl", nm: "Fill", c: staticValue(color), o: staticValue(100), r: 1 },
      { ty: "tr", p: staticValue([0, 0]), a: staticValue([0, 0]), s: staticValue([100, 100]), r: staticValue(0), o: staticValue(100) },
    ] }],
    ip: 0, op: 120, st: 0, bm: 0,
  }
}

// Lottie renders the signal and halo as SVG. The HTML nodes below stay legible
// when animation is reduced, unavailable, or still loading.
function chainAnimation(width: number, height: number, startX: number, endX: number, centerY: number) {
  const start = [startX, centerY, 0]
  const end = [endX, centerY, 0]
  return {
    v: "5.7.1", fr: 30, ip: 0, op: 120, w: width, h: height, nm: "AI Mentions process signal", ddd: 0, assets: [],
    layers: [
      dotLayer("Signal", 21, [0.71, 0.47, 1, 1], 100, 1, start, end),
      dotLayer("Signal halo", 47, [0.71, 0.47, 1, 1], 17, 2, start, end),
    ],
  }
}

export function ProcessFlow() {
  const flowRef = useRef<HTMLDivElement>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    let active = true
    let item: AnimationItem | undefined
    let observer: ResizeObserver | undefined
    import("lottie-web/build/player/lottie_light").then(({ default: lottie }) => {
      const flow = flowRef.current
      const container = ref.current
      if (!active || !flow || !container) return

      let previousWidth = 0
      let previousHeight = 0
      const render = () => {
        const bounds = flow.getBoundingClientRect()
        const width = Math.round(bounds.width)
        const height = Math.round(bounds.height)
        if (!width || !height || (width === previousWidth && height === previousHeight)) return

        const nodes = flow.querySelectorAll(".process-flow-nodes span")
        if (nodes.length < 2) return
        const first = nodes[0].getBoundingClientRect()
        const last = nodes[nodes.length - 1].getBoundingClientRect()
        const startX = first.left - bounds.left + first.width / 2
        const endX = last.left - bounds.left + last.width / 2
        const centerY = first.top - bounds.top + first.height / 2

        previousWidth = width
        previousHeight = height
        item?.destroy()
        item = lottie.loadAnimation({
          container,
          renderer: "svg",
          loop: true,
          autoplay: true,
          animationData: chainAnimation(width, height, startX, endX, centerY),
          rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
        })
      }

      observer = new ResizeObserver(render)
      observer.observe(flow)
      render()
    })
    return () => { active = false; observer?.disconnect(); item?.destroy() }
  }, [])

  return (
    <div className="process-flow" ref={flowRef} aria-hidden="true">
      <div className="process-flow-line" />
      <div className="process-flow-nodes"><span /><span /><span /></div>
      <div className="process-flow-lottie" ref={ref} />
    </div>
  )
}
