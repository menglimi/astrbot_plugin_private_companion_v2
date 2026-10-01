"""Unified state and platform-presentation options with exact private grants."""

from companion_v2.configuration.models import ApplyMode, ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.configuration.registry import FieldDefinition, ValueKind
from companion_v2.execution.models import digest
from companion_v2.foundation.refs import ScopeKind
from companion_v2.identity_policy.models import AuthorizationTier, GrantState
from companion_v2.identity_policy.personas import PersonaDirectory
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from .cycle import DEFAULTS as CYCLE_DEFAULTS, validate_settings
from .humanized import DEFAULTS as HUMANIZED_DEFAULTS, LIMITS as HUMANIZED_LIMITS
from .humanized import validate_settings as validate_humanized
from .settings_scope import PhysicalSettingsOwner
from companion_v2.agenda.planning_config import DEFAULTS as PLANNING_DEFAULTS, MAXIMUMS as PLANNING_MAXIMUMS
from companion_v2.agenda.planning_config import WEATHER_MAX_AGE_MINIMUM
from companion_v2.agenda.planning_config import validate_settings as validate_planning

GROUP = "role.state"
OWNER = "role.state.settings"
DEFAULTS = {"enabled": False, "maintenance_minutes": 30, "hunger_enabled": True,
    "health_enabled": True, "cycle_enabled": False, "calendar_enabled": False,
    "home_show_energy": True, "home_show_health": True, "home_show_hunger": True,
    "home_show_sleep": True, "home_show_cycle": True, "home_show_busy": True,
    "home_show_location": True,
    # Refresh without a stop/start toggle. Four seconds reduces request frequency;
    # actual expiry and flicker depend on the QQ client and need field validation.
    "typing_enabled": False, "typing_refresh_seconds": 4, "presence_enabled": False,
    "online_status_enabled": False,
    # Bounded mood dynamics. The probability shape the update, the half-life shapes the
    # regression, and the step cap keeps one message from swinging an axis to an extreme.
    # Retained for stored-config compatibility; role simulation is always persona-wide.
    "mood_enabled": False, "mood_cross_window": True, "mood_update_probability": 0.6,
    "mood_interest_window_minutes": 120, "mood_update_max_delta": 2,
    "mood_decay_half_life_minutes": 90, "mood_neutral_band": 3,
    # Bounded humanised expression plus the V1 daily-review cadence/retention.
    **HUMANIZED_DEFAULTS, **CYCLE_DEFAULTS, **PLANNING_DEFAULTS}
MOOD_LIMITS = {"mood_interest_window_minutes": (5, 1440), "mood_update_max_delta": (1, 4),
    "mood_decay_half_life_minutes": (5, 1440), "mood_neutral_band": (1, 4)}
PERMISSIONS = {"enabled": ("role.state.read", "role.state.maintain"),
    "calendar_enabled": ("calendar.read", "calendar.write"),
    "typing_enabled": ("platform.typing",), "presence_enabled": ("platform.presence",),
    "online_status_enabled": ("platform.presence",)}


def validate_mood_settings(values):
    """Mood bounds are closed here too, so a page or direct write cannot widen them."""
    for name, (low, high) in MOOD_LIMITS.items():
        value = values[name]
        if type(value) is not int or not low <= value <= high:
            raise ConfigurationError("state_mood_settings", f"{name} must be an integer from {low} to {high}")
    probability = values["mood_update_probability"]
    if type(probability) not in (int, float) or not 0 <= probability <= 1:
        raise ConfigurationError("state_mood_settings", "mood_update_probability must be a fraction from 0 to 1")
    for name in ("mood_enabled", "mood_cross_window"):
        if type(values[name]) is not bool:
            raise ConfigurationError("state_mood_settings", f"{name} must be a boolean")


def target_for(context):
    return ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW, context.role_binding.role, context.scope)


