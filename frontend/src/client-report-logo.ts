import markUrl from "../design-system/aireyt-quote.svg?inline"
import wordmarkUrl from "../design-system/aireyt-wordmark.svg?inline"
import { reportSurface } from "./client-report"

export const reportLogoSize = { width: 142, height: 38 }

export async function clientReportLogo() {
  const [mark, wordmark] = await Promise.all([markUrl, wordmarkUrl].map(async url => {
    const image = new Image()
    image.src = url
    await image.decode()
    return image
  }))
  const canvas = document.createElement("canvas")
  canvas.width = reportLogoSize.width * 3
  canvas.height = reportLogoSize.height * 3
  const context = canvas.getContext("2d")
  if (!context) throw new Error("Не удалось подготовить логотип отчёта")
  context.scale(3, 3)
  context.roundRect(0, 0, reportLogoSize.width, reportLogoSize.height, 8)
  context.fillStyle = reportSurface
  context.fill()
  context.drawImage(mark, 7, 6, 26, 26)
  const wordmarkWidth = 99
  const wordmarkHeight = wordmarkWidth * wordmark.naturalHeight / wordmark.naturalWidth
  context.drawImage(wordmark, 36, (reportLogoSize.height - wordmarkHeight) / 2, wordmarkWidth, wordmarkHeight)
  return canvas.toDataURL("image/png")
}
