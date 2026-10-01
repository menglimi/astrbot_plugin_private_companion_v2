"""V1 数据迁移的管理界面接口。

三条路由，对应界面上三步：

    GET  /legacy             发现：V1 的每一份来源在不在、归谁、按合同怎么处置
    GET  /legacy/plan        试算：会写哪些字段、哪一项被改了、为什么（**不写库**）
    POST /legacy/apply       执行：按试算结果写入 V2

## 为什么把写库放在这里而不是域核心

配置写入在 V2 里要经 ``ConfigurationService.patch``，需要**操作者身份**、一次已
登记的 operation、以及当前 edit token——这三样只有宿主层拿得到。所以域侧的
``LegacyMigration`` 只产出 ``ConfigIntent``（作用域 + 分组 + 字段改动），由这里带着
真实 actor 提交。这样切还有个好处：发现与试算成了纯读操作，可以反复跑、可以测；
真正写库的路径只有下面 ``_apply_intent`` 一处。

## 为什么 apply 要重算

``apply`` **不接受**客户端传回来的字段值，只接受一个 ``plan_token``：它必须等于
当前 V1 目录的指纹。不这么做的话，客户端可以在「试算」与「执行」之间换一份数据，
或者干脆自己编一份改动——那等于把「先看后做」这个保证作废。重算一次很便宜
（只读 + 纯转换），换来的是「界面上看到的」与「实际写入的」必定是同一份。
"""

import hashlib
import json

from astrbot.api.web import request
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.legacy.migration import LegacyMigration, MigrationState

from .management_identity import dashboard_operator


PREFIX = "/astrbot_plugin_private_companion_v2/legacy"
MAX_REQUEST_BYTES = 8192

# V1 插件的目录名。V2 是 ``…_v2``，所以去掉后缀就是它的数据目录名。
V1_PLUGIN_DATA_NAME = "astrbot_plugin_private_companion"


class LegacyMigrationWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.discovery, ["GET"], "Locate the V1 data this installation could migrate"),
                (PREFIX + "/plan", self.plan, ["GET"], "Convert a V1 installation without writing anything"),
                (PREFIX + "/apply", self.apply, ["POST"], "Write the planned V2 settings")]

    # ── 定址 ───────────────────────────────────────────────────────────
    def _v1_root(self):
        """V1 数据目录在哪。

        先在配置里找显式路径；没有就按「V2 数据目录的同级目录里那个不带 _v2 的
        同名插件」去找——AstrBot 的 plugin_data 是平铺的，所以这是 V1 换 V2 时
        最常见的布局。两条路都不通就如实报错，不猜也不创建目录。
        """
        configured = (self.controller.config or {}).get("legacy", {})
        if isinstance(configured, dict):
            explicit = configured.get("v1_root")
            if type(explicit) is str and explicit.strip():
                from pathlib import Path
                return Path(explicit.strip()), "configured"

        from pathlib import Path
        base = Path(getattr(self.controller, "data_root", "."))
        # 数据根形如 …/plugin_data/astrbot_plugin_private_companion_v2，
        # 所以同级目录就是 …/plugin_data。
        for candidate in (base.parent / V1_PLUGIN_DATA_NAME, base / V1_PLUGIN_DATA_NAME):
            if candidate.is_dir():
                return candidate, "sibling"
        return base.parent / V1_PLUGIN_DATA_NAME, "missing"

    def _migration(self):
        root, origin = self._v1_root()
        return LegacyMigration(v1_root=root), root, origin

    @staticmethod
    def _fingerprint(root) -> str:
        """V1 目录的指纹：只取顶层条目的「名字 + 大小 + 修改时间」。

        用途只有一个——保证「试算」与「执行」面对的是同一份数据。所以不必读内容
        （那可能很贵），只要目录结构变了指纹就变。取不到（目录不存在）返回空串。
        """
        try:
            entries = sorted(
                (child.name, child.stat().st_size, int(child.stat().st_mtime))
                for child in root.iterdir()
            )
        except OSError:
            return ""
        digest = hashlib.sha256(repr(entries).encode("utf-8")).hexdigest()
        return digest

    # ── 路由 ───────────────────────────────────────────────────────────
    async def discovery(self):
        from .web_api import outcome_response
        if request.query:
            return outcome_response(Outcome.failed("legacy_request_invalid", "invalid legacy query"))
        return await self._run(lambda migration, root, session: self._discovery(migration, root, session))

    async def plan(self):
        from .web_api import outcome_response
        if request.query:
            return outcome_response(Outcome.failed("legacy_request_invalid", "invalid legacy query"))
        return await self._run(lambda migration, root, session: self._plan(migration, root, session))

    async def apply(self):
        from .web_api import outcome_response
        try:
            raw = await request.body()
            if len(raw) > MAX_REQUEST_BYTES:
                raise ValueError()
            arguments = json.loads(raw.decode("utf-8")) if raw else {}
            if type(arguments) is not dict or set(arguments) != {"plan_token"}:
                raise ValueError()
            if type(arguments["plan_token"]) is not str or not arguments["plan_token"]:
                raise ValueError()
        except (ValueError, UnicodeError, RecursionError):
            return outcome_response(Outcome.failed("legacy_request_invalid", "invalid apply request"))
        return await self._run(
            lambda migration, root, session: self._apply(migration, root, session, arguments["plan_token"])
        )

    async def _run(self, work):
        """统一取管理员身份、加载运行档、调用 work(migration, root, session)。"""
        from .web_api import outcome_response
        controller = self.controller
        async with controller._control_lock:
            try:
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "plugin is stopped")
                username = request.username
                if type(username) is not str or not username.strip():
                    raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
                session = controller.session or controller.last_session
                if session is None or controller.runtime is None:
                    raise TaskError("staging_not_initialized", "load the explicit V2 profile before migrating")
                dashboard_operator(controller.runtime, username, at=controller.now())
                migration, root, origin = self._migration()
                return outcome_response(work(migration, root, session))
            except TaskError as error:
                return outcome_response(Outcome.failed(error.code, str(error)))
            except (TypeError, ValueError, KeyError):
                return outcome_response(Outcome.failed("legacy_request_invalid", "invalid legacy arguments"))

    # ── 实现 ───────────────────────────────────────────────────────────
    def _discovery(self, migration, root, session):
        found = migration.discover()
        if not found.is_success:
            return found
        return Outcome.success({
            "v1_root": str(root),
            "findings": [item.document() for item in found.unwrap()],
            "scope_status": self._scope_status(session, migration.plan()),
        })

    def _plan(self, migration, root, session):
        planned = migration.plan()
        if not planned.is_success:
            return planned
        document = planned.unwrap().document()
        document["plan_token"] = self._fingerprint(root)
        document["scope_status"] = self._scope_status(session, planned)
        return Outcome.success(document)

    def _apply(self, migration, root, session, plan_token):
        """按当前 V1 目录重算一遍，再用宿主的配置服务写入。

        重算而不是相信客户端传来的改动：那是「先看后做」这个保证的全部意义所在。
        """
        if plan_token != self._fingerprint(root):
            return Outcome.failed(
                "legacy_plan_stale",
                "V1 数据在这期间发生了变化，请重新试算再执行。",
            )
        planned = migration.plan()
        if not planned.is_success:
            return planned
        plan = planned.unwrap()
        if not plan.migratable:
            return Outcome.failed(
                "legacy_nothing_to_migrate",
                "这份 V1 数据里没有可以自动迁移的来源。",
            )
        if not plan.intents:
            return Outcome.failed(
                "legacy_nothing_to_migrate",
                "试算没有产出任何可写入的设置。",
            )

        written: list[str] = []
        errors: list[dict] = []
        for intent in plan.intents:
            try:
                written.extend(self._apply_intent(intent, session))
            except TaskError as error:
                errors.append({"scope": intent.scope, "code": error.code, "reason": str(error)})
            except Exception as error:  # noqa: BLE001 - 一组失败不该拖垮其余组
                errors.append({"scope": intent.scope, "code": "legacy_apply_failed", "reason": str(error)})

        if not written and errors:
            return Outcome.failed(
                "legacy_apply_failed",
                "迁移没有写入任何设置：" + "；".join(item["reason"] for item in errors),
            )
        return Outcome.success({
            "v1_root": str(root),
            "written": written,
            "written_count": len(written),
            "change_count": plan.change_count,
            "differences": list(plan.differences),
            "errors": errors,
            "skipped": [
                {"source_id": item.source_id, "state": item.state, "detail": item.detail}
                for item in plan.findings
                if item.state not in (MigrationState.READY.value, MigrationState.ABSENT.value)
            ],
        })

    def _apply_intent(self, intent, session):
        """把一条 ConfigIntent 交给配置服务写。

        用 ``patch`` 而不是绕过它直接写表：patch 会带上操作者身份、写变更记录、
        检查 edit token——绕过它等于让这批改动在审计里凭空出现。
        """
        service = session.application.configuration
        operator = self._operator()
        target = self._scope_target(session, intent)
        if target is None:
            raise TaskError("legacy_scope_unavailable", f"当前运行档没有 {intent.scope} 这个作用域")

        snapshot = service._snapshot(operator, target, intent.group_id, self.controller.now(), "configuration.read")
        changes = {f"{intent.group_id}.{field}": value for field, value in intent.changes.items()}
        # operation 的属主是**分组声明的 owner_id**，不是分组名——patch 会拿
        # `registry.group(group_id)[0].owner_id` 去比，写成分组名必被判成
        # operation_scope_mismatch（这条原先也从未被测试走到）。
        owner_id = service.registry.group(intent.group_id)[0].owner_id
        operation = self._operation(intent, target, owner_id)
        receipt = service.patch(
            operator, target=target, group_id=intent.group_id, operation=operation,
            expected_edit_token=snapshot.edit_token, changes=changes,
            observed_at=self.controller.now(),
        )
        if not receipt.is_success:
            raise TaskError(receipt.failure.code, receipt.failure.reason)
        return list(receipt.unwrap().changed_fields)

    def _operator(self):
        from astrbot.api.web import request
        return dashboard_operator(self.controller.runtime, request.username, at=self.controller.now())

    # ── 作用域可用性 ───────────────────────────────────────────────────
    def _scope_target(self, session, intent):
        """作用域 → 配置目标。

        目标从**会话的管线上下文**推出来（``session.profile.target``）——这与
        ``configuration_api`` 的取法相同。单目标下它是固定 profile 的那个上下文；
        多目标下这些路由按角色挂载，``TargetControllerView.session`` 给的就是
        该目标 + 该角色的上下文。

        以前这里传的是 ``controller.context``（宿主上下文，只有注册路由那套接口），
        于是目标推导必然 AttributeError、被下面兜底成 ``legacy_apply_failed``：
        界面上看着走到了执行，实际一条都没写进去。
        """
        if intent.scope == "role.state":
            from companion_v2.role_work.state.configuration import target_for
        elif intent.scope == "proactive.contact":
            from companion_v2.proactive.configuration import target_for
        else:
            return None
        try:
            return target_for(session.profile.target)
        except (AttributeError, KeyError, TypeError):
            return None

    def _scope_status(self, session, planned):
        """试算阶段就回答「这些作用域在这份运行档里能不能写」。

        原先只有执行时才会以 ``legacy_scope_unavailable`` 失败——用户点了执行才知道。
        判据两条：作用域有没有目标推导、分组有没有注册在配置注册表里。
        """
        if not planned.is_success:
            return []
        status = []
        registry = session.application.configuration.registry
        for intent in planned.unwrap().intents:
            target = self._scope_target(session, intent)
            if target is None:
                status.append({"scope": intent.scope, "group_id": intent.group_id,
                               "available": False, "reason": "unsupported_scope"})
                continue
            try:
                registry.group(intent.group_id)
            except Exception:  # noqa: BLE001 - 注册表用 ConfigurationError 表示未知分组
                status.append({"scope": intent.scope, "group_id": intent.group_id,
                               "available": False, "reason": "group_not_registered"})
                continue
            status.append({"scope": intent.scope, "group_id": intent.group_id, "available": True, "reason": ""})
        return status

    def _operation(self, intent, target, owner_id):
        """为这一次迁移造一条 operation。

        operation_id 必须唯一：配置变更表的 operation_id 是主键，重复提交会被当成
        重放而静默返回旧结果——迁移场景里那意味着「点了执行却没写进去」。
        所以带上一段时间戳与作用域名，而不是一个固定的 id。

        ``owner_id`` 来自分组声明（``registry.group(...)[0].owner_id``），
        作用域用 **目标的授权作用域**——两者都与 ``configuration/service.py``
        的 patch 校验逐字对齐。
        """
        from companion_v2.foundation.refs import OperationRef, VersionRef
        stamp = self.controller.now().strftime("%Y%m%d%H%M%S%f")
        scope = intent.scope.replace(".", "-")
        operation_id = f"legacy-{scope}-{stamp}"
        return OperationRef(operation_id, owner_id, target.authorization_scope,
                            VersionRef(operation_id, 1), operation_id)

