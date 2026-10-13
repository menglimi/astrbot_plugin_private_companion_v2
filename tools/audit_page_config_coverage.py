#!/usr/bin/env python3
"""页面配置覆盖面自检：后端注册表 vs 前端 config-editor.js 的 spec。

用途：每次往任何配置组加字段后跑一次，确认页面确实声明了这个字段。

为什么需要它：纯 grep 会漏两类情况——
  ①页面用字符串拼接字段名（`"cycle_"+key+"_days"`），grep 抓不到字面量；
  ②模块映射写错（`life` 的字段其实在 `role_work.life.configuration`，
     不再是它早期以为的那个模块），会整组漏判。
本脚本直接 import 各模块的 `configuration_fields()` 拿真实短名。

用法：python3 tools/audit_page_config_coverage.py
退出码：0 全部覆盖；1 有缺口（逐组打印）。
"""
import importlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 分区 → 注册表所在模块。**加分区时这里也要加**，否则该组完全不参与自检。
MODULES = {
    "quota": "companion_v2.conversation.media.quota",
    "image_review": "companion_v2.conversation.media.review",
    "busy_gate": "companion_v2.conversation.busy_gate",
    "reaction": "companion_v2.expression.reaction_configuration",
    "budget": "companion_v2.model_gateway.budget",
    "recall": "companion_v2.conversation.recall_settings",
    "screen": "companion_v2.screen.configuration",
    "person": "companion_v2.memory.person.configuration",
    "person.learning": "companion_v2.memory.person.configuration:learning_configuration_fields",
    # 私聊用户权限的默认值与拒绝文案；按人的权限本身是 grant，不在这张表里。
    "private_access": "companion_v2.relationships.private_access",
    "role_growth": "companion_v2.role_work.growth.configuration",
    # 拆分出来的技能组要单列，而且必须指到它自己的字段提供函数：该模块的
    # `configuration_fields()` 只返回权限组，用它比对会把两个权限开关当成
    # 技能字段，报出一串并不存在的「缺控件」。
    "role.growth.skills": "companion_v2.role_work.growth.configuration:skill_configuration_fields",
    "knowledge": "companion_v2.knowledge.configuration",
    "life": "companion_v2.role_work.life.configuration",
    "library": "companion_v2.library.configuration",
    "wardrobe": "companion_v2.references.wardrobe",
    "photo.reference": "companion_v2.references.configuration",
    # QQ 空间拓展的角色级开关与节流；安装与逐会话同意不在这张表里（归能力安装路由）。
    "qzone": "companion_v2.qzone.configuration",
    "group_participation": "companion_v2.conversation.participation",
    # 唯一一个四层组（安装/角色/关系/窗口），160 个字段；此前不在表里，
    # 于是整组不参与自检——92 项没有控件的字段也一直是「通过」。
    "proactive.contact": "companion_v2.proactive.configuration",
}

# 有意不接的字段：值写明理由。**不要**为了「让自检通过」把它们加进页面，
# 也不要为了消掉噪音把它们从这里删掉——两件事都会掩盖真实的疏漏。
INTENTIONAL = {
    "knowledge": {
        "import_enabled": "旧世界书导入设置保留在后端合同中；当前页面只管理官方知识库来源",
        "import_paths": "当前页面不接收原始文件路径，避免保存后没有可用的导入管理入口",
    },
    "role.state": {
        "mood_cross_window": "跨窗口共享，操作员难以判断实际影响",
        "mood_interest_window_minutes": "与更新概率高度耦合，单独调反而更难预期",
        "mood_neutral_band": "偏玄学，默认值已够用",
        "online_status_enabled": "保存时会撤销对应 grant，与授权流程耦合",
    },
    "role.life": {},
}

# 在其他页面单独维护的字段。审计时确认它们仍由指定页面承接，避免把
# 拆分后的成员编辑器误报成通用工作台缺少控件。
EXTERNAL_CONTROLS = {
    "role_growth": {
        "read_enabled": "pages/陪伴小屋/learning-page.js",
        "proposals_enabled": "pages/陪伴小屋/learning-page.js",
    },
    "person.learning": {
        "acquaintance_learning_enabled": "pages/关系与权限/member-editor.js",
    },
}


