"""Reviewed collection observations and disposals; no name-based stock deductions."""

import csv
import hashlib
import io
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from .goal_definitions import GOAL_DEFINITIONS
from .importer import get_image_url
from .models import (
    Card, CollectionGoal, GoalCardPrinting, ReconciliationBatch, ReconciliationEntry, db,
)
from .ownership import canonical_inventory_scryfall_id, reconcile_goal_collection
from .performance import record_observation, sync_quantity_lots
from .scryfall_bulk import load_bulk_lookup

SOURCES = {"collectr": "Collectr", "deckcheck": "Deckcheck", "ebay": "eBay", "buylist": "Buylist"}
FIELDS = [
    ("name", "Card / listing title"), ("quantity", "Quantity"),
    ("scryfall_id", "Scryfall printing ID"), ("set_code", "Set code"),
    ("collector_number", "Collector number"), ("finish", "Finish"),
    ("language", "Language"), ("reference", "Order / transaction reference"),
    ("line_id", "Line / item reference"), ("status", "Sale status"),
]
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000


class ReconciliationError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def quantity(value, *, allow_zero):
    try:
        number = Decimal(str(value).strip())
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError
        amount = int(number)
        if amount < (0 if allow_zero else 1) or amount > 1_000_000:
            raise ValueError
        return amount
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise ReconciliationError("Quantity must be a whole number within 0–1,000,000 (disposals need at least 1).") from exc


def create_batch(upload, form):
    source, kind = form.get("source"), form.get("kind")
    basis = form.get("basis", "")
    if source not in SOURCES or kind not in {"snapshot", "disposal"}:
        raise ReconciliationError("Choose a source and an import type.")
    if kind == "disposal" and basis not in {"unreflected", "already_reflected"}:
        raise ReconciliationError("Choose whether these disposals are already removed from your collection counts.")
    if source == "buylist" and not form.get("source_account", "").strip():
        raise ReconciliationError("Enter the buylist store or vendor so its statement references stay separate.")
    try:
        observed_on = date.fromisoformat(form.get("observed_on", ""))
        if observed_on > date.today():
            raise ValueError
    except ValueError as exc:
        raise ReconciliationError("Enter the export's date, today or earlier.") from exc
    data = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ReconciliationError("Use a CSV of at most 2 MB and 1,000 rows. Split larger exports.")
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        headers = reader.fieldnames
        if not headers or any(not h.strip() for h in headers) or len(set(headers)) != len(headers):
            raise ReconciliationError("Use a CSV with a unique, non-empty header for each column.")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ReconciliationError("Each CSV row must have the same columns as its header.")
            if any(value.strip() for value in row.values()):
                rows.append(row)
            if len(rows) > MAX_ROWS:
                raise ReconciliationError("Split exports into at most 1,000 rows per file.")
    except (UnicodeError, csv.Error) as exc:
        raise ReconciliationError("Use a UTF-8, comma-separated CSV. Save Excel files as CSV UTF-8 first.") from exc
    if not rows:
        raise ReconciliationError("This CSV has no data rows.")
    batch = ReconciliationBatch(
        source=source, source_account=form.get("source_account", "").strip()[:100],
        kind=kind, basis=basis if kind == "disposal" else "", observed_on=observed_on,
        reference=form.get("reference", "").strip()[:200],
        filename=(upload.filename or "export.csv")[:200], content_hash=hashlib.sha256(data).hexdigest(),
        raw_json=json.dumps({"headers": headers, "rows": rows}),
    )
    db.session.add(batch)
    db.session.commit()
    return batch


def column_suggestions(headers):
    aliases = {
        "name": ["name", "card name", "title", "item title"],
        "quantity": ["quantity", "qty"], "scryfall_id": ["card scryfall id", "scryfall id"],
        "set_code": ["set code"], "collector_number": ["collector number", "card number"],
        "finish": ["finish"], "language": ["language"],
        "reference": ["order number", "order id", "transaction id"],
        "line_id": ["line item id", "item id"], "status": ["status", "order status"],
    }
    available = {header.strip().casefold(): header for header in headers}
    return {field: next((available[a] for a in names if a in available), "") for field, names in aliases.items()}


