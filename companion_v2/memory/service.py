"""Memory composition without host SDK imports or a second fact database."""

from companion_v2.capabilities.ownership import DEFAULT_MEMORY_OWNER, delegated_memory

from .context import MemoryContext
from .models import MemoryPolicy
from .query import MemoryQuery
from .writer import MemoryWriter
from .experiences import MemoryExperiences
from .configuration import MemorySettings


class MemoryService:
    def __init__(self, tasks, *, policy=MemoryPolicy(), configuration=None, owner=DEFAULT_MEMORY_OWNER):
        self.tasks, self.runtime, self.policy = tasks, tasks.runtime, policy
        # 「记忆对外由谁提供」由宿主注入的一个只读端口回答；缺省是 V2 自己。这一个
        # 端口同时管住注入（MemoryContext）与工具目录（LocalRoleTools），两处读的
        # 是同一个判定，所以不会出现「一边让位、另一边还在写」的分裂状态。
        self.owner = owner
        self.settings = MemorySettings(configuration) if configuration is not None else None
        self.writer = MemoryWriter(tasks, policy=policy, settings=self.settings)
        self.query = MemoryQuery(self.writer)
        self.context = MemoryContext(self)
        self.experiences = MemoryExperiences(self.writer)
        self.activity = None
        self.game = None

    def delegated(self) -> bool:
        """这段时期记忆的对外表达是否已经让给别家插件。

        保留成服务上的一个方法，是为了让调用方不再需要知道「端口在 ``owner``
        字段里」——注入侧（``MemoryContext``）与工具侧（``LocalRoleTools``）问的
        是同一句话，一方改了判定另一方不会漏掉。判定每次重新求值，不缓存。
        """

        return delegated_memory(self.owner)

    def attach_life(self, life_context, *, require_running=None):
        """Bind real life receipt production; callers advance authenticated contexts."""
        from .activity_ingestion import MemoryActivityIngestion
        activity = MemoryActivityIngestion(self, life_context, require_running=require_running)
        if self.activity is not None:
            self.activity.close()
        self.activity = activity
        return self.activity

    def attach_game(self, external, *, require_running=None):
        from .game_ingestion import MemoryGameIngestion
        game = MemoryGameIngestion(self, external, require_running=require_running)
        if self.game is not None:
            self.game.close()
        self.game = game
        return game

    def bind_query_wire_v1(self, **binding):
        """Construct an explicitly bound query adapter for a trusted host registry."""
        from .wire import MemoryQueryWireV1
        return MemoryQueryWireV1(self, **binding)

    def bind_proposal_wire_v1(self, **binding):
        """Bind synchronous commands to an explicit trusted host lifecycle."""
        from .proposal_wire import MemoryProposalWireV1
        return MemoryProposalWireV1(self, **binding)

    def bind_operation_wire_v1(self, **binding):
        from .wire_operations import MemoryOperationWireV1
        return MemoryOperationWireV1(self, **binding)

    def attach_messages(self, messages):
        from .sent_sources import ConfirmedReplySources
        if messages.tasks is not self.tasks:
            raise ValueError("memory reply sources must use the original task owner")
        self.writer.access.sent_sources = ConfirmedReplySources(self, messages)
