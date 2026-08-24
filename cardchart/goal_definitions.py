import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from .models import CollectionGoal, GoalCard, db


MANIFEST_SCHEMA_VERSION = 1
MANIFEST_DIRECTORY = Path(__file__).with_name("goals")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SUPPORTED_FINISHES = {"nonfoil", "foil", "etched"}


class GoalManifestError(ValueError):
    """Raised when a maintained goal manifest is unsafe to load."""


@dataclass(frozen=True)
class GoalVersionDefinition:
    key: str
    label: str
    scryfall_id: str
    collector_number: str
    finish: str
    language: str
    set_code: str | None = None
    cardmarket_expansion: str | None = None
    cardmarket_version: str | None = None
    wants_list_default: bool = False


@dataclass(frozen=True)
class GoalEntryDefinition:
    key: str
    name: str
    accepted_scryfall_ids: tuple[str, ...]
    oracle_id: str | None = None
    collector_number: str | None = None
    language: str | None = None
    treatment: str | None = None
    image_url: str | None = None
    set_code: str | None = None
    versions: tuple[GoalVersionDefinition, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GoalDefinition:
    slug: str
    title: str
    description: str
    set_code: str | None
    entries: tuple[GoalEntryDefinition, ...] = field(default_factory=tuple)
    image_url: str | None = None
    cardmarket_expansion: str | None = None
    cardmarket_standard_version: str | None = None
    cardmarket_wants_version_key: str | None = None
    source_path: Path | None = None
    position: int = 0


def load_goal_manifest(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GoalManifestError(f"{path}: could not read manifest: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GoalManifestError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
        ) from exc

    try:
        return parse_goal_manifest(data, source_path=path)
    except GoalManifestError as exc:
        raise GoalManifestError(f"{path}: {exc}") from exc


def load_goal_manifests(directory=MANIFEST_DIRECTORY):
    directory = Path(directory)
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise GoalManifestError(f"No goal manifests found in {directory}.")

    definitions = tuple(load_goal_manifest(path) for path in paths)
    seen_slugs = {}
    for definition in definitions:
        previous = seen_slugs.get(definition.slug)
        if previous:
            raise GoalManifestError(
                f"Duplicate goal slug {definition.slug!r} in "
                f"{previous} and {definition.source_path}."
            )
        seen_slugs[definition.slug] = definition.source_path
    return tuple(sorted(definitions, key=lambda item: (item.position, item.slug)))


def parse_goal_manifest(data, source_path=None):
    if not isinstance(data, dict):
        raise GoalManifestError("manifest root must be an object")
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise GoalManifestError(
            f"schema_version must be {MANIFEST_SCHEMA_VERSION}"
        )

    slug = required_string(data, "slug")
    if not SLUG_PATTERN.fullmatch(slug):
        raise GoalManifestError(
            "slug must contain lowercase letters, numbers, and single hyphens only"
        )
    title = required_string(data, "title")
    description = required_string(data, "description")
    goal_position = data.get("position", 0)
    if (
        not isinstance(goal_position, int)
        or isinstance(goal_position, bool)
        or goal_position < 0
    ):
        raise GoalManifestError("position must be a non-negative integer")
    defaults = optional_object(data, "defaults")
    default_set_code = optional_string(defaults, "set_code")
    default_language = optional_string(defaults, "language")
    image_url = optional_string(data, "image_url")

    cardmarket = optional_object(data, "cardmarket")
    cardmarket_expansion = optional_string(cardmarket, "expansion")
    cardmarket_standard_version = optional_string(cardmarket, "default_version")
    cardmarket_wants_version_key = optional_string(
        cardmarket, "wants_list_version_key"
    )

    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise GoalManifestError("entries must be a non-empty array")

    entries = []
    entry_keys = set()
    printing_owners = {}
    for entry_position, raw_entry in enumerate(raw_entries, start=1):
        location = f"entries[{entry_position - 1}]"
        entry = parse_goal_entry(
            raw_entry,
            location=location,
            default_set_code=default_set_code,
            default_language=default_language,
        )
        if entry.key in entry_keys:
            raise GoalManifestError(f"{location}.key duplicates {entry.key!r}")
        entry_keys.add(entry.key)

        for printing_id in entry.accepted_scryfall_ids:
            previous = printing_owners.get(printing_id)
            if previous and previous != entry.key:
                raise GoalManifestError(
                    f"Scryfall printing {printing_id!r} belongs to both "
                    f"{previous!r} and {entry.key!r}"
                )
            printing_owners[printing_id] = entry.key
        entries.append(entry)

    definition = GoalDefinition(
        slug=slug,
        title=title,
        description=description,
        set_code=default_set_code,
        entries=tuple(entries),
        image_url=image_url,
        cardmarket_expansion=cardmarket_expansion,
        cardmarket_standard_version=cardmarket_standard_version,
        cardmarket_wants_version_key=cardmarket_wants_version_key,
        source_path=Path(source_path) if source_path else None,
        position=goal_position,
    )
    validate_cardmarket_configuration(definition)
    return definition


def parse_goal_entry(raw_entry, location, default_set_code, default_language):
    if not isinstance(raw_entry, dict):
        raise GoalManifestError(f"{location} must be an object")

    key = required_string(raw_entry, "key", location)
    name = required_string(raw_entry, "name", location)
    oracle_id = optional_uuid(raw_entry, "oracle_id", location)
    collector_number = optional_string(raw_entry, "collector_number")
    language = optional_string(raw_entry, "language") or default_language
    set_code = optional_string(raw_entry, "set_code") or default_set_code
    treatment = optional_string(raw_entry, "treatment")
    image_url = optional_string(raw_entry, "image_url")

    raw_versions = raw_entry.get("versions")
    if not isinstance(raw_versions, list) or not raw_versions:
        raise GoalManifestError(f"{location}.versions must be a non-empty array")

    versions = []
    version_keys = set()
    version_identities = set()
    accepted_ids = []
    for index, raw_version in enumerate(raw_versions):
        version_location = f"{location}.versions[{index}]"
        version = parse_goal_version(
            raw_version,
            location=version_location,
            default_set_code=set_code,
            default_language=language,
            default_collector_number=collector_number,
        )
        if version.key in version_keys:
            raise GoalManifestError(
                f"{version_location}.key duplicates {version.key!r}"
            )
        version_keys.add(version.key)
        identity = (version.scryfall_id, version.finish, version.language)
        if identity in version_identities:
            raise GoalManifestError(
                f"{version_location} duplicates a Scryfall ID, finish, and language"
            )
        version_identities.add(identity)
        if version.scryfall_id not in accepted_ids:
            accepted_ids.append(version.scryfall_id)
        versions.append(version)

    if sum(version.wants_list_default for version in versions) > 1:
        raise GoalManifestError(
            f"{location} may mark only one version as wants_list_default"
        )

    primary = versions[0]
    return GoalEntryDefinition(
        key=key,
        name=name,
        accepted_scryfall_ids=tuple(accepted_ids),
        oracle_id=oracle_id,
        collector_number=collector_number or primary.collector_number,
        language=language or primary.language,
        treatment=treatment,
        image_url=image_url,
        set_code=set_code or primary.set_code,
        versions=tuple(versions),
    )


def parse_goal_version(
    raw_version,
    location,
    default_set_code,
    default_language,
    default_collector_number,
):
    if not isinstance(raw_version, dict):
        raise GoalManifestError(f"{location} must be an object")
    key = required_string(raw_version, "key", location)
    label = required_string(raw_version, "label", location)
    scryfall_id = required_uuid(raw_version, "scryfall_id", location)
    collector_number = (
        optional_string(raw_version, "collector_number") or default_collector_number
    )
    if not collector_number:
        raise GoalManifestError(f"{location}.collector_number is required")
    finish = required_string(raw_version, "finish", location).lower()
    if finish not in SUPPORTED_FINISHES:
        raise GoalManifestError(
            f"{location}.finish must be one of {sorted(SUPPORTED_FINISHES)}"
        )
    language = optional_string(raw_version, "language") or default_language
    if not language:
        raise GoalManifestError(f"{location}.language is required")
    set_code = optional_string(raw_version, "set_code") or default_set_code
    if not set_code:
        raise GoalManifestError(f"{location}.set_code is required")
    wants_list_default = raw_version.get("wants_list_default", False)
    if not isinstance(wants_list_default, bool):
        raise GoalManifestError(
            f"{location}.wants_list_default must be true or false"
        )

    return GoalVersionDefinition(
        key=key,
        label=label,
        scryfall_id=scryfall_id,
        collector_number=collector_number,
        finish=finish,
        language=language.lower(),
        set_code=set_code.lower(),
        cardmarket_expansion=optional_string(
            raw_version, "cardmarket_expansion"
        ),
        cardmarket_version=optional_string(raw_version, "cardmarket_version"),
        wants_list_default=wants_list_default,
    )


def validate_cardmarket_configuration(definition):
    configured = bool(
        definition.cardmarket_expansion
        or definition.cardmarket_standard_version
        or any(
            version.cardmarket_expansion or version.cardmarket_version
            for entry in definition.entries
            for version in entry.versions
        )
    )
    if not configured:
        return

    for entry in definition.entries:
        version = cardmarket_wants_version(definition, entry)
        if version is None:
            raise GoalManifestError(
                f"entry {entry.key!r} has no Cardmarket Wants List default version"
            )
        expansion = version.cardmarket_expansion or definition.cardmarket_expansion
        market_version = (
            version.cardmarket_version or definition.cardmarket_standard_version
        )
        if not expansion or not market_version:
            raise GoalManifestError(
                f"entry {entry.key!r} has incomplete Cardmarket expansion/version data"
            )


def cardmarket_wants_version(definition, entry):
    marked = next(
        (version for version in entry.versions if version.wants_list_default), None
    )
    if marked:
        return marked
    if definition.cardmarket_wants_version_key:
        return next(
            (
                version
                for version in entry.versions
                if version.key == definition.cardmarket_wants_version_key
            ),
            None,
        )
    return None


def cardmarket_wants_mapping(definition, entry):
    version = cardmarket_wants_version(definition, entry)
    if version is None:
        return None
    expansion = version.cardmarket_expansion or definition.cardmarket_expansion
    market_version = version.cardmarket_version or definition.cardmarket_standard_version
    if not expansion or not market_version:
        return None
    return market_version, expansion


def required_string(data, key, location=None):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        prefix = f"{location}." if location else ""
        raise GoalManifestError(f"{prefix}{key} must be a non-empty string")
    return value.strip()


def optional_string(data, key):
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise GoalManifestError(f"{key} must be a non-empty string when present")
    return value.strip()


def optional_object(data, key):
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise GoalManifestError(f"{key} must be an object")
    return value


def required_uuid(data, key, location=None):
    value = required_string(data, key, location)
    try:
        UUID(value)
    except ValueError as exc:
        prefix = f"{location}." if location else ""
        raise GoalManifestError(f"{prefix}{key} must be a UUID") from exc
    return value.lower()


def optional_uuid(data, key, location=None):
    value = data.get(key)
    if value is None:
        return None
    return required_uuid(data, key, location)


GOAL_DEFINITIONS = list(load_goal_manifests())


def goal_definition(goal_slug):
    return next(
        (definition for definition in GOAL_DEFINITIONS if definition.slug == goal_slug),
        None,
    )


def register_goal_definition(definition):
    """Expose one newly activated manifest without restarting the process."""
    if goal_definition(definition.slug) is not None:
        raise GoalManifestError(f"Goal slug {definition.slug!r} is already active.")
    GOAL_DEFINITIONS.append(definition)
    GOAL_DEFINITIONS.sort(key=lambda item: (item.position, item.slug))


def unregister_goal_definition(goal_slug):
    """Remove a just-registered definition when activation is rolled back."""
    GOAL_DEFINITIONS[:] = [
        definition
        for definition in GOAL_DEFINITIONS
        if definition.slug != goal_slug
    ]


middle_earth_classic_artists = goal_definition("middle-earth-classic-artists")
japanese_mystical_archive = goal_definition("japanese-mystical-archive")


def goal_entry_definition(goal_slug, stable_key):
    definition = goal_definition(goal_slug)
    if definition is None:
        return None
    return next(
        (entry for entry in definition.entries if entry.key == stable_key), None
    )


def goal_entry_versions(goal_slug, stable_key):
    entry = goal_entry_definition(goal_slug, stable_key)
    return entry.versions if entry else ()


def synchronize_goals(definitions=None):
    """Create and safely refresh curated goals, including exact inventory matches."""
    from .ownership import reconcile_goal_collection

    definitions = GOAL_DEFINITIONS if definitions is None else definitions
    ownership_matches = 0
    for definition in definitions:
        goal = CollectionGoal.query.filter_by(slug=definition.slug).first()
        if goal is None:
            goal = CollectionGoal(slug=definition.slug)
            db.session.add(goal)

        goal.name = definition.title
        goal.description = definition.description
        goal.scryfall_set_code = definition.set_code
        goal.image_url = definition.image_url
        goal.updated_at = datetime.now(timezone.utc)

        existing = {card.stable_key: card for card in goal.cards}
        for position, entry in enumerate(definition.entries, start=1):
            card = existing.get(entry.key)
            if card is None:
                card = GoalCard(goal=goal, stable_key=entry.key)
                db.session.add(card)
            card.position = position
            card.name = entry.name
            card.oracle_id = entry.oracle_id
            card.expected_set_code = entry.set_code or definition.set_code
            card.expected_collector_number = entry.collector_number
            card.image_url = entry.image_url
            card.notes = entry.treatment
            card.accepted_scryfall_ids = ",".join(entry.accepted_scryfall_ids)

        ownership_matches += reconcile_goal_collection(goal, definition)

    db.session.commit()
    return ownership_matches
