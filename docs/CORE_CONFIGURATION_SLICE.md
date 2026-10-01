# CORE-01 持久身份与统一配置首批切片

日期：2026-09-21。状态：隔离实现及定向测试通过；CORE-01 整项、配置专项及管理页尚未完成。本切片回补 G1/G2 的本体依赖，不接管现役 V1，不注册宿主入口。

依据：[本体前置对照](V1_CORE_FEATURE_PREREQUISITES.md)、[配置一致性与页面性能](CONFIGURATION_CONSISTENCY_AND_PANEL_PERFORMANCE.md)。本轮从设计进入代码，提供可由后续便签、角色服务和页面复用的持久身份与配置接口。

## 1. 已实现的闭环

| 部分 | 实际实现 | 本轮证明的边界 |
| --- | --- | --- |
| 持久身份 | [PersistentIdentityDirectory](../companion_v2/identity_policy/repository.py)保存可信账号绑定、授权及精确 scope 到角色的绑定；沿用原 G1 判断规则。 | 两连接可观察撤权/换绑，带预期修订的修改不会覆盖新决定；独立 Python 进程无需传入身份快照即可读取原绑定。没有接真实宿主认证或管理员页面。 |
| 字段注册 | [FieldRegistry](../companion_v2/configuration/registry.py)统一字段 ID、类型、默认值、适用层级、精度、owner、消费模块和生效边界。 | 重名、非法默认值、不一致的分组归属在装配时拒绝；当前支持布尔、整数、文本、概率和权重标量。完整 V1 字段目录未导入。 |
| 本体配置继承 | [SparseConfigurationOwner](../companion_v2/configuration/owners.py)在 SQLite 保存显式差异，按安装、角色、窗口解析。 | false、0、空文本与缺失分别处理；重置继承移除覆盖。快照含有效值、来源、来源字段修订和编辑依据。个人/关系层级、完整 Actor 档案尚未加入。 |
| 同一保存入口 | [ConfigurationService](../companion_v2/configuration/service.py)校验当前权限/角色绑定、字段和预期版本，复用公共 operation。 | 配置、版本、原操作结果和变更记录同事务提交；未知字段/类型/范围错误明确失败。回包丢失可以查询原结果，同参数重试不覆盖后来修改。 |
| 运行采用 | 配置消费者按 generation 报告应用成功或失败，页面可查询目标与采用状态。 | 已保存不会自动显示已采用；旧快照/旧运行代回执被拒绝，失败保留当前代已采用值。重启字段需新 consumer generation；同值改回也不冒用原字段修订的成功回执。这是本地回执接口，真实宿主消费者尚未全部接入。 |
| 能力设置共用入口 | [CapabilityConfigurationOwner](../companion_v2/capabilities/configuration.py)将已有 G6 范围偏好接入相同服务。 | 仍由原 `capability_settings` 表持有开关和权重，`configuration_values` 不复制一份。家具投影与 Screen 业务读取同一记录；原正数权重精度保留。 |
| 增量读取 | `changes_since()`只返回获准目标、当前分组及继承链相关的变更位置，带游标和有限分页。 | 排除无变化保存、其他分组/角色，不返回别处的设置值或操作正文；消费者收到提示后重读当前值，不重放旧补丁。完整后台调度/订阅尚未接入。 |
| 数值转换 | 概率内部使用 0..1，百分比显示转换显式进行；权重独立为正有限数。 | 0%、0.1%、1%、12.5%、100% 多次往返稳定；空值、负概率、100 作为规范概率、布尔和非有限数被拒绝。旧单位转换原语按版本/字段/单位解释，未实施完整 V1 自动迁移。 |

本体分组和能力分组由同一个服务实例装配 owner。每次修改只面向一个分组/owner，owner 必须共享同一个 StorageRuntime 才能参加本地事务；跨库配置批量保存没有被伪装成原子提交。`configuration_targets` 对外部 owner 只登记目标地址，配置值与权威修订仍由该 owner 提供。

G6 当前设置按能力和精确 scope 归属，因此使用 `ConfigLayer.SCOPE`，不假装具有角色继承；不接受 `reset_to_inherit`。窗口本体配置使用 `ConfigLayer.WINDOW` 并绑定角色，两种目标不互换。安装、丢弃、角色启用和设备授权仍是各自业务操作，普通配置写入不会暗中执行这些动作。

## 2. 数据库及事务

[storage schema](../companion_v2/storage/schema.py)增加内部 `storage.v2 -> storage.v3` 事务迁移，保留 `v1 -> v2` 的原定义和指纹；空库按既有升级链建立。升级前校验安装身份、旧结构和迁移记录；半迁移、旧指纹不可信及未知版本不自动补齐。v3 新增持久身份、角色绑定、配置差异、操作结果/变更和采用记录。

