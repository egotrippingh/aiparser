import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { mountHeroAnimation } from "./landing-hero-animation"

const loadAnimation = vi.hoisted(() => vi.fn())
vi.mock("lottie-web", () => ({ default: { loadAnimation } }))

class Media extends EventTarget {
  matches = false
  change(value: boolean) { this.matches = value; this.dispatchEvent(new Event("change")) }
}

let mobile: Media, reduced: Media
let dispose: (() => void) | undefined
let events: Record<string, () => void>
const item = { destroy: vi.fn(), addEventListener: vi.fn((name: string, listener: () => void) => { events[name] = listener }) }

beforeEach(() => {
  vi.clearAllMocks()
  mobile = new Media()
  reduced = new Media()
  events = {}
  vi.stubGlobal("window", { matchMedia: (query: string) => query.includes("prefers-reduced-motion") ? reduced : mobile })
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ w: 1000 }) }))
  loadAnimation.mockReturnValue(item)
})
afterEach(() => { dispose?.(); dispose = undefined; vi.unstubAllGlobals() })

it("loads the selected composition and exposes it only after the renderer is ready", async () => {
  const ready = vi.fn()
  dispose = mountHeroAnimation({} as HTMLElement, ready)
  await vi.waitFor(() => expect(loadAnimation).toHaveBeenCalledOnce())
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("airate-hero.json"), expect.anything())
  expect(loadAnimation).toHaveBeenCalledWith(expect.objectContaining({ autoplay: false, renderer: "svg", loop: true }))
  expect(ready).toHaveBeenLastCalledWith(null)
  events.DOMLoaded()
  expect(ready).toHaveBeenLastCalledWith(item)
  mobile.change(true)
  await vi.waitFor(() => expect(loadAnimation).toHaveBeenCalledTimes(2))
  expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining("airate-hero-mobile.json"), expect.anything())
  expect(item.destroy).toHaveBeenCalledOnce()
})

it("keeps the static frame for reduced motion and stops when the preference changes", async () => {
  reduced.matches = true
  dispose = mountHeroAnimation({} as HTMLElement, vi.fn())
  expect(fetch).not.toHaveBeenCalled()
  reduced.change(false)
  await vi.waitFor(() => expect(loadAnimation).toHaveBeenCalledOnce())
  reduced.change(true)
  expect(item.destroy).toHaveBeenCalledOnce()
  expect(fetch).toHaveBeenCalledOnce()
})

it("discards late responses and removes listeners after unmount", async () => {
  let resolveData!: (value: object) => void
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: () => new Promise(resolve => { resolveData = resolve }) } as Response)
  const ready = vi.fn()
  dispose = mountHeroAnimation({} as HTMLElement, ready)
  await vi.waitFor(() => expect(resolveData).toBeTypeOf("function"))
  dispose()
  dispose = undefined
  const calls = ready.mock.calls.length
  resolveData({ w: 1000 })
  await new Promise(resolve => setTimeout(resolve, 0))
  mobile.change(true)
  expect(loadAnimation).not.toHaveBeenCalled()
  expect(ready).toHaveBeenCalledTimes(calls)
  expect(fetch).toHaveBeenCalledOnce()
})

it("leaves the still visible after HTTP or renderer failure", async () => {
  const ready = vi.fn()
  vi.mocked(fetch).mockResolvedValue({ ok: false } as Response)
  dispose = mountHeroAnimation({} as HTMLElement, ready)
  await vi.waitFor(() => expect(ready).toHaveBeenCalledTimes(2))
  expect(loadAnimation).not.toHaveBeenCalled()
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({}) } as Response)
  mobile.change(true)
  await vi.waitFor(() => expect(loadAnimation).toHaveBeenCalledOnce())
  events.DOMLoaded()
  events.data_failed()
  expect(ready).toHaveBeenLastCalledWith(null)
  expect(item.destroy).toHaveBeenCalledOnce()
})
