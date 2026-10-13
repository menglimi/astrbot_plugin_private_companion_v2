/* 尺度审计的测试包装。
 *
 * 审计本身在 tools/audit_page_scale.py（Python，因为要解析 CSS 文本、
 * 跑正则与阈值判断）。这里把它接到 node --test 的面上，
 * 让 `node tests/test_page_scale.cjs` 与其它测试一样能跑、能进 CI。
 *
 * 为什么值得：尺度一旦失控，症状是"看着有点乱"这种无法断言的感觉。
 * 把它落成"已迁移页面必须零写死 + 令牌只有一个源 + 字号档位间距 ≥1px"三条，
 * 回退就会在下一次运行时直接变成红灯。
 */
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const SCRIPT = path.join(ROOT, 'tools', 'audit_page_scale.py');

/* 找得到哪个 Python 就用哪个。
   原来裸写 'python3'：在 Windows 上这个名字通常不存在（本机就没有），
   于是 execFileSync 抛 ENOENT，测试报「尺度审计未通过」——而审计本身其实
   是绿的，只是根本没跑起来。红灯指向了错的东西，比没有测试更坏：它会让人
   去改一个没坏的文件。不写死解释器路径：每台机器的 Python 位置不同，写死
   只是把同一个问题挪到下一台机器上。

   还要强制 UTF-8：审计会打印 ✓ / ✗，而在中文 Windows 上子进程默认用 GBK
   编码 stdout，一遇到这两个字符就 UnicodeEncodeError 崩掉——看起来同样像
   「审计未通过」。用 -X utf8 + PYTHONIOENCODING 两头都压住，无论父进程的
   代码页是什么。 */
const PY_FLAGS = ['-X', 'utf8'];
const PY_ENV = {...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1'};

function pythonExecutable() {
  const candidates = [process.env.DSH_PYTHON, 'python3', 'python', 'py'].filter(Boolean);
  for (const candidate of candidates) {
    try {
      execFileSync(candidate, [...PY_FLAGS, '-c', 'pass'], {cwd: ROOT, stdio: 'ignore', env: PY_ENV});
      return candidate;
    } catch (error) { /* 试下一个 */ }
  }
  return null;
}

/* 审计失败时 Python 以非零码退出，并已把明细打在 stdout 上。
   这里把它接住转成断言失败，好让报错信息里带着具体是哪个文件越界。 */
function run() {
  const python = pythonExecutable();
  if (!python) {
    return {ok: false, out: '找不到可用的 Python 解释器（试过 DSH_PYTHON / python3 / python / py）。'};
  }
  try {
    const out = execFileSync(python, [...PY_FLAGS, SCRIPT], {cwd: ROOT, encoding: 'utf8', env: PY_ENV});
    return {ok: true, out};
  } catch (error) {
    return {ok: false, out: (error.stdout || '') + (error.stderr || '')};
  }
}

test('尺度审计通过：已迁移页面零写死、令牌单源、档位间距足够', () => {
  const {ok, out} = run();
  if (!ok) {
    // 只带出失败明细，不要把整份报告塞进断言信息
    const detail = (out.match(/✗[^\n]*/g) || []).join('\n');
    assert.fail('尺度审计未通过：\n' + (detail || out));
  }
  assert.match(out, /尺度审计通过/);
});

/* 名单里的页面逐页核对，而不是抽查一两个：
   一个页面悄悄滑出名单，就会同时失去零写死判定与自发现的覆盖。
   新迁入 MIGRATED 的页面要同步加到这里，否则这条断言只是"老几页还在"，
   对新增页面完全没有保护。 */
test('所有已迁移页面都在判定名单内且零写死', () => {
  const {out} = run();
  for (const name of ['memory-page.css', 'learning-page.css', 'contact-page.css',
                      'models-page.css', 'entrance.css', 'host-options.css',
                      'learning-hub.css', 'perception-subpages.css', 'state-config.css',
                      'storage-page.css', 'understanding-page.css', 'weather-source.css',
                      'native-extension-panel.css']) {
    assert.ok(out.includes(name), name + ' 未出现在审计输出里');
    const line = out.split('\n').find(l => l.includes(name) && /^\s+[✓✗?]/.test(l)) || '';
    assert.match(line, /^  ✓/, name + ' 未通过：' + line.trim());
  }
});

test('字号令牌齐全，且不含已被合并的 --fs-small', () => {
  const fs = require('node:fs');
  const tokens = fs.readFileSync(path.join(ROOT, 'pages', '陪伴小屋', 'tokens.css'), 'utf8');
  for (const tier of ['micro', 'tiny', 'body', 'lead', 'title', 'head', 'display', 'hero']) {
    assert.ok(tokens.includes('--fs-' + tier + ':'), '缺少 --fs-' + tier);
  }
  /* --fs-small 曾与 --fs-body 只差 1px，两档被合并。
     它若回来，说明有人又在相邻 1px 上开了一档。 */
  assert.ok(!/--fs-small\s*:/.test(tokens), '--fs-small 已并入 --fs-body，不应再声明');
});

test('字号令牌乘的是 --font-scale，用户字号设置才真正生效', () => {
  const fs = require('node:fs');
  const tokens = fs.readFileSync(path.join(ROOT, 'pages', '陪伴小屋', 'tokens.css'), 'utf8');
  /* 这一条防的是本次修掉的真实缺陷：令牌曾经乘 --type-scale 之外的东西，
     而 --type-scale 只作用于 body，导致"字号设置"对拓展页完全无效。 */
  assert.match(tokens, /--font-scale:calc\(var\(--type-scale\) \* var\(--density-scale\)\)/);
  const sizes = tokens.match(/--fs-[a-z]+:calc\([^)]*var\(--font-scale\)\)/g) || [];
  assert.equal(sizes.length, 8, '八个字号档都该乘 --font-scale');
});

test('尺度令牌只在 tokens.css 声明一次', () => {
  const fs = require('node:fs');
  const dir = path.join(ROOT, 'pages', '陪伴小屋');
  for (const name of fs.readdirSync(dir).filter(f => f.endsWith('.css'))) {
    if (name === 'tokens.css') continue;
    const text = fs.readFileSync(path.join(dir, name), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, ' ');
    const defs = text.match(/--(?:r|sp|fs)-[a-z0-9]+\s*:/g) || [];
    /* tokens-bridge.css 曾有一份与 tokens.css 重复的尺度快照，
       同为 :root 优先级、加载在后，静默覆盖掉新加的令牌。 */
    assert.equal(defs.length, 0, name + ' 重复声明了尺度令牌：' + defs.join(' '));
  }
});
