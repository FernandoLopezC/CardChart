"""Captured GBP guide comparisons for reviewed goal printings."""
import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from flask import current_app

from .goal_definitions import GOAL_DEFINITIONS, goal_entry_versions
from .models import GoalPriceObservation, db
from .performance import _valid_evidence
from .pricing import guide_metadata, load_goal_price_index, price_for_version


def printing_key(version):
    return f"{version.scryfall_id}:{version.finish}"


def record_goal_prices(rate_info):
    """Join the guide-refresh transaction; page reads never establish a baseline."""
    source = guide_metadata()["source_updated_at"]
    if not current_app.config["MARKET_PRICING_ENABLED"] or not _valid_evidence(source, rate_info):
        return
    index = load_goal_price_index()
    prices = {
        printing_key(version): price_for_version(version, index, rate_info)["gbp"]
        for definition in GOAL_DEFINITIONS
        for entry in definition.entries
        for version in entry.versions
    }
    encoded = json.dumps(prices, sort_keys=True)
    latest = GoalPriceObservation.query.order_by(GoalPriceObservation.id.desc()).first()
    if latest:
        if datetime.fromisoformat(source.replace("Z", "+00:00")) < datetime.fromisoformat(latest.source_updated_at.replace("Z", "+00:00")):
            raise ValueError("Goal guide source is older than the last recorded refresh.")
        if (latest.source_updated_at, latest.fx_rate, latest.fx_date, latest.prices_json) == (source, rate_info["rate"], rate_info["rate_date"], encoded):
            return
    db.session.add(GoalPriceObservation(
        source_updated_at=source, fx_rate=rate_info["rate"],
        fx_date=rate_info["rate_date"], prices_json=encoded,
    ))


def goal_price_drops(goal, price_index, rate_info):
    result = {"cards": {}, "status": "waiting", "comparable_count": 0}
    observations = GoalPriceObservation.query.order_by(GoalPriceObservation.id.desc()).limit(2).all()
    source = guide_metadata()["source_updated_at"]
    if not current_app.config["MARKET_PRICING_ENABLED"] or not _valid_evidence(source, rate_info):
        result["status"] = "unavailable"
        return result
    if not observations:
        return result
    latest = observations[0]
    if (latest.source_updated_at, Decimal(latest.fx_rate), latest.fx_date) != (source, Decimal(rate_info["rate"]), rate_info["rate_date"]):
        result["status"] = "refresh"
        return result
    if len(observations) < 2:
        return result
    previous = observations[1]
    current_prices, previous_prices = json.loads(latest.prices_json), json.loads(previous.prices_json)
    result.update(status="ready", previous=previous, latest=latest)
    for card in goal.cards:
        if card.is_owned:
            continue
        drops = []
        comparable = False
        for version in goal_entry_versions(goal.slug, card.stable_key):
            key = printing_key(version)
            before, after = previous_prices.get(key), current_prices.get(key)
            live = price_for_version(version, price_index, rate_info)
            if before is None or after is None or live["gbp"] != after:
                continue
            comparable = True
            change = Decimal(before) - Decimal(after)
            if change < Decimal("0.01"):
                continue
            percent = (change * 100 / Decimal(before)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            drops.append({"version": version, "before": before, "after": after,
                          "drop": f"{change:.2f}", "percent": f"{percent:.1f}",
                          "url": live["cardmarket_url"]})
        result["comparable_count"] += int(comparable)
        if drops:
            result["cards"][card.id] = drops
    return result