def map_batch(batch, form):
    if batch.state == "applied":
        raise ReconciliationError("This import has been applied. Upload the file again to review remaining rows.")
    raw = json.loads(batch.raw_json)
    mapping = {key: form.get(key, "") for key, _ in FIELDS}
    if not mapping["quantity"] or any(value and value not in raw["headers"] for value in mapping.values()):
        raise ReconciliationError("Choose a quantity column and valid source columns.")
    statuses = {s.strip().casefold() for s in form.get("eligible_statuses", "").split(",") if s.strip()}
    if batch.kind == "disposal":
        if mapping["status"] and not statuses:
            raise ReconciliationError("List the completed sale statuses to include. Other statuses stay excluded.")
        if not mapping["status"] and form.get("confirmed_completed") != "yes":
            raise ReconciliationError("Confirm all rows are completed disposals, or map a status column.")
    normalized = []
    for index, raw_row in enumerate(raw["rows"]):
        row = {field: raw_row[column].strip() if column else "" for field, column in mapping.items()}
        row.update(index=index, line=index + 2, error="")
        row["finish"] = (row["finish"] or form.get("default_finish", "")).lower().replace("-", "").replace(" ", "")
        row["language"] = (row["language"] or form.get("default_language", "en")).lower().strip()
        row["reference"] = row["reference"] or batch.reference
        row["eligible"] = batch.kind == "snapshot" or not mapping["status"] or row["status"].casefold() in statuses
        try:
            row["quantity"] = quantity(row["quantity"], allow_zero=batch.kind == "snapshot")
            if row["finish"] not in {"nonfoil", "foil", "etched"}:
                raise ReconciliationError("Choose a finish column or a default finish.")
            if batch.kind == "disposal" and not row["reference"]:
                raise ReconciliationError("A transaction or statement reference is required to recognise repeat imports.")
        except ReconciliationError as exc:
            row["error"] = str(exc)
        normalized.append(row)
    settings = dict(mapping)
    for key in ("default_finish", "default_language", "eligible_statuses", "confirmed_completed"):
        settings[key] = form.get(key, "")
    batch.mapping_json = json.dumps(settings)
    batch.rows_json = json.dumps(normalized)
    batch.preview_json = "{}"
    batch.preview_token = None
    batch.state = "review"
    db.session.commit()


def source_scope(batch):
    return f"{batch.source}:{batch.source_account.casefold()}"


def event_identity(batch, row, identity):
    if batch.kind == "snapshot":
        key = ["snapshot", batch.observed_on.isoformat(), batch.content_hash, identity]
    else:
        key = ["disposal", row["reference"], row["line_id"] or identity]
    return digest(key)


def event_signature(row, identity):
    return digest([identity, row["quantity"]])


def check_reference_mapping(batch, row, identity):
    if batch.kind != "disposal":
        return
    previous = ReconciliationEntry.query.filter_by(
        source_scope=source_scope(batch), kind="disposal", reference=row["reference"],
        printing_key=digest(identity),
    ).all()
    if any(bool(entry.line_id) != bool(row["line_id"]) for entry in previous):
        raise ReconciliationError("Item-reference mapping changed for a previously recorded transaction. Use the original line/item mapping before importing it again.")


