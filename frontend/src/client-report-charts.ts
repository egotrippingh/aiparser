import { reportAccent, reportChangeColors, reportChartDecrease, reportChartIncrease, reportChartLine, reportChartMuted, reportPercent, reportSigned, reportSurface, reportTint, type ClientReport } from "./client-report"

export const chartSize = { width: 680, height: 260 }
export const reportChangeBadgeSize = 14
const servicePanelLeft = 344

const changeMarks = {
  up: "M7 10V4 M4 7L7 4L10 7",
  equal: "M4 5.5H10 M4 8.5H10",
  down: "M7 4V10 M4 7L7 10L10 7",
}

function changeBadge(direction: keyof typeof changeMarks) {
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = reportChangeBadgeSize * 4
  const ctx = canvas.getContext("2d")
  if (!ctx) throw new Error("Не удалось построить индикатор динамики")
  ctx.scale(4, 4)
  ctx.fillStyle = reportChangeColors[direction]
  ctx.beginPath()
  ctx.arc(7, 7, 7, 0, Math.PI * 2)
  ctx.fill()
  ctx.lineWidth = 1.5
  ctx.lineCap = "round"
  ctx.lineJoin = "round"
  ctx.strokeStyle = reportSurface
  ctx.stroke(new Path2D(changeMarks[direction]))
  return canvas.toDataURL("image/png")
}

function drawIcon(ctx: CanvasRenderingContext2D, icon: HTMLImageElement, x: number, y: number, size: number) {
  const scale = size / Math.max(icon.naturalWidth, icon.naturalHeight)
  const w = icon.naturalWidth * scale, h = icon.naturalHeight * scale
  ctx.drawImage(icon, x - w / 2, y - h / 2, w, h)
}

export async function clientReportCharts(report: ClientReport) {
  const canvas = document.createElement("canvas")
  canvas.width = chartSize.width * 2
  canvas.height = chartSize.height * 2
  const context = canvas.getContext("2d")
  if (!context) throw new Error("Не удалось построить диаграммы отчёта")
  const ctx = context
  ctx.scale(2, 2)
  ctx.textBaseline = "middle"
  const urls = new Map([...report.services, ...report.serviceTables].map(({ id, icon }) => [id, icon]))
  const icons = new Map(await Promise.all([...urls].map(async ([id, url]) => {
    if (!url) return [id, null] as const
    const image = new Image()
    image.src = url
    return [id, await image.decode().then(() => image, () => null)] as const
  })))

  function text(value: string, x: number, y: number, size = 13, color = reportTint, bold = false) {
    ctx.font = `${bold ? "bold " : ""}${size}px Arial, sans-serif`
    ctx.fillStyle = color
    ctx.fillText(value, x, y)
  }

  function barSegment(left: number, top: number, width: number, height: number, color: string, dashed = false) {
    const stroke = dashed ? Math.min(1.5, height / 2) : 0
    ctx.beginPath()
    ctx.roundRect(left + stroke / 2, top + stroke / 2, width - stroke, height - stroke, Math.min(7, (height - stroke) / 2))
    if (dashed) {
      ctx.save()
      ctx.fillStyle = reportSurface
      ctx.fill()
      ctx.strokeStyle = color
      ctx.lineWidth = stroke
      ctx.lineCap = "round"
      ctx.setLineDash([4, 4])
      ctx.stroke()
      ctx.restore()
    } else {
      ctx.fillStyle = color
      ctx.fill()
    }
  }

  for (const x of [0, servicePanelLeft]) {
    ctx.beginPath()
    ctx.roundRect(x + 0.5, 0.5, 335, chartSize.height - 1, 16)
    ctx.fillStyle = reportSurface
    ctx.fill()
    ctx.strokeStyle = reportChartLine
    ctx.stroke()
  }
  text("Результаты проверок", 18, 25, 17, reportTint, true)
  text("По ИИ-системам", 362, 25, 17, reportTint, true)
  if (report.comparison) {
    text(`${report.comparison[0]} → ${report.comparison[1]} · Изм., %`, 362, 45, 11, reportChartMuted)
  }

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

  const serviceCenter = (servicePanelLeft + chartSize.width) / 2
  const plotLeft = serviceCenter - 133, plotRight = serviceCenter + 133, baseline = 191
  const plotHeight = report.comparison ? 109 : 122
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
  report.services.forEach(({ id, label, value, previous }, index) => {
    const x = plotLeft + spacing * (index + 0.5)
    const current = value ?? 0, reference = previous ?? current
    const height = plotHeight * Math.max(current, reference) / 100
    const capHeight = plotHeight * Math.abs(current - reference) / 100
    const baseHeight = plotHeight * Math.min(current, reference) / 100
    const gap = capHeight > 0 ? Math.min(3, baseHeight / 2) : 0
    const top = baseline - height
    const delta = current - reference
    const capColor = delta > 0 ? reportChartIncrease : reportChartDecrease
    const inside = capHeight >= 13
    const left = x - width / 2
    if (baseHeight > 0) {
      const baseTop = baseline - baseHeight + gap
      const base = baseHeight - gap
      barSegment(left, baseTop, width, base, reportAccent)
      if (delta > 0) {
        const capRadius = Math.min(7, capHeight / 2)
        const baseRadius = Math.min(7, base / 2)
        ctx.fillRect(left, baseTop - gap - capRadius, width, capRadius + gap + baseRadius)
      }
    }
    if (capHeight > 0) barSegment(left, top, width, capHeight, capColor, delta < 0)
    if (delta) {
      text(`${reportSigned(delta)}%`, x, inside ? top + capHeight / 2 : top - 10,
        inside ? 7 : 11, delta < 0 ? reportChartDecrease : "#FFFFFF", !inside)
    }
    const icon = icons.get(id)
    if (icon) {
      ctx.save()
      if (id === "chatgpt") ctx.filter = "brightness(0) invert(1)"
      drawIcon(ctx, icon, x, 214, 23)
      ctx.restore()
    } else text(label.slice(0, 2), x, 214, 12, reportChartMuted, true)
    text(reportPercent(value), x, 240, 16, value === null ? reportChartMuted : reportTint, true)
  })

  const serviceIcons = new Map<string, string>()
  const iconCanvas = document.createElement("canvas")
  iconCanvas.width = iconCanvas.height = 64
  const iconContext = iconCanvas.getContext("2d")
  if (iconContext) for (const [id, icon] of icons) {
    if (!icon) continue
    iconContext.clearRect(0, 0, 64, 64)
    drawIcon(iconContext, icon, 32, 32, 62)
    serviceIcons.set(id, iconCanvas.toDataURL("image/png"))
  }
  const badges = { up: changeBadge("up"), equal: changeBadge("equal"), down: changeBadge("down") }
  return {
    serviceIcons,
    badges,
    changes: report.changeCards.map(({ label, value, share, direction }) => ({
      label: `${label} (${share})`, value, badge: badges[direction],
    })),
    url: canvas.toDataURL("image/png"),
    description: [
      ...report.outcomes.map(({ label, value }) => `${label} — ${value}`),
      ...(report.comparison ? [`Сравнение по ИИ-системам ${report.comparison.join(" → ")}`] : []),
      ...report.services.map(({ label, value, previous }) => value !== null && previous !== null
        ? `${label} — ${reportPercent(previous)} → ${reportPercent(value)} (${reportSigned(value - previous)}%)`
        : `${label} — ${reportPercent(value)}`),
    ].join(". "),
  }
}
