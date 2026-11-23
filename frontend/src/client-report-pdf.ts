import pdfMake from "pdfmake/build/pdfmake"
import fonts from "pdfmake/build/vfs_fonts"
import type { Content, TableCell, TDocumentDefinitions } from "pdfmake/interfaces"
import { clientReportCharts, reportChangeBadgeSize } from "./client-report-charts"
import { clientReportLogo, reportLogoSize } from "./client-report-logo"
import { reportChartMuted, reportHeading, reportInk, reportLine, reportMethod, reportMetricCard, reportMetricFontSize, reportMuted, reportSurface, reportTint, reportTitle, serviceTableHeaders, type ClientReport, type ReportMetric, type ServiceVisibility } from "./client-report"

pdfMake.addVirtualFileSystem(fonts)

// The table lays out to the longest unbroken token, including URLs and imported queries.
const wrap = (text: string, limit = 24) => text.replace(new RegExp(`\\S{${limit}}(?=\\S)`, "gu"), "$&\u200B")

export async function clientReportPdf(report: ClientReport) {
  const [charts, logo] = await Promise.all([clientReportCharts(report), clientReportLogo()])
  const { changes, badges, serviceIcons } = charts
  const width = reportMetricCard.width * 0.75
  const height = reportMetricCard.height * 0.75
  const cards = (metrics: ReportMetric[], margin: [number, number, number, number]): Content => ({
    margin,
    columnGap: reportMetricCard.gap * 0.75,
    columns: metrics.map(({ label, value, badge }) => {
      const number = { text: value, fontSize: reportMetricFontSize(value), lineHeight: 1, color: reportTint, bold: true }
      const caption = { text: label, fontSize: 9, lineHeight: 1, color: reportChartMuted }
      return {
        width,
        stack: [
          { canvas: [{ type: "rect", x: 0, y: 0, w: width, h: height, r: reportMetricCard.radius * 0.75, color: reportSurface }] },
          {
            relativePosition: { x: 12, y: (badge ? 11 : 9) - height },
            stack: badge ? [
              { columns: [{ image: badge, width: reportChangeBadgeSize * 0.75 }, caption], columnGap: 5, margin: [0, 0, 0, 3] },
              number,
            ] : [{ ...number, margin: [0, 0, 0, 3] }, caption],
          },
        ],
      }
    }),
  })
  const tableContent = (headers: string[], rows: readonly (readonly (string | ServiceVisibility)[])[],
    color?: string, service?: { id: string; label: string }): Content => {
    const alignment = (column: number) => color && column >= 2 ? "right" : "left"
    const serviceHeading: TableCell[] = service ? [{
      colSpan: headers.length, border: [false, false, false, false], margin: [-4, 0, 0, 0],
      columns: [
        ...(serviceIcons.has(service.id) ? [{ image: service.id, width: 14 }] : []),
        { text: service.label },
      ],
      columnGap: 5, fontSize: 12, bold: true, color: reportHeading,
    }, {}, {}] : []
    return {
      margin: service ? [0, 8, 0, 0] : undefined,
      table: {
        widths: color ? [85, "*", 62, 62, 58] : [85, "*", 108],
        headerRows: service ? 2 : 1, keepWithHeaderRows: 1,
        body: [
          ...(service ? [serviceHeading] : []),
          headers.map((text, column) => ({ text, alignment: alignment(column), fillColor: reportSurface, color: reportTint, bold: true })),
          ...rows.map((row, index) => row.map<TableCell>((cell, column) => {
            const fillColor = index % 2 ? reportTint : "#FFFFFF"
            if (typeof cell !== "string") return cell.direction ? {
              columns: [{ image: cell.direction, width: reportChangeBadgeSize * 0.75 }, { text: cell.text }],
              columnGap: 5, fillColor,
            } : { text: cell.text, fillColor, color: reportMuted }
            const delta = color && column === row.length - 1
            return {
              text: column < 2 ? wrap(cell, column === 0 ? 8 : 18) : cell,
              alignment: alignment(column), fillColor, color: delta ? color : reportInk, bold: !!delta,
            }
          })),
        ],
      },
      layout: {
        hLineWidth: index => service && index < 2 ? 0 : 0.5,
        hLineColor: () => reportLine, vLineWidth: () => 0, paddingTop: () => 6, paddingBottom: () => 6,
      },
    }
  }
  const content: Content[] = [
    { image: logo, width: reportLogoSize.width * 0.75, margin: [0, 0, 0, 15] },
    { text: reportTitle, fontSize: 26, bold: true, margin: [0, 0, 0, 7] },
    { text: wrap(report.project), color: reportHeading, fontSize: 16, bold: true, margin: [0, 0, 0, 5] },
    { text: `${report.period}  ·  ${report.mode}`, style: "note" },
    ...(report.filterNotes ? [{ text: wrap(report.filterNotes), style: "note" }] : []),
    cards(report.metrics, [0, 13, 0, 13]),
    { image: charts.url, width: 511 },
    ...(report.dates.length > 0 ? [{ text: `Даты отчёта: ${report.dates.join(", ")}`, style: "dates" }] : []),
    { text: "Динамика по запросам", style: "heading", headlineLevel: 1 },
    ...(changes.length ? [cards(changes, [0, 2, 0, 5])] : []),
    ...(report.changeNote ? [{ text: report.changeNote, style: "note" }] : []),
    ...(report.comparison ? report.tables.flatMap<Content>(table => [
      { text: table.title, style: "subheading", headlineLevel: 1 },
      table.rows.length ? tableContent(report.tableHeaders, table.rows, table.color) : { text: table.empty, style: "note" },
    ]) : []),
    { unbreakable: true, stack: [
      { text: "Методика", style: "subheading" },
      { text: reportMethod, style: "note" },
    ] },
    { text: "Запросы по ИИ-системам", style: "heading", headlineLevel: 1 },
    ...(report.detailDates ? [{ text: report.detailDates, style: "note" }] : []),
    ...report.serviceTables.map(({ id, label, rows }) => tableContent(serviceTableHeaders,
      rows.length ? rows : [["", "Нет запросов.", ""]], undefined, { id, label })),
  ]
  const definition: TDocumentDefinitions = {
    info: { title: reportTitle, author: "AIRate" },
    pageSize: "A4",
    pageMargins: [42, 37, 42, 42],
    images: { ...badges, ...Object.fromEntries(serviceIcons) },
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
