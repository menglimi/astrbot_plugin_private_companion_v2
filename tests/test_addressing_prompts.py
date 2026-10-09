import unittest

from companion_v2.conversation.addressing import (
    ADDRESSING_INSTRUCTION,
    ADDRESSING_REFLECTION_INSTRUCTION,
)
from companion_v2.conversation.foreground import EvidencePromptCompiler, ForegroundContextAssembler
from companion_v2.conversation.group_context import INSTRUCTION as GROUP_INSTRUCTION
from companion_v2.memory.prompts import REFLECTION_INSTRUCTION

from tests.test_foreground_conversation import (
    event,
    identity_directory,
    publish,
    reference,
    role_binding,
)
from companion_v2.sources.repositories import SourceRepository
from companion_v2.storage.runtime import StorageRuntime
from tempfile import TemporaryDirectory
from pathlib import Path


class AddressingPromptTests(unittest.TestCase):
    def test_conversation_keeps_addressing_as_model_judgement(self):
        self.assertIn("结合本轮语境自行判断", ADDRESSING_INSTRUCTION)
        self.assertIn("拿不准时省略称呼", GROUP_INSTRUCTION)
        self.assertNotIn("必须使用", ADDRESSING_INSTRUCTION)

    def test_reflection_requires_source_bounded_review(self):
        self.assertIn("反思阶段要复核称呼是否合适", ADDRESSING_REFLECTION_INSTRUCTION)
        self.assertIn("证据不足", REFLECTION_INSTRUCTION)
        self.assertIn("一次称呼不自动形成长期偏好", REFLECTION_INSTRUCTION)

    def test_foreground_compiler_always_includes_addressing_judgement(self):
        with TemporaryDirectory(prefix="companion-v2-addressing-") as temporary:
            runtime = StorageRuntime.open(
                data_root=Path(temporary) / "v2-data",
                installation_id="installation-alpha",
            )
            sources = SourceRepository(runtime)
            source = reference()
            publish(sources, source)
            record = sources.read(
                source,
                resolved=identity_directory().resolve_authenticated(
                    event(source).principal,
                    observed_at=event(source).received_at,
                ).unwrap(),
                capability="conversation.read",
                observed_at=event(source).received_at,
                authorizer=identity_directory(),
            ).unwrap()
            context = ForegroundContextAssembler().seal(primary=record)
            request = EvidencePromptCompiler().compile(
                event=event(source),
                role_instruction="Stay in character.",
                role_binding=role_binding(),
                context=context,
            )
            self.assertIn(ADDRESSING_INSTRUCTION, request.instruction)
            self.assertIn("pc_reaction_expression", request.instruction)
            self.assertIn("Express the emotion naturally.", request.instruction)
            runtime.close()


if __name__ == "__main__":
    unittest.main()
