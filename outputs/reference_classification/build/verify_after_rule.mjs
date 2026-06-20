import fs from 'node:fs/promises';
import path from 'node:path';
import { SpreadsheetFile } from '@oai/artifact-tool';
const outDir = 'C:/Users/Administrator/Documents/珠宝上手图片生成/outputs/reference_classification';
const file = path.join(outDir, '参考图用途风格分类表.xlsx');
const data = await fs.readFile(file);
const wb = await SpreadsheetFile.importXlsx(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength));
const detail = await wb.inspect({ kind:'table', range:'分类明细!A1:O8', include:'values', tableMaxRows:8, tableMaxCols:15, maxChars:6000 });
console.log(detail.ndjson);
const errors = await wb.inspect({ kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A', options:{useRegex:true,maxResults:100}, maxChars:1000 });
console.log(errors.ndjson);
for (const name of ['分类明细','分类汇总','预览索引']) {
  const png = await wb.render({ sheetName:name, autoCrop:'all', scale:1, format:'png' });
  await fs.writeFile(path.join(outDir, `verify_${name}.png`), new Uint8Array(await png.arrayBuffer()));
}
