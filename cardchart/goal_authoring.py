import json
import re
from collections import defaultdict
from pathlib import Path
from uuid import UUID, uuid4

from flask import current_app

from .goal_definitions import (
    MANIFEST_DIRECTORY,
    GoalManifestError,
    goal_definition,
    load_goal_manifest,
    parse_goal_manifest,
    register_goal_definition,
    synchronize_goals,
    unregister_goal_definition,
)
from .models import CollectionGoal, db


FINISH_LABELS = {
    "nonfoil": "Non-foil",
    "foil": "Foil",
    "etched": "Etched foil",
}

PROMO_TREATMENT_LABELS = {
    "sourcematerial": "Source material",
    "surgefoil": "Surge foil",
    "silverscroll": "Silver Scroll",
    "poster": "Poster",
    "textured": "Textured foil",
    "cosmicfoil": "Cosmic foil",
    "galaxyfoil": "Galaxy foil",
    "rainbowfoil": "Rainbow foil",
    "confettifoil": "Confetti foil",
    "fracturefoil": "Fracture foil",
    "oil_slick": "Oil slick foil",
    "stepandcompleat": "Step-and-compleat foil",
    "serialized": "Serialized",
    "headliner": "Headliner",
    "buyabox": "Buy-a-Box",
    "bundle": "Bundle promo",
    "prerelease": "Prerelease promo",
}
FRAME_TREATMENT_LABELS = {
    "showcase": "Showcase",
    "extendedart": "Extended art",
    "colorshifted": "Colorshifted frame",
    "tombstone": "Tombstone frame",
    "nyxtouched": "Nyx frame",
    "shatteredglass": "Shattered glass",
}


def draft_directory():
    configured = current_app.config.get("GOAL_DRAFT_DIRECTORY")
    return Path(configured) if configured else Path(current_app.instance_path) / "goal-drafts"


def create_goal_draft(manifest):
    draft_id = str(uuid4())
    save_goal_draft(draft_id, manifest)
    return draft_id


