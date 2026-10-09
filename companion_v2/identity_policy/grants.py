"""Shared grant lineages for bootstrap authority and explicit person decisions.

Bootstrap creates grants only once. Conversation and proactive permission may
subsequently be managed per person; host assembly preserves those decisions.
Other host grants, including Screen preparation, retain their fixed contract.
"""

from __future__ import annotations


# One grant per configured capability: ``<prefix><capability>``.
STAGING_CAPABILITY_GRANT_PREFIX = "astrbot-staging-grant:"
# The fixed delivery lineage. The first grant uses the bare name and every
# re-issued successor appends ``:<n>`` -- see ``staging_delivery.delivery_grant_id``.
DELIVERY_GRANT_ID = "astrbot-staging-delivery"
# One grant per Screen action: ``<prefix><capability>``.
STAGING_SCREEN_GRANT_PREFIX = "astrbot-staging-screen:"
# Every lineage a configuration document owns, as exact prefixes.
CONFIGURATION_GRANT_PREFIXES = (STAGING_CAPABILITY_GRANT_PREFIX, DELIVERY_GRANT_ID,
                                STAGING_SCREEN_GRANT_PREFIX, "host-multi-grant:")
PERSON_PERMISSION_GRANT_PREFIX = "acquaintance-grant:"
