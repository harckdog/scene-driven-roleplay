"""Typed schema and validation for roleplay character profiles."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


ROLE_SCHEMA_VERSION = 2
_ROLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_AVATAR_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})


class RoleProfileError(ValueError):
    """Raised when a character profile does not satisfy the schema."""


@dataclass(frozen=True)
class Identity:
    """Stable public identity information for a character."""

    full_name: str
    aliases: tuple[str, ...]
    age_description: str | None
    height: str | None
    occupation: str | None
    appearance: str | None
    affiliation: tuple[str, ...]


@dataclass(frozen=True)
class Relationship:
    """A canonical relationship to another character."""

    name: str
    relation: str
    attitude: str | None


@dataclass(frozen=True)
class Canon:
    """Canonical background and knowledge boundaries."""

    background: str
    relationships: tuple[Relationship, ...]
    knowledge_boundary: tuple[str, ...]


@dataclass(frozen=True)
class Personality:
    """Core personality constraints for roleplay responses."""

    core_traits: tuple[str, ...]
    motivations: tuple[str, ...]
    fears: tuple[str, ...]
    contradictions: tuple[str, ...]
    likes: tuple[str, ...]
    dislikes: tuple[str, ...]


@dataclass(frozen=True)
class SpeechExample:
    """An original example of the character's response style."""

    context: str
    response: str


@dataclass(frozen=True)
class Speech:
    """Speech style and prohibited phrasing."""

    register: str
    sentence_length: str | None
    verbal_habits: tuple[str, ...]
    address_user: str | None
    forbidden_patterns: tuple[str, ...]
    examples: tuple[SpeechExample, ...]


@dataclass(frozen=True)
class Behavior:
    """Behavioral constraints separate from spoken style."""

    initiative_level: str
    emotional_expression: str | None
    relationship_pacing: str | None
    high_intimacy_expression: str | None
    conflict_style: str | None
    help_style: str | None
    interaction_modes: tuple["InteractionMode", ...]
    never_do: tuple[str, ...]


@dataclass(frozen=True)
class InteractionMode:
    """Situation-specific tone and behavior guidance for a role."""

    name: str
    tone: str
    behavior: tuple[str, ...]


@dataclass(frozen=True)
class RoleplaySettings:
    """Static presentation settings for a role."""

    default_scene: str | None
    allow_scene_description: bool
    narration_style: str | None
    action_format: str | None
    user_role: str | None
    default_interaction_mode: str | None
    opening_message: str | None
    message_split: "MessageSplitSettings"
    knowledge_base_id: str | None
    expression_policy: "ExpressionPolicy"
    state_policy: "StatePolicy"


@dataclass(frozen=True)
class MessageSplitSettings:
    """Optional multi-bubble response and presentation settings."""

    enabled: bool
    max_messages: int
    display_interval_ms: int


@dataclass(frozen=True)
class ExpressionPolicy:
    """Optional role-specific calibration for contextual sticker expressions."""

    resolver_mode: str | None
    intensity_scale: str
    medium_channels: int
    high_channels: int
    extreme_channels: int
    defensive_protest_affect: str | None
    intimacy_startle_affect: str | None
    anger_requires_visible_evidence: bool


@dataclass(frozen=True)
class StatePolicy:
    """Optional, ordinal runtime-state calibration for a role."""

    enabled: bool
    default_reactivity: str
    default_expressivity: str
    default_recovery: str
    reactivity: dict[str, str]
    expressivity: dict[str, str]
    recovery: dict[str, str]
    familiarity: str
    trust: str
    comfort: str
    romantic_status: str
    implicit_updates: bool


@dataclass(frozen=True)
class MemoryPolicy:
    """Static guidance for future role-specific memory extraction."""

    remember: tuple[str, ...]
    ignore: tuple[str, ...]


@dataclass(frozen=True)
class ProfileSummary:
    """A short authored runtime fact or boundary."""

    summary: str


