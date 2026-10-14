# 后台生活任务排队与排程公平性

日期：2026-09-24。

阅读、日记/梦境、衍生提取和角色状态维护已接入同一个后台等待队列。后台名额暂时用满时，已受理的原任务保留输入和截止时间，等待可用名额；此前会直接结束为 `owner_unavailable`，导致自动阅读暂停或当日日记失败。本批同时修复旧状态排程长期挡住后续目标的问题。

## 实现

`execution/waiting.py` 只管理当前宿主持有原输入的等待调用；`ExactTaskRunner` 可选接入，由 `host/application.py` 装配给阅读、私人书写和状态维护。仍使用同一 SQLite 任务监督器领取原任务，后台总名额、任务种类并发和同 scope 并发继续逐次检查。

排队顺序按进入时间，较早且满足条件的任务优先领取。某种任务或 scope 达到并发上限时，其他符合条件的任务可以使用剩余名额；较长阅读的下一片段不能抢在已等待的日记/状态任务之前。记忆反思、主动联系和其他后台消费者仍使用其原调度策略，本批的公平顺序适用于接入队列的角色生活任务。

等待期间原 `execution_tasks` 记录保持 `created`、`attempt_no=0`，模型调用与预算预留尚未发生。临时队列只保存上下文、原任务 ID 和等待句柄；原输入仍由领域服务持有，执行前重新核验权限、人格绑定、资料和版本。不会为通过校验而替换已经封存的素材；等待期间素材已失效的任务仍应失败。

原任务的 180 秒截止时间继续有效，等待不会延期。精确领取先处理截止时间，再检查容量，因此名额一直被占用也不会让到期等待任务永久挂起。前台使用独立名额；已有的在途协程停止证明继续决定后台物理名额何时释放。

## 停止与恢复

等待调用计入执行器及宿主的活动句柄。撤回资料、切换人格或停机可取消排队任务；取消若恰好发生在“已分配名额、原执行器尚未开始”之间，只释放这个已确认没有 worker 的 claim。重复等待者不能占用同一原任务，也不能取消原等待者。

宿主启动按每批 32 条清理上一代、已登记生活任务种类中 `created + attempt_no=0` 的遗留任务：原内存输入已经丢失，记录结束为 `owner_unavailable`，释放队列容量。当前代任务、其他领域任务及已派发的尝试不在此清理范围内；未知结果不重新执行。

正常停机后，从未开始的阅读可按当前视图明确重试；已派发且结果未知的阅读保持原边界。日记/梦境日期回执沿用既有受理和不重放规则，重复请求在原请求等待时返回 `accepted`，原请求完成后返回同一个写入回执。

## 状态排程

`role_work/state/maintenance.py` 改为以 `(next_at, context_key)` 续扫，每批最多 16 条。旧人格、未重新绑定、禁用或暂不适合维护的记录不会把后续目标永久挡在首页之外；整批尚未扫完时通知宿主继续，批次之间让出执行权。依然只有当前可信绑定可以执行，未来时间和前台活动仍按既有规则检查。

一次维护的下次执行时间仍在派发前持久化，重启不补跑未知调用。任务等待共享名额时持有原维护输入，设置或材料变化仍会触发原版本校验。

## 验证

新增 15 项：`tests/test_background_waiting.py` 的 9 项和 `tests/test_astrbot_background_fairness.py` 的 6 项。覆盖 FIFO、被种类/scope 阻塞的队首、两个物理名额、截止时间、重复等待、代次替换、分配后取消、旧未开始任务清理、两个原人格自动阅读、日记/状态先于下一阅读片段、前台继续响应、原文撤回、排队中切换人格、停机/重载和 40 条历史排程后的当前目标维护。两项原书写测试更新为等待契约。

受影响范围共 **199 项**定向回归，首轮 **198 项通过、1 项失败**。唯一失败是接管恢复测试使用通用 `claim(Lane.BACKGROUND)` 夹具，领取了较早的等待任务，导致“从未开始”和“已开始”的测试身份颠倒；改为按原任务 ID 精确领取并开始后，队列专项 **9/9 项复验通过**。修正仅涉及测试夹具，未改实现；199 项范围内每项最终均有通过记录，未将复验重复累计，也未称为同批 199/199 一次全过。

定向回归命令：

```powershell
$env:PYTHONPATH = 'C:/Users/99505/.astrbot/backend/app'
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 -m unittest tests.test_background_waiting tests.test_astrbot_background_fairness tests.test_execution tests.test_execution_runner tests.test_execution_diagnostics tests.test_role_journal_writing tests.test_role_journal_scheduling tests.test_role_journal_triggers tests.test_role_life_runtime tests.test_role_life_api tests.test_role_reading tests.test_role_state tests.test_role_state_api tests.test_astrbot_multi_life tests.test_astrbot_multi_life_recovery tests.test_astrbot_multi_state tests.test_astrbot_multi_host tests.test_astrbot_staging_host tests.test_host_recovery tests.test_isolation -q
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 -m unittest tests.test_background_waiting -v
& 'C:/Users/99505/.astrbot/backend/python/python.exe' -B -X utf8 -m tests.multi_life_entry_process
```

真实 AstrBot SDK 独立进程入口已通过初始化、四组生活路由、启动、睡眠命令、停机、数据库关闭和路由注销。日志保存在系统临时目录 `companion-background-fairness-regression.log`、`companion-background-fairness-queue-recheck.log` 和 `companion-background-fairness-entry.log`。验证使用临时 V2 数据根及模型/平台替身；没有在线重载、真实模型/QQ 调用或 V1 数据访问。本批无 schema 迁移。

## 后续进展

同一角色跨窗口的身体状态、睡眠连续性和共享作息已分别由[角色身体正本](CORE_SHARED_ROLE_BODY_20260924.md)与[共享睡眠排程](CORE_SHARED_ROLE_SLEEP_SCHEDULE_20260924.md)接续完成。生活管理页面已接入「陪伴小屋」；生产平台现场效果仍需独立验收。
