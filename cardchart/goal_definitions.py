from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import CollectionGoal, GoalCard, db


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


@dataclass(frozen=True)
class GoalDefinition:
    slug: str
    title: str
    description: str
    set_code: str
    entries: tuple[GoalEntryDefinition, ...] = field(default_factory=tuple)
    image_url: str | None = None


# Membership remains empty until the exact subsets and printing UUIDs can be
# verified from Scryfall. The goals themselves are still useful placeholders.
middle_earth_classic_artists = GoalDefinition(
    slug="middle-earth-classic-artists",
    title="Middle-earth Classic Artist Cards",
    description="A curated checklist of Classic Artist cards associated with HOC.",
    set_code="hoc",
)

japanese_mystical_archive = GoalDefinition(
    slug="japanese-mystical-archive",
    title="Japanese Mystical Archive",
    description="A curated checklist of Japanese Mystical Archive cards associated with SOA.",
    set_code="soa",
)

GOAL_DEFINITIONS = (middle_earth_classic_artists, japanese_mystical_archive)


def synchronize_goals(definitions=GOAL_DEFINITIONS):
    """Create and safely refresh curated goals without changing ownership."""
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
            card.expected_set_code = definition.set_code
            card.expected_collector_number = entry.collector_number
            card.image_url = entry.image_url
            card.notes = entry.treatment
            card.accepted_scryfall_ids = ",".join(entry.accepted_scryfall_ids)

    db.session.commit()
