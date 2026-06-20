import fs from 'node:fs/promises';
import path from 'node:path';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const root = 'C:/Users/Administrator/Documents/珠宝上手图片生成';
const outDir = path.join(root, 'outputs', 'reference_classification');
const manifest = JSON.parse(await fs.readFile(path.join(outDir, 'image_manifest.json'), 'utf8'));

function classify(item, idx0) {
  const n = idx0 + 1;
  let purpose=''; let style=''; let scene=''; let product=''; let recommendation=''; let notes=''; let confidence='中'; let braceletUse='待判断';
  if (n <= 49) {
    purpose = '上手姿势/手模构图参考';
    product = '无明确饰品/弱饰品';
    recommendation = '适合生成前期参考手势、手臂角度、皮肤光感与留白构图';
    if (n <= 29 || n === 33 || n === 34 || n === 38 || n === 39 || n === 48 || n === 49) { style='清透奶油系/白衬衫'; scene='室内自然光、白衣、柔和生活感'; }
    else if (n <= 47) { style='暗调高级/黑衣近景'; scene='黑底或车内暗光，突出手部线条'; }
    else { style='颈肩清透/穿搭参考'; scene='锁骨、肩颈与手臂构图'; }
    notes='主要看手部姿态，不建议作为具体饰品款式依据';
    confidence='高';
  } else if (n <= 55) {
    purpose='包挂/挂件场景参考'; product='包挂/车挂/钥匙挂件'; style='生活抓拍/包包搭配'; scene='包袋、车内、真人穿搭'; recommendation='适合生成挂件在包、手机或随身物上的搭配图'; confidence='高';
  } else if (n <= 65) {
    purpose='产品静物/单品展示参考'; product='手串/挂件/项链'; style='电商静物/暗调或白底'; scene='桌面、黑布、白底、包装盒'; recommendation='适合生成白底商品图、详情页主图或单品材质参考'; confidence='高';
  } else if (n <= 83) {
    purpose='佩戴展示-手链/项链'; product='手链、项链、戒指组合'; style='清透温柔/轻法式'; scene='白衣、针织、自然光、近景佩戴'; recommendation='适合女性日常佩戴图、锁骨链/手链的温柔氛围图'; confidence='高';
  } else if (n <= 97) {
    purpose='佩戴展示-红色系手串/项链'; product='红色手串、红绳、吊坠'; style='新中式/节庆红色'; scene='红色道具、暖光、手腕或胸前佩戴'; recommendation='适合朱砂、南红、转运珠、端午/节庆主题素材'; confidence='高';
  } else if (n <= 104) {
    purpose='佩戴展示-多层叠戴/穿搭'; product='多层手串、项链、包挂'; style='清透生活抓拍/浅色穿搭'; scene='咖啡店、街拍、包袋与上身穿搭'; recommendation='适合多条叠戴、日常穿搭种草图'; confidence='高';
  } else if (n <= 114) {
    purpose='包挂/车挂/手机挂件参考'; product='包挂、车挂、手机挂、吊坠'; style='生活方式/车内与包袋场景'; scene='车内后视镜、手机、包袋、白底'; recommendation='适合挂件使用场景、买家秀式展示'; confidence='高';
  } else if (n <= 123) {
    purpose='佩戴展示-紫色/白色多层手串'; product='紫水晶/珍珠/多层手串'; style='暗调车内/闪光质感'; scene='车内、黑衣、手腕近景'; recommendation='适合突出珠子通透度、叠戴层次和夜间氛围'; confidence='高';
  } else if (n <= 133) {
    purpose='生活方式穿搭参考'; product='弱饰品/珍珠手链/穿搭'; style='韩系少女/街拍咖啡馆'; scene='半身穿搭、咖啡馆、帽子、自拍视角'; recommendation='适合做种草封面、穿搭氛围和人物背景参考'; confidence='中';
  } else if (n <= 146) {
    purpose='产品氛围/人群细分参考'; product='手串、红绳、挂件'; style='新中式/复古手作/银发人群'; scene='暗红布景、手持、老年手部、图文卡片'; recommendation='适合复古国风、手作感、长辈礼物或情绪化海报'; confidence='高';
  } else if (n <= 158) {
    purpose='佩戴展示-多色手串/叠戴'; product='彩色手串、手链、戒指'; style='暗调高级/车内轻奢'; scene='黑衣、车内、方向盘、手腕近景'; recommendation='适合强调手串质感、叠戴层次和轻奢买家秀'; confidence='高';
  } else if (n <= 165) {
    purpose='佩戴展示-绿色系手串'; product='绿珠手串/吊坠'; style='极简暗调/视频截图'; scene='黑衣、卫生间镜头、手腕近景'; recommendation='适合绿色珠串上手、短视频封面或手势参考'; notes='163-164 为视频截图界面，使用时需注意裁掉界面元素'; confidence='高';
  } else if (n <= 172) {
    purpose='耳饰/吊坠单品与佩戴参考'; product='耳坠、耳饰、吊坠'; style='中式温润/自然光静物'; scene='耳部近景、手持、耳饰架、木质/石材背景'; recommendation='适合耳饰详情、材质展示与佩戴比例参考'; confidence='高';
  } else if (n <= 178) {
    purpose='佩戴展示-玉石/中式项链手镯'; product='玉镯、玉石项链、手链'; style='新中式温润/浅色长袍'; scene='亚麻、长裙、手镯与项链搭配'; recommendation='适合玉石类、东方感穿搭和气质型佩戴图'; confidence='高';
  } else if (n <= 185) {
    purpose='戒指上手/手部近景参考'; product='戒指'; style='暗调精致/手部特写'; scene='手指特写、黑底或奶油布景'; recommendation='适合戒指上手比例、指甲与手势参考'; confidence='高';
  } else if (n <= 195) {
    purpose='节庆/亲子/儿童佩戴参考'; product='儿童手链、端午手绳、挂件'; style='节庆童趣/端午国风'; scene='宝宝脚腕、亲子手部、童装胸针、红绿配色'; recommendation='适合端午、儿童款、亲子礼品和可爱场景图'; confidence='高';
  } else if (n <= 206) {
    purpose='佩戴展示-手串/项链综合'; product='珍珠/绿珠/多层手串/项链'; style='清透生活/暗调混合'; scene='白衣、车内、手腕与胸前近景'; recommendation='适合通用佩戴图、叠戴和浅色服装搭配参考'; confidence='高';
  } else {
    purpose='耳饰佩戴参考'; product='耳钉/小耳饰'; style='极简清透/耳部特写'; scene='耳部近景、低饱和背景'; recommendation='适合耳钉佩戴比例、耳部构图和小饰品展示'; confidence='高';
  }
  const largeWristRanges = [
    [1,49], [66,75], [77,81], [85,86], [88,91], [94,101], [115,123],
    [131,133], [137,138], [141,146], [149,165], [173,176], [178,178],
    [186,193], [196,201], [204,206]
  ];
  const isLargeWrist = largeWristRanges.some(([a,b]) => n >= a && n <= b);
  braceletUse = isLargeWrist ? '是：手腕/前臂露出面积足，可用于手链/手串上手参考' : '否/弱：手腕露出不足或主体不是手腕';
  if (isLargeWrist && !/手链|手串/.test(product)) {
    product = product && product !== '无明确饰品/弱饰品' ? `${product}；手链/手串` : '手链/手串';
  }
  if (isLargeWrist && !/手链|手串/.test(purpose)) {
    notes = notes ? `${notes}；补充：可用于手链/手串上手参考` : '补充：可用于手链/手串上手参考';
  }
  return {序号:n, 文件名:item.name, 相对路径:item.rel, 绝对路径:item.path, 宽度:item.w||'', 高度:item.h||'', 大小MB: +(item.bytes/1024/1024).toFixed(2), 用途分类:purpose, 手链手串适用性:braceletUse, 风格分类:style, 场景关键词:scene, 饰品类型:product, 推荐使用方式:recommendation, 备注:notes, 判断置信度:confidence};
}