@dataclass(frozen=True)
class RuntimeIdentity:
    name: str
    user_address: str
    relationship: ProfileSummary
    stable_character: ProfileSummary


@dataclass(frozen=True)
class GenerationBoundary:
    current_reality: str
    scene_use: str
    knowledge: str


@dataclass(frozen=True)
class RoleProfile:
    """Validated canonical definition of one roleplay character."""

    schema_version: int
    id: str
    display_name: str
    source: str | None
    language: str
    identity: Identity
    canon: Canon
    personality: Personality
    speech: Speech
    behavior: Behavior
    roleplay: RoleplaySettings
    memory_policy: MemoryPolicy
    sticker_pack: str | None
    speech_habit_pack: str | None
    avatar: str | None
    runtime_identity: RuntimeIdentity | None = None
    generation_boundary: GenerationBoundary | None = None

    @classmethod
    def from_mapping(cls, data: object) -> "RoleProfile":
        """Build a profile from decoded YAML or JSON data.

        Args:
            data: Parsed document content.

        Returns:
            Validated typed role profile.

        Raises:
            RoleProfileError: If a required field is missing or invalid.
        """
        root = _mapping(data, "profile")
        version = _required_int(root, "schema_version")
        if version not in {1, ROLE_SCHEMA_VERSION}:
            raise RoleProfileError(
                f"schema_version: expected 1 or {ROLE_SCHEMA_VERSION}, received {version}"
            )

        role_id = _required_str(root, "id")
        if not _ROLE_ID_PATTERN.fullmatch(role_id):
            raise RoleProfileError(
                "id: use lowercase letters, digits, and underscores; it must start with a letter"
            )

        if version == 2:
            return _profile_v2(root, role_id)

        identity_data = _mapping(_required(root, "identity"), "identity")
        canon_data = _mapping(_required(root, "canon"), "canon")
        personality_data = _mapping(_required(root, "personality"), "personality")
        speech_data = _mapping(_required(root, "speech"), "speech")
        behavior_data = _mapping(_required(root, "behavior"), "behavior")
        roleplay_data = _mapping(_required(root, "roleplay"), "roleplay")
        memory_data = _mapping(_required(root, "memory_policy"), "memory_policy")

        return cls(
            schema_version=version,
            id=role_id,
            display_name=_required_str(root, "display_name"),
            source=_optional_str(root, "source"),
            language=_required_str(root, "language"),
            identity=Identity(
                full_name=_required_str(identity_data, "full_name", "identity"),
                aliases=_string_list(identity_data.get("aliases", []), "identity.aliases"),
                age_description=_optional_str(identity_data, "age_description", "identity"),
                height=_optional_str(identity_data, "height", "identity"),
                occupation=_optional_str(identity_data, "occupation", "identity"),
                appearance=_optional_str(identity_data, "appearance", "identity"),
                affiliation=_string_list(identity_data.get("affiliation", []), "identity.affiliation"),
            ),
            canon=Canon(
                background=_required_str(canon_data, "background", "canon"),
                relationships=_relationships(canon_data.get("relationships", [])),
                knowledge_boundary=_string_list(
                    canon_data.get("knowledge_boundary", []),
                    "canon.knowledge_boundary",
                ),
            ),
            personality=Personality(
                core_traits=_string_list(
                    _required(personality_data, "core_traits", "personality"),
                    "personality.core_traits",
                ),
                motivations=_string_list(personality_data.get("motivations", []), "personality.motivations"),
                fears=_string_list(personality_data.get("fears", []), "personality.fears"),
                contradictions=_string_list(
                    personality_data.get("contradictions", []),
                    "personality.contradictions",
                ),
                likes=_string_list(personality_data.get("likes", []), "personality.likes"),
                dislikes=_string_list(personality_data.get("dislikes", []), "personality.dislikes"),
            ),
            speech=Speech(
                register=_required_str(speech_data, "register", "speech"),
                sentence_length=_optional_str(speech_data, "sentence_length", "speech"),
                verbal_habits=_string_list(speech_data.get("verbal_habits", []), "speech.verbal_habits"),
                address_user=_address_user(speech_data.get("address_user")),
                forbidden_patterns=_string_list(
                    speech_data.get("forbidden_patterns", []),
                    "speech.forbidden_patterns",
                ),
                examples=_speech_examples(speech_data.get("examples", [])),
            ),
            behavior=Behavior(
                initiative_level=_required_str(behavior_data, "initiative_level", "behavior"),
                emotional_expression=_optional_str(
                    behavior_data,
                    "emotional_expression",
                    "behavior",
                ),
                relationship_pacing=_optional_str(
                    behavior_data,
                    "relationship_pacing",
                    "behavior",
                ),
                high_intimacy_expression=_optional_str(
                    behavior_data,
                    "high_intimacy_expression",
                    "behavior",
                ),
                conflict_style=_optional_str(behavior_data, "conflict_style", "behavior"),
                help_style=_optional_str(behavior_data, "help_style", "behavior"),
                interaction_modes=_interaction_modes(behavior_data.get("interaction_modes", {})),
                never_do=_string_list(behavior_data.get("never_do", []), "behavior.never_do"),
            ),
            roleplay=RoleplaySettings(
                default_scene=_optional_str(roleplay_data, "default_scene", "roleplay"),
                allow_scene_description=_optional_bool(
                    roleplay_data,
                    "allow_scene_description",
                    "roleplay",
                    default=True,
                ),
                narration_style=_optional_str(roleplay_data, "narration_style", "roleplay"),
                action_format=_optional_str(roleplay_data, "action_format", "roleplay"),
                user_role=_optional_str(roleplay_data, "user_role", "roleplay"),
                default_interaction_mode=_optional_str(
                    roleplay_data, "default_interaction_mode", "roleplay"
                ),
                opening_message=_optional_str(roleplay_data, "opening_message", "roleplay"),
                message_split=_message_split_settings(roleplay_data.get("message_split")),
                knowledge_base_id=_optional_knowledge_base_id(roleplay_data.get("knowledge_base_id")),
                expression_policy=_expression_policy(roleplay_data.get("expression_policy")),
                state_policy=_state_policy(roleplay_data.get("state_policy")),
            ),
            memory_policy=MemoryPolicy(
                remember=_string_list(memory_data.get("remember", []), "memory_policy.remember"),
                ignore=_string_list(memory_data.get("ignore", []), "memory_policy.ignore"),
            ),
            sticker_pack=_optional_identifier(root, "sticker_pack"),
            speech_habit_pack=_optional_identifier(root, "speech_habit_pack"),
            avatar=_optional_avatar(root),
        )


