import { reportInk, reportLine, reportMuted, reportNavy, reportPercent, reportTint, type ClientReport } from "./client-report"

export const chartSize = { width: 680, height: 238 }

export function clientReportCharts(report: ClientReport) {
  const canvas = document.createElement("canvas")
  canvas.width = chartSize.width * 2
  canvas.height = chartSize.height * 2
  const context = canvas.getContext("2d")
  if (!context) throw new Error("Не удалось построить диаграммы отчёта")
  const ctx = context
  ctx.scale(2, 2)
  ctx.textBaseline = "middle"

  function text(value: string, x: number, y: number, size = 13, color = reportInk, bold = false) {
    ctx.font = `${bold ? "bold " : ""}${size}px Arial, sans-serif`
    ctx.fillStyle = color
    ctx.fillText(value, x, y)
  }

  for (const x of [0, 344]) {
    ctx.beginPath()
    ctx.roundRect(x + 0.5, 0.5, 335, chartSize.height - 1, 12)
    ctx.fillStyle = reportTint
    ctx.fill()
    ctx.strokeStyle = reportLine
    ctx.stroke()
  }
  text("Результаты проверок", 18, 25, 17, reportNavy, true)
  text("По ИИ-системам", 362, 25, 17, reportNavy, true)

  const centerX = 81, centerY = 131, radius = 52
  function arc(start: number, end: number, color: string) {
    ctx.beginPath()
    ctx.arc(centerX, centerY, radius, start, end)
    ctx.lineWidth = 17
    ctx.strokeStyle = color
    ctx.stroke()
  }
  let angle = -Math.PI / 2
  arc(angle, angle + 2 * Math.PI, reportLine)
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
    text(String(value), 317, y, 13, reportInk, true)
    ctx.textAlign = "left"
  })
  ctx.textAlign = "center"
  text(String(report.total), centerX, centerY - 7, 23, reportNavy, true)
  text("всего", centerX, centerY + 14, 12, reportMuted)
  ctx.textAlign = "left"

  report.services.forEach(({ label, value, color }, index) => {
    const y = 58 + index * 32
    text(label, 362, y, 13)
    ctx.textAlign = "right"
    text(reportPercent(value), 662, y, 13, reportInk, true)
    ctx.textAlign = "left"
    ctx.fillStyle = reportLine
    ctx.fillRect(362, y + 11, 300, 5)
    if (value !== null) {
      ctx.fillStyle = color
      ctx.fillRect(362, y + 11, 3 * value, 5)
    }
  })

  return {
    url: canvas.toDataURL("image/png"),
    description: [
      ...report.outcomes.map(({ label, value }) => `${label} — ${value}`),
      ...report.services.map(({ label, value }) => `${label} — ${reportPercent(value)}`),
    ].join(". "),
  }
}
