/**
 * 《借星》· 生成 standalone.html（单文件版，双击即可打开）
 * 依赖 app.bundle.js 已由 esbuild 生成。
 * 用法：node gen_standalone.cjs
 *
 * 注意：必须用 replacer 函数做替换。String.replace 的替换串里 $& / $` / $'
 * 会被解释为「插入匹配项 / 匹配前内容 / 匹配后内容」，而 three.js 压缩代码中
 * 含有 `$&&` 这类序列，用字符串替换会把 bundle 打乱并注入假的 <script src> 标签，
 * 导致浏览器在 bundle 中间截断脚本（单独拷走文件时直接白屏）。
 */
const fs = require('fs');
const path = require('path');

const HERE = __dirname;
const esc = (s) => s.replace(/<\/script/gi, '<\\/script');

const bundle = fs.readFileSync(path.join(HERE, 'app.bundle.js'), 'utf8');
const glbB64 = fs.readFileSync(path.join(HERE, 'assets', 'garden.glb')).toString('base64');
const anchors = fs.readFileSync(path.join(HERE, 'assets', 'anchors.json'), 'utf8');

let html = fs.readFileSync(path.join(HERE, 'index.html'), 'utf8');
// 允许引用带缓存破坏参数（?v=数字）
const tagRe = /<script src="app\.bundle\.js(\?v=\d+)?"><\/script>/;
if (!tagRe.test(html)) {
  console.error('index.html 中未找到 <script src="app.bundle.js[?v=N]"></script>');
  process.exit(1);
}

const REPL =
  '<script>window.__EMBEDDED_ANCHORS__=' + esc(anchors) + ';</script>\n' +
  '<script>window.__EMBEDDED_GLB__="' + glbB64 + '";</script>\n' +
  '<script>' + esc(bundle) + '</script>';

// replacer 函数：返回值按字面使用，不做 $ 模式展开
html = html.replace(tagRe, () => REPL);

const out = path.join(HERE, 'standalone.html');
fs.writeFileSync(out, html);

/* ---------- 自检 ---------- */
const stray = (html.match(/src="app\.bundle\.js(\?v=\d+)?"/g) || []).length;
if (stray) {
  console.error('自检失败：生成文件中残留 ' + stray + ' 处外部脚本引用（$ 模式污染）');
  process.exit(1);
}
const inlineRe = /<script>([\s\S]*?)<\/script>/g;
let m, n = 0, bad = 0;
while ((m = inlineRe.exec(html)) !== null) {
  n++;
  try { new Function(m[1]); }
  catch (e) { bad++; console.error('自检失败：内联脚本#' + n + ' 解析错误: ' + e.message); }
}
if (bad) process.exit(1);
console.log('standalone.html ->', (html.length / 1024 / 1024).toFixed(2), 'MB');
console.log('自检通过：无外部引用，' + n + ' 个内联脚本全部可解析');