def _relationship_summary(data: dict[str, Any]) -> str:
    """Accept the flat v2 summary or a newer teacher-scoped relationship block."""
    if "summary" in data:
        return _required_str(data, "summary", "runtime_identity.relationship")
    sensei = data.get("sensei")
    if isinstance(sensei, dict):
        return _required_str(sensei, "summary", "runtime_identity.relationship.sensei")
    raise RoleProfileError(
        "runtime_identity.relationship.summary: required field is missing "
        "(or provide runtime_identity.relationship.sensei.summary)"
    )


def _profile_v2(root: dict[str, Any], role_id: str) -> RoleProfile:
    """Parse the compact runtime profile while retaining safe legacy accessors."""
    runtime = _mapping(_required(root, "runtime_identity"), "runtime_identity")
    relationship = _mapping(_required(runtime, "relationship", "runtime_identity"), "runtime_identity.relationship")
    stable = _mapping(_required(runtime, "stable_character", "runtime_identity"), "runtime_identity.stable_character")
    boundary = _mapping(_required(root, "generation_boundary"), "generation_boundary")
    roleplay = _mapping(_required(root, "roleplay"), "roleplay")
    memory = _mapping(_required(root, "memory_policy"), "memory_policy")

    identity = RuntimeIdentity(
        name=_required_str(runtime, "name", "runtime_identity"),
        user_address=_required_str(runtime, "user_address", "runtime_identity"),
        relationship=ProfileSummary(_relationship_summary(relationship)),
        stable_character=ProfileSummary(_required_str(stable, "summary", "runtime_identity.stable_character")),
    )
    generation_boundary = GenerationBoundary(
        current_reality=_required_str(boundary, "current_reality", "generation_boundary"),
        scene_use=_required_str(boundary, "scene_use", "generation_boundary"),
        knowledge=_required_str(boundary, "knowledge", "generation_boundary"),
    )
    display_name = _required_str(root, "display_name")
    if identity.name != display_name:
        raise RoleProfileError("runtime_identity.name: must match display_name")
    user_role = _required_str(roleplay, "user_role", "roleplay")
    if identity.user_address != user_role:
        raise RoleProfileError("runtime_identity.user_address: must match roleplay.user_role")

    return RoleProfile(
        schema_version=2,
        id=role_id,
        display_name=display_name,
        source=_optional_str(root, "source"),
        language=_required_str(root, "language"),
        # The v1-shaped fields below keep existing non-generator services safe.
        # The active Scene-only Generator reads only the authored v2 fields.
        identity=Identity(identity.name, (), None, None, None, None, ()),
        canon=Canon(identity.stable_character.summary, (), (generation_boundary.knowledge,)),
        personality=Personality((identity.stable_character.summary,), (), (), (), (), ()),
        speech=Speech("自然对话", None, (), identity.user_address, (), ()),
        behavior=Behavior("contextual", None, identity.relationship.summary, None, None, None, (), ()),
        roleplay=RoleplaySettings(
            default_scene=None,
            allow_scene_description=True,
            narration_style=_required_str(roleplay, "narration_style", "roleplay"),
            action_format=_required_str(roleplay, "action_format", "roleplay"),
            user_role=user_role,
            default_interaction_mode=None,
            opening_message=None,
            message_split=_message_split_settings(roleplay.get("message_split")),
            knowledge_base_id=_optional_knowledge_base_id(roleplay.get("knowledge_base_id")),
            expression_policy=_expression_policy(None),
            state_policy=_state_policy(None),
        ),
        memory_policy=MemoryPolicy(
            remember=_string_list(_required(memory, "remember", "memory_policy"), "memory_policy.remember"),
            ignore=_string_list(memory.get("ignore", []), "memory_policy.ignore"),
        ),
        sticker_pack=role_id,
        speech_habit_pack=None,
        avatar=_optional_avatar(root),
        runtime_identity=identity,
        generation_boundary=generation_boundary,
    )


