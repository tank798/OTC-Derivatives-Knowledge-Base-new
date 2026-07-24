#!/usr/bin/env node

import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(import.meta.dirname, "..");
const outputPath = path.join(root, "更新的法规", "场外衍生品法规分类与证据_20260724.xlsx");
const previewDir = path.join(root, "output", "spreadsheet_previews");
const classificationPath = path.join(root, "data", "metadata", "viewer_legacy_7d_classifications.json");
const evidencePath = path.join(root, "data", "metadata", "viewer_legacy_7d_evidence.jsonl");
const catalogPath = path.join(root, "data", "metadata", "regulations.jsonl");

async function loadArtifactTool() {
  try {
    return await import("@oai/artifact-tool");
  } catch {
    const fallback = path.join(
      os.homedir(),
      ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules",
      "@oai/artifact-tool/dist/artifact_tool.mjs",
    );
    return import(pathToFileURL(fallback).href);
  }
}

function readJsonl(text) {
  return text.split(/\r?\n/u).filter(Boolean).map((line) => JSON.parse(line));
}

function colLetter(index) {
  let value = index + 1;
  let result = "";
  while (value) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

const DEEP_BLUE = "#17365D";
const LIGHT_GRAY = "#F2F4F7";
const BORDER = "#D9DEE7";
const TEXT = "#1F2937";
const MUTED = "#667085";
const CHINESE_FONT = "KaiTi";
const ENGLISH_FONT = "Arial";
let tableCounter = 0;

function styleDataSheet(sheet, { title, subtitle, headers, rows, widths, technicalColumns = [] }) {
  const endColumn = colLetter(headers.length - 1);
  const lastRow = rows.length + 4;
  sheet.showGridLines = false;
  sheet.mergeCells(`A1:${endColumn}1`);
  sheet.getRange("A1").values = [[title]];
  sheet.getRange(`A1:${endColumn}1`).format = {
    fill: DEEP_BLUE,
    font: { bold: true, color: "#FFFFFF", name: CHINESE_FONT, size: 16 },
    verticalAlignment: "center",
  };
  sheet.getRange(`A1:${endColumn}1`).format.rowHeight = 30;
  sheet.mergeCells(`A2:${endColumn}2`);
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange(`A2:${endColumn}2`).format = {
    fill: "#E9EEF5",
    font: { color: MUTED, name: CHINESE_FONT, size: 10 },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${endColumn}2`).format.rowHeight = 28;
  sheet.getRange(`A4:${endColumn}4`).values = [headers];
  sheet.getRange(`A4:${endColumn}4`).format = {
    fill: DEEP_BLUE,
    font: { bold: true, color: "#FFFFFF", name: CHINESE_FONT, size: 10 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: BORDER },
  };
  sheet.getRange(`A4:${endColumn}4`).format.rowHeight = 26;
  if (rows.length) {
    sheet.getRange(`A5:${endColumn}${lastRow}`).values = rows;
    const dataRange = sheet.getRange(`A5:${endColumn}${lastRow}`);
    dataRange.format = {
      fill: "#FFFFFF",
      font: { color: TEXT, name: CHINESE_FONT, size: 10 },
      verticalAlignment: "top",
      wrapText: true,
      borders: {
        insideHorizontal: { style: "thin", color: BORDER },
        bottom: { style: "thin", color: BORDER },
      },
    };
    dataRange.conditionalFormats.addCustom(
      "=MOD(ROW(),2)=0",
      { fill: LIGHT_GRAY },
    );
    for (const columnIndex of technicalColumns) {
      sheet.getRange(`${colLetter(columnIndex)}5:${colLetter(columnIndex)}${lastRow}`).format.font = {
        name: ENGLISH_FONT,
        size: 9,
        color: TEXT,
      };
    }
    tableCounter += 1;
    const table = sheet.tables.add(`A4:${endColumn}${lastRow}`, true, `ClassificationTable${tableCounter}`);
    table.style = "TableStyleLight1";
    table.showBandedRows = false;
    table.showFilterButton = true;
    sheet.getRange(`A4:${endColumn}4`).format.fill = DEEP_BLUE;
    sheet.getRange(`A4:${endColumn}4`).format.font = {
      bold: true,
      color: "#FFFFFF",
      name: CHINESE_FONT,
      size: 10,
    };
  }
  widths.forEach((width, index) => {
    sheet.getRange(`${colLetter(index)}:${colLetter(index)}`).format.columnWidth = width;
  });
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(1);
}

const { SpreadsheetFile, Workbook } = await loadArtifactTool();
console.error("[workbook] artifact-tool loaded");
const [classificationText, evidenceText, catalogText] = await Promise.all([
  fs.readFile(classificationPath, "utf8"),
  fs.readFile(evidencePath, "utf8"),
  fs.readFile(catalogPath, "utf8"),
]);
const classifications = JSON.parse(classificationText);
const evidenceRows = readJsonl(evidenceText);
const catalogRows = readJsonl(catalogText).filter((row) => row.source_status !== "excluded_embedded_attachment");
const catalogById = new Map(catalogRows.map((row) => [row.document_id, row]));
const classificationById = new Map(classifications.documents.map((row) => [row.document_id, row]));

const workbook = Workbook.create();
console.error("[workbook] source data loaded");

const guide = workbook.worksheets.add("使用说明");
styleDataSheet(guide, {
  title: "场外衍生品法规分类与原文证据",
  subtitle: `分类版本：${classifications.classification_version}｜法规：${classifications.documents.length}部｜逐标签证据：${evidenceRows.length}条`,
  headers: ["项目", "说明"],
  rows: [
    ["工作簿用途", "统一展示分类标准、法规与标签映射，以及每一个标签对应的原文定位和摘录。"],
    ["分类原则", "HTML沿用用户确认的旧版七维筛选器及既有标签；每个标签逐项关联规范化完整正文或官方发布信息，不以单道问答题目作特判。"],
    ["证据口径", "每个标签均有独立证据行，记录标注理由、原文定位、页码、Block ID、原文摘录和证据等级，可回到HTML“阅读详情”复核。"],
    ["颜色与字体", "表头深蓝；数据行白色与浅灰交替。中文内容使用楷体，网址、ID、页码等技术字段使用Arial。"],
    ["官网链接", "沿用用户提供的旧版HTML链接；旧版缺少的两部法规使用补充清单中的链接，不以新目录覆盖旧链接。"],
    ["数据来源", "data/processed/documents/json、viewer_legacy_7d_classifications.json及viewer_legacy_7d_evidence.jsonl。"],
    ["排除说明", "“可投资国家或者地区”“期货期权交易所”已作为《保险资金境外投资管理暂行办法实施细则》内嵌附件保留，不作为独立法规重复入库。"],
  ],
  widths: [22, 105],
});

const standardCounts = new Map();
for (const row of evidenceRows) {
  const key = `${row.dimension}\u0000${row.tag}`;
  const current = standardCounts.get(key) ?? { documents: new Set(), evidence: 0, reason: row.reason ?? "" };
  current.documents.add(row.document_id);
  current.evidence += 1;
  standardCounts.set(key, current);
}
const standardRows = [];
for (const [dimension, labels] of Object.entries(classifications.dimensions)) {
  for (const label of labels) {
    const stats = standardCounts.get(`${dimension}\u0000${label}`) ?? { documents: new Set(), evidence: 0, reason: "" };
    standardRows.push([dimension, label, stats.reason, stats.documents.size, stats.evidence]);
  }
}
const standards = workbook.worksheets.add("分类标准");
styleDataSheet(standards, {
  title: "分类标准",
  subtitle: "与旧版HTML完全一致的七项筛选维度；每个标签的法规数量与证据数量可以相互核对。",
  headers: ["分类维度", "标签", "判定说明", "命中法规数", "证据条数"],
  rows: standardRows,
  widths: [18, 28, 72, 14, 14],
  technicalColumns: [3, 4],
});

const overviewRows = catalogRows.map((catalog) => {
  const classification = classificationById.get(catalog.document_id);
  if (!classification) {
    throw new Error(`缺少分类映射：${catalog.document_title}`);
  }
  return [
    catalog.catalog_index ?? "",
    catalog.document_title,
    catalog.issuing_authority,
    catalog.publication_date,
    catalog.validity_status,
    classification.authority_groups.join("、"),
    classification.trading_venues.join("、"),
    classification.underlying_business_types.join("、"),
    classification.client_entity_types.join("、"),
    classification.funding_sources.join("、"),
    classification.product_vehicles.join("、"),
    classification.conduct_categories.join("、"),
    catalog.chunk_count,
    catalog.character_count,
    classification.official_url,
    catalog.document_id,
  ];
});
const overview = workbook.worksheets.add("法规标签总览");
styleDataSheet(overview, {
  title: "法规标签总览",
  subtitle: "216部有效法规的一行式七维标签映射，可按任意列筛选；官网链接沿用旧版HTML。",
  headers: ["序号", "法规名称", "实际发布机关", "发布日期", "效力状态", "发文主体筛选", "交易场所", "标的及业务品种", "客户主体", "资金来源", "产品载体", "涉及交易行为", "Chunk数", "正文字符数", "官方链接", "Document ID"],
  rows: overviewRows,
  widths: [8, 52, 32, 14, 16, 22, 14, 34, 54, 28, 24, 42, 11, 13, 48, 31],
  technicalColumns: [0, 3, 12, 13, 14, 15],
});
overview.getRange(`O5:O${overviewRows.length + 4}`).format.wrapText = false;

const detailRows = evidenceRows.map((row, index) => {
  const catalog = catalogById.get(row.document_id);
  if (!catalog) {
    throw new Error(`证据引用未知法规：${row.document_id}`);
  }
  return [
    index + 1,
    row.document_title,
    row.issuing_authority,
    row.dimension,
    row.tag,
    row.reason ?? "",
    row.location ?? "",
    row.page,
    row.block_id,
    row.matched_text,
    row.basis,
    row.evidence_level ?? "",
    row.citation_nature ?? "",
    row.special_review_result ?? "",
    row.official_url ?? classificationById.get(row.document_id)?.official_url ?? "",
    row.document_id,
  ];
});
const details = workbook.worksheets.add("标签证据明细");
styleDataSheet(details, {
  title: "标签证据明细",
  subtitle: "每行严格对应“某部法规—某个七维标签”的一条证据；证据等级区分直接条款、官方发布信息和需进一步人工复核的综合判断。",
  headers: ["序号", "法规名称", "实际发布机关", "分类维度", "标签", "标注理由", "原文定位", "页码", "Block ID", "命中词", "法规原文摘录", "证据等级", "引用性质", "复核状态", "官方链接", "Document ID"],
  rows: detailRows,
  widths: [8, 48, 30, 18, 26, 48, 28, 9, 13, 18, 90, 24, 24, 20, 48, 31],
  technicalColumns: [0, 7, 8, 14, 15],
});
details.getRange(`O5:O${detailRows.length + 4}`).format.wrapText = false;
console.error("[workbook] four sheets built");

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
const previewSpecs = [
  ["使用说明", "A1:B12"],
  ["分类标准", "A1:E90"],
  ["法规标签总览", "A1:P22"],
  ["标签证据明细", "A1:P22"],
];
for (const [sheetName, range] of previewSpecs) {
  console.error(`[workbook] rendering ${sheetName}`);
  const preview = await workbook.render({
    sheetName,
    range,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(previewDir, `${sheetName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
  console.error(`[workbook] rendered ${sheetName}`);
}
console.error("[workbook] inspecting");
let inspection = { ndjson: "" };
try {
  inspection = await workbook.inspect({
    kind: "sheet",
    include: "id,name",
    maxChars: 3000,
  });
  console.error("[workbook] inspected");
} catch (error) {
  console.error(`[workbook] inspect unavailable: ${error instanceof Error ? error.message : String(error)}`);
}
let xlsx;
try {
  xlsx = await SpreadsheetFile.exportXlsx(workbook);
  console.error("[workbook] exported");
  await xlsx.save(outputPath);
  console.error("[workbook] saved");
} catch (error) {
  console.error(`[workbook] export failed: ${error instanceof Error ? error.message : String(error)}`);
  throw error;
}
console.log(JSON.stringify({
  output: outputPath,
  sheets: previewSpecs.map(([name]) => name),
  regulations: overviewRows.length,
  evidence_rows: detailRows.length,
  preview_dir: previewDir,
  inspection: inspection.ndjson,
}, null, 2));
