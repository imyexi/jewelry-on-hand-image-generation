import fs from 'node:fs';
const file = 'outputs/reference_classification/build/build_reference_classification.mjs';
let s = fs.readFileSync(file, 'utf8');
s = s.replace("let purpose=''; let style=''; let scene=''; let product=''; let recommendation=''; let notes=''; let confidence='中';", "let purpose=''; let style=''; let scene=''; let product=''; let recommendation=''; let notes=''; let confidence='中'; let braceletUse='待判断';");
const retRe = /  return \{序号:n,[\s\S]*?判断置信度:confidence\};/;
if (!retRe.test(s)) throw new Error('return block not found');
s = s.replace(retRe, `  const largeWristRanges = [
    [1,49], [66,75], [77,81], [85,86], [88,91], [94,101], [115,123],
    [131,133], [137,138], [141,146], [149,165], [173,176], [178,178],
    [186,193], [196,201], [204,206]
  ];
  const isLargeWrist = largeWristRanges.some(([a,b]) => n >= a && n <= b);
  braceletUse = isLargeWrist ? '是：手腕/前臂露出面积足，可用于手链/手串上手参考' : '否/弱：手腕露出不足或主体不是手腕';
  if (isLargeWrist && !/手链|手串/.test(purpose)) {
    notes = notes ? \`${'${notes}'}；补充：可用于手链/手串上手参考\` : '补充：可用于手链/手串上手参考';
  }
  return {序号:n, 文件名:item.name, 相对路径:item.rel, 绝对路径:item.path, 宽度:item.w||'', 高度:item.h||'', 大小MB: +(item.bytes/1024/1024).toFixed(2), 用途分类:purpose, 手链手串适用性:braceletUse, 风格分类:style, 场景关键词:scene, 饰品类型:product, 推荐使用方式:recommendation, 备注:notes, 判断置信度:confidence};`);
s = s.replace("const widths = [52,210,330,520,58,58,70,170,170,210,150,310,190,90];", "const widths = [52,210,330,520,58,58,70,260,170,210,150,310,190,90,90];");
s = s.replace("detail.getRangeByIndexes(1,7,rows.length,7).format.wrapText = true;", "detail.getRangeByIndexes(1,7,rows.length,8).format.wrapText = true;");
s = s.replace("detail.tables.add(`A1:N${rows.length+1}`, true, 'ReferenceClassification');", "detail.tables.add(`A1:O${rows.length+1}`, true, 'ReferenceClassification');");
s = s.replace("说明：本表依据文件夹现有 209 张参考图的视觉内容进行人工归纳式分类，重点围绕“生成珠宝上手/佩戴图片”可复用的用途、风格、场景和饰品类型。若后续要做批量生成，可优先筛选“用途分类”和“风格分类”两列。", "说明：本表依据文件夹现有 209 张参考图的视觉内容进行人工归纳式分类，重点围绕“生成珠宝上手/佩戴图片”可复用的用途、风格、场景和饰品类型。已补充规则：模特大面积露出手腕/前臂时，可用于手链/手串上手参考；后续可优先筛选“手链手串适用性”“用途分类”和“风格分类”。");
fs.writeFileSync(file, s, 'utf8');
console.log('patched');
