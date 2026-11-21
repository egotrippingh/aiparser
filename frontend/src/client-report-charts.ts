import { reportAccent, reportChartLine, reportChartMuted, reportPercent, reportSurface, reportTint, type ClientReport } from "./client-report"

export const chartSize = { width: 680, height: 238 }

export async function clientReportCharts(report: ClientReport) {
  const canvas = document.createElement("canvas")
  canvas.width = chartSize.width * 2
  canvas.height = chartSize.height * 2
  const context = canvas.getContext("2d")
  if (!context) throw new Error("Не удалось построить диаграммы отчёта")
  const ctx = context
  ctx.scale(2, 2)
  ctx.textBaseline = "middle"
  const icons = await Promise.all(report.services.map(async ({ icon }) => {
    if (!icon) return null
    const image = new Image()
    image.src = icon
    return image.decode().then(() => image, () => null)
  }))

  function text(value: string, x: number, y: number, size = 13, color = reportTint, bold = false) {
    ctx.font = `${bold ? "bold " : ""}${size}px Arial, sans-serif`
    ctx.fillStyle = color
    ctx.fillText(value, x, y)
  }

  for (const x of [0, 344]) {
    ctx.beginPath()
    ctx.roundRect(x + 0.5, 0.5, 335, chartSize.height - 1, 16)
    ctx.fillStyle = reportSurface
    ctx.fill()
    ctx.strokeStyle = reportChartLine
    ctx.stroke()
  }
  text("Результаты проверок", 18, 25, 17, reportTint, true)
  text("По ИИ-системам", 362, 25, 17, reportTint, true)

  const centerX = 81, centerY = 131, radius = 52
  function arc(start: number, end: number, color: string) {
    ctx.beginPath()
    ctx.arc(centerX, centerY, radius, start, end)
    ctx.lineWidth = 17
    ctx.strokeStyle = color
    ctx.stroke()
  }
  let angle = -Math.PI / 2
  arc(angle, angle + 2 * Math.PI, reportChartLine)
  report.outcomes.forEach(({ label, value, color }, index) => {
    if (value > 0 && report.total) {
      const next = angle + value / report.total * 2 * Math.PI
      arc(angle, next, color)
      angle = next
    }
    const y = 77 + index * 27
    ctx.fillStyle = color
    ctx.fillRect(156, y - 5, 10, 10)
    text(label, 174, y)
    ctx.textAlign = "right"
    text(String(value), 317, y, 13, reportTint, true)
    ctx.textAlign = "left"
  })
  ctx.textAlign = "center"
  text(String(report.total), centerX, centerY - 7, 23, reportTint, true)
  text("всего", centerX, centerY + 14, 12, reportChartMuted)
  ctx.textAlign = "left"

  const plotLeft = 396, plotRight = 662, baseline = 191, plotHeight = 122
  ctx.textAlign = "right"
  ctx.lineWidth = 1
  ctx.strokeStyle = reportChartLine
  for (const step of [0, 25, 50, 75, 100]) {
    const y = baseline - plotHeight * step / 100 + 0.5
    ctx.beginPath()
    ctx.moveTo(plotLeft, y)
    ctx.lineTo(plotRight, y)
    ctx.stroke()
    text(String(step), plotLeft - 8, y, 11, reportChartMuted)
  }
  const spacing = (plotRight - plotLeft) / Math.max(1, report.services.length)
  const width = Math.min(44, spacing - 14)
  ctx.textAlign = "center"
  report.services.forEach(({ id, label, value }, index) => {
    const x = plotLeft + spacing * (index + 0.5)
    const height = plotHeight * (value ?? 0) / 100
    const top = baseline - height
    if (height > 0) {
      ctx.beginPath()
      ctx.roundRect(x - width / 2, top, width, height, Math.min(7, height / 2))
      ctx.fillStyle = reportAccent
      ctx.fill()
    }
    text(reportPercent(value), x, top - 11, 13, value === null ? reportChartMuted : reportTint, true)
    const icon = icons[index]
    if (icon) {
      const scale = 23 / Math.max(icon.naturalWidth, icon.naturalHeight)
      const w = icon.naturalWidth * scale, h = icon.naturalHeight * scale
      ctx.save()
      if (id === "chatgpt") ctx.filter = "brightness(0) invert(1)"
      ctx.drawImage(icon, x - w / 2, 214 - h / 2, w, h)
      ctx.restore()
    } else text(label.slice(0, 2), x, 214, 12, reportChartMuted, true)
  })

  return {
    url: canvas.toDataURL("image/png"),
    description: [
      ...report.outcomes.map(({ label, value }) => `${label} — ${value}`),
      ...report.services.map(({ label, value }) => `${label} — ${reportPercent(value)}`),
    ].join(". "),
  }
}