const rows = manifest.map(classify);
const headers = Object.keys(rows[0]);
const wb = Workbook.create();
const detail = wb.worksheets.add('分类明细');
detail.showGridLines = false;
detail.getRangeByIndexes(0,0,1,headers.length).values = [headers];
detail.getRangeByIndexes(1,0,rows.length,headers.length).values = rows.map(r => headers.map(h => r[h]));
const used = detail.getRangeByIndexes(0,0,rows.length+1,headers.length);
used.format = { font: { name: 'Microsoft YaHei', size: 10 }, borders: { preset: 'all', style: 'thin', color: '#E5E7EB' } };
detail.getRangeByIndexes(0,0,1,headers.length).format = { fill: '#7A3E20', font: { bold: true, color: '#FFFFFF', name: 'Microsoft YaHei', size: 10 }, wrapText: true };
detail.freezePanes.freezeRows(1);
const widths = [52,210,330,520,58,58,70,260,170,210,150,310,190,90,90];
for (let c=0;c<widths.length;c++) detail.getRangeByIndexes(0,c,rows.length+1,1).format.columnWidthPx = widths[c];
detail.getRangeByIndexes(1,7,rows.length,8).format.wrapText = true;
try { detail.tables.add(`A1:O${rows.length+1}`, true, 'ReferenceClassification'); } catch(e) {}