def _required(data: dict[str, Any], key: str, prefix: str = "") -> object:
    """Return a required mapping value or raise a field-specific error."""
    if key not in data:
        field = f"{prefix}.{key}" if prefix else key
        raise RoleProfileError(f"{field}: required field is missing")
    return data[key]


def _mapping(value: object, field: str) -> dict[str, Any]:
    """Validate one mapping value."""
    if not isinstance(value, dict):
        raise RoleProfileError(f"{field}: expected an object")
    return value


def _required_str(data: dict[str, Any], key: str, prefix: str = "") -> str:
    """Validate a required non-empty string."""
    field = f"{prefix}.{key}" if prefix else key
    value = _required(data, key, prefix)
    if not isinstance(value, str) or not value.strip():
        raise RoleProfileError(f"{field}: expected a non-empty string")
    return value.strip()


def _optional_str(data: dict[str, Any], key: str, prefix: str = "") -> str | None:
    """Validate an optional string."""
    field = f"{prefix}.{key}" if prefix else key
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RoleProfileError(f"{field}: expected a non-empty string when provided")
    return value.strip()


def _optional_identifier(data: dict[str, Any], key: str) -> str | None:
    """Validate an optional lowercase identifier used for local registries."""
    value = _optional_str(data, key)
    if value is not None and not _ROLE_ID_PATTERN.fullmatch(value):
        raise RoleProfileError(
            f"{key}: use lowercase letters, digits, and underscores; it must start with a letter"
        )
    return value


