function prepareTyping(code: HTMLElement, delay: number, duration: number) {
  const length = code.textContent.length
  const visual = code.cloneNode(true) as HTMLElement
  visual.removeAttribute("id")
  visual.setAttribute("aria-hidden", "true")
  visual.classList.add("api-panel__animated-code")
  const walker = document.createTreeWalker(visual, NodeFilter.SHOW_TEXT)
  const parts: [Text, string][] = []
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node as Text
    parts.push([text, text.data])
    text.data = ""
  }
  code.classList.add("api-panel__accessible-code")
  code.after(visual)

  function reveal() {
    visual.remove()
    code.classList.remove("api-panel__accessible-code")
  }

  return {
    reveal,
    render(elapsed: number) {
      if (elapsed < delay || !visual.isConnected) return
      if (elapsed >= delay + duration) return reveal()
      visual.classList.add("api-panel--typing")
      let remaining = Math.floor((elapsed - delay) * length / duration)
      for (const [node, text] of parts) {
        node.data = text.slice(0, Math.max(0, remaining))
        remaining -= text.length
      }
    },
  }
}

export function mountApiDemo(root: ParentNode) {
  const button = root.querySelector<HTMLButtonElement>("#copy-api")
  const command = root.querySelector<HTMLElement>("#api-request")
  const response = root.querySelector<HTMLElement>("#api-response")
  const status = root.querySelector<HTMLElement>("#api-demo__status")
  const commandPanel = command?.closest("pre")
  const responsePanel = response?.closest("pre")
  if (!button || !command || !response || !status || !commandPanel || !responsePanel) return
  const fullCommand = command.textContent
  const reduced = matchMedia("(prefers-reduced-motion: reduce)")
  const listeners = new AbortController()
  const { signal } = listeners
  let observer: IntersectionObserver | undefined
  let finishTyping: (() => void) | undefined

  if (!reduced.matches && "IntersectionObserver" in window) {
    const commandDuration = 2800, responseDuration = 1450
    observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return
      observer?.disconnect()
      if (reduced.matches || signal.aborted) return
      const stages = [
        prepareTyping(command, 0, commandDuration),
        prepareTyping(response, commandDuration, responseDuration),
      ]
      const start = performance.now()
      let frame = 0
      const finish = () => {
        cancelAnimationFrame(frame)
        for (const stage of stages) stage.reveal()
        reduced.removeEventListener("change", finish)
        finishTyping = undefined
      }
      finishTyping = finish
      reduced.addEventListener("change", finish, { signal })
      function render(now: number) {
        const elapsed = now - start
        if (elapsed >= commandDuration + responseDuration) return finish()
        for (const stage of stages) stage.render(elapsed)
        frame = requestAnimationFrame(render)
      }
      render(start)
    }, { threshold: 0.2 })
    observer.observe(commandPanel)
    for (const panel of [commandPanel, responsePanel]) {
      panel.addEventListener("focus", () => {
        observer?.disconnect()
        finishTyping?.()
      }, { signal })
    }
  }

  if (navigator.clipboard?.writeText) {
    button.hidden = false
    button.addEventListener("click", async () => {
      finishTyping?.()
      try {
        await navigator.clipboard.writeText(fullCommand)
        status.textContent = "Команда скопирована."
      } catch {
        status.textContent = "Не удалось скопировать. Выделите команду и скопируйте её вручную."
      }
    }, { signal })
  }
  return () => {
    observer?.disconnect()
    finishTyping?.()
    listeners.abort()
    button.hidden = true
  }
}

if (typeof document !== "undefined" && document.body.classList.contains("landing-page")) {
  const dispose = mountApiDemo(document)
  import.meta.hot?.dispose(() => dispose?.())
}
