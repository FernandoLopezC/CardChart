"""Transactional guide observations and remaining-inventory movement."""
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import current_app

from .models import Card, GuideObservation, GuideObservationValue, QuantityLot, db
from .ownership import canonical_inventory_scryfall_id
from .pricing import guide_metadata, load_eur_to_gbp_rate, load_scryfall_price_index, price_for_printing


def sync_quantity_lots(card, before_quantity):
    db.session.flush()
    lots = QuantityLot.query.filter_by(card_id=card.id).order_by(QuantityLot.id).all()
    tracked = sum(lot.remaining_quantity for lot in lots)
    if tracked < before_quantity:
        db.session.add(QuantityLot(card=card, scryfall_id=canonical_inventory_scryfall_id(card.scryfall_id), finish=card.finish.lower(), original_quantity=before_quantity - tracked, remaining_quantity=before_quantity - tracked))
        db.session.flush()
        lots = QuantityLot.query.filter_by(card_id=card.id).order_by(QuantityLot.id).all()
    if tracked > before_quantity:
        raise ValueError("Tracked inventory exceeds the previous quantity.")
    delta = card.quantity - before_quantity
    if delta > 0:
        db.session.add(QuantityLot(card=card, scryfall_id=canonical_inventory_scryfall_id(card.scryfall_id), finish=card.finish.lower(), original_quantity=delta, remaining_quantity=delta))
    elif delta < 0:
        remaining = -delta
        for lot in lots:
            used = min(lot.remaining_quantity, remaining)
            lot.remaining_quantity -= used
            remaining -= used
            if not remaining:
                break
        if remaining:
            raise ValueError("Insufficient tracked inventory for disposal.")