def _interaction_modes(value: object) -> tuple[InteractionMode, ...]:
    """Validate optional named interaction modes while preserving YAML order."""
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise RoleProfileError("behavior.interaction_modes: expected an object")

    modes: list[InteractionMode] = []
    for name, raw_mode in value.items():
        if not isinstance(name, str) or not name.strip():
            raise RoleProfileError("behavior.interaction_modes: mode names must be non-empty strings")
        mode = _mapping(raw_mode, f"behavior.interaction_modes.{name}")
        modes.append(
            InteractionMode(
                name=name.strip(),
                tone=_required_str(mode, "tone", f"behavior.interaction_modes.{name}"),
                behavior=_string_list(
                    mode.get("behavior", []),
                    f"behavior.interaction_modes.{name}.behavior",
                ),
            )
        )
    return tuple(modes)


def _message_split_settings(value: object) -> MessageSplitSettings:
    """Validate optional multi-message settings with single-message defaults."""
    if value is None:
        return MessageSplitSettings(enabled=False, max_messages=1, display_interval_ms=0)
    data = _mapping(value, "roleplay.message_split")
    enabled = _optional_bool(data, "enabled", "roleplay.message_split", default=False)
    max_messages = _optional_bounded_int(
        data,
        "max_messages",
        "roleplay.message_split",
        default=3 if enabled else 1,
        minimum=1,
        maximum=5,
    )
    interval = _optional_bounded_int(
        data,
        "display_interval_ms",
        "roleplay.message_split",
        default=700,
        minimum=0,
        maximum=5_000,
    )
    return MessageSplitSettings(
        enabled=enabled,
        max_messages=max_messages if enabled else 1,
        display_interval_ms=interval if enabled else 0,
    )


_EXPRESSION_AFFECTS = frozenset(
    {
        "neutral", "calm", "gentle", "happy", "playful", "smug",
        "embarrassed", "shy", "awkward", "overwhelmed", "surprised",
        "troubled", "resigned", "angry", "gloomy", "anxious", "tired",
        "sleepy", "confused", "serious", "moved",
    }
)


def _expression_policy(value: object) -> ExpressionPolicy:
    """Validate optional per-role expression calibration without global coupling."""
    if value is None:
        return ExpressionPolicy(
            resolver_mode=None,
            intensity_scale="standard",
            medium_channels=1,
            high_channels=2,
            extreme_channels=4,
            defensive_protest_affect=None,
            intimacy_startle_affect=None,
            anger_requires_visible_evidence=False,
        )
    data = _mapping(value, "roleplay.expression_policy")
    resolver_mode = data.get("resolver_mode")
    if resolver_mode is not None and resolver_mode not in {"off", "conflict", "always"}:
        raise RoleProfileError("roleplay.expression_policy.resolver_mode: expected off, conflict, or always")
    intensity_scale = data.get("intensity_scale", "standard")
    if intensity_scale not in {"standard", "rich"}:
        raise RoleProfileError("roleplay.expression_policy.intensity_scale: expected standard or rich")
    medium = _optional_bounded_int(
        data, "medium_channels", "roleplay.expression_policy", default=1, minimum=1, maximum=5
    )
    high = _optional_bounded_int(
        data, "high_channels", "roleplay.expression_policy", default=2, minimum=1, maximum=5
    )
    extreme = _optional_bounded_int(
        data, "extreme_channels", "roleplay.expression_policy", default=4, minimum=1, maximum=5
    )
    if not medium < high < extreme:
        raise RoleProfileError(
            "roleplay.expression_policy: medium_channels < high_channels < extreme_channels is required"
        )
    return ExpressionPolicy(
        resolver_mode=resolver_mode,
        intensity_scale=intensity_scale,
        medium_channels=medium,
        high_channels=high,
        extreme_channels=extreme,
        defensive_protest_affect=_optional_expression_affect(data, "defensive_protest_affect"),
        intimacy_startle_affect=_optional_expression_affect(data, "intimacy_startle_affect"),
        anger_requires_visible_evidence=_optional_bool(
            data,
            "anger_requires_visible_evidence",
            "roleplay.expression_policy",
            default=False,
        ),
    )