def configuration_fields():
    fields = []
    for name, value in DEFAULTS.items():
        kind = (ValueKind.BOOLEAN if type(value) is bool else ValueKind.PROBABILITY if name == "mood_update_probability"
                else ValueKind.INTEGER if type(value) is int else ValueKind.TEXT)
        bounds = {}
        if name in MOOD_LIMITS:
            bounds = {"minimum": MOOD_LIMITS[name][0], "maximum": MOOD_LIMITS[name][1]}
        elif name in HUMANIZED_LIMITS:
            bounds = {"minimum": HUMANIZED_LIMITS[name][0], "maximum": HUMANIZED_LIMITS[name][1]}
        elif name == "planning_weather_max_age_minutes":
            # Bounded here too, so the registry cannot advertise a value validate_settings rejects.
            bounds = {"minimum": WEATHER_MAX_AGE_MINIMUM, "maximum": PLANNING_MAXIMUMS[name]}
        elif name == "cycle_discomfort_chance":
            bounds = {"minimum": 0, "maximum": 100}
        elif kind is ValueKind.INTEGER:
            phase_energy = name.startswith("cycle_") and name.endswith("_energy")
            bounds = {"minimum": -50 if phase_energy else 1,
                      "maximum": PLANNING_MAXIMUMS.get(name, 30 if name.startswith("cycle_")
                                                       else 10 if name == "typing_refresh_seconds" else 1440)}
        fields.append(FieldDefinition(GROUP + "." + name, GROUP, GROUP, kind, value,
            layers=(ConfigLayer.WINDOW,), apply_mode=ApplyMode.IMMEDIATE, core_only=True, owner_id=OWNER, **bounds))
    return tuple(fields)


class StateConfigurationOwner(PhysicalSettingsOwner):
    owner_id = OWNER

    def preview_set(self, target, fields, *, changes):
        result = super().preview_set(target, fields, changes=changes)
        values = {key.rsplit(".", 1)[-1]: field.value for key, field in result.items()}
        validate_settings(values)
        validate_planning(values)
        validate_mood_settings(values)
        validate_humanized(values)
        return result

    def write(self, target, fields, *, changes, reset, expected_revision, observed_at):
        with self.runtime.transaction():
            route = PersonaDirectory(self.runtime).resolve(target.scope, observed_at=observed_at)
            if (target.scope.kind is not ScopeKind.PRIVATE or not route.is_success
                    or route.unwrap().binding.role != target.role or route.unwrap().route.user is None):
                raise ConfigurationError("state_target_changed", "select the current private role and participant")
            participant = route.unwrap().route.user
            proposed = {key.rsplit(".", 1)[-1]: field.value for key, field in self.read(target, fields).fields.items()}
            proposed.update({key.rsplit(".", 1)[-1]: value for key, value in changes.items()})
            proposed.update({key.rsplit(".", 1)[-1]: DEFAULTS[key.rsplit(".", 1)[-1]] for key in reset})
            validate_settings(proposed)
            validate_planning(proposed)
            validate_mood_settings(proposed)
            validate_humanized(proposed)
            saved = super().write(target, fields, changes=changes, reset=reset,
                                  expected_revision=expected_revision, observed_at=observed_at)
            identity = PersistentIdentityDirectory(self.runtime)
            changed = {key.rsplit(".", 1)[-1] for key in (*changes, *reset)}
            for action in {action for actions in PERMISSIONS.values() for action in actions}:
                options = [name for name, actions in PERMISSIONS.items() if action in actions]
                if not changed.intersection(options):
                    continue
                prefix = "state-grant:" + digest([target.key, participant, action]) + ":"
                for grant in identity.snapshot().grants:
                    if grant.grant_id.startswith(prefix) and grant.state is GrantState.ACTIVE:
                        identity.revoke_grant(grant.grant_id, revoked_at=observed_at,
                                              expected_revision=identity.revision)
                if any(proposed[name] for name in options):
                    identity.issue_grant(grant_id=prefix + str(identity.revision), subject=participant,
                        scope=target.scope, capability=action, tier=AuthorizationTier.STANDARD,
                        valid_from=observed_at, expected_revision=identity.revision)
            return saved