// 汇总
function countsBy(field){ const m=new Map(); for(const r of rows) m.set(r[field], (m.get(r[field])||0)+1); return [...m.entries()].sort((a,b)=>b[1]-a[1]); }
const summary = wb.worksheets.add('分类汇总');
summary.showGridLines = false;
summary.getRange('A1:H1').merge();
summary.getRange('A1').values = [['参考图用途与风格分类汇总']];
summary.getRange('A1').format = { fill: '#2F261F', font: { bold: true, color: '#FFFFFF', size: 16, name: 'Microsoft YaHei' } };
summary.getRange('A3:B3').values = [['总图片数', rows.length]];
summary.getRange('D3:E3').values = [['生成日期', '2026-06-12']];
summary.getRange('A5:B5').values = [['用途分类', '数量']];
const purposeCounts = countsBy('用途分类');
summary.getRangeByIndexes(5,0,purposeCounts.length,2).values = purposeCounts;
summary.getRange('D5:E5').values = [['风格分类', '数量']];
const styleCounts = countsBy('风格分类');
summary.getRangeByIndexes(5,3,styleCounts.length,2).values = styleCounts;
summary.getRange('G5:H5').values = [['饰品类型', '数量']];
const productCounts = countsBy('饰品类型');
summary.getRangeByIndexes(5,6,productCounts.length,2).values = productCounts;
for (const rng of ['A5:B5','D5:E5','G5:H5']) summary.getRange(rng).format = { fill: '#B87A42', font: { bold: true, color: '#FFFFFF', name: 'Microsoft YaHei' } };
summary.getRange('A3:H30').format = { font: { name:'Microsoft YaHei', size: 10 }, borders: { preset:'all', style:'thin', color:'#E7DED4' } };
for (let c=0;c<8;c++) summary.getRangeByIndexes(0,c,30,1).format.columnWidthPx = [190,70,30,190,70,30,190,70][c];
summary.getRange('A32:H36').merge();
summary.getRange('A32').values = [['说明：本表依据文件夹现有 209 张参考图的视觉内容进行人工归纳式分类，重点围绕“生成珠宝上手/佩戴图片”可复用的用途、风格、场景和饰品类型。已补充规则：模特大面积露出手腕/前臂时，可用于手链/手串上手参考；后续可优先筛选“手链手串适用性”“用途分类”和“风格分类”。']];
summary.getRange('A32').format = { fill:'#F7F0E8', font:{ color:'#4B3425', name:'Microsoft YaHei', size: 10 }, wrapText:true };

// 索引页（不嵌入所有原图，避免文件过大；提供联系表路径）
const index = wb.worksheets.add('预览索引');
index.showGridLines = false;
index.getRange('A1:E1').values = [['联系表', '覆盖序号', '文件路径', '说明', '用途']];
const pages = Math.ceil(rows.length/20);
const idxRows=[];
for(let p=1;p<=pages;p++) idxRows.push([`contact_sheet_${String(p).padStart(2,'0')}.jpg`, `${(p-1)*20+1}-${Math.min(p*20,rows.length)}`, path.join(outDir, `contact_sheet_${String(p).padStart(2,'0')}.jpg`), '快速浏览缩略图与序号', '辅助核对分类']);
index.getRangeByIndexes(1,0,idxRows.length,5).values = idxRows;
index.getRange('A1:E1').format = { fill:'#7A3E20', font:{bold:true,color:'#FFFFFF',name:'Microsoft YaHei'} };
index.getRangeByIndexes(0,0,idxRows.length+1,5).format = { font:{name:'Microsoft YaHei',size:10}, borders:{preset:'all',style:'thin',color:'#E5E7EB'}, wrapText:true };
for (let c=0;c<5;c++) index.getRangeByIndexes(0,c,idxRows.length+1,1).format.columnWidthPx = [150,90,560,180,140][c];
try { index.tables.add(`A1:E${idxRows.length+1}`, true, 'PreviewIndex'); } catch(e) {}

// verify compact
const inspect = await wb.inspect({ kind:'table', range:'分类汇总!A1:H24', include:'values', tableMaxRows:24, tableMaxCols:8, maxChars:6000 });
console.log(inspect.ndjson);
const errors = await wb.inspect({ kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A', options:{useRegex:true,maxResults:100}, summary:'final formula error scan', maxChars:1000 });
console.log(errors.ndjson);
const preview = await wb.render({ sheetName:'分类汇总', autoCrop:'all', scale:1, format:'png' });
await fs.writeFile(path.join(outDir, 'summary_preview.png'), new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(wb);
const outFile = path.join(outDir, '参考图用途风格分类表.xlsx');
await xlsx.save(outFile);
console.log('SAVED', outFile);