_ORDINAL_LEVELS = frozenset({"very_low", "low", "medium", "high", "very_high"})
_RECOVERY_SPEEDS = frozenset({"immediate", "fast", "medium", "slow"})
_STATE_AFFECTS = frozenset({"neutral", "serious", "confused", "gentle", "happy", "moved", "embarrassed", "surprised", "troubled", "anxious", "angry", "tired"})


def _state_policy(value: object) -> StatePolicy:
    """Read an optional state policy without requiring a schema-version bump."""
    defaults = StatePolicy(False, "medium", "medium", "fast", {}, {}, {}, "medium", "medium", "medium", "unconfirmed", False)
    if value is None:
        return defaults
    data = _mapping(value, "roleplay.state_policy")
    affect = _mapping(data.get("affect", {}), "roleplay.state_policy.affect")
    relationship = _mapping(data.get("relationship", {}), "roleplay.state_policy.relationship")
    baseline = _mapping(relationship.get("baseline", {}), "roleplay.state_policy.relationship.baseline")
    return StatePolicy(
        enabled=_optional_bool(data, "enabled", "roleplay.state_policy", default=True),
        default_reactivity=_state_ordinal(affect.get("default_reactivity", "medium"), "roleplay.state_policy.affect.default_reactivity"),
        default_expressivity=_state_ordinal(affect.get("default_expressivity", "medium"), "roleplay.state_policy.affect.default_expressivity"),
        default_recovery=_state_recovery(affect.get("default_recovery", "fast"), "roleplay.state_policy.affect.default_recovery"),
        reactivity=_state_affect_map(affect.get("reactivity", {}), "roleplay.state_policy.affect.reactivity", _state_ordinal),
        expressivity=_state_affect_map(affect.get("expressivity", {}), "roleplay.state_policy.affect.expressivity", _state_ordinal),
        recovery=_state_affect_map(affect.get("recovery", {}), "roleplay.state_policy.affect.recovery", _state_recovery),
        familiarity=_state_ordinal(baseline.get("familiarity", "medium"), "roleplay.state_policy.relationship.baseline.familiarity"),
        trust=_state_ordinal(baseline.get("trust", "medium"), "roleplay.state_policy.relationship.baseline.trust"),
        comfort=_state_ordinal(baseline.get("comfort", "medium"), "roleplay.state_policy.relationship.baseline.comfort"),
        romantic_status=_state_romantic_status(baseline.get("romantic_status", "unconfirmed")),
        implicit_updates=_optional_bool(relationship, "implicit_updates", "roleplay.state_policy.relationship", default=False),
    )


def _state_affect_map(value: object, field: str, validator) -> dict[str, str]:
    data = _mapping(value, field)
    result: dict[str, str] = {}
    for affect, level in data.items():
        if affect not in _STATE_AFFECTS:
            raise RoleProfileError(f"{field}: unsupported affect {affect!r}")
        result[affect] = validator(level, f"{field}.{affect}")
    return result


def _state_ordinal(value: object, field: str) -> str:
    if value not in _ORDINAL_LEVELS:
        raise RoleProfileError(f"{field}: expected one of {', '.join(sorted(_ORDINAL_LEVELS))}")
    return value


def _state_recovery(value: object, field: str) -> str:
    if value not in _RECOVERY_SPEEDS:
        raise RoleProfileError(f"{field}: expected immediate, fast, medium, or slow")
    return value


