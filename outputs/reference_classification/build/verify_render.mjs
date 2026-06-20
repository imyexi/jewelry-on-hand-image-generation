import fs from 'node:fs/promises';
import path from 'node:path';
import { SpreadsheetFile } from '@oai/artifact-tool';
const outDir = 'C:/Users/Administrator/Documents/珠宝上手图片生成/outputs/reference_classification';
const file = path.join(outDir, '参考图用途风格分类表.xlsx');
const data = await fs.readFile(file);
const wb = await SpreadsheetFile.importXlsx(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength));
const sheets = ['分类明细','分类汇总','预览索引'];
for (const name of sheets) {
  const png = await wb.render({ sheetName:name, autoCrop:'all', scale:1, format:'png' });
  await fs.writeFile(path.join(outDir, `verify_${name}.png`), new Uint8Array(await png.arrayBuffer()));
  console.log('rendered', name);
}
const overview = await wb.inspect({ kind:'workbook,sheet', include:'name,id', maxChars:2000 });
console.log(overview.ndjson);
