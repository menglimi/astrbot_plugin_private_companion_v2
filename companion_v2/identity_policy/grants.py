"""Names for the grant lineages that are not operator intent.

An operator can only *own* a grant this project's own management pages issue.
Some grants are instead materialised from a profile configuration document and
re-issued on every load: ``staging_bootstrap.initialize`` writes one grant per
``config.capabilities`` entry, the delivery authorization writes the fixed
delivery lineage, and Screen preparation writes one per Screen action.

Those are re-created (and, for Screen, *verified*) on each bootstrap, so a page
that revoked one would show "已撤销" while the capability keeps working -- and
Screen preparation would fail outright with ``staging_screen_grant_changed``.
Any surface that classifies grants therefore has to recognise these lineages,
and it has to recognise them from one place: two copies of the same literal
drift apart, and a drifted copy silently classifies a derived grant as
page-managed. The writers and the classifier both read this module instead.
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
                                STAGING_SCREEN_GRANT_PREFIX)
