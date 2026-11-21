import pdfMake from "pdfmake/build/pdfmake"
import fonts from "pdfmake/build/vfs_fonts"
import type { Content, TableCell, TDocumentDefinitions } from "pdfmake/interfaces"
import { clientReportCharts } from "./client-report-charts"
import { reportInk, reportLine, reportMethod, reportMuted, reportNavy, reportTint, reportTitle, type ClientReport } from "./client-report"

pdfMake.addVirtualFileSystem(fonts)

// The table lays out to the longest unbroken token, including URLs and imported queries.
const wrap = (text: string) => text.replace(/\S{24}(?=\S)/gu, "$&\u200B")

export function clientReportPdf(report: ClientReport) {
  const content: Content[] = [
    { text: "AIRate", color: reportNavy, bold: true, fontSize: 14, margin: [0, 0, 0, 15] },
    { text: reportTitle, fontSize: 26, bold: true, margin: [0, 0, 0, 7] },
    { text: wrap(report.project), color: reportNavy, fontSize: 16, bold: true, margin: [0, 0, 0, 5] },
    { text: `${report.period}  ·  ${report.mode}`, style: "note" },
    ...(report.filterNotes ? [{ text: wrap(report.filterNotes), style: "note" }] : []),
    {
      margin: [0, 13, 0, 13],
      columns: report.metrics.map(({ label, value }) => ({
        stack: [{ text: value, fontSize: 23, color: reportNavy, bold: true }, { text: label, style: "note" }],
      })),
    },
    { image: clientReportCharts(report).url, width: 511 },
    ...(report.dates.length > 0 ? [{ text: `Даты отчёта: ${report.dates.join(", ")}`, style: "dates" }] : []),
    { text: "Динамика по запросам", style: "heading" },
    { text: report.changeSummary, style: "note" },
    ...(report.comparison ? report.tables.flatMap<Content>(table => [
      { text: table.title, style: "subheading", headlineLevel: 1 },
      table.rows.length ? {
        table: {
          widths: ["*", 65, 65, 54], headerRows: 1,
          body: [
            report.tableHeaders.map((text, index) => ({ text, alignment: index ? "right" : "left", fillColor: reportNavy, color: "#FFFFFF", bold: true })),
            ...table.rows.map((row, index) => row.map<TableCell>((text, column) => ({
              text: column ? text : wrap(text), alignment: column ? "right" : "left", fillColor: index % 2 ? reportTint : "#FFFFFF",
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
      heading: { fontSize: 17, bold: true, color: reportNavy, margin: [0, 14, 0, 4] },
      subheading: { fontSize: 12, bold: true, color: reportNavy, margin: [0, 12, 0, 4] },
    },
    footer: (page, pages) => ({ text: `AIRate  /  ${page} из ${pages}`, alignment: "right", margin: [42, 11, 42, 0], style: "note" }),
    pageBreakBefore: (node, positions) => node.headlineLevel === 1 && !positions.getFollowingNodesOnPage().length,
    content,
  }
  return pdfMake.createPdf(definition).getBlob()
}
