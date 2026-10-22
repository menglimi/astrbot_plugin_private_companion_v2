"""生成自包含的外壳预览页。

把 index.html 引用的全部 CSS 与 JS 按原顺序内联成一个文件，所以这是
真实外壳的渲染，不是示意图——改完样式重新生成就能看到实际效果，
不需要装 AstrBot。

用法：python3 tools/build_page_preview.py [输出路径]

为什么不用现成的主题预览页（build_theme_preview.py）：
那个只内联主题与小屋，不含 app.js 的外壳逻辑，所以看不到导航、
面板切换与状态卡片。这个页补的是外壳那一层。
"""
import base64
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "陪伴小屋"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else PAGE / "shell-preview.html"
REPLY_EFFICIENCY_FIXTURE = ROOT / "fixtures" / "reply_efficiency_preview.json"


def read(name):
    path = PAGE / name
    if not path.exists():
        raise SystemExit(f"缺少文件：{path}")
    return path.read_text(encoding="utf-8")


def inline_safe(script):
    """让 JS 能安全地内联进 <script> 块。

    HTML 解析器不认 JS 的注释与字符串——它只要在脚本内容里看到字面的
    `</script`，就会在那里提前结束脚本块，后面的代码全部变成页面文本，
    而且不报错。按规范把 `</` 写成 `<\\/` 即可：JS 里两者等价
    （\\/ 就是 /），但 HTML 解析器不再把它当作结束标签。
    """
    return script.replace("</", "<\\/")


def font_face():
    """MiSans 内联成 base64，否则预览页离开插件目录就取不到字体。"""
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


