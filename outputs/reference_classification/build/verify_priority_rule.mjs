import fs from 'node:fs/promises';
import path from 'node:path';
import { SpreadsheetFile } from '@oai/artifact-tool';
const outDir = 'C:/Users/Administrator/Documents/珠宝上手图片生成/outputs/reference_classification';
const file = path.join(outDir, '参考图用途风格分类表_修正版_v2.xlsx');
const data = await fs.readFile(file);
const wb = await SpreadsheetFile.importXlsx(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength));
for (const range of ['分类明细!A124:M130','分类明细!A135:M146','分类明细!A188:M196']) {
  const check = await wb.inspect({kind:'table', range, include:'values', tableMaxRows:12, tableMaxCols:13, maxChars:6000});
  console.log('RANGE', range); console.log(check.ndjson);
}
const errors = await wb.inspect({ kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A', options:{useRegex:true,maxResults:100}, maxChars:1000 });
console.log(errors.ndjson);