def _state_romantic_status(value: object) -> str:
    if value not in {"unconfirmed", "mutual_interest", "explicit_relationship"}:
        raise RoleProfileError("roleplay.state_policy.relationship.baseline.romantic_status: invalid status")
    return value


def _optional_expression_affect(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or value not in _EXPRESSION_AFFECTS:
        raise RoleProfileError(f"roleplay.expression_policy.{key}: expected a supported expression affect")
    return value


def _optional_knowledge_base_id(value: object) -> str | None:
    """Validate an optional isolated world-lore knowledge-base identifier."""
    if value is None:
        return None
    try:
        from knowledge.schema import KnowledgeSchemaError, validate_knowledge_base_id

        return validate_knowledge_base_id(value)
    except KnowledgeSchemaError as error:
        raise RoleProfileError(f"roleplay.knowledge_base_id: {error}") from error


def _optional_avatar(data: dict[str, Any]) -> str | None:
    """Validate an optional local avatar declaration without requiring its file yet."""
    value = data.get("avatar")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RoleProfileError("avatar: expected null or a non-empty assets/avatars image path")
    normalized = value.strip().replace("\\", "/")
    parts = normalized.split("/")
    suffix = normalized[normalized.rfind(".") :].lower() if "." in normalized else ""
    if (
        not normalized.startswith("assets/avatars/")
        or any(part in {"", ".", ".."} for part in parts)
        or suffix not in _AVATAR_SUFFIXES
    ):
        raise RoleProfileError("avatar: expected a safe PNG, JPEG, or WebP path inside assets/avatars")
    return normalized


def _required_int(data: dict[str, Any], key: str) -> int:
    """Validate a required integer without accepting booleans."""
    value = _required(data, key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RoleProfileError(f"{key}: expected an integer")
    return value


def _optional_bool(
    data: dict[str, Any],
    key: str,
    prefix: str,
    *,
    default: bool,
) -> bool:
    """Validate an optional boolean."""
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise RoleProfileError(f"{prefix}.{key}: expected a boolean")
    return value


def _optional_bounded_int(
    data: dict[str, Any],
    key: str,
    prefix: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise RoleProfileError(f"{prefix}.{key}: expected an integer from {minimum} to {maximum}")
    return value


def _string_list(value: object, field: str) -> tuple[str, ...]:
    """Validate a list of non-empty strings."""
    if not isinstance(value, list):
        raise RoleProfileError(f"{field}: expected a list of strings")
    values: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise RoleProfileError(f"{field}[{index}]: expected a non-empty string")
        values.append(item.strip())
    return tuple(values)


def _relationships(value: object) -> tuple[Relationship, ...]:
    """Validate canonical relationship records."""
    if not isinstance(value, list):
        raise RoleProfileError("canon.relationships: expected a list")
    relationships: list[Relationship] = []
    for index, item in enumerate(value):
        relation = _mapping(item, f"canon.relationships[{index}]")
        relationships.append(
            Relationship(
                name=_required_str(relation, "name", f"canon.relationships[{index}]"),
                relation=_required_str(relation, "relation", f"canon.relationships[{index}]"),
                attitude=_optional_str(relation, "attitude", f"canon.relationships[{index}]"),
            )
        )
    return tuple(relationships)


def _address_user(value: object) -> str | None:
    """Read a direct address string or the documented address-user object."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        return _optional_str(value, "default", "speech.address_user")
    raise RoleProfileError("speech.address_user: expected a string or object with default")


def _speech_examples(value: object) -> tuple[SpeechExample, ...]:
    """Validate original speech example records."""
    if not isinstance(value, list):
        raise RoleProfileError("speech.examples: expected a list")
    examples: list[SpeechExample] = []
    for index, item in enumerate(value):
        example = _mapping(item, f"speech.examples[{index}]")
        examples.append(
            SpeechExample(
                context=_required_str(example, "context", f"speech.examples[{index}]"),
                response=_required_str(example, "response", f"speech.examples[{index}]"),
            )
        )
    return tuple(examples)
