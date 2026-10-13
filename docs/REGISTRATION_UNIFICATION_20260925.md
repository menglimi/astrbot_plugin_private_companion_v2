# 新框架注册与入口统一记录

日期：2026-09-25。协调任务：`01a0cd49-59e3-7e90-8050-9d6281c49d18`。

> **当前实现状态（2026-10-11）**：本文前期盘点中的“七个可选伴侣仍各自登记”是历史快照，不是当前 V2 运行合同。Content、Image、Together、Game、Screen、Reality、Live 已作为 `astrbot_plugin_private_companion_v2` 内部 native extension 装配，由唯一 V2 Star 统一启停和治理；它们不再是 V2 的运行依赖，也不注册独立 Star。`providers` 仅保留给真正的外部兼容状态入口。

## 最终状态

新框架本体只有 **1 个**，统一为 `astrbot_plugin_private_companion_v2`，显示名「我会永远陪着你 V2.0」，版本 `2.0.0`；公开 Dashboard 入口只有 **「陪伴小屋」**。插件已启用的登记状态不表示宿主已接管消息。

| 盘点项 | 整理前 | 整理后 |
| --- | --- | --- |
| AstrBot 全站登记项（含停用项） | 47 | 46 |
| 新框架本体 | 1 | 1 |
| 重名插件注册 | 图片伴侣 0.4.5 与 PR8 0.4.1 | 0 |
| V2 公开页面 | 陪伴小屋、宿主管理、日记与生活、关系与记忆 | 陪伴小屋 |
| Content 新框架开发预览 | `pages/framework-preview-v1` 被发现为页面 | `design-previews/companion-v2`，不再作为插件页面 |

当时的七个可选伴侣登记记录仅用于解释整理前的在线状态。当前运行时使用 `integration/manifest.extensions` 和 V2 native registry，内部拓展的 owner 统一为 `companion_v2`；旧核心 `astrbot_plugin_private_companion` 仍可作为外部兼容状态入口，但不参与 V2 对话和拓展执行。

## 身份与页面规范

- 目录名、`metadata.name`、`main.py` 的 `PLUGIN_NAME` 及 `@register(PLUGIN_NAME, ...)` 对齐为 `astrbot_plugin_private_companion_v2`。本体 Python 类名沿用 `PrivateCompanionV2StagingPlugin`。
- `private_companion.v2` 仍是领域产品合同 ID，与 AstrBot 插件注册名承担不同职责。
- `pages/陪伴小屋/` 是页面规范源，只有它直接包含公开发现所需的 `index.html`。
- `pages/宿主管理/`、`pages/日记与生活/`、`pages/关系与记忆/` 的源码入口改为 `workspace.html`，由 `tools/sync_framework_page.py` 生成小屋内的 `workspaces/{host,life,relationships}/index.html` 及资源包。三个工作区的功能保留在小屋内。
- Content 开发预览完整保留在 `design-previews/companion-v2/`；构建及检查脚本、Demo 路由夹具和安装包校验已使用新的位置与入口。

## 重复图片实例处理

重复实例来自放在 AstrBot 一级插件扫描目录内的 PR8 Git worktree。检查其工作树干净后，使用 `git worktree move` 完整移至扫描目录外：

`C:/Users/99505/.astrbot/worktrees/astrbot_plugin_image_companion_pr8`

分支 `pr-8`、提交 `0f469a2822189a1dba0679e1cf8ef3002c7b6214`、文件及 Git 链接均保留，最终工作树仍干净。主目录图片伴侣 `0.4.5` 保持启用。

AstrBot 4.27.2 的插件重载 API 按名称定位首个实例。本次每步先核对根目录与版本，再依次重载正常实例、注销已移出扫描范围的旧实例；最终在线清单只剩主目录 `0.4.5`。未使用全局重载。

## 跨任务协调

