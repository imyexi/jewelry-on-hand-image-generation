import fs from 'node:fs';
const file = 'outputs/reference_classification/build/build_reference_classification.mjs';
let s = fs.readFileSync(file, 'utf8');
const old = `  if (isLargeWrist && !/手链|手串/.test(purpose)) {
    notes = notes ? \`${'${notes}'}；补充：可用于手链/手串上手参考\` : '补充：可用于手链/手串上手参考';
  }
  return {序号:n, 文件名:item.name, 相对路径:item.rel, 绝对路径:item.path, 宽度:item.w||'', 高度:item.h||'', 大小MB: +(item.bytes/1024/1024).toFixed(2), 用途分类:purpose, 手链手串适用性:braceletUse, 风格分类:style, 场景关键词:scene, 饰品类型:product, 推荐使用方式:recommendation, 备注:notes, 判断置信度:confidence};`;
const neu = `  if (isLargeWrist && !/手链|手串/.test(product)) {
    product = product && product !== '无明确饰品/弱饰品' ? `${'${product}；'}手链/手串` : '手链/手串';
  }
  if (isLargeWrist && !/手链|手串/.test(purpose)) {
    notes = notes ? \`${'${notes}'}；补充：可用于手链/手串上手参考\` : '补充：可用于手链/手串上手参考';
  }
  return {序号:n, 文件名:item.name, 相对路径:item.rel, 绝对路径:item.path, 宽度:item.w||'', 高度:item.h||'', 大小MB: +(item.bytes/1024/1024).toFixed(2), 用途分类:purpose, 手链手串适用性:braceletUse, 风格分类:style, 场景关键词:scene, 饰品类型:product, 推荐使用方式:recommendation, 备注:notes, 判断置信度:confidence};`;
if (!s.includes(old)) throw new Error('target block not found');
s = s.replace(old, neu);
fs.writeFileSync(file, s, 'utf8');
console.log('patched product rule');