def page_spec():
    """在前端环境里真的加载一次，取到的就是运行时用的那份 spec。"""
    script = """
const fs=require('fs'),vm=require('vm');
const root='pages/陪伴小屋/';
const c=vm.createContext({window:{},document:{},sessionStorage:{},Intl,Date,Object});
vm.runInContext(fs.readFileSync(root+'workbench-page.js','utf8'),c);
vm.runInContext(fs.readFileSync(root+'config-editor.js','utf8'),c);
process.stdout.write(JSON.stringify(c.window.CompanionConfigEditors.spec));
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8")
    if result.returncode != 0:
        raise SystemExit("前端 spec 加载失败（先确认 workbench-page.js 在 config-editor.js 之前）:\n"
                         + result.stderr)
    return json.loads(result.stdout)


def backend_fields(module_name):
    """该模块声明的字段短名，按 field_id 去掉 group_id 前缀切。

    模块名可以带 ``:函数名``。一个模块里可能有多个字段提供函数（技能组就是从
    ``growth.configuration`` 拆出去的），而 ``configuration_fields()`` 只返回其中
    一组；不指明函数就会拿错组去比对，报出一串并不存在的「缺控件」。
    """
    target, _, factory = module_name.partition(":")
    module = importlib.import_module(target)
    fields = getattr(module, factory or "configuration_fields")()
    if not fields:
        return None, set()
    group = fields[0].group_id
    return group, {field.field_id.removeprefix(group + ".") for field in fields}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    spec = page_spec()
    problems = []
    counted = {}

    missing_sections = [kind for kind in MODULES if kind not in spec and kind not in EXTERNAL_CONTROLS]
    for kind in missing_sections:
        problems.append(f"分区 {kind} 在注册表里有、前端 spec 里没有")

    for kind, module_name in MODULES.items():
        group, short = backend_fields(module_name)
        if not short:
            problems.append(f"分区 {kind}: {module_name} 没声明字段")
            continue
        counted[kind] = short
        external = EXTERNAL_CONTROLS.get(kind, {})
        for name, owner in external.items():
            owner_path = ROOT / owner
            source = owner_path.read_text(encoding="utf-8") if owner_path.is_file() else ""
            if name not in short or name not in source:
                problems.append(f"{kind} ({group}): 外部控件声明 {name} 未在 {owner} 中找到")
            if kind == "role_growth" and 'data-access="${field}"' not in source:
                problems.append(f"{kind} ({group}): {owner} 缺少专用授权控件绑定")
        excused = set(INTENTIONAL.get(group, {})) | (set(external) & short)

        if kind not in spec:
            for name in sorted(short - excused):
                problems.append(f"分区 {kind} ({group}): 字段 {name} 没有专用控件声明")
            continue

        entry = spec[kind]
        order = set(entry.get("order", []))
        labels = set(entry.get("labels", {}))
        sections = {name for section in entry.get("sections", []) for name in section["fields"]}

        for name in sorted(short - order - excused):
            problems.append(f"{kind} ({group}): 字段 {name} 没有控件声明（order 缺）")
        for name in sorted(short - labels - excused):
            problems.append(f"{kind} ({group}): 字段 {name} 没有标签（labels 缺）")
        if sections:
            for name in sorted(short - sections - excused):
                problems.append(f"{kind} ({group}): 字段 {name} 没落进任何段落（sections 缺）")

    if problems:
        print(f"发现 {len(problems)} 处覆盖缺口：")
        for item in problems:
            print("  -", item)
        return 1
    total = sum(len(names) for names in counted.values())
    excused = sum(len(group) for group in INTENTIONAL.values())
    external = sum(len(group) for group in EXTERNAL_CONTROLS.values())
    print(f"全部 {len(counted)} 个分区覆盖自检通过"
          f"（共 {total} 字段，其中 {excused} 项有意不接、{external} 项由其他页面维护）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