def save_goal_draft(draft_id, manifest):
    path = goal_draft_path(draft_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_goal_draft(draft_id):
    path = goal_draft_path(draft_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GoalManifestError(f"Could not read goal draft: {exc}") from exc
    if not isinstance(data, dict):
        raise GoalManifestError("Goal draft must contain a JSON object.")
    return data


def delete_goal_draft(draft_id):
    path = goal_draft_path(draft_id)
    if path.exists():
        path.unlink()


def goal_draft_path(draft_id):
    try:
        normalized = str(UUID(str(draft_id)))
    except ValueError as exc:
        raise GoalManifestError("Invalid goal draft identifier.") from exc
    return draft_directory() / f"{normalized}.json"


def apply_goal_review(manifest, form):
    reviewed = json.loads(json.dumps(manifest))
    reviewed["title"] = form.get("title", "").strip()
    reviewed["description"] = form.get("description", "").strip()
    has_cardmarket = bool(reviewed.get("cardmarket"))
    entries = []
    for entry_index, source_entry in enumerate(reviewed.get("entries", ())):
        if form.get(f"include_entry_{entry_index}") != "yes":
            continue
        entry = json.loads(json.dumps(source_entry))
        entry["name"] = form.get(
            f"entry_name_{entry_index}", entry.get("name", "")
        ).strip()
        treatment = form.get(f"treatment_{entry_index}", "").strip()
        if treatment:
            entry["treatment"] = treatment
        else:
            entry.pop("treatment", None)

        selected_versions = []
        default_index = form.get(f"wants_default_{entry_index}")
        for version_index, source_version in enumerate(entry.get("versions", ())):
            if form.get(
                f"include_version_{entry_index}_{version_index}"
            ) != "yes":
                continue
            version = json.loads(json.dumps(source_version))
            version["label"] = form.get(
                f"version_label_{entry_index}_{version_index}",
                version.get("label", ""),
            ).strip()
            version.pop("wants_list_default", None)
            if has_cardmarket and default_index == str(version_index):
                version["wants_list_default"] = True
            selected_versions.append(version)
        entry["versions"] = selected_versions
        entries.append(entry)

    reviewed["entries"] = entries
    if entries:
        reviewed["image_url"] = entries[0].get("image_url")
    return reviewed


def activate_goal_manifest(manifest, lookup):
    definition = parse_goal_manifest(manifest)
    if goal_definition(definition.slug) is not None:
        raise GoalManifestError(f"Goal slug {definition.slug!r} already exists.")
    if CollectionGoal.query.filter_by(slug=definition.slug).first() is not None:
        raise GoalManifestError(
            f"A database goal with slug {definition.slug!r} already exists."
        )

    errors = validate_definitions_against_bulk((definition,), lookup)
    if errors:
        raise GoalManifestError("Scryfall validation failed: " + "; ".join(errors))

    target = MANIFEST_DIRECTORY / f"{definition.slug}.json"
    if target.exists():
        raise GoalManifestError(f"Manifest {target.name!r} already exists.")

    target.parent.mkdir(parents=True, exist_ok=True)
    registered = False
    created = False
    try:
        with target.open("x", encoding="utf-8") as manifest_file:
            created = True
            manifest_file.write(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
            )
        activated = load_goal_manifest(target)
        register_goal_definition(activated)
        registered = True
        synchronize_goals((activated,))
    except Exception:
        db.session.rollback()
        if registered:
            unregister_goal_definition(definition.slug)
        if created and target.exists():
            target.unlink()
        raise
    return activated


def validate_definitions_against_bulk(definitions, lookup):
    errors = []
    for definition in definitions:
        for entry in definition.entries:
            for version in entry.versions:
                card = lookup.find_by_id(version.scryfall_id)
                prefix = f"{definition.slug}/{entry.key}/{version.key}"
                if card is None:
                    errors.append(f"{prefix}: Scryfall ID is absent from the cache")
                    continue
                if (card.get("set") or "").lower() != version.set_code:
                    errors.append(
                        f"{prefix}: set is {card.get('set')!r}, expected "
                        f"{version.set_code!r}"
                    )
                if str(card.get("collector_number") or "") != version.collector_number:
                    errors.append(
                        f"{prefix}: collector number is "
                        f"{card.get('collector_number')!r}, expected "
                        f"{version.collector_number!r}"
                    )
                if (card.get("lang") or "").lower() != version.language:
                    errors.append(
                        f"{prefix}: language is {card.get('lang')!r}, expected "
                        f"{version.language!r}"
                    )
                finishes = set(card.get("finishes") or ())
                if finishes and version.finish not in finishes:
                    errors.append(
                        f"{prefix}: finish {version.finish!r} is not in "
                        f"{sorted(finishes)!r}"
                    )
                if entry.oracle_id and card.get("oracle_id") != entry.oracle_id:
                    errors.append(f"{prefix}: Oracle ID does not match the entry")
                if card.get("name") and card.get("name") != entry.name:
                    errors.append(
                        f"{prefix}: card name is {card.get('name')!r}, expected "
                        f"{entry.name!r}"
                    )
    return errors


def parse_filter(expression):
    if "=" not in expression:
        raise ValueError(f"Invalid filter {expression!r}; use FIELD=VALUE.")
    field, value = (part.strip() for part in expression.split("=", 1))
    if not field or not value:
        raise ValueError(f"Invalid filter {expression!r}; use FIELD=VALUE.")
    if not re.fullmatch(r"[a-z0-9_]+", field):
        raise ValueError(f"Invalid Scryfall field name {field!r}.")
    return field, value


def card_matches_filter(card, item):
    field, expected = item
    actual = card.get(field)
    if isinstance(actual, list):
        return any(string_matches(value, expected) for value in actual)
    if isinstance(actual, bool):
        return actual is (expected.casefold() == "true")
    return string_matches(actual, expected)


def string_matches(actual, expected):
    return str(actual or "").casefold() == expected.casefold()


def collector_in_range(card, collector_from, collector_to):
    if collector_from is None and collector_to is None:
        return True
    match = re.fullmatch(r"0*(\d+)", str(card.get("collector_number") or ""))
    if not match:
        return False
    number = int(match.group(1))
    return (collector_from is None or number >= collector_from) and (
        collector_to is None or number <= collector_to
    )


def is_paper_card(card):
    games = card.get("games")
    return not games or "paper" in games


def candidate_cards(
    lookup,
    set_code,
    language,
    collector_from=None,
    collector_to=None,
    filters=(),
):
    return [
        card
        for card in lookup.matching_cards(set_code=set_code, language=language)
        if is_paper_card(card)
        and collector_in_range(card, collector_from, collector_to)
        and all(card_matches_filter(card, item) for item in filters)
    ]


def card_treatment_labels(card):
    labels = []
    for promo_type in card.get("promo_types") or ():
        label = PROMO_TREATMENT_LABELS.get(promo_type)
        if label and label not in labels:
            labels.append(label)
    for frame_effect in card.get("frame_effects") or ():
        label = FRAME_TREATMENT_LABELS.get(frame_effect)
        if label and label not in labels:
            labels.append(label)
    if card.get("border_color") == "borderless" and "Borderless" not in labels:
        labels.append("Borderless")
    if card.get("full_art") and "Full art" not in labels:
        labels.append("Full art")
    if "etched" in (card.get("finishes") or ()) and "Etched foil" not in labels:
        labels.append("Etched foil")
    return tuple(labels or ("Standard",))


def candidate_groups(cards, set_code):
    groups = defaultdict(list)
    for card in cards:
        groups[card.get("oracle_id") or card["id"]].append(card)

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: min(collector_sort_key(card) for card in group),
    )
    used_keys = set()
    result = []
    for group in ordered_groups:
        group.sort(key=collector_sort_key)
        primary = group[0]
        entry_key = unique_entry_key(
            f"{set_code.lower()}-{primary.get('collector_number')}", used_keys
        )
        result.append((entry_key, group))
    return tuple(result)


def build_candidate_preview(cards, set_code):
    entries = []
    treatment_counts = defaultdict(int)
    for entry_key, group in candidate_groups(cards, set_code):
        primary = group[0]
        labels = []
        for card in group:
            for label in card_treatment_labels(card):
                if label not in labels:
                    labels.append(label)
        if len(labels) > 1 and "Standard" in labels:
            labels.remove("Standard")
        treatment_keys = [treatment_key(label) for label in labels]
        for key in treatment_keys:
            treatment_counts[key] += 1
        entries.append(
            {
                "key": entry_key,
                "name": primary.get("name")
                or primary.get("printed_name")
                or "Unknown card",
                "collector_number": str(primary.get("collector_number") or ""),
                "image_url": card_image_url(primary),
                "treatments": labels,
                "treatment_keys": treatment_keys,
                "version_count": len(build_candidate_versions(group)),
            }
        )

    treatment_labels = {
        treatment_key(label): label
        for entry in entries
        for label in entry["treatments"]
    }
    treatments = [
        {
            "key": key,
            "label": label,
            "count": treatment_counts[key],
        }
        for key, label in sorted(
            treatment_labels.items(),
            key=lambda item: (item[1] == "Standard", item[1].casefold()),
        )
    ]
    return {"entries": entries, "treatments": treatments}


def build_candidate_manifest(
    slug,
    title,
    description,
    set_code,
    language,
    cards,
    cardmarket_expansion=None,
    cardmarket_version=None,
):
    entries = []
    groups = candidate_groups(cards, set_code)
    for entry_key, group in groups:
        primary = group[0]
        versions = build_candidate_versions(
            group, wants_list=bool(cardmarket_expansion)
        )
        entry = {
            "key": entry_key,
            "name": primary.get("name")
            or primary.get("printed_name")
            or "Unknown card",
            "oracle_id": primary.get("oracle_id"),
            "collector_number": str(primary.get("collector_number") or ""),
            "image_url": card_image_url(primary),
            "versions": versions,
        }
        entries.append(
            {key: value for key, value in entry.items() if value is not None}
        )

    manifest = {
        "schema_version": 1,
        "position": 100,
        "slug": slug,
        "title": title,
        "description": description,
        "defaults": {"set_code": set_code.lower(), "language": language.lower()},
        "image_url": card_image_url(groups[0][1][0]),
        "entries": entries,
    }
    if cardmarket_expansion:
        manifest["cardmarket"] = {
            "expansion": cardmarket_expansion,
            "default_version": cardmarket_version,
        }
    return manifest


def build_candidate_versions(cards, wants_list=False):
    candidates = []
    for card_index, card in enumerate(cards):
        finishes = card.get("finishes") or ["nonfoil"]
        for finish in finishes:
            if finish not in FINISH_LABELS:
                continue
            candidates.append((card_index, card, finish))

    preferred_index = next(
        (
            index
            for index, (_card_index, _card, finish) in enumerate(candidates)
            if finish == "nonfoil"
        ),
        0,
    )
    versions = []
    used_keys = set()
    for index, (card_index, card, finish) in enumerate(candidates):
        collector_number = str(card.get("collector_number") or "")
        base_key = finish if card_index == 0 else f"{collector_number}-{finish}"
        key = unique_entry_key(base_key, used_keys)
        label = FINISH_LABELS[finish]
        if sum(
            1
            for _card_index, _card, item_finish in candidates
            if item_finish == finish
        ) > 1:
            label = f"{label} ({collector_number})"
        version = {
            "key": key,
            "label": label,
            "scryfall_id": card["id"],
            "collector_number": collector_number,
            "finish": finish,
        }
        if wants_list and index == preferred_index:
            version["wants_list_default"] = True
        versions.append(version)
    return versions


def unique_entry_key(base, used_keys):
    base = re.sub(r"[^a-z0-9]+", "-", str(base).lower()).strip("-") or "entry"
    candidate = base
    suffix = 2
    while candidate in used_keys:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used_keys.add(candidate)
    return candidate


def treatment_key(label):
    return re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")


def collector_sort_key(card):
    collector_number = str(card.get("collector_number") or "")
    parts = re.split(r"(\d+)", collector_number.casefold())
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in parts
        if part
    )


def card_image_url(card):
    image_uris = card.get("image_uris") or {}
    if image_uris.get("normal"):
        return image_uris["normal"]
    for face in card.get("card_faces") or ():
        face_images = face.get("image_uris") or {}
        if face_images.get("normal"):
            return face_images["normal"]
    return None
