import pdfMake from "pdfmake/build/pdfmake"
import fonts from "pdfmake/build/vfs_fonts"
import type { Content, TableCell, TDocumentDefinitions } from "pdfmake/interfaces"
import { clientReportCharts } from "./client-report-charts"
import { clientReportLogo, reportLogoSize } from "./client-report-logo"
import { reportChartMuted, reportHeading, reportInk, reportLine, reportMethod, reportMetricCard, reportMetricFontSize, reportMuted, reportSurface, reportTint, reportTitle, type ClientReport } from "./client-report"

pdfMake.addVirtualFileSystem(fonts)

// The table lays out to the longest unbroken token, including URLs and imported queries.
const wrap = (text: string, limit = 24) => text.replace(new RegExp(`\\S{${limit}}(?=\\S)`, "gu"), "$&\u200B")

export async function clientReportPdf(report: ClientReport) {
  const [charts, logo] = await Promise.all([clientReportCharts(report), clientReportLogo()])
  const width = reportMetricCard.width * 0.75
  const height = reportMetricCard.height * 0.75
  const content: Content[] = [
    { image: logo, width: reportLogoSize.width * 0.75, margin: [0, 0, 0, 15] },
    { text: reportTitle, fontSize: 26, bold: true, margin: [0, 0, 0, 7] },
    { text: wrap(report.project), color: reportHeading, fontSize: 16, bold: true, margin: [0, 0, 0, 5] },
    { text: `${report.period}  ·  ${report.mode}`, style: "note" },
    ...(report.filterNotes ? [{ text: wrap(report.filterNotes), style: "note" }] : []),
    {
      margin: [0, 13, 0, 13],
      columnGap: reportMetricCard.gap * 0.75,
      columns: report.metrics.map(({ label, value }) => ({
        width,
        stack: [
          { canvas: [{ type: "rect", x: 0, y: 0, w: width, h: height, r: reportMetricCard.radius * 0.75, color: reportSurface }] },
          {
            relativePosition: { x: 12, y: 9 - height },
            stack: [
              { text: value, fontSize: reportMetricFontSize(value), lineHeight: 1, color: reportTint, bold: true, margin: [0, 0, 0, 3] },
              { text: label, fontSize: 9, lineHeight: 1, color: reportChartMuted },
            ],
          },
        ],
      })),
    },
    { image: charts.url, width: 511 },
    ...(report.dates.length > 0 ? [{ text: `Даты отчёта: ${report.dates.join(", ")}`, style: "dates" }] : []),
    { text: "Динамика по запросам", style: "heading" },
    { text: report.changeSummary, style: "note" },
    ...(report.comparison ? report.tables.flatMap<Content>(table => [
      { text: table.title, style: "subheading", headlineLevel: 1 },
      table.rows.length ? {
        table: {
          widths: [85, "*", 62, 62, 58], headerRows: 1,
          body: [
            report.tableHeaders.map((text, column) => ({
              text, alignment: column < 2 ? "left" : "right", fillColor: reportSurface, color: reportTint, bold: true,
            })),
            ...table.rows.map((row, index) => row.map<TableCell>((text, column) => ({
              text: column < 2 ? wrap(text, column === 0 ? 8 : 18) : text,
              alignment: column < 2 ? "left" : "right",
              fillColor: index % 2 ? reportTint : "#FFFFFF",
              color: column === row.length - 1 ? table.color : reportInk,
              bold: column === row.length - 1,
            }))),
          ],
        },
        layout: { hLineWidth: () => 0.5, hLineColor: () => reportLine, vLineWidth: () => 0, paddingTop: () => 6, paddingBottom: () => 6 },
      } : { text: table.empty, style: "note" },
    ]) : []),
    { text: "Методика", style: "subheading", headlineLevel: 1 },
    { text: reportMethod, style: "note" },
  ]
  const definition: TDocumentDefinitions = {
    info: { title: reportTitle, author: "AIRate" },
    pageSize: "A4",
    pageMargins: [42, 37, 42, 42],
    defaultStyle: { font: "Roboto", fontSize: 10, color: reportInk, lineHeight: 1.15 },
    styles: {
      note: { fontSize: 9, color: reportMuted },
      dates: { fontSize: 9, color: reportMuted, margin: [0, 7, 0, 0] },
      heading: { fontSize: 17, bold: true, color: reportHeading, margin: [0, 14, 0, 4] },
      subheading: { fontSize: 12, bold: true, color: reportHeading, margin: [0, 12, 0, 4] },
    },
    footer: (page, pages) => ({ text: `AIRate  /  ${page} из ${pages}`, alignment: "right", margin: [42, 11, 42, 0], style: "note" }),
    pageBreakBefore: (node, positions) => node.headlineLevel === 1 && !positions.getFollowingNodesOnPage().length,
    content,
  }
  return pdfMake.createPdf(definition).getBlob()
}