def _valid_evidence(source, rate_info):
    try:
        updated = datetime.fromisoformat(source.replace("Z", "+00:00"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        rate = Decimal(str(rate_info["rate"]))
        rate_date = date.fromisoformat(rate_info["rate_date"])
        fetched = date.fromisoformat(rate_info["fetched_on"])
        now = datetime.now(timezone.utc)
        return rate.is_finite() and rate > 0 and updated <= now and rate_date <= fetched == now.date()
    except (AttributeError, TypeError, KeyError, ValueError, InvalidOperation):
        return False


def record_observation(price_index=None, rate_info=None, source_updated_at=None):
    cards = Card.query.filter(Card.quantity > 0).order_by(Card.id).all()
    for card in cards:
        sync_quantity_lots(card, card.quantity)
    enabled = current_app.config["MARKET_PRICING_ENABLED"]
    if price_index is None:
        price_index = load_scryfall_price_index([canonical_inventory_scryfall_id(c.scryfall_id) for c in cards]) if enabled else {}
    if rate_info is None and enabled:
        rate_info = load_eur_to_gbp_rate(cached_only=True)
    if source_updated_at is None and enabled:
        source_updated_at = guide_metadata()["source_updated_at"]
    valid = enabled and _valid_evidence(source_updated_at, rate_info)
    evidence = rate_info if valid else {}
    rows = []
    for card in cards:
        identity = canonical_inventory_scryfall_id(card.scryfall_id)
        finish = card.finish.lower()
        price = price_for_printing(identity, finish, price_index, evidence)
        # Preserve the provider's original EUR text, without rounding it for display.
        field = {"nonfoil": "eur", "foil": "eur_foil"}.get(finish)
        data = price_index.get(identity, {})
        prices = data.get("prices", {}) if isinstance(data, dict) else {}
        eur = prices.get(field) if isinstance(prices, dict) and field and price["eur"] is not None else None
        rows.append((card, identity, finish, str(eur) if eur is not None else None, price["gbp"] if valid else None))
    db.session.flush()
    lots = QuantityLot.query.order_by(QuantityLot.id).all()
    state = [source_updated_at, evidence.get("rate"), evidence.get("rate_date"), evidence.get("fetched_on"), [(c.id, i, f, c.quantity, e, g) for c, i, f, e, g in rows], [(lot.id, lot.remaining_quantity) for lot in lots]]
    fingerprint = hashlib.sha256(json.dumps(state, separators=(",", ":")).encode()).hexdigest()
    latest = GuideObservation.query.order_by(GuideObservation.id.desc()).first()
    if latest and latest.fingerprint == fingerprint:
        observation = latest
    else:
        observation = GuideObservation(source_updated_at=source_updated_at, fx_rate=evidence.get("rate"), fx_date=evidence.get("rate_date"), fx_fetched_on=evidence.get("fetched_on"), fingerprint=fingerprint)
        db.session.add(observation)
        for card, identity, finish, eur, gbp in rows:
            unit = Decimal(gbp) if gbp is not None else None
            db.session.add(GuideObservationValue(observation=observation, card=card, scryfall_id=identity, finish=finish, quantity=card.quantity, eur_unit=eur, gbp_unit=unit, gbp_total=unit * card.quantity if unit is not None else None))
        db.session.flush()
    values = {value.card_id: value for value in observation.values}
    for lot in QuantityLot.query.filter(QuantityLot.remaining_quantity > 0, QuantityLot.baseline_value_id.is_(None)).all():
        value = values.get(lot.card_id)
        if value and value.gbp_unit is not None and value.scryfall_id == lot.scryfall_id and value.finish == lot.finish:
            lot.baseline_value = value
    return observation


def _amount(value):
    return f"{value:.2f}" if value is not None else None


def _percent(change, baseline):
    return _amount(change * 100 / baseline) if baseline else None


def performance_summary(price_index, rate_info):
    cards = Card.query.filter(Card.quantity > 0).order_by(Card.id).all()
    total_quantity = sum(card.quantity for card in cards)
    baseline = current = Decimal("0")
    comparable = 0
    movers = []
    for card in cards:
        price = price_for_printing(canonical_inventory_scryfall_id(card.scryfall_id), card.finish.lower(), price_index, rate_info)
        if price["gbp"] is None:
            continue
        lots = QuantityLot.query.filter_by(card_id=card.id).filter(QuantityLot.remaining_quantity > 0, QuantityLot.baseline_value_id.isnot(None)).all()
        lots = [lot for lot in lots if lot.scryfall_id == canonical_inventory_scryfall_id(card.scryfall_id) and lot.finish == card.finish.lower()]
        quantity = sum(lot.remaining_quantity for lot in lots)
        if not quantity:
            continue
        base = sum((lot.baseline_value.gbp_unit * lot.remaining_quantity for lot in lots), Decimal("0"))
        value = Decimal(price["gbp"]) * quantity
        change = value - base
        baseline += base
        current += value
        comparable += quantity
        baseline_dates = [lot.baseline_value.observation.recorded_at.date().isoformat() for lot in lots]
        movers.append({"card": card, "quantity": quantity, "baseline_gbp": _amount(base), "current_gbp": _amount(value), "change_gbp": _amount(change), "percent": _percent(change, base), "baseline_from": min(baseline_dates), "baseline_to": max(baseline_dates)})
    change = current - baseline
    return {"baseline_gbp": _amount(baseline) if comparable else None, "current_gbp": _amount(current) if comparable else None, "change_gbp": _amount(change) if comparable else None, "percent": _percent(change, baseline), "comparable_quantity": comparable, "total_quantity": total_quantity, "movers": movers}


def observation_history():
    history = []
    previous = 0
    previous_lines = {}
    for observation in GuideObservation.query.order_by(GuideObservation.id).all():
        values = observation.values
        quantity = sum(value.quantity for value in values)
        priced = [value for value in values if value.gbp_total is not None]
        total = sum((value.gbp_total for value in priced), Decimal("0")) if priced or not values else None
        timestamp = observation.recorded_at.replace(tzinfo=timezone.utc).isoformat()
        lines = {value.card_id: value.quantity for value in values}
        changes = [{"card_id": card_id, "quantity_change": lines.get(card_id, 0) - previous_lines.get(card_id, 0)} for card_id in sorted(lines.keys() | previous_lines.keys()) if lines.get(card_id, 0) != previous_lines.get(card_id, 0)]
        history.append({"id": observation.id, "observed_at": timestamp, "gbp": _amount(total), "priced_count": len(priced), "inventory_count": len(values), "quantity": quantity, "quantity_change": quantity - previous, "quantity_changes": changes})
        previous = quantity
        previous_lines = lines
    return history