def reply_efficiency_mock_script():
    if not REPLY_EFFICIENCY_FIXTURE.exists():
        raise SystemExit(f"缺少模拟数据：{REPLY_EFFICIENCY_FIXTURE}")
    fixture = json.dumps(
        json.loads(REPLY_EFFICIENCY_FIXTURE.read_text(encoding="utf-8")),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    template = r'''<script>
(() => {
  if (new URLSearchParams(location.search).get("mock") !== "reply-efficiency") return;
  const fixture = __FIXTURE__;
  const host = "astrbot_plugin_private_companion";
  const responses = {
    "integration/manifest": {extensions: [], providers: [], summary: {extension_ready_count: 0, connected_count: 0}},
    "page/targets": {
      installation_id: "preview-installation",
      operator_id: "preview-operator",
      targets: [{
        target_id: "preview-target", scope_kind: "private", platform_id: "onebot",
        account_id: "preview-account", participant_id: "preview-user", display_name: "模拟私聊",
        roles: [{role_id: "preview-role", role_name: "示例角色",
          model_api: "/" + host + "/model"}]
      }]
    },
    "model/maintenance": fixture.maintenance,
    "model/voice": fixture.voice,
    "model/image": fixture.image,
    "model": fixture.model,
    "model/balance": fixture.balance
  };
  window.AstrBotPluginPage = {
    ready: async () => ({pluginName: host}),
    onContext: () => () => {},
    apiGet: async endpoint => {
      const path = String(endpoint || "").replace(/^\/+/, "");
      if (!Object.hasOwn(responses, path)) throw Object.assign(new Error("预览没有配置此读取路由"), {code: "preview_route_unavailable"});
      return structuredClone(responses[path]);
    },
    apiPost: async () => { throw Object.assign(new Error("模拟预览为只读"), {code: "preview_read_only"}); }
  };
  const badge = document.createElement("div");
  badge.setAttribute("role", "status");
  badge.className = "preview-mock-badge";
  badge.textContent = "模拟数据 · 只读预览";
  badge.style.cssText = "position:fixed;top:10px;right:12px;z-index:10000;padding:6px 10px;border:1px solid var(--t-line);border-radius:var(--r-2xs);background:var(--t-surface);color:var(--t-text-soft);font:var(--fs-tiny) MiSans,sans-serif;box-shadow:var(--shadow-1);pointer-events:none";
  document.body.append(badge);
})();
</script>'''
    return template.replace("__FIXTURE__", fixture)


def main():
    html = read("index.html")

    # 按出现顺序收集引用。顺序要紧：config-snapshot 要先于用它的脚本，
    # workbench-page 要先于 config-editor，shell 要先于 app。
    styles = re.findall(r'<link rel="stylesheet" href="([^"?]+)[^"]*">', html)
    # 放宽：脚本标签可能带别的属性（voxel-room.js 挂着 onload/onerror 放行首屏）。
    # 原先要求 defer src 之后直接是 "></script>"，多一个属性就匹配不到——
    # 而漏掉的表现是「预览页比真实页少 660 KB 且小屋不显示」，自检也照过。
    scripts = re.findall(r'<script[^>]*\ssrc="([^"?]+)[^"]*"[^>]*></script>', html)
    boot = re.search(r"<script>\s*(/\* 主题引导.*?)\s*</script>", html, re.S)

    missing = [name for name in styles + scripts if not (PAGE / name).exists()]
    if missing:
        raise SystemExit("引用的文件不存在：" + "、".join(missing))

    css = "\n".join(read(name) for name in styles)
    js = "\n;\n".join(read(name) for name in scripts)

    # The dynamic output view copies this static template, including its asset URL.
    image = base64.b64encode((PAGE / "assets" / "chengxi.jpg").read_bytes()).decode("ascii")
    html = html.replace('src="assets/chengxi.jpg"', f'src="data:image/jpeg;base64,{image}"')

    # 去掉外链标签，换成内联。引导脚本保持内联位置（它必须在样式生效前跑）。
    body = html
    for name in styles:
        body = re.sub(r'<link rel="stylesheet" href="' + re.escape(name) + r'[^"]*">\s*', "", body)
    for name in scripts:
        body = re.sub(r'<script defer src="' + re.escape(name) + r'[^"]*"></script>\s*', "", body)
    if boot:
        body = body.replace(boot.group(0), "")
    body = re.sub(r"^\s*<!doctype html>.*?<body>", "", body, flags=re.S | re.I)
    body = re.sub(r"</body>.*$", "", body, flags=re.S | re.I)

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>陪伴小屋 · 外壳预览</title>
<style>
{font_face()}
{css}
</style>
<script>
{boot.group(1) if boot else ""}
/* 小屋就绪闸门直接放行。
 *
 * 真实页面里 data-room-ready 由入场定格（app.js 的 settleEntrance）写入，
 * 为的是让首屏等整段入场演完。预览页没有入场序列——entrance.js 不在内联
 * 范围内——也就没人来放行，兜底的 7 秒超时成了唯一路径，开局白屏七秒。
 * 所以这里直接放行：预览页的目的是看静态成品，不是看入场。 */
document.documentElement.dataset.roomReady="";
</script>
</head>
<body>
{body}
{reply_efficiency_mock_script()}
<script>
{inline_safe(js)}
</script>
</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(document, encoding="utf-8", newline="\n")

    # 自检：内联漏掉一个文件的表现是页面照常渲染、只是那一块功能没有，
    # 很难一眼看出来，所以这里断言关键的几个全局确实进来了。
    checks = {
        "CompanionShell": "window.CompanionShell",
        "CompanionEntrance": "window.CompanionEntrance",
        "PrivateCompanionHomeRoom3D": "window.PrivateCompanionHomeRoom3D",
        "CompanionProduct": "window.CompanionProduct",
    }
    absent = [name for name, needle in checks.items() if needle not in document]
    if absent:
        raise SystemExit("内联自检失败，以下全局没进生成页：" + "、".join(absent))

    print(f"已生成 {OUT}")
    print(f"  尺寸 {OUT.stat().st_size / 1024:.0f} KB")
    print(f"  内联样式 {len(styles)} 份、脚本 {len(scripts)} 份")
    print("  自检通过：外壳、入场序列、体素控制器、产品桥接都已内联")


if __name__ == "__main__":
    main()