非空 v2 夹具含暂停的 Screen 安装选择、显式关闭及权重；升级和重开保持原值/修订。故障注入证明 DDL、版本及新迁移记录一起回滚。这里的 v1/v2/v3 都是 V2 工程自身的数据库格式，不能解释为已经迁移 V1 插件用户数据。

[StorageRuntime](../companion_v2/storage/runtime.py)现在支持写事务内部的 SAVEPOINT 组合。嵌套仓储成功仍受外层提交约束；内层失败可单独回滚，外层失败撤销全部嵌套写入。最外层只读快照不能被仓储接口升级为写事务。配置 owner 的更新和公共 operation/变更记录因此可以共同提交，不依靠“先改运行属性，保存失败再尽力恢复”。

身份及能力 Repository 的直接修改方法仍是可信控制面的持久原语。应用配置入口必须使用统一 service 才会产生公共配置变更记录；直接调用旧 G6 设置原语不产生这条通知，但下一次读取仍会发现 owner 修订变化并拒绝旧页覆盖。尚未开放网络管理端点。

## 3. 测试及证据

新增 42 项：配置 21、持久身份 6、配置存储/事务 8、能力配置集成 7。连同受数据库和事务影响的已有来源、对话、能力、Screen、主动分享、身份及隔离回归，定向运行 99 项全部通过；`compileall` 通过，隔离扫描包含在该批测试中。

```powershell
python -m unittest tests.test_configuration tests.test_capability_configuration tests.test_persistent_identity tests.test_configuration_storage tests.test_storage_migrations tests.test_storage_runtime tests.test_source_repositories tests.test_capabilities tests.test_screen_pipeline tests.test_isolated_conversation tests.test_foreground_conversation tests.test_proactive_sharing tests.test_identity_policy tests.test_isolation -q
python -m compileall -q companion_v2
```

随后只补强并重测规模用例，未重复运行未改动的整批：

```powershell
python -m unittest tests.test_configuration.ConfigurationTests.test_group_read_work_is_bounded_with_700_and_1500_registered_fields -v
```

规模样例为 700/1500 个注册字段、10 个角色，实际写入 7000/15000 条合成配置值。从窗口读取继承的一个 20 字段分组时，两种规模查询次数相同且不超过 16 次，结果只含当前分组并保留角色来源。该证据只证明服务端读取工作有界；没有测试管理页首屏、网络载荷、p95、手机或并发真实聊天，也未把此用例当作 CFG-04 全部通过。

独立进程测试用系统 Python 子进程重开临时 V2 库，验证绑定、0.01 概率、false 和空文本恢复，且上个服务实例的应用成功不会被新实例直接认领。Screen 集成测试通过统一 service 开/关主动偏好后，现有处理链分别接受/拒绝主动反馈锚点；权重不改变资料读取或发送资格。全程无真实模型、设备、平台 sender 或 TTS 调用，Screen 不创建投递 outbox。

## 4. 尚未完成的责任与下一步

- CORE-01 尚缺完整角色档案、用户/关系配置层级、宿主可信管理员入口及所有业务的持久身份切换。本轮窗口角色绑定不是完整 Session 或群成员服务。
- 配置字段目前为有限标量契约；列表/对象、敏感字段遮罩、搜索/展示描述、跨字段业务校验、全量 V1 字段/别名映射、版本化定义升级及旧运行进程的写入交接仍待实现。未实现的字段不能借通用接口标成已支持。
- 应用回执是可信消费者接口，不向页面开放“标记已生效”。消费者必须在本次实例取得新 generation，再就实际装载的快照回执。真实模块的启动/停止、外部重连查账、任务配置封存及后台持久游标随后接 CORE-08；正常聊天使用配置不应依赖发消息的用户具有管理页读权限，内部任务读取端口仍待接线。
- SCOPE 能力偏好沿既有 G6 粒度适配，不代表已完成 CORE-06 的 13 类主动目的、个人偏好和临时暂停继承；能力安装、更新、授权和退出仍按 G6 原路线推进。
- CFG-04 页面、草稿、搜索、切角色、按需拆包、3D 延迟加载及实际性能预算尚未实现。真实 V1 迁移和直接替换仍在 G9/G10。

下一本体切片进入 CORE-04 的便签/提醒本地闭环：复用持久身份、同事务原操作和版本记录，先实现保存、修改、完成/取消及原操作恢复，再接重复期次、到期调度和本地回执；真实提醒投递留在 G8。所需领域字段与约束随该切片登记，配置底座的剩余类型/入口随实际消费者接入补齐，不提前铺完所有表单。
