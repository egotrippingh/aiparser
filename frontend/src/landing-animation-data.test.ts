import { expect, it } from "vitest"
import desktop from "./assets/landing/airate-hero.json?raw"
import mobile from "./assets/landing/airate-hero-mobile.json?raw"

type Layer = { nm: string; ks: { o: { k: { t: number; s: number[] }[] } }; shapes: { ty: string; w?: { k: number }; ks?: { k: { s: unknown }[] } }[] }
type Composition = { w: number; h: number; fr: number; ip: number; op: number; layers: Layer[]; assets: { layers?: Layer[] }[] }

it.each([["desktop", desktop], ["mobile", mobile]])("keeps the approved 12s scan and seamless report reset in %s", (_name, json) => {
  const data: Composition = JSON.parse(json)
  expect((data.op - data.ip) / data.fr).toBe(12)
  const layers = [...data.layers, ...data.assets.flatMap(asset => asset.layers || [])]
  const checks = layers.filter(layer => layer.nm.startsWith("Галочка "))
  expect(layers.filter(layer => layer.nm === "Ячейка")).toHaveLength(15)
  expect(checks).toHaveLength(12)
  for (const [frame, count] of [[0, 0], [214, 3], [424, 9], [634, 12], [708, 0]]) {
    expect(checks.filter(layer => layer.ks.o.k.findLast(key => key.t <= frame)!.s[0] === 100)).toHaveLength(count)
  }
  const charts = layers.filter(layer => layer.nm.startsWith("График сервиса "))
  expect(charts).toHaveLength(5)
  for (const chart of charts) {
    expect(chart.shapes.find(shape => shape.ty === "st")?.w?.k).toBe(.75)
    const path = chart.shapes.find(shape => shape.ty === "sh")!.ks!.k
    expect(path.at(-1)!.s).toEqual(path[0].s)
  }
})