def resolve_metadata(row, lookup):
    if not lookup:
        return None
    if row["scryfall_id"]:
        printing_id = canonical_inventory_scryfall_id(row["scryfall_id"])
        if not printing_id:
            return None
        card = lookup.find_by_id(printing_id)
        candidates = [card] if card else []
    elif row["set_code"] and row["collector_number"] and row["language"]:
        candidates = [
            card for card in lookup.matching_cards(set_code=row["set_code"], language=row["language"])
            if str(card.get("collector_number")) == row["collector_number"]
        ]
    else:
        return None
    candidates = [c for c in candidates if row["finish"] in c.get("finishes", ()) and "paper" in c.get("games", ())]
    if len(candidates) != 1:
        return None
    card = candidates[0]
    return {
        "scryfall_id": card["id"], "name": card["name"], "set_code": card["set"],
        "set_name": card.get("set_name") or card["set"].upper(),
        "collector_number": str(card["collector_number"]), "rarity": card.get("rarity") or "unknown",
        "finish": row["finish"], "finish_display": row["finish"].title(),
        "image_url": get_image_url(card), "scryfall_uri": card.get("scryfall_uri"),
    }


def card_identity(card):
    return [canonical_inventory_scryfall_id(card.scryfall_id) or card.scryfall_id, card.finish.lower()]


def prepare_preview(batch):
    if batch.state != "review":
        raise ReconciliationError("Map this file before reviewing quantities.")
    cards = Card.query.order_by(Card.name, Card.id).all()
    lookup = load_bulk_lookup(refresh=False)
    inventory = [{"id": c.id, "label": f"{c.name} · {c.set_code.upper()} #{c.collector_number} · {c.finish}", "quantity": c.quantity} for c in cards]
    snapshots = {str(c.id): {"quantity": c.quantity, "identity": card_identity(c)} for c in cards}
    rows = []
    for normalized in json.loads(batch.rows_json):
        row = dict(normalized)
        row.update(card_id=None, current_quantity=None, proposed_quantity=None, match_label="Choose a printing", duplicate=False, metadata=None)
        printing_id = canonical_inventory_scryfall_id(row["scryfall_id"])
        matches = [c for c in cards if printing_id and card_identity(c) == [printing_id, row["finish"]]]
        metadata = resolve_metadata(row, lookup)
        if not matches and metadata:
            matches = [c for c in cards if card_identity(c) == [metadata["scryfall_id"], row["finish"]]]
        if len(matches) == 1:
            card = matches[0]
            row.update(card_id=card.id, current_quantity=card.quantity, match_label=f"{card.name} · {card.set_code.upper()} #{card.collector_number} · {card.finish}")
            identity = card_identity(card)
        elif not matches and metadata and (batch.kind == "snapshot" or batch.basis == "already_reflected"):
            row.update(metadata=metadata, current_quantity=0, match_label=f"New: {metadata['name']} · {metadata['set_code'].upper()} #{metadata['collector_number']} · {row['finish']}")
            identity = [metadata["scryfall_id"], row["finish"]]
        else:
            identity = None
        message = row["error"]
        if not row["eligible"]:
            message = "Excluded sale status. Previously processed refunds/cancellations need a separately reviewed stock correction."
        elif not message and identity is None:
            message = "No unique exact match. Choose an existing printing, or refresh the local Scryfall cache and remap. Names and lot titles are never matched automatically."
        if identity:
            try:
                check_reference_mapping(batch, row, identity)
            except ReconciliationError as exc:
                row["error"] = message = str(exc)
            entry = ReconciliationEntry.query.filter_by(source_scope=source_scope(batch), event_key=event_identity(batch, row, identity)).first()
            if entry:
                if entry.signature != event_signature(row, identity):
                    message = "This transaction reference was applied with different contents. Check the reference; do not deduct it again."
                    row["error"] = message
                else:
                    row["duplicate"] = True
                    message = "Already recorded; this row will not be applied again."
            if not row["error"] and row["eligible"]:
                amount = row["quantity"]
                row["proposed_quantity"] = amount if batch.kind == "snapshot" else row["current_quantity"] - (amount if batch.basis == "unreflected" else 0)
        row["message"] = message
        row["blocked"] = bool(row["error"] or not row["eligible"] or identity is None)
        rows.append(row)
    batch.preview_token = uuid4().hex
    batch.preview_json = json.dumps({"rows": rows, "inventory": snapshots})
    db.session.commit()
    return rows, inventory


