import { useEffect, useRef, useState } from "react"
import type { AnimationItem } from "lottie-web"
import desktopAnimation from "../../design-system/landing/hero-lavender-desktop.json?url"
import mobileAnimation from "../../design-system/landing/hero-lavender-mobile.json?url"

export function mountHeroAnimation(container: HTMLElement, onReady: (item: AnimationItem | null) => void) {
  const mobile = window.matchMedia("(max-aspect-ratio: 1/1)")
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)")
  let generation = 0
  let controller: AbortController | undefined
  let item: AnimationItem | null = null
  const render = async () => {
    const current = ++generation
    controller?.abort()
    item?.destroy()
    item = null
    onReady(null)
    if (reduced.matches) return
    controller = new AbortController()
    try {
      const [response, { default: lottie }] = await Promise.all([
        fetch(mobile.matches ? mobileAnimation : desktopAnimation, { signal: controller.signal }),
        import("lottie-web"),
      ])
      if (!response.ok) throw new Error("Hero animation unavailable")
      const data = await response.json()
      if (current !== generation) return
      item = lottie.loadAnimation({
        container, renderer: "svg", loop: true, autoplay: false,
        animationData: data,
      })
      item.addEventListener("DOMLoaded", () => { if (current === generation) onReady(item) })
      item.addEventListener("data_failed", () => {
        if (current !== generation) return
        item?.destroy()
        item = null
        onReady(null)
      })
    } catch {
      // The exported first frame remains visible when loading fails.
      if (current === generation) onReady(null)
    }
  }
  void render()
  mobile.addEventListener("change", render)
  reduced.addEventListener("change", render)
  return () => {
    generation++
    controller?.abort()
    mobile.removeEventListener("change", render)
    reduced.removeEventListener("change", render)
    item?.destroy()
  }
}

export function LandingHeroAnimation() {
  const container = useRef<HTMLDivElement>(null)
  const [animation, setAnimation] = useState<AnimationItem | null>(null)
  useEffect(() => {
    if (container.current) return mountHeroAnimation(container.current, setAnimation)
  }, [])

  useEffect(() => {
    const sync = () => {
      if (document.hidden) animation?.pause()
      else animation?.play()
    }
    sync()
    document.addEventListener("visibilitychange", sync)
    return () => document.removeEventListener("visibilitychange", sync)
  }, [animation])

  return <div className="home-hero__stage">
    <div className={`home-hero__art${animation ? " home-hero__art--ready" : ""}`} role="img" aria-label="Сканирование Google, Яндекса, Gemini, ChatGPT и Perplexity: данные поступают в отчёт, графики и упоминания обновляются.">
      <picture className="home-hero__still" aria-hidden="true">
        <source media="(max-aspect-ratio: 1/1)" srcSet="/assets/landing/hero-lavender-mobile.webp"/>
        <img src="/assets/landing/hero-lavender-desktop.webp" alt="" width="1000" height="400" fetchPriority="high"/>
      </picture>
      <div id="hero-lottie" ref={container} aria-hidden="true"/>
    </div>
  </div>
}
