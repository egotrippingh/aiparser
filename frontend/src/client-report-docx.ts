import {
  AlignmentType, BorderStyle, Document, Footer, HeadingLevel, ImageRun, LineRuleType, Packer, PageNumber,
  Paragraph, Table, TableCell, TableLayoutType, TableRow, TextRun, WidthType, type IParagraphOptions,
} from "docx"
import { ShapeGroupRun, type IShapeGroupChildOptions } from "docx/shapes"
import { chartSize, clientReportCharts, reportChangeBadgeSize } from "./client-report-charts"
import { clientReportLogo, reportLogoSize } from "./client-report-logo"
import { reportChartMuted, reportHeading, reportInk, reportLine, reportMethod, reportMetricCard, reportMetricFontSize, reportMuted, reportSurface, reportTint, reportTitle, serviceTableHeaders, type ClientReport, type ReportMetric, type ServiceVisibility } from "./client-report"

const headingColor = reportHeading.slice(1), ink = reportInk.slice(1), muted = reportMuted.slice(1)
const pageWidth = 10218
const border = { style: BorderStyle.SINGLE, size: 4, color: reportLine.slice(1) }
const noBorder = { style: BorderStyle.NONE }
const hint = (text: string, keepNext = false) => new Paragraph({
  spacing: { after: 75 },
  keepNext,
  children: [new TextRun({ text, size: 18, color: muted })],
})
const inlineIcon = (data: string, size: number) =>
  new ImageRun({ type: "png", data, transformation: { width: size, height: size } })
const heading = (text: string, level: typeof HeadingLevel.HEADING_1 | typeof HeadingLevel.HEADING_2, icon?: string) =>
  new Paragraph({
    heading: level, spacing: { before: 240, after: 75 }, keepNext: true,
    children: [...(icon ? [inlineIcon(icon, 18)] : []), new TextRun({ text: icon ? `  ${text}` : text, color: headingColor, bold: true })],
  })

function reportTable(headers: string[], rows: readonly (readonly (string | ServiceVisibility)[])[],
  badges: Awaited<ReturnType<typeof clientReportCharts>>["badges"], color?: string, service?: { label: string; icon?: string }) {
  const widths = color ? [1960, 3658, 1600, 1600, 1400] : [1960, 6108, 2150]
  const serviceHeading = service ? [new TableRow({
    tableHeader: true,
    children: [new TableCell({
      columnSpan: headers.length,
      margins: { top: 0, bottom: 0, left: 0, right: 0 },
      borders: { top: noBorder, bottom: noBorder },
      children: [heading(service.label, HeadingLevel.HEADING_2, service.icon)],
    })],
  })] : []
  return new Table({
    columnWidths: widths, width: { type: WidthType.DXA, size: pageWidth }, layout: TableLayoutType.FIXED,
    borders: { top: service ? noBorder : border, bottom: border, insideHorizontal: border, left: noBorder, right: noBorder, insideVertical: noBorder },
    margins: { top: 85, bottom: 85, left: 110, right: 110 },
    rows: [...serviceHeading, ...[headers, ...rows].map((row, index) => new TableRow({
      tableHeader: index === 0,
      children: row.map((cell, column) => new TableCell({
        width: { size: widths[column], type: WidthType.DXA },
        shading: { fill: index === 0 ? reportSurface.slice(1) : index % 2 === 0 ? reportTint.slice(1) : "FFFFFF" },
        children: [new Paragraph({
          alignment: color && column >= 2 ? AlignmentType.RIGHT : AlignmentType.LEFT,
          keepNext: index === 0,
          children: typeof cell === "string" ? [new TextRun({
            text: cell, size: 19, color: index === 0 ? reportTint.slice(1) : color && column === row.length - 1 ? color.slice(1) : ink,
            bold: index === 0 || !!color && column === row.length - 1,
          })] : [
            ...(cell.direction ? [inlineIcon(badges[cell.direction], reportChangeBadgeSize)] : []),
            new TextRun({ text: cell.direction ? `  ${cell.text}` : cell.text, size: 19, color: cell.direction ? ink : muted }),
          ],
        })],
      })),
    }))],
  })
}

