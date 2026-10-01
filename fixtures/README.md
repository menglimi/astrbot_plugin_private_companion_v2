# Fixtures

G0 fixtures must be synthetic and non-sensitive. No production database, message body,
device credential, image original, or host configuration belongs in this directory.

`astrbot_staging.example.json` is a synthetic preview configuration for the
trusted staging bootstrap. Its account IDs, persona/provider fingerprints and
budgets come from local test doubles. They are not live host settings. Validate
its format with `tools/validate_staging_config.py`; see the
[bootstrap slice](../docs/CORE_ASTRBOT_STAGING_BOOTSTRAP_SLICE.md) for authority and lifecycle semantics.