def update_matches(batch, form):
    if batch.state != "review":
        raise ReconciliationError("Map the file before updating matches.")
    lookup = load_bulk_lookup(refresh=False)
    if lookup is None:
        raise ReconciliationError("Download the local Scryfall bulk cache before matching a new printing ID.")
    rows = json.loads(batch.rows_json)
    changes = 0
    for row in rows:
        printing_id = form.get(f"printing_{row['index']}", "").strip()
        if not printing_id:
            continue
        if row["error"]:
            raise ReconciliationError(f"Correct CSV row {row['line']}'s column mapping before matching a printing.")
        candidate = dict(row, scryfall_id=printing_id, finish=form.get(f"printing_finish_{row['index']}", row["finish"]))
        metadata = resolve_metadata(candidate, lookup)
        if metadata is None:
            raise ReconciliationError(f"Row {row['line']}: this exact printing and finish were not found in the local paper-card cache.")
        row["scryfall_id"] = metadata["scryfall_id"]
        row["finish"] = metadata["finish"]
        changes += 1
    if not changes:
        raise ReconciliationError("Enter a Scryfall printing ID for an unmatched row first.")
    batch.rows_json = json.dumps(rows)
    batch.preview_json = "{}"
    batch.preview_token = None
    db.session.commit()


def apply_review(batch, form):
    if batch.state != "review" or not batch.preview_token or batch.preview_token != form.get("preview_token"):
        raise ReconciliationError("This review is out of date or already applied. Reload it before continuing.")
    if form.get("confirmed") != "yes":
        raise ReconciliationError("Confirm how the selected rows affect your collection counts.")
    if any(key.startswith("printing_") and not key.startswith("printing_finish_") and value.strip() for key, value in form.items()):
        raise ReconciliationError("Use Update printing matches before applying newly entered printing IDs.")
    preview = json.loads(batch.preview_json)
    operations, seen_cards, seen_events, running_quantities, reference_modes = [], set(), set(), {}, {}
    try:
        for row in preview["rows"]:
            if form.get(f"apply_{row['index']}") != "yes":
                continue
            if row["error"] or not row["eligible"]:
                raise ReconciliationError(f"Row {row['line']}: {row['message']}")
            chosen_id = form.get(f"card_{row['index']}") or row["card_id"]
            card = None
            if chosen_id:
                try:
                    card = db.session.get(Card, int(chosen_id))
                except ValueError as exc:
                    raise ReconciliationError("Choose a printing from the inventory list.") from exc
                before = preview["inventory"].get(str(chosen_id))
                if not card or not before or card.quantity != before["quantity"] or card_identity(card) != before["identity"]:
                    raise ReconciliationError("Inventory changed since this review. Reload and review the latest quantities.")
                identity = card_identity(card)
                old_quantity = card.quantity
                metadata = None
            elif row["metadata"] and (batch.kind == "snapshot" or batch.basis == "already_reflected"):
                metadata = row["metadata"]
                identity = [metadata["scryfall_id"], metadata["finish"]]
                if any(card_identity(c) == identity for c in Card.query.all()):
                    raise ReconciliationError("A printing was added since this review. Reload the latest inventory.")
                old_quantity = 0
            else:
                raise ReconciliationError(f"Row {row['line']}: choose an exact printing before applying it.")
            event_key = event_identity(batch, row, identity)
            signature = event_signature(row, identity)
            check_reference_mapping(batch, row, identity)
            reference_identity = (row["reference"], digest(identity))
            if batch.kind == "disposal" and reference_identity in reference_modes and reference_modes[reference_identity] != bool(row["line_id"]):
                raise ReconciliationError("Use consistent line/item references for transactions affecting the same printing.")
            reference_modes[reference_identity] = bool(row["line_id"])
            existing = ReconciliationEntry.query.filter_by(source_scope=source_scope(batch), event_key=event_key).first()
            if existing:
                if existing.signature != signature:
                    raise ReconciliationError("A transaction reference has already been used with different contents.")
                continue
            if event_key in seen_events:
                raise ReconciliationError("Two selected rows share a transaction reference. Map unique line/item references, or select one row.")
            seen_events.add(event_key)
            identity_key = tuple(identity)
            if batch.kind == "snapshot" and identity_key in seen_cards:
                raise ReconciliationError("Two selected snapshot rows describe the same printing. Select one row and enter its combined total explicitly.")
            seen_cards.add(identity_key)
            old_quantity = running_quantities.get(identity_key, old_quantity)
            target = quantity(form.get(f"quantity_{row['index']}", row["quantity"]), allow_zero=True) if batch.kind == "snapshot" else old_quantity - (row["quantity"] if batch.basis == "unreflected" else 0)
            if target < 0:
                raise ReconciliationError(f"Row {row['line']}: disposal exceeds owned quantity. Check the match or whether this sale was already reflected.")
            running_quantities[identity_key] = target
            operations.append((card, metadata, row, identity, event_key, signature, old_quantity, target))
        if not operations:
            raise ReconciliationError("Select at least one new row to apply. Already recorded rows are skipped.")
        claimed = ReconciliationBatch.query.filter_by(id=batch.id, state="review", preview_token=batch.preview_token).update({"state": "applied"}, synchronize_session=False)
        if claimed != 1:
            raise ReconciliationError("Another request applied this review. Reload its history.")
        results, created_cards = [], {}
        for card, metadata, row, identity, event_key, signature, old_quantity, target in operations:
            if card is None:
                card = created_cards.get(tuple(identity))
            if card:
                updated = Card.query.filter_by(id=card.id, quantity=old_quantity).update({"quantity": target, "updated_at": datetime.now(timezone.utc)}, synchronize_session=False)
                if updated != 1:
                    raise ReconciliationError("Inventory changed while applying this review. Reload and try again.")
            else:
                stored_id = metadata["scryfall_id"]
                if Card.query.filter_by(scryfall_id=stored_id).first():
                    stored_id = f"{stored_id}:{metadata['finish']}"
                card = Card(**dict(metadata, scryfall_id=stored_id), quantity=target)
                db.session.add(card)
                db.session.flush()
                created_cards[tuple(identity)] = card
            db.session.expire(card)
            sync_quantity_lots(card, old_quantity)
            GoalCardPrinting.query.filter_by(card_id=card.id).update({"quantity": target}, synchronize_session=False)
            db.session.add(ReconciliationEntry(
                batch_id=batch.id, card_id=card.id, source_scope=source_scope(batch),
                kind=batch.kind, line_id=row["line_id"], printing_key=digest(identity),
                event_key=event_key, signature=signature, reference=row["reference"] or batch.observed_on.isoformat(),
                quantity=row["quantity"], before_quantity=old_quantity, after_quantity=target,
            ))
            results.append({"name": card.name, "before": old_quantity, "after": target, "reference": row["reference"], "action": "Counts already reflected" if batch.basis == "already_reflected" else "Set total" if batch.kind == "snapshot" else "Disposal"})
        db.session.expire_all()
        for definition in GOAL_DEFINITIONS:
            goal = CollectionGoal.query.filter_by(slug=definition.slug).first()
            if goal:
                reconcile_goal_collection(goal, definition)
        batch = db.session.get(ReconciliationBatch, batch.id)
        batch.results_json = json.dumps(results)
        batch.raw_json = "{}"
        record_observation()
        db.session.commit()
        return results
    except IntegrityError as exc:
        db.session.rollback()
        raise ReconciliationError("A printing or transaction was recorded during this review. Reload before applying again.") from exc
    except Exception:
        db.session.rollback()
        raise
