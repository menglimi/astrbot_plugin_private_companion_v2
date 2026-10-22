"""生成自包含的主题与入场预览页。

把真实的 tokens.css、theme.js、entrance.css、voxel-room.js 读进来内联，
所以这是真渲染而不是示意图——改令牌后重新生成就能看到真实效果。

用法：python3 tools/build_theme_preview.py [输出路径]

产物默认写到仓库的 build/（已 gitignore），不再写进 pages/陪伴小屋/。
写进页面目录的那一版曾被发布脚本原样打进插件 ZIP：单文件 13.9 MB，
压缩后占整个安装包的四分之一。
"""
import base64
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "陪伴小屋"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "theme-preview.html"

THEMES = [
    ("courtyard", "庭院", "日间的清爽草绿与天光，默认外观", "day"),
    ("dawn", "晨雾", "清晨的浅暖米白与木色", "dawn"),
    ("dusk", "暮色", "傍晚的琥珀与陶土", "dusk"),
    ("night", "夜读", "低照度靛蓝，适合夜间查看", "night"),
    ("walnut", "深林", "胡桃木与苔绿，暖而稳的深色", "dusk"),
    ("contrast", "高对比", "纯黑白加单一强调色，强光或弱视环境", "day"),
]


def read(name):
    path = PAGE / name
    if not path.exists():
        raise SystemExit(f"缺少文件：{path}")
    return path.read_text(encoding="utf-8")


def inline_safe(script):
    """让 JS 能安全地内联进 <script> 块。

    HTML 解析器不认 JS 的注释与字符串——它只要在脚本内容里看到字面的
    `</script`，就会在那里提前结束脚本块，后面的代码全部变成页面文本。
    这个坑真的踩到了：theme.js 的文档注释里写着 `<script defer src="theme.js"></script>`
    作为用法示例，内联后整页 JS 失效。

    按 HTML 规范，把 `</` 写成 `<\\/` 即可：JS 里两者等价（\\/ 就是 /），
    但 HTML 解析器不再把它当作结束标签。这是唯一可靠的写法，
    因为 JS 的字符串与注释规则与 HTML 的标记规则是两套东西。
    """
    return script.replace("</", "<\\/")


def font_face():
    """MiSans 直接内联成 base64，否则预览页离开插件目录就取不到字体。"""
    blocks = []
    for file, weight in (("MiSans-Regular.woff2", 400), ("MiSans-Demibold.woff2", 600)):
        path = PAGE / "assets" / file
        if not path.exists():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        blocks.append(
            "@font-face{font-family:MiSans;src:url(data:font/woff2;base64,"
            + encoded
            + f") format('woff2');font-weight:{weight};font-display:block}}"
        )
    return "".join(blocks)


