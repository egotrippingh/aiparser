import {
  AlignmentType, BorderStyle, Document, Footer, HeadingLevel, ImageRun, Packer, PageNumber,
  Paragraph, Table, TableCell, TableLayoutType, TableRow, TextRun, WidthType, type IParagraphOptions,
} from "docx"
import { chartSize, clientReportCharts } from "./client-report-charts"
import { reportInk, reportLine, reportMethod, reportMuted, reportHeading, reportTint, reportTitle, reportTableHeading, type ClientReport } from "./client-report"

const headingColor = reportHeading.slice(1), ink = reportInk.slice(1), muted = reportMuted.slice(1)
const widths = [1960, 3658, 1600, 1600, 1400]
const pageWidth = widths.reduce((total, width) => total + width, 0)
const border = { style: BorderStyle.SINGLE, size: 4, color: reportLine.slice(1) }
const noBorder = { style: BorderStyle.NONE }
const hint = (text: string) => new Paragraph({
  spacing: { after: 75 },
  children: [new TextRun({ text, size: 18, color: muted })],
})
const heading = (text: string, level: typeof HeadingLevel.HEADING_1 | typeof HeadingLevel.HEADING_2) =>
  new Paragraph({ heading: level, spacing: { before: 240, after: 75 }, keepNext: true, children: [new TextRun({ text, color: headingColor, bold: true })] })

function changeTable(headers: string[], { rows, color }: ClientReport["tables"][number]) {
  return new Table({
    columnWidths: widths, width: { type: WidthType.DXA, size: pageWidth }, layout: TableLayoutType.FIXED,
    borders: { top: border, bottom: border, insideHorizontal: border, left: noBorder, right: noBorder, insideVertical: noBorder },
    margins: { top: 85, bottom: 85, left: 110, right: 110 },
    rows: [headers, ...rows].map((row, index) => new TableRow({
      tableHeader: index === 0,
      children: row.map((text, column) => new TableCell({
        width: { size: widths[column], type: WidthType.DXA },
        shading: { fill: index === 0 ? reportTableHeading.slice(1) : index % 2 === 0 ? reportTint.slice(1) : "FFFFFF" },
        children: [new Paragraph({
          alignment: column < 2 ? AlignmentType.LEFT : AlignmentType.RIGHT,
          children: [new TextRun({
            text, size: 19, color: index > 0 && column === row.length - 1 ? color.slice(1) : ink,
            bold: index === 0 || column === row.length - 1,
          })],
        })],
      })),
    })),
  })
}

export async function clientReportDocx(report: ClientReport) {
  const charts = await clientReportCharts(report)
  const metric = (text: string, size: number, bold: boolean, color: string, options: IParagraphOptions) =>
    new Paragraph({ ...options, children: [new TextRun({ text, size, bold, color })] })
  const metrics = new Table({
    width: { type: WidthType.PERCENTAGE, size: 100 },
    borders: Object.fromEntries(["top", "bottom", "left", "right", "insideHorizontal", "insideVertical"]
      .map(side => [side, noBorder])),
    margins: { top: 90, bottom: 155, right: 85 },
    rows: [new TableRow({ cantSplit: true, children: report.metrics.map(({ label, value }) => new TableCell({
      width: { type: WidthType.DXA, size: Math.floor(pageWidth / 3) },
      children: [metric(value, 44, true, headingColor, {}), metric(label, 18, false, muted, {})],
    })) })],
  })
  const doc = new Document({
    title: reportTitle, creator: "AIRate",
    styles: { default: { document: { run: { font: "Arial", size: 20, color: ink } } } },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 }, margin: {
        top: 750, bottom: 850, left: 844, right: 844, footer: 438,
      } } },
      footers: { default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [new TextRun({ color: muted, size: 18, children: ["AIRate  /  ", PageNumber.CURRENT, " из ", PageNumber.TOTAL_PAGES] })],
      })] }) },
      children: [
        metric("AIRate", 28, true, headingColor, { spacing: { after: 235 } }),
        metric(reportTitle, 48, true, "000000", { heading: HeadingLevel.TITLE, spacing: { after: 100 }, keepNext: true }),
        metric(report.project, 32, true, headingColor, { spacing: { after: 80 } }),
        hint(`${report.period}  ·  ${report.mode}`),
        ...(report.filterNotes ? [hint(report.filterNotes)] : []),
        metrics,
        new Paragraph({ spacing: { after: 100 }, children: [new ImageRun({
          type: "png", data: charts.url, transformation: chartSize,
          altText: { name: "Диаграммы", title: "Результаты проверок и упоминаемость по ИИ-системам", description: charts.description },
        })] }),
        ...(report.dates.length ? [hint(`Даты отчёта: ${report.dates.join(", ")}`)] : []),
        heading("Динамика по запросам", HeadingLevel.HEADING_1),
        hint(report.changeSummary),
        ...(report.comparison ? report.tables.flatMap(table => [
          heading(table.title, HeadingLevel.HEADING_2),
          table.rows.length ? changeTable(report.tableHeaders, table) : hint(table.empty),
        ]) : []),
        heading("Методика", HeadingLevel.HEADING_2),
        hint(reportMethod),
      ],
    }],
  })
  return Packer.toBlob(doc)
}
