from uuid import UUID

from .models import Card, GoalCardPrinting, db


def canonical_inventory_scryfall_id(value):
    """Return the canonical UUID from an inventory ID, including finish-suffixed IDs."""
    value = (value or "").strip().lower()
    candidates = (value, value.partition(":")[0])
    for candidate in candidates:
        try:
            return str(UUID(candidate))
        except ValueError:
            continue
    return None


def reconcile_goal_collection(goal, definition):
    """Attach exact accepted inventory versions without changing existing ownership."""
    inventory_by_identity = {}
    for card in Card.query.filter(Card.quantity > 0).order_by(Card.id).all():
        printing_id = canonical_inventory_scryfall_id(card.scryfall_id)
        finish = (card.finish or "").strip().lower()
        if printing_id and finish:
            inventory_by_identity.setdefault((printing_id, finish), card)

    entries = {entry.key: entry for entry in definition.entries}
    matches = 0
    for goal_card in goal.cards:
        entry = entries.get(goal_card.stable_key)
        if entry is None:
            continue
        existing = {
            (
                printing.scryfall_id.lower(),
                printing.finish.lower(),
                printing.language.lower(),
            )
            for printing in goal_card.printings
        }
        for version in entry.versions:
            inventory_card = inventory_by_identity.get(
                (version.scryfall_id.lower(), version.finish.lower())
            )
            identity = (
                version.scryfall_id.lower(),
                version.finish.lower(),
                version.language.lower(),
            )
            if inventory_card is None or identity in existing:
                continue

            db.session.add(
                GoalCardPrinting(
                    goal_card=goal_card,
                    card=inventory_card,
                    scryfall_id=version.scryfall_id,
                    set_code=version.set_code or entry.set_code or definition.set_code,
                    collector_number=version.collector_number,
                    finish=version.finish,
                    language=version.language,
                    quantity=inventory_card.quantity,
                )
            )
            existing.add(identity)
            matches += 1
    return matches
