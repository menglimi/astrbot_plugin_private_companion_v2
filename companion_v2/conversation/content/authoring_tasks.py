"""Dedicated model route for native Content creation."""

from companion_v2.execution.models import Lane
from companion_v2.model_gateway.models import ModelTaskProfile


DRAFT_KIND = "content.authoring.draft"
WRITING_KINDS = frozenset({DRAFT_KIND})

PROMPTS = {
    DRAFT_KIND: "以当前角色完成用户明确要求的作品，延续时保持既有人物、主线与人工修订。",
}


def authoring_profiles(provider, *, draft_tokens=4096):
    return (ModelTaskProfile(DRAFT_KIND, Lane.BACKGROUND, provider, PROMPTS[DRAFT_KIND],
                             max_output_tokens=draft_tokens, timeout_seconds=180),)


__all__ = ["DRAFT_KIND", "PROMPTS", "WRITING_KINDS", "authoring_profiles"]