def main():
    tokens = read("tokens.css")
    entrance_css = read("entrance.css")
    theme = read("theme.js")
    entrance_js = read("entrance.js")
    voxel = read("assets/voxel-room.js")

    cards = "".join(
        f'<button class="swatch" data-theme="{tid}">'
        f'<span class="swatch-face" data-theme="{tid}">'
        f'<span class="swatch-bar"></span><span class="swatch-line"></span>'
        f'<span class="swatch-line short"></span><span class="swatch-chip"></span>'
        f"</span>"
        f'<span class="swatch-copy"><strong>{label}</strong><small>{note}</small></span>'
        f"</button>"
        for tid, label, note, _ in THEMES
    )
    theme_json = json.dumps(
        [{"id": t, "label": l, "note": n, "light": light} for t, l, n, light in THEMES],
        ensure_ascii=False,
    )

    html = f"""<!doctype html>
<html lang="zh-CN" data-theme="courtyard">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>陪伴小屋 · 主题与入场预览</title>
<style>
{font_face()}
{tokens}
{entrance_css}
/* === 预览页外壳。刻意极简——它只是承载真实令牌的画布。 === */
*{{box-sizing:border-box}}
html{{scrollbar-gutter:stable}}
body{{
  margin:0;min-height:100vh;
  background:var(--t-canvas);color:var(--t-text);
  font-family:MiSans,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  font-size:14px;line-height:1.6;
}}
.wrap{{max-width:1120px;margin:0 auto;padding:34px 26px 64px}}
h1{{font-size:23px;margin:0 0 6px;font-weight:600;letter-spacing:.2px}}
.lead{{color:var(--t-text-soft);font-size:13px;margin:0 0 30px;max-width:62ch;line-height:1.75}}
h2{{font-size:13px;font-weight:600;margin:0 0 4px}}
.hint{{color:var(--t-text-faint);font-size:11.5px;margin:0 0 18px;line-height:1.7}}

section{{margin-bottom:44px}}

/* 色卡：每个色卡自己带 data-theme，所以卡内取的是那套主题的真实令牌。
   这不是画出来的示意色块——是同一套 CSS 变量作用在局部的结果。 */
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
@media(max-width:820px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:520px){{.grid{{grid-template-columns:1fr}}}}
.swatch{{
  display:flex;align-items:center;gap:12px;text-align:left;width:100%;
  padding:11px;border:1px solid var(--t-line);border-radius:var(--r-md);
  background:var(--t-surface);color:var(--t-text);
  box-shadow:var(--t-shadow);cursor:pointer;
  transition:border-color var(--dur-fast),box-shadow var(--dur-fast),transform var(--dur-fast);
}}
.swatch:hover{{border-color:var(--t-line-firm);box-shadow:var(--t-shadow-lift);transform:translateY(-1px)}}
.swatch[aria-pressed="true"]{{border-color:var(--t-accent);box-shadow:0 0 0 2px var(--t-focus)}}
.swatch-face{{
  position:relative;flex:none;display:block;width:58px;height:46px;
  border-radius:var(--r-sm);overflow:hidden;
  background:var(--t-canvas);border:1px solid var(--t-line-firm);
}}
.swatch-bar{{position:absolute;inset:0 0 auto 0;height:9px;background:var(--t-accent);opacity:.9}}
.swatch-line{{position:absolute;left:7px;top:18px;width:31px;height:3px;border-radius:2px;background:var(--t-text-faint);opacity:.7}}
.swatch-line.short{{top:25px;width:19px;opacity:.45}}
.swatch-chip{{position:absolute;right:7px;bottom:6px;width:14px;height:10px;border-radius:3px;background:var(--t-accent-quiet);border:1px solid var(--t-accent);opacity:.9}}
.swatch-copy{{display:flex;flex-direction:column;gap:3px;min-width:0}}
.swatch-copy strong{{font-size:12.5px;font-weight:600}}
.swatch-copy small{{font-size:10.5px;color:var(--t-text-faint);line-height:1.6}}

/* 小屋舞台：真实体素渲染。 */
.stage{{position:relative;border:1px solid var(--t-line);border-radius:var(--r-lg);
  background:var(--t-surface);box-shadow:var(--t-shadow);overflow:hidden}}
.voxel{{width:100%;aspect-ratio:1.5;display:block}}
.stage-bar{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;
  padding:10px 14px;border-top:1px solid var(--t-line);background:var(--t-surface-soft)}}
.stage-bar button{{font:inherit;font-size:11.5px;padding:6px 11px;border-radius:var(--r-sm);
  border:1px solid var(--t-line-firm);background:var(--t-surface);color:var(--t-text);cursor:pointer;
  transition:border-color var(--dur-fast),color var(--dur-fast)}}
.stage-bar button:hover{{border-color:var(--t-accent);color:var(--t-accent-ink)}}
.stage-note{{margin-left:auto;color:var(--t-text-faint);font-size:11px;
  font-family:var(--numeric-font);letter-spacing:var(--numeric-spacing)}}

/* 令牌转储：看清每套主题的实际取值。 */
table{{border-collapse:collapse;width:100%;font-size:11.5px}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--t-line);white-space:nowrap}}
th{{color:var(--t-text-faint);font-weight:500}}
td.sw{{font-family:var(--numeric-font);font-size:11px}}
td.chip{{width:26px;padding:7px 4px}}
td.chip i{{display:block;width:20px;height:20px;border-radius:5px;border:1px solid var(--t-line-firm)}}
.scroll{{overflow-x:auto;border:1px solid var(--t-line);border-radius:var(--r-md);background:var(--t-surface)}}
.telemetry{{
  margin:0;padding:13px 15px;border-top:1px solid var(--t-line);
  background:var(--t-surface-sunken);color:var(--t-text-soft);
  font-family:var(--numeric-font);font-size:11px;line-height:1.75;
  white-space:pre-wrap;overflow-x:auto;max-height:280px;
}}
</style>
</head>
<body>
<div class="wrap">
  <h1>陪伴小屋 · 主题与入场预览</h1>
  <p class="lead">这份预览直接内联了 <code>tokens.css</code>、<code>entrance.css</code> 与真实的体素包，
  所以色卡、界面和小屋都是真渲染。点色卡换主题，界面走叠化过渡；点「重播入场」看四拍动画
  （中央近景 → 拉远与缩小 → 定格 → UI 浮现）。</p>

  <section>
    <h2>主题</h2>
    <p class="hint">六套按明暗分组，每套对应小屋的一个时段。色卡里的颜色由该色卡自己的
    <code>data-theme</code> 取自真实令牌——切换后完全一致，不存在两套色值。</p>
    <div class="grid" id="swatches">{cards}</div>
  </section>

  <section>
    <h2>小屋与入场</h2>
    <p class="hint">体素场景来自插件里的同一份编译产物。入场序列只调用它的公开接口
    （<code>setEntranceProgress</code> / <code>setLight</code> / <code>setLayout</code>），不改动包本身。</p>
    <div class="stage" id="stage">
      <div class="voxel" id="voxel" role="img" aria-label="体素小屋"></div>
      <div class="stage-bar">
        <button id="replay">重播入场</button>
        <button id="light-dawn">清晨光照</button>
        <button id="light-day">日间光照</button>
        <button id="light-dusk">黄昏光照</button>
        <button id="light-night">夜晚光照</button>
        <span class="stage-note" id="phase">待播放</span>
      </div>
    </div>
    <pre class="telemetry" id="telemetry" hidden></pre>
  </section>

  <section>
    <h2>令牌取值</h2>
    <p class="hint">六套主题的实到色值。加主题后重新生成本页即可核对，不需要另抄一份色表。</p>
    <div class="scroll"><table id="dump"></table></div>
  </section>
</div>

<script>{inline_safe(voxel)}</script>
<script>{inline_safe(theme)}</script>
<script>{inline_safe(entrance_js)}</script>
<script>
"use strict";
const THEMES = {theme_json};
const root = document.documentElement;

/* === 叠化换主题 ===
   与 product-page.js 的 crossfadeTheme 同法：自定义属性不能插值，
   所以盖一层用旧主题渲染的覆层再淡出。这里独立实现一份是因为
   预览页不加载 product-page.js（它要宿主桥接）。 */
function crossfade(next) {{
  const previous = root.dataset.theme;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced || previous === next) {{ root.dataset.theme = next; return; }}
  const veil = document.createElement("div");
  veil.className = "theme-crossfade";
  veil.dataset.theme = previous;
  document.body.appendChild(veil);
  void veil.offsetHeight;
  root.dataset.theme = next;
  veil.classList.add("is-fading");
  veil.addEventListener("transitionend", () => veil.remove(), {{once: true}});
  setTimeout(() => veil.remove(), 1000);
}}

const swatches = [...document.querySelectorAll(".swatch")];
function mark(active) {{
  swatches.forEach(node => node.setAttribute("aria-pressed", String(node.dataset.theme === active)));
}}
swatches.forEach(node => node.addEventListener("click", () => {{
  crossfade(node.dataset.theme);
  mark(node.dataset.theme);
}}));
root.dataset.themeReady = "";
mark(root.dataset.theme);

/* === 小屋 === */
const stage = document.getElementById("stage");
const host = document.getElementById("voxel");
const phaseLabel = document.getElementById("phase");
let controller = null, handle = null;

function mount() {{
  if (!window.PrivateCompanionHomeRoom3D || !host.isConnected) return;
  try {{
    controller = window.PrivateCompanionHomeRoom3D.mount(host, {{
      light: "day",
      reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
    }});
    controller.setAtmosphere({{condition: "clear"}});
    controller.setActive(true);
  }} catch (error) {{
    host.textContent = "体素场景未能启动：" + error.message;
    console.warn(error);
  }}
}}

/* 世代计数：重播时上一段的 done 会在新序列启动之后才 resolve。
   若不加判别，旧段收尾会把 entrance-settled 加到刚开始的新序列上，
   入场状态被提前摘掉——表现为「点了重播却什么也没发生」。
   每次 play 递增世代，只有当代的收尾才被采纳。 */
let generation = 0;
function settle(of) {{
  if (of !== generation) return;
  document.body.classList.remove("is-entrance");
  document.body.classList.add("entrance-settled");
  stage.classList.remove("is-entrance");
}}

function play() {{
  if (!controller || !window.CompanionEntrance) {{ phaseLabel.textContent = "序列不可用"; return; }}
  const mine = ++generation;
  handle?.skip();
  document.body.classList.remove("entrance-settled");
  document.body.classList.add("is-entrance");
  stage.classList.add("is-entrance");
  try {{
    handle = window.CompanionEntrance.run(controller, host, {{
      debug: true,
      light: root.dataset.theme === "night" || root.dataset.theme === "walnut" ? "night" : "day",
      onPhase: phase => {{
        phaseLabel.textContent = ({{prime: "① 中央近景", pull: "② 拉远并缩小", settle: "③ 定格", done: "定格完成"}})[phase] || phase;
        if (phase === "done") {{ settle(mine); report(handle); }}
      }},
    }});
    handle.done.then(() => settle(mine));
  }} catch (error) {{
    console.warn("入场未能启动：", error);
    settle(mine);
  }}
}}

/* === 遥测读取 ===
   入场是「看不见的过程」——出问题时只看到最终画面不对，看不出是哪一拍坏了。
   这里把入场记录的每帧相机位姿抽出来，直接回答「镜头有没有停下、
   停在哪、视场角是不是一直在缩」。

   换行一律用 String.fromCharCode(10) 拼，不写字面转义序列：
   这段代码要穿过 Python 的模板替换再变成 HTML 里的 JS，
   多层转义里 \n 很容易被吃掉一次，变成真实换行、把字符串截断。 */
const NL = String.fromCharCode(10);
function report(run) {{
  const panel = document.getElementById("telemetry");
  if (!run || !run.log) {{ panel.textContent = "这次运行没有遥测数据。"; return; }}
  const entries = run.log.all();
  const track = run.log.cameraTrack();
  const actions = entries.filter(item => item.kind !== "frame");
  const first = track[0];
  const last = track[track.length - 1];
  const fovs = track.map(item => item.fov);
  const summary = [
    "帧采样 " + track.length + " 条，动作 " + actions.length + " 条" +
      (first && last ? "，耗时 " + (last.at - first.at) + "ms" : ""),
    first ? "起始 位置 [" + first.pos + "] 视场 " + first.fov + "°" : "无帧数据",
    last ? "结束 位置 [" + last.pos + "] 视场 " + last.fov + "°" : "",
    fovs.length ? "视场范围 " + Math.min.apply(null, fovs) + "° – " + Math.max.apply(null, fovs) + "°" : "",
    last ? "结束时仍在移动：" + (last.moving ? "是 ← 镜头没有停下" : "否") +
      "；巡游运行中：" + (last.tour ? "是" : "否") : "",
  ].filter(Boolean).join(NL);
  const lines = actions.map(item => {{
    const rest = Object.keys(item).filter(key => key !== "at" && key !== "kind")
      .map(key => key + "=" + item[key]).join(" ");
    return "  +" + String(item.at).padStart(5) + "ms  " + item.kind.padEnd(9) + " " + rest;
  }}).join(NL);
  panel.textContent = summary + NL + NL + "动作序列：" + NL + (lines || "  （无）");
  panel.hidden = false;
}}

document.getElementById("replay").addEventListener("click", play);
for (const [id, light] of [["light-dawn", "dawn"], ["light-day", "day"], ["light-dusk", "dusk"], ["light-night", "night"]]) {{
  document.getElementById(id).addEventListener("click", () => controller?.setLight?.(light));
}}

/* === 令牌取值表 === */
const DUMP_KEYS = ["t-canvas", "t-surface", "t-surface-soft", "t-text", "t-text-soft",
  "t-accent", "t-accent-quiet", "t-ok", "t-warn", "t-risk"];
function dump() {{
  const table = document.getElementById("dump");
  const probe = document.createElement("div");
  document.body.appendChild(probe);
  const rows = THEMES.map(item => {{
    probe.dataset.theme = item.id;
    const styles = getComputedStyle(probe);
    const value = name => styles.getPropertyValue("--" + name).trim();
    const cells = DUMP_KEYS.map(name =>
      `<td class="sw" title="${{name}}">${{value(name) || "—"}}</td>`).join("");
    const chips = ["t-canvas", "t-accent", "t-accent-quiet"].map(name =>
      `<td class="chip"><i style="background:${{value(name) || "transparent"}}"></i></td>`).join("");
    return `<tr><th>${{item.label}} <code>${{item.id}}</code></th>${{chips}}${{cells}}</tr>`;
  }}).join(String.fromCharCode(10))
  probe.remove();
  table.innerHTML =
    "<thead><tr><th>主题</th><th colspan=3>色块</th>"
    + DUMP_KEYS.map(name => `<th>${{name.replace("t-", "")}}</th>`).join("") + "</tr></thead>"
    + "<tbody>" + rows + "</tbody>";
}}

mount();
dump();
/* 体素包是同步内联的，挂载可能早于布局完成；下一帧补一次尺寸。 */
requestAnimationFrame(() => {{ controller?.resize?.(); replayOnce(); }});
let played = false;
function replayOnce() {{ if (!played) {{ played = true; play(); }} }}
</script>
</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8", newline="\n")
    print(f"已生成 {OUT}")
    print(f"  尺寸 {OUT.stat().st_size / 1024:.0f} KB")
    print(f"  色板令牌 {len(re.findall(r'--t-[a-z-]+:', tokens))} 条声明")
    print(f"  主题 {len(THEMES)} 套")

    # 内联自检：只引用不内联是最难发现的一类缺陷——页面照常渲染，
    # 只有点到那个按钮才会看到兜底文案。entrance.js 就这样漏过一次。
    missing = [name for name, body in (("CompanionEntrance", entrance_js), ("PrivateCompanionHomeRoom3D", voxel))
               if f"window.{name}" not in html and f"window.{name}" not in body]
    if missing:
        raise SystemExit("内联自检失败，以下全局没有出现在生成页里：" + "、".join(missing))
    for name, expected in (("CompanionEntrance", "window.CompanionEntrance ="), ("PrivateCompanionHomeRoom3D", "window.PrivateCompanionHomeRoom3D")):
        if html.count(name) < 2:
            raise SystemExit(f"内联自检失败：{name} 在页面里只出现 {html.count(name)} 次，可能只有引用没有定义")
    print("  内联自检通过：入场序列与体素控制器都已内联")


if __name__ == "__main__":
    main()
