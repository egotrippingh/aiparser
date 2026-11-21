import markUrl from "../design-system/aireyt-quote.svg?inline"
import wordmarkSvg from "../design-system/aireyt-wordmark.svg?raw"

const wordmarkUrl = `data:image/svg+xml,${encodeURIComponent(wordmarkSvg.replace("#F7F4EF", "#000000"))}`
export const reportLogoSize = { width: 130, height: 34 }

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
  context.drawImage(mark, 0, 4, 26, 26)
  const wordmarkWidth = 99
  const wordmarkHeight = wordmarkWidth * wordmark.naturalHeight / wordmark.naturalWidth
  context.drawImage(wordmark, 30, (reportLogoSize.height - wordmarkHeight) / 2, wordmarkWidth, wordmarkHeight)
  return canvas.toDataURL("image/png")
}
