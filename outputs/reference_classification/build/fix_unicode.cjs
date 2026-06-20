const fs = require('fs');
const file = 'outputs/reference_classification/build/build_reference_classification.mjs';
let lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);
for (let i=0; i<lines.length; i++) {
  if (lines[i].includes('test(product)')) {
    lines[i] = "  if (isLargeWrist && !/\u624b\u94fe|\u624b\u4e32/.test(product)) {";
    lines[i+1] = "    product = product && product !== '\u65e0\u660e\u786e\u9970\u54c1/\u5f31\u9970\u54c1' ? `${product}\uff1b\u624b\u94fe/\u624b\u4e32` : '\u624b\u94fe/\u624b\u4e32';";
    break;
  }
}
fs.writeFileSync(file, lines.join('\n'), 'utf8');
console.log('fixed unicode');
