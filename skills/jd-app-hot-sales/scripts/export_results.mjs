import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const args = process.argv.slice(2);
const argument = name => {
  const i = args.indexOf(name);
  if (i < 0 || !args[i + 1]) throw new Error(`Required ${name}`);
  return path.resolve(args[i + 1]);
};
const data = JSON.parse(await fs.readFile(argument('--data'), 'utf8'));
const output = argument('--output');
if (data.rule !== 'display-tier-100w-inclusive-1000w-exclusive-v1') throw new Error('Unsupported rule');
const wb = Workbook.create();
const serial = value => value ? (Date.parse(value) + 8 * 3600000) / 86400000 + 25569 : null;
const row = r => [r.sku, r.title, r.raw_metric, r.display_floor === null ? null : Number(r.display_floor), r.status, serial(r.collected_at)];
const matched = data.rows.filter(r => r.hit === true);
if (data.total !== data.rows.length || data.hits !== matched.length || new Set(data.rows.map(r => r.sku)).size !== data.total) throw new Error('Inconsistent export counts');

function setup(name, title, headers, rows) {
  const sheet = wb.worksheets.add(name);
  const end = Math.max(8, rows.length + 7);
  sheet.showGridLines = false;
  sheet.getRangeByIndexes(0, 0, end, headers.length).format.font = { name: 'Arial', size: 11, color: '#222222' };
  sheet.getRangeByIndexes(0, 0, end, headers.length).format.rowHeight = 26;
  sheet.getRangeByIndexes(0, 0, end, headers.length).format.verticalAlignment = 'center';
  sheet.getRange('A2').values = [[title]];
  sheet.getRange('A2').format.font = { name: 'Arial', size: 16, bold: true };
  sheet.getRange('A4:F4').values = [['输入SKU', data.total, '已处理', data.checked, '命中', data.hits]];
  sheet.getRange('A5:F5').values = [['待核验', data.unresolved, '未遍历', data.pending, data.pending ? '遍历未完成' : '全部输入已处理', null]];
  sheet.getRange('H4').values = [['100万+纳入，1000万+排除；按显示档位下限筛选，不是精确销量区间。']];
  sheet.getRange('H5').values = [['未知热销值保留空白；标题不一致、同名商品或用户确认排除不归入命中。']];
  sheet.getRange('H4:H5').format.columnWidth = 95;
  sheet.getRangeByIndexes(6, 0, 1, headers.length).values = [headers];
  sheet.getRangeByIndexes(6, 0, 1, headers.length).format = { fill: '#344B62', font: { name: 'Arial', size: 11, bold: true, color: '#FFFFFF' }, horizontalAlignment: 'center', rowHeight: 28 };
  if (rows.length) {
    sheet.getRangeByIndexes(7, 0, rows.length, headers.length).values = rows;
    sheet.tables.add(`A7:${String.fromCharCode(64 + headers.length)}${end}`, true, name === '命中SKU' ? 'MatchedSkus' : 'CollectionRecords');
  }
  sheet.getRangeByIndexes(0, 0, end, headers.length).format.columnWidth = 20;
  sheet.getRange(`B1:B${end}`).format.columnWidth = 56;
  sheet.getRange(`E1:E${end}`).format.columnWidth = 28;
  sheet.getRange(`F1:F${end}`).format.columnWidth = 26;
  sheet.getRange(`A8:A${end}`).setNumberFormat('0'); // Values remain identifier strings.
  sheet.getRange(`D8:D${end}`).setNumberFormat('#,##0');
  sheet.getRange(`F8:F${end}`).setNumberFormat('yyyy-mm-dd hh:mm:ss');
  sheet.freezePanes.freezeRows(7);
  return sheet;
}

const headers = ['SKU', '商品名称', '全网热销原文', '显示档位下限', '采集状态', '采集时间（北京时间）'];
const main = setup('命中SKU', '京东全网热销展示档位筛选', headers, matched.map(row));
const detail = setup('采集明细', '全部输入SKU采集状态', [...headers, '来源表', '来源Excel行', '待核验原因', '页面标题'],
  data.rows.map(r => [...row(r), r.source_sheet ?? null, r.source_excel_row ?? null, r.reason ?? null, r.observed_title ?? null]));
detail.getRange(`I1:J${Math.max(8, data.total + 7)}`).format.columnWidth = 60;
wb.recalculate();
console.log((await wb.inspect({ kind: 'table', range: '命中SKU!A4:F12', include: 'values', tableMaxRows: 9, tableMaxCols: 6, maxChars: 1800 })).ndjson);
console.log((await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 10 }, maxChars: 800 })).ndjson);
await fs.mkdir(path.dirname(output), { recursive: true });
for (const sheet of [main, detail]) {
  const preview = await wb.render({ sheetName: sheet.name, range: 'A1:F15', scale: 1.5, format: 'png' });
  await fs.writeFile(path.join(path.dirname(output), `${sheet.name}-preview.png`), new Uint8Array(await preview.arrayBuffer()));
}
const file = await SpreadsheetFile.exportXlsx(wb);
await file.save(output);
console.log(JSON.stringify({ output, total: data.total, checked: data.checked, hits: data.hits, unresolved: data.unresolved, pending: data.pending }));