| 任务 | 分工与确认 |
| --- | --- |
| `01a0b900-c7a3-71f0-b95e-f05c7c40eda8`（整理打包目前所有的设计稿内容） | 已确认；负责小屋整合、三个工作区入口收敛、构建、七个可选伴侣的状态发现与套件交付。入口统一、解压验证及套件交付均已完成，见下方交付补记。 |
| `01a0c791-c1c3-7cc0-b916-7a8ce4528fc4`（继续新框架搭建） | 已确认；负责群聊媒体与图片出站链，沿用同一本体，不另建注册。 |
| `01a0cfae-f62f-7502-bd7d-e7c6399a8345`（看看陪伴插件新框架的建设进度） | 已确认；负责角色状态、共享作息及 QQ 展示管理，页面沿用小屋规范源。 |
| `01a0af0a-eb17-75b0-b8fe-9fdcf6cd3da5`（我们来设计新框架下的Content 拓展） | 已发送统一身份、入口和分工约定；此前发生 HTTP 504，重发后任务继续运行，协调回执待收到。 |

前三个任务已约定不再单独改名、新增本体注册或在线重载。各自业务工作继续，注册整理由本任务完成。详细回执见同目录 `REGISTRATION_COORDINATION_20260925_*.md`。

整合任务在收到协调消息之前约 12:38–12:40 已对 V2 做过一次在线重载，将在线版本从 0.2.0 更新至 2.0.0；其回执记录宿主未接管消息。本次协调任务随后只为图片重复实例执行上述定向维护，没有再重载 V2、启动宿主或增加真实投递授权。没有读取、迁移或修改 V1 用户数据。

## 验证与证据

- 页面与产品测试：`tests.test_page_targets_api`、`tests.test_product_integration`，共 **12 项通过**，覆盖真实 SDK 只发现小屋、内部工作区仍可访问、Content 旧预览不再公开及能力发现。
- 四个独立进程的 Demo 宿主验收：单目标新建 9 项、单目标恢复 6 项、多目标新建 9 项、多目标恢复 6 项，共 **30 项通过**；覆盖真实插件入口、SDK HTTP 分发、浏览器、SQLite、恢复与停机清理。
- 四进程模型使用替身，真实模型请求与平台消息均为 0；浏览器错误、服务端错误及意外浏览器网络请求均为 0，临时数据已回收。
- 页面同步检查 `tools/sync_framework_page.py --check` 通过，变更列表为空。
- 最终在线 API 核验：46 个登记项、无重名、一个 V2 本体及一个公开小屋入口、Content 无公开页、图片仅正常 0.4.5。V1 与其他插件原有启用状态保持。

本轮证据目录：`D:/codex/workspaces/v2-registration-20260925/`。

- `before.json`：页面已收敛、图片重复实例尚未清理时的快照，并非最早的四页面快照。
- `image-main-reload.json`、`image-duplicate-removed.json`：图片定向维护结果。
- `final.json`：最终在线清单。
- `registration-tests.json`、`registration-tests.log`：12 项测试结果。
- `demo/demo-acceptance-results.json` 及各子目录：30 项独立进程验收记录。

跨任务测试可能有重叠，本记录仅统计协调任务此次的 12 项及 30 项，不与其他窗口数字累加。

## 交付补记

整合任务已完成交付，协调任务另行核对以下 ZIP 的 SHA-256，与回执一致。交付目录为 `D:/codex/workspaces/companion-v2-release-20260925/dist/`：

| 交付物 | 大小 | SHA-256 |
| --- | --- | --- |
| `astrbot_plugin_private_companion_v2-2.0.0.zip` | 12,793,434 字节 | `61cfed459fc1f266b8a31a36b474953d7e726bb8af02af1559a0c9c36dbc21b5` |
| `companion-v2-2.0.0-suite.zip` | 16,034,613 字节 | `116d5142bcfc66a7ea0d1b4670ce40e0df36e5c18797b1d89af218fa525dd9cc` |

该历史套件曾包含本体及七个可选伴侣的独立安装包；当前 V2 交付包只包含唯一的 `astrbot_plugin_private_companion_v2`，七项能力随本体内置。`verified/package-verification.json` 等历史证据仍保留，不能作为当前包结构的说明。

最终包使用已验收快照，已包含注册统一记录及工程约定，没有纳入状态窗口后续尚在开发的功能。本节为历史交付补记；当前包结构以 `tools/build_v2_release.py` 和 `tools/verify_v2_release.py` 的单包合同为准。

## 下一步

各领域继续在同一本体内维护功能。新增能力沿用 native extension registry 和唯一「陪伴小屋」入口；可加载 worktree、备份及测试副本继续放在 AstrBot 的一级插件扫描目录之外，避免再次被当作插件加载。
