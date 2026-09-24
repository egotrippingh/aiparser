import { useEffect, useRef } from "react"
import type { AnimationItem } from "lottie-web"

const staticValue = (value: number | number[]) => ({ a: 0, k: value })
const position = {
  a: 1,
  k: [
    { t: 0, s: [80, 75, 0], e: [1120, 75, 0], o: { x: 0.45, y: 0 }, i: { x: 0.55, y: 1 } },
    { t: 119, s: [1120, 75, 0] },
  ],
}

function dotLayer(name: string, size: number, color: number[], opacity: number, index: number) {
  return {
    ddd: 0, ind: index, ty: 4, nm: name, sr: 1,
    ks: { o: staticValue(opacity), r: staticValue(0), p: position, a: staticValue([0, 0, 0]), s: staticValue([100, 100, 100]) },
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
const chainAnimation = {
  v: "5.7.1", fr: 30, ip: 0, op: 120, w: 1200, h: 150, nm: "AI Mentions process signal", ddd: 0, assets: [],
  layers: [
    dotLayer("Signal", 21, [0.14, 0.35, 0.87, 1], 100, 1),
    dotLayer("Signal halo", 47, [0.14, 0.35, 0.87, 1], 17, 2),
  ],
}

export function ProcessFlow() {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    let active = true
    let item: AnimationItem | undefined
    import("lottie-web/build/player/lottie_light").then(({ default: lottie }) => {
      if (!active || !ref.current) return
      item = lottie.loadAnimation({
        container: ref.current,
        renderer: "svg",
        loop: true,
        autoplay: true,
        animationData: chainAnimation,
        rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
      })
    })
    return () => { active = false; item?.destroy() }
  }, [])

  return (
    <div className="process-flow" aria-hidden="true">
      <div className="process-flow-line" />
      <div className="process-flow-nodes"><span /><span /><span /></div>
      <div className="process-flow-lottie" ref={ref} />
    </div>
  )
}
