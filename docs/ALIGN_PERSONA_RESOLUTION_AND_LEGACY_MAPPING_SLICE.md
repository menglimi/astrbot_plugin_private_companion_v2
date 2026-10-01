# ALIGN-01：人格解析与旧范围映射切片

日期：2026-09-21。本切片接续[多 Bot 作用域与角色归属首批切片](ALIGN_SCOPE_AND_ROLE_OWNERSHIP_SLICE.md)，把先前仅有的“精确窗口角色行”升级为持久、可诊断的人格选择，并让正式入站事件携带一次解析完成的运行上下文。同时新增旧范围映射的证据登记原语；它不读取或认领现役 V1 数据。

## 1. 人格解析规则已落地

[人格目录](../companion_v2/identity_policy/personas.py)保存不可变会话参与者和追加式 `PersonaBinding` 历史。绑定记录包含 selector、人格、显式 precedence、有效期、revision、来源、authority 和是否允许被其他 authority 覆盖。解析先限定安装、逻辑 Bot 及平台登录账号，再按场景选择：

- 私聊：session > conversation+user > conversation > user > bot > installation；
- 群聊：session > conversation/group > bot > installation；
- 线程必须声明父场景是私聊还是群聊；群场景不会登记发言成员为人格 owner，因此不会套用其私聊 user 绑定；
- 同一层、同一 precedence 出现多个候选时返回 `persona_binding_conflict`，不猜一个；
- 临时绑定在 `effective_until` 到期后自动回落；受保护 authority 的绑定不能由其他来源更新。

解析 revision 表示该会话实际选择结果的历史代次。A→B→A 会得到新的 revision，原 A 请求仍失效；修改无关窗口或未胜出的较低层绑定不会无故中断当前请求。配置、便签、到期准备、原角色工具续答和前台生成均改用带当前时间的同一解析入口，不再各自读取精确窗口表。

旧 `role_bindings` 行保留为内部兼容资料。为已有精确行登记新路由时必须提交它的准确 revision，才会生成一条来源为 `exact-window-adoption` 的人格绑定；不能把当前 Bot 或新会话默认套给旧行。

## 2. 运行上下文进入正式入站链

`RuntimeIdentity` 由装配层提供 ecosystem、当前 runtime instance、宿主类型和宿主实例；`ConversationRoute` 由已认证宿主字段提供会话、实际私聊用户或群身份；解析后形成不可变 `RuntimeScope`。稳定角色 owner 仍只使用 installation + bot + persona，runtime、session 和绑定 revision 只用于路由及失效检查，不进入长期角色归属。

[AstrBot 窄适配器](../companion_v2/adapters/astrbot/inbound.py)现在依次核验登录 Bot/账号、宿主实例、受众、会话参与者和人格解析，成功后才发布消息来源。正式入站事件携带捕获的 `RuntimeScope`；前台默认使用其中的人格快照，外部调用方传入不同 `RoleBinding` 会得到 `role_binding_input_mismatch`。真实 AstrBot self_id、adapter、UMO、群/线程字段的具体提取器仍待宿主装配阶段实现，本切片没有导入 AstrBot。

## 3. 旧范围映射保持显式和可撤回

[旧范围映射目录](../companion_v2/legacy/scope_mapping.py)只允许给一个未解析旧会话 scope 增加 Bot、账号、规范会话和 session；安装、平台、场景类型及原窗口 ID 必须保持一致。每条映射绑定一个有版本的 V2 来源原件、authority、当时的真实账号绑定及已登记会话参与者。原件缺失、版本不符、过期或撤权、账号换绑后读取均失败；多个有效映射产生冲突诊断。映射撤回后恢复为 `scope_unresolved`，不会寻找最新来源或当前活跃 Bot 顶替。来源 owner 的元数据校验端口只返回原件引用，不泄露正文或授予资料读取权。

这只是后续迁移器可调用的准备/复核原语。各领域迁移仍须逐条验证原记录归属、分叉和操作结果，本轮没有打开 V1 数据根，也没有把任何旧便签、记忆或配置写入新归属。

## 4. 存储和验证

V2 内部 schema 升至 v7，新增会话路由、追加式人格绑定事件和旧范围映射三张表。v6→v7 在同一事务中建表、校验结构/引用并记录固定指纹；半升级、故障回滚和指纹篡改均拒绝打开。v1-v6 既有 DDL 与迁移指纹保持不变。

最终新增 22 项测试：人格选择 10 项、v6→v7 存储 3 项、旧范围映射 6 项，以及正式入站快照不能被重盖、A→B→A 失效和生成中人格到期 3 项。v7 首次贯通时的全套 **227 项**隔离测试通过；后续补充线程、跨账号、映射换绑等场景后，与 ALIGN-02 一起完成最后 **176 项定向回归**，编译检查通过。测试只使用临时 V2 数据库、合成事件和本地替身，不访问现役 V1、AstrBot、模型、网络、设备或平台。

ALIGN-01 由此完成“可信作用域、人格解析、稳定角色 owner、明确旧范围映射”的首个贯通版本。仍待后续领域逐一补全用户/群关系、记忆和日历等稳定 owner 投影，以及真实宿主字段提取。随后已完成 [ALIGN-02 配置/能力公共权限首批服务](ALIGN_COMMON_MANAGEMENT_ACCESS_SLICE.md)，下一步为 ALIGN-03 最小诊断证据与答疑服务。