export async function clientReportDocx(report: ClientReport) {
  const [charts, logo] = await Promise.all([clientReportCharts(report), clientReportLogo()])
  const { changes, serviceIcons, badges } = charts
  const metric = (text: string, size: number, bold: boolean, color: string, options: IParagraphOptions) =>
    new Paragraph({ ...options, children: [new TextRun({ text, size, bold, color })] })
  const { width, height, gap, radius } = reportMetricCard
  const cards = (metrics: ReportMetric[], name: string, spacing: IParagraphOptions["spacing"]) => new Paragraph({
    spacing,
    children: [new ShapeGroupRun({
      altText: {
        name,
        description: metrics.map(({ label, value }) => `${label} — ${value}`).join(". "),
      },
      children: metrics.flatMap<IShapeGroupChildOptions>(({ label, value, badge }, index) => {
        const left = index * (width + gap)
        const number = metric(value, reportMetricFontSize(value) * 2, true, reportTint.slice(1), { spacing: { after: badge ? 0 : 55 } })
        const caption = metric(label, 18, false, reportChartMuted.slice(1), badge ? { indent: { left: 300 }, spacing: { after: 55 } } : {})
        const card: IShapeGroupChildOptions = {
          type: "roundedRectangle",
          transformation: { width, height, offset: { left, top: 0 } },
          adjustments: { cornerRadius: 100 * radius / height },
          fill: reportSurface.slice(1),
          line: "none",
          textOptions: badge
            ? { verticalAlignment: "top", margins: { top: 14, left: 12, right: 10 } }
            : { margins: { left: 12, right: 10 } },
          children: badge ? [caption, number] : [number, caption],
        }
        return badge ? [card, {
          type: "picture",
          image: { type: "png", data: badge },
          transformation: { width: reportChangeBadgeSize, height: reportChangeBadgeSize, offset: { left: left + 19, top: 22 } },
        }] : [card]
      }),
    })],
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
        new Paragraph({ spacing: { after: 235 }, keepNext: true, children: [new ImageRun({
          type: "png", data: logo, transformation: reportLogoSize,
          altText: { name: "Аирейт", title: "Аирейт", description: "Фирменный знак и надпись Аирейт" },
        })] }),
        metric(reportTitle, 48, true, "000000", { heading: HeadingLevel.TITLE, spacing: { after: 100 }, keepNext: true }),
        metric(report.project, 32, true, headingColor, { spacing: { after: 80 } }),
        hint(`${report.period}  ·  ${report.mode}`),
        ...(report.filterNotes ? [hint(report.filterNotes)] : []),
        cards(report.metrics, "Сводка", { before: 180, after: 240 }),
        new Paragraph({ spacing: { after: 100 }, children: [new ImageRun({
          type: "png", data: charts.url, transformation: chartSize,
          altText: { name: "Диаграммы", title: "Результаты проверок и упоминаемость по ИИ-системам", description: charts.description },
        })] }),
        ...(report.dates.length ? [hint(`Даты отчёта: ${report.dates.join(", ")}`)] : []),
        heading("Динамика по запросам", HeadingLevel.HEADING_1),
        ...(changes.length ? [cards(changes, "Динамика по запросам", { after: 100 })] : []),
        ...(report.changeNote ? [hint(report.changeNote)] : []),
        ...(report.comparison ? report.tables.flatMap(table => [
          heading(table.title, HeadingLevel.HEADING_2),
          table.rows.length ? reportTable(report.tableHeaders, table.rows, badges, table.color) : hint(table.empty),
        ]) : []),
        heading("Методика", HeadingLevel.HEADING_2),
        hint(reportMethod),
        heading("Запросы по ИИ-системам", HeadingLevel.HEADING_1),
        ...(report.detailDates ? [hint(report.detailDates, true)] : []),
        ...report.serviceTables.flatMap(({ id, label, rows }) => [
          // Word merges adjacent tables without a paragraph, including their repeating headers.
          new Paragraph({ keepNext: true, spacing: { line: 20, lineRule: LineRuleType.EXACT } }),
          reportTable(serviceTableHeaders, rows.length ? rows : [["", "Нет запросов.", ""]],
            badges, undefined, { label, icon: serviceIcons.get(id) }),
        ]),
      ],
    }],
  })
  return Packer.toBlob(doc)
}
