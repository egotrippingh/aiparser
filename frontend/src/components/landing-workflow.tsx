import { useEffect, useRef, useState } from "react"
import type { AnimationItem } from "lottie-web"

type Scene = "queries" | "services" | "report"
type SceneData = Record<Scene, object>

declare global {
  interface Window { airateWorkflowScenes?: SceneData }
}

let scenesPromise: Promise<SceneData> | undefined

function loadScenes() {
  scenesPromise ??= new Promise<SceneData>((resolve, reject) => {
    const script = document.createElement("script")
    script.src = "/assets/workflow/workflow-animations.js"
    script.onload = () => window.airateWorkflowScenes ? resolve(window.airateWorkflowScenes) : reject(new Error("Workflow scenes unavailable"))
    script.onerror = () => { script.remove(); scenesPromise = undefined; reject(new Error("Workflow scenes unavailable")) }
    document.head.append(script)
  })
  return scenesPromise
}

function WorkflowStep({ scene, title, text }: { scene: Scene; title: string; text: string }) {
  const host = useRef<HTMLSpanElement>(null)
  const item = useRef<AnimationItem | null>(null)
  const loading = useRef(false)
  const [reduced, setReduced] = useState(false)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)")
    const sync = () => {
      setReduced(media.matches)
      if (!media.matches) return
      item.current?.destroy()
      item.current = null
      setPlaying(false)
    }
    sync(); media.addEventListener("change", sync)
    return () => { media.removeEventListener("change", sync); item.current?.destroy() }
  }, [])

  async function play() {
    const container = host.current
    if (reduced || !container || loading.current) return
    if (item.current) { setPlaying(true); item.current.goToAndPlay(0, true); return }
    loading.current = true
    try {
      const [scenes, { default: lottie }] = await Promise.all([loadScenes(), import("lottie-web")])
      if (host.current !== container || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
      const animation = lottie.loadAnimation({ container, renderer: "svg", loop: false, autoplay: true, animationData: structuredClone(scenes[scene]) })
      item.current = animation
      animation.addEventListener("DOMLoaded", () => setPlaying(true))
      animation.addEventListener("complete", () => setPlaying(false))
      animation.addEventListener("data_failed", () => { setPlaying(false); animation.destroy(); item.current = null })
    } catch { setPlaying(false) } finally { loading.current = false }
  }

  return <li>
    <button type="button" className={`landing-workflow__art${playing ? " landing-workflow__art--playing" : ""}`} onPointerEnter={event => { if (event.pointerType === "mouse") void play() }} onClick={play} disabled={reduced} aria-label={`Показать анимацию: ${title}`}>
      <img src={`/assets/workflow/${scene}.svg`} width="340" height="192" alt="" loading="lazy"/><span ref={host} aria-hidden="true"/>
    </button>
    <h3>{title}</h3><p>{text}</p>
  </li>
}

export function LandingWorkflow() {
  return <section className="landing-workflow" id="how" aria-labelledby="how-title"><div className="container landing-section-grid"><h2 id="how-title">Как проходит проверка</h2>
    <ol className="landing-workflow__steps">
      <WorkflowStep scene="queries" title="Добавьте запросы" text="Укажите бренд и вопросы, которые задают покупатели."/>
      <WorkflowStep scene="services" title="Выберите сервисы" text="Запустите проверку или задайте расписание."/>
      <WorkflowStep scene="report" title="Откройте отчёт" text="Посмотрите ответы и дайте доступ команде или клиенту."/>
    </ol>
  </div></section>
}
