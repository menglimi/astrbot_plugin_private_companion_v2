# 同一角色跨窗口状态与睡眠连续性

日期：2026-09-24

## 本批完成

角色模拟状态正本、状态偏好和实际睡眠连续性归属 installation/Bot/role。窗口只提供管理授权与来源核验，不定义角色状态的归属。代码仍放在 companion_v2 领域内，根级 Python 入口仍只有 main.py。

### 身体正本与来源

role_work/state/ownership.py 新增 RoleStateRecords。角色状态使用角色 owner 保存，修订号在同一角色的窗口之间连续；幂等操作 ID 仍限定在原窗口。窗口旧记录和回执保留不动。某窗口首次成功写入时，以该窗口既有历史作为角色正本的起点；version(..., storage="window"/"role") 可明确读取两个历史分支。读授权视图时由角色历史的共享标记验证投影资格，不开放原 Source 正文。

role_work/state/evidence.py 对角色状态的来源及所有传递依赖执行来源与治理复核。跨窗口只投影角色自身的模拟状态，不公开原始 Source 正文或聊天记录；维护提示要求心情、位置、忙碌和临时状态只描述角色自身，不带入聊天对象身份、私人活动或窗口日程。来源撤回后，派生状态和未发送材料仍会失效。

同一人格的 energy、hunger、health、sleep、cycle、mood、location、busy、presence、online_mode 与 conditions 使用同一份跨窗口状态。操作者、原因、日历安排、平台授权、正在输入和 QQ 展示回执仍按窗口核验。状态投影发布为当前窗口授权视图 Source，并保留上游依赖，确保后续撤回/撤权可以沿依赖传播。普通对话快照记录观测到的版本；未发送材料在依赖变动后失效，已封存的历史仍反映当时观测。新快照使用 projection version 3，旧快照继续按原窗口分支解读。

### 生理配置

role_work/state/settings_scope.py 将 hunger_enabled、health_enabled 及全部 cycle_* 参数归到 installation/Bot/role 共用配置 owner。首次明确设置时兼容采用当前窗口的身体参数。窗口开关、维护间隔、日历、typing 和 presence 保持原有窗口范围。

现有管理 API 的权限签发及撤销仍按窗口执行；合并角色与窗口 revision/dependencies，使跨窗口配置变化能使旧配置令牌失效。状态管理结果新增 body_scope，供宿主说明身体参数的共享归属。

### 睡眠连续性

role_work/life/body_clock.py 从活动正本读取实际睡眠，只投影睡眠依据、状态和起止时间，不公开活动 ID、描述、对象或梦境。到期完成会持久化且不会重复执行。跨窗口入睡在事务内检查整个角色，避免同一角色重复睡眠；阅读开始时也会检查角色是否正在睡眠。

本批完成时，同一角色当前有效、启用自动睡眠的窗口按 context.key 选出唯一排程执行者；当时自动睡眠时间、时区与时长仍属于选中窗口的配置。后续已由[共享自动睡眠排程](CORE_SHARED_ROLE_SLEEP_SCHEDULE_20260924.md)提升为角色级作息设置，并继续保留唯一执行窗口、原生人格 guard 和个人日记/活动的窗口边界。

### 验证与边界

本批新增 21 个测试；按测试 ID 去重，受影响范围共 227 项，每项最终都有通过记录。它们由多个分批回归组成，并非单次 227 项命令全部通过。初轮出现的旧快照夹具、跨窗口管理回执重试和迁移记录数固定断言问题均已修正，并完成对应复验。最新身体共享/API 专项为 27/27，周期与跨原生账号连续性补测为 2/2，存储专项修正后为 8/8。

主要定向命令（在插件目录运行）：

    $env:PYTHONPATH = 'C:\Users\99505\.astrbot\backend\app'
    & 'C:\Users\99505\.astrbot\backend\python\python.exe' -B -X utf8 -m unittest tests.test_role_body tests.test_astrbot_shared_body tests.test_role_state_api

按变更范围复跑的其余测试模块包括 tests.test_role_state_configuration、tests.test_role_cycle、tests.test_role_cycle_optimization、tests.test_role_cycle_variation、tests.test_role_life_runtime、tests.test_role_life_host、tests.test_role_life_api、tests.test_configuration、tests.test_configuration_storage、tests.test_role_presence、tests.test_astrbot_background_fairness、tests.test_astrbot_staging_host、tests.test_isolation、tests.test_state_storage_migrations 和 tests.test_role_life_context，以及回归范围内既有状态/生活/宿主模块。最终去重统计为 227 项、全部有通过记录；测试输出保存在 %TEMP%/companion-shared-body-*.log。

另以 AstrBot 随附 Python 和真实 SDK 夹具在独立进程验证插件加载、生活路由注册、启动、睡眠命令、停机、数据库关闭及路由注销；模型调用和平台投递计数均为 0。文件编码、换行和 AST 检查通过；根级 Python 仍只有 main.py。

本批没有数据库 schema 迁移，没有在线重载，没有调用真实模型或 QQ，也没有读取、迁移或修改 V1 数据。当前共享工作区数据库迁移版本保持 v29；v29 属于此前工作，不是本批引入。

## 后续进展

角色共享作息与睡眠连续性已经落地，管理页显示共享范围、唯一执行窗口及入睡/唤醒时间；睡眠压力、欠睡恢复、观察窗口、睡眠中断、午休和赖床逻辑见[共享自动睡眠排程](CORE_SHARED_ROLE_SLEEP_SCHEDULE_20260924.md)。私人日记和聊天资料仍按窗口管理。
