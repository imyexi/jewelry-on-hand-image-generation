const fs = require('fs');
const file = 'outputs/reference_classification/build/rebuild_fixed_final.mjs';
let s = fs.readFileSync(file, 'utf8');
if (!s.includes('默认使用策略:usePolicy')) {
  s = s.replace(/(\s*if \(isLargeWrist && ![\s\S]*?;\n)(\s*return \{序号:n,[\s\S]*?手链手串适用性:braceletUse, )(风格分类:style,)/, `$1  const lowPriorityStyles = ['节庆童趣/端午国风', '新中式/复古手作/银发人群', '韩系少女/街拍咖啡馆'];\n  const usePolicy = lowPriorityStyles.includes(style) ? '无特殊要求不优先使用' : '常规可优先使用';\n$2默认使用策略:usePolicy, $3`);
}
s = s.replace('[52,210,330,520,58,58,70,170,260,170,210,150,310,190,90].forEach', '[52,210,330,520,58,58,70,170,260,170,170,210,150,310,190,90].forEach');
s = s.replace('detail.getRangeByIndexes(1,7,rows.length,8).format.wrapText = true;', 'detail.getRangeByIndexes(1,7,rows.length,9).format.wrapText = true;');
s = s.replace("detail.tables.add(`A1:O${rows.length+1}`, true, 'ReferenceClassificationFixed');", "detail.tables.add(`A1:P${rows.length+1}`, true, 'ReferenceClassificationFixed');");
s = s.replace('说明：已把 1 (1).png 这类“手腕/前臂大面积露出但未佩戴饰品”的参考图，直接在“饰品类型”列写入“手链/手串”。', '说明：已把 1 (1).png 这类“手腕/前臂大面积露出但未佩戴饰品”的参考图，直接在“饰品类型”列写入“手链/手串”。并新增“默认使用策略”：节日、童趣、老人、街拍咖啡馆风格若无特殊要求，则不优先使用。');
s = s.replace("const fixedFile = path.join(outDir, '参考图用途风格分类表_修正版.xlsx');", "const fixedFile = path.join(outDir, '参考图用途风格分类表_修正版_v2.xlsx');");
s = s.replace("await xlsx.save(path.join(outDir, '参考图用途风格分类表.xlsx'));", "// 原文件可能正被 Excel/WPS 打开而锁定，先只保存新修正版。");
s = s.replace("const check = await imported.inspect({kind:'table', range:'分类明细!L1:L3', include:'values', tableMaxRows:3, tableMaxCols:1, maxChars:1000});", "const check = await imported.inspect({kind:'table', range:'分类明细!I1:M8', include:'values', tableMaxRows:8, tableMaxCols:5, maxChars:4000});");
if (!s.includes('默认使用策略:usePolicy')) throw new Error('patch failed: 默认使用策略 not inserted');
fs.writeFileSync(file, s, 'utf8');
console.log('patched v2');
