/* 单目标 / 多目标两种宿主模式下，后端注册的接口不是同一套——
 * 页面因此必须按模式给出正确的行为（而不是给出注定失败的按钮）。
 *
 * 2026-09-30 的变化：备份与 V1 迁移都补进了多目标注册表；
 * 迁移改为按角色挂载，页面在多目标下先选目标与角色，再对着那个角色的地址侦察、试算、执行。
 *
 * 已知差异（由本文件第一条用例锁住，变了就会红）：
 *   单目标专属：`AccountSessionWebAPI`（账号与会话）
 *     —— 它写的是**共享宿主**那一套账号/人格/窗口映射，多目标下同一件事由
 *        宿主管理的绑定编辑器（`all_targets`）承担，接口自己也会以
 *        `account_config_mode_required` 拒绝；页面据此分支（见宿主管理页
 *        「账号与会话编辑仅适用于共享宿主模式」与 `isMissingRoute` 兜底）。
 *   多目标专属：`GroupMemoryWebAPI`、`GroupReplyWebAPI`（群公共记忆与群回复）
 *
 * 判据只有一个：`page/targets` 返回的 `mode`（页面侧 `product.targetsMode()`）。
 *
 * 用 node --test 运行。
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const HOST = path.join(ROOT, "astrbot_host");
const PAGE = path.join(ROOT, "pages", "陪伴小屋");

const read = file => fs.readFileSync(file, "utf8");
const registeredApis = source => new Set([...source.matchAll(/(\w+WebAPI)\s*\(/g)]
  .map(match => match[1]).filter(name => name !== "StagingWebAPI"));

test("两种模式各自注册的接口集合（前提变了就要回来改页面）", () => {
  const single = registeredApis(read(path.join(HOST, "web_api.py")));
  const multi = registeredApis(read(path.join(HOST, "multi_api.py")));
  const singleOnly = [...single].filter(name => !multi.has(name)).sort();
  const multiOnly = [...multi].filter(name => !single.has(name)).sort();

  assert.deepStrictEqual(singleOnly, ["AccountSessionWebAPI"],
    "单目标专属接口变了：新增的要补进多目标注册表，或在页面上按 targetsMode 分支");
  /* 单目标专属的那一个必须是"页面明明按模式分支过"的：页面若不再处理它，
     多目标下就会露出一个注定失败的入口。 */
  const hostPage = read(path.join(ROOT, "pages", "宿主管理", "app.js"));
  assert.match(hostPage, /account_config_mode_required/,
    "页面要认得账号与会话的模式限制，而不是把它当普通错误弹出来");
  assert.deepStrictEqual(multiOnly, ["GroupMemoryWebAPI", "GroupReplyWebAPI"],
    "多目标专属接口变了：页面一旦消费它们，同样要按模式分支");
});

test("备份入口两种模式都出现，且范围由还原预览说明", () => {
  const app = read(path.join(PAGE, "app.js"));
  const at = app.indexOf('id="backupWorkspace"');
  assert.ok(at > 0, "app.js 里找不到备份工作区的挂载点");
  const fnStart = app.indexOf("function renderDataOriginal");
  assert.ok(fnStart > 0 && fnStart < at, "找不到包含备份挂载点的渲染函数");
  const head = app.slice(fnStart, at);
  /* 备份现在两种模式都注册（多目标也在开库前应用暂存还原），
     所以挂载点不该再落在 multi 三元的一支里。 */
  assert.doesNotMatch(head, /multi\s*\?/, "备份入口不再按模式分支");
  assert.match(app, /function renderHostWorkspace\(\)/);

  /* 还原是整根替换，影响面必须写给用户：后端随预览下发 scope，页面渲染它。
     话术不锁死（它改过一轮：从「影响范围」改成直接说清会替换掉什么），
     锁的是"这一行确实由后端下发的 scope 驱动、并且点名了目标与角色数"。 */
  const api = read(path.join(HOST, "backup_api.py"));
  assert.match(api, /_installation_scope/, "后端要下发这次还原覆盖多少目标与角色");
  assert.match(api, /"scope": self\._installation_scope\(\)/);
  const page = read(path.join(PAGE, "backup-page.js"));
  assert.match(page, /state\.scope/, "备份页要渲染后端给的影响范围");
  assert.match(page, /backup-preview-scope/);
  assert.match(page, /scope\.targets/, "影响面要点名覆盖几个目标");
  assert.match(page, /scope\.roles/, "影响面要点名覆盖几个角色");
});

test("多目标下迁移先选目标与角色，地址来自页面目录", () => {
  const source = read(path.join(PAGE, "setup-guide.js"));
  /* 判据只有一个：page/targets 的 mode。 */
  assert.match(source, /const isMulti = \(\) => product\(\)\?\.targetsMode\?\.\(\) === "multi"/);
  /* 路由按角色挂载：地址从页面目录取，并且必须交给页面桥的**插件内相对路径**
     约定（前导斜杠与插件目录名都不能出现）。用哪个 helper 实现不锁死：
     `product().relative()` 与手写剥前缀都算数，锁的是"别把绝对地址交出去"。 */
  assert.match(source, /function legacyChoices\(\)/, "多目标下要能列出可选的目标与角色");
  assert.match(source, /function legacyAddress\(\)/);
  const normalized = source.includes("relative(role.legacy_api)")
    || /legacy_api\)\s*\.replace\(/.test(source)
    || /\.replace\(\s*\/\^\\\//.test(source);
  assert.ok(normalized, "地址要相对路径化（交给页面桥的必须是插件内相对路径）");
  assert.match(source, /if \(isMulti\(\) && !legacyScope\) return legacyScopePanel\(\)/,
    "没选之前给选择面板，而不是给按钮");
  /* 三个动作都要走 legacyAddress()，没有地址就不发请求。 */
  for (const action of ["legacy-scan", "legacy-plan", "legacy-apply"]) {
    const at = source.indexOf(`action === "${action}"`);
    assert.ok(at > 0, `找不到 ${action} 的处理`);
    assert.match(source.slice(at, at + 200), /if \(!legacyAddress\(\)\)/,
      `${action} 必须在地址为空时直接返回`);
  }
  /* 试算阶段就报缺哪些生效范围。 */
  assert.match(source, /function legacyScopeStatus/, "缺的生效范围要在试算/侦察阶段列出来");
});

test("页面消费多目标专属接口时同样要分支", () => {
  /* 今天页面没有消费 group_memory/group_reply。将来接群公共记忆页面时，
     这条会提醒按模式分支（那是唯一多目标专属的一对接口）。 */
  for (const name of fs.readdirSync(PAGE).filter(file => file.endsWith(".js"))) {
    const source = read(path.join(PAGE, name));
    if (!/group_memory|group_reply/.test(source)) continue;
    assert.match(source, /targetsMode/,
      `${name} 消费了多目标专属接口，但没有按 targetsMode 分支`);
  }
});
