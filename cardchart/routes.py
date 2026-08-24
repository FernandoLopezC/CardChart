import json
from datetime import date
from decimal import Decimal
from math import ceil

import requests
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .goal_authoring import (
    activate_goal_manifest,
    apply_goal_review,
    build_candidate_manifest,
    build_candidate_preview,
    candidate_cards,
    create_goal_draft,
    delete_goal_draft,
    load_goal_draft,
    parse_filter,
    save_goal_draft,
)

from .goal_definitions import (
    GoalManifestError,
    GoalVersionDefinition,
    cardmarket_wants_mapping,
    goal_definition,
    goal_entry_definition,
    goal_entry_versions,
    parse_goal_manifest,
)
from .importer import import_cards
from .models import Card, CollectionGoal, GoalCard, GoalCardPrinting, PriceSnapshot, db
from .pricing import (
    cheapest_price_for_versions,
    load_eur_to_gbp_rate,
    load_goal_price_index,
    load_scryfall_price_index,
    price_for_printing,
    price_for_version,
)
from .scrapers import scrape_cardmarket, scrape_ebay_sold
from .scryfall_bulk import bulk_cache_available, load_bulk_lookup, load_bulk_metadata

bp = Blueprint("main", __name__)
GOAL_PAGE_SIZE = 20
GOAL_FILTERS = {"all", "missing", "owned"}
INVENTORY_PAGE_SIZE = 20
INVENTORY_SORT_OPTIONS = (
    ("name-asc", "Name: A to Z"),
    ("name-desc", "Name: Z to A"),
    ("set-asc", "Set and collector number"),
    ("quantity-desc", "Quantity: high to low"),
    ("price-asc", "Value: low to high"),
    ("price-desc", "Value: high to low"),
)
INVENTORY_SORTS = {value for value, _label in INVENTORY_SORT_OPTIONS}


@bp.route("/")
def index():
    return redirect(url_for("main.goals"))


@bp.route("/inventory")
def inventory():
    cards = Card.query.order_by(Card.name).all()
    search_query = request.args.get("q", "").strip()
    selected_sort = request.args.get("sort", "name-asc")
    if selected_sort not in INVENTORY_SORTS:
        selected_sort = "name-asc"
    price_index = {}
    rate_info = None
    if current_app.config["MARKET_PRICING_ENABLED"] and cards:
        price_index = load_scryfall_price_index(
            card.scryfall_id for card in cards
        )
        if price_index:
            rate_info = load_eur_to_gbp_rate()
    all_card_views = [
        inventory_card_view(card, price_index, rate_info) for card in cards
    ]
    priced_views = [
        view for view in all_card_views if view["line_gbp"] is not None
    ]
    inventory_total = sum(
        (Decimal(view["line_gbp"]) for view in priced_views), Decimal("0")
    )
    matching_views = [
        view for view in all_card_views if inventory_view_matches(view, search_query)
    ]
    matching_views = sort_inventory_views(matching_views, selected_sort)
    total_results = len(matching_views)
    total_pages = max(1, ceil(total_results / INVENTORY_PAGE_SIZE))
    page = max(1, request.args.get("page", 1, type=int))
    page = min(page, total_pages)
    page_start = (page - 1) * INVENTORY_PAGE_SIZE
    card_views = matching_views[page_start:page_start + INVENTORY_PAGE_SIZE]
    return render_template(
        "index.html",
        card_views=card_views,
        inventory_total=f"{inventory_total:.2f}" if priced_views or not cards else None,
        priced_count=len(priced_views),
        inventory_count=len(cards),
        total_results=total_results,
        search_query=search_query,
        selected_sort=selected_sort,
        sort_options=INVENTORY_SORT_OPTIONS,
        page=page,
        total_pages=total_pages,
        rate_info=rate_info,
    )


def inventory_card_view(card, price_index, rate_info):
    price = price_for_printing(
        card.scryfall_id, card.finish, price_index, rate_info
    )
    line_gbp = (
        Decimal(price["gbp"]) * card.quantity
        if price["gbp"] is not None
        else None
    )
    return {
        "card": card,
        "price": price,
        "line_gbp": f"{line_gbp:.2f}" if line_gbp is not None else None,
    }


def inventory_view_matches(view, search_query):
    if not search_query:
        return True
    card = view["card"]
    haystack = " ".join(
        (
            card.name,
            card.set_name,
            card.set_code,
            card.collector_number,
            card.finish,
            card.finish_display,
        )
    ).casefold()
    return search_query.casefold() in haystack


def sort_inventory_views(views, selected_sort):
    name_key = lambda view: (
        view["card"].name.casefold(),
        view["card"].set_code.casefold(),
        view["card"].collector_number.casefold(),
    )
    if selected_sort == "name-desc":
        return sorted(views, key=name_key, reverse=True)
    if selected_sort == "set-asc":
        return sorted(
            views,
            key=lambda view: (
                view["card"].set_name.casefold(),
                view["card"].collector_number.casefold(),
                view["card"].name.casefold(),
            ),
        )
    if selected_sort == "quantity-desc":
        return sorted(
            views,
            key=lambda view: (-view["card"].quantity, *name_key(view)),
        )
    if selected_sort in {"price-asc", "price-desc"}:
        priced = [view for view in views if view["line_gbp"] is not None]
        unavailable = [view for view in views if view["line_gbp"] is None]
        priced.sort(
            key=lambda view: (Decimal(view["line_gbp"]), name_key(view)),
            reverse=selected_sort == "price-desc",
        )
        return priced + sorted(unavailable, key=name_key)
    return sorted(views, key=name_key)


@bp.route("/goals")
def goals():
    goals = CollectionGoal.query.order_by(CollectionGoal.name).all()
    return render_template("goals.html", goals=goals)


@bp.route("/goals/new", methods=["GET", "POST"])
def new_goal():
    form_values = request.form if request.method == "POST" else {}
    if request.method == "POST":
        try:
            manifest = build_goal_candidate_from_form(request.form)
            parse_goal_manifest(manifest)
            draft_id = create_goal_draft(manifest)
        except (GoalManifestError, ValueError, OSError) as exc:
            flash(str(exc), "error")
        else:
            return redirect(url_for("main.review_goal_draft", draft_id=draft_id))

    lookup = load_bulk_lookup(refresh=False) if bulk_cache_available() else None
    return render_template(
        "new_goal.html",
        bulk_available=bulk_cache_available(),
        bulk_metadata=load_bulk_metadata(),
        set_catalog=lookup.set_catalog() if lookup else (),
        form_values=form_values,
    )


@bp.route("/goals/new/preview")
def preview_goal_cards():
    set_code = request.args.get("set_code", "").strip()
    language = request.args.get("language", "en").strip()
    if not set_code or not language:
        return jsonify({"error": "Choose a set and language first."}), 400
    try:
        collector_from = optional_form_integer(request.args, "collector_from")
        collector_to = optional_form_integer(request.args, "collector_to")
        if (
            collector_from is not None
            and collector_to is not None
            and collector_from > collector_to
        ):
            raise GoalManifestError(
                "Collector number from cannot exceed collector number to."
            )
        filter_lines = request.args.get("metadata_filters", "").splitlines()
        filters = tuple(
            parse_filter(line.strip()) for line in filter_lines if line.strip()
        )
        lookup = load_bulk_lookup(refresh=False)
        if lookup is None:
            raise GoalManifestError(
                "No local Scryfall bulk data exists. Refresh it first."
            )
        cards = candidate_cards(
            lookup,
            set_code=set_code,
            language=language,
            collector_from=collector_from,
            collector_to=collector_to,
            filters=filters,
        )
        if not cards:
            raise GoalManifestError("No Scryfall cards matched those filters.")
    except (GoalManifestError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(build_candidate_preview(cards, set_code))


@bp.route("/goals/new/refresh-bulk", methods=["POST"])
def refresh_goal_bulk():
    try:
        lookup = load_bulk_lookup(refresh=True)
    except (requests.RequestException, KeyError, OSError, ValueError) as exc:
        flash(f"Scryfall bulk refresh failed: {exc}", "error")
    else:
        flash(f"Scryfall bulk data is ready with {len(lookup.cards)} cards.", "success")
    return redirect(url_for("main.new_goal"))


@bp.route("/goals/new/<draft_id>/review", methods=["GET", "POST"])
def review_goal_draft(draft_id):
    draft = goal_draft_or_404(draft_id)
    if request.method == "POST":
        reviewed = apply_goal_review(draft, request.form)
        try:
            parse_goal_manifest(reviewed)
            save_goal_draft(draft_id, reviewed)
            lookup = load_bulk_lookup(refresh=False)
            if lookup is None:
                raise GoalManifestError(
                    "The Scryfall bulk cache is missing. Refresh it before activation."
                )
            definition = activate_goal_manifest(reviewed, lookup)
        except (GoalManifestError, OSError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("main.review_goal_draft", draft_id=draft_id))

        delete_goal_draft(draft_id)
        goal = CollectionGoal.query.filter_by(slug=definition.slug).one()
        owned_message = (
            f" Found {goal.owned_count} already owned in your collection."
            if goal.owned_count
            else ""
        )
        flash(
            f"Created {definition.title} with {len(definition.entries)} cards."
            f"{owned_message}",
            "success",
        )
        return redirect(url_for("main.goal_detail", slug=definition.slug))

    return render_template("review_goal.html", draft=draft, draft_id=draft_id)


@bp.route("/goals/new/<draft_id>/discard", methods=["POST"])
def discard_goal_draft(draft_id):
    goal_draft_or_404(draft_id)
    delete_goal_draft(draft_id)
    flash("Goal draft discarded.", "success")
    return redirect(url_for("main.goals"))


def build_goal_candidate_from_form(form):
    required = {
        "slug": form.get("slug", "").strip(),
        "title": form.get("title", "").strip(),
        "description": form.get("description", "").strip(),
        "set_code": form.get("set_code", "").strip(),
        "language": form.get("language", "").strip(),
    }
    missing = [label.replace("_", " ") for label, value in required.items() if not value]
    if missing:
        raise GoalManifestError(f"Complete these fields: {', '.join(missing)}.")
    if goal_definition(required["slug"]) is not None:
        raise GoalManifestError(f"Goal slug {required['slug']!r} already exists.")
    if CollectionGoal.query.filter_by(slug=required["slug"]).first() is not None:
        raise GoalManifestError(f"Goal slug {required['slug']!r} already exists.")

    collector_from = optional_form_integer(form, "collector_from")
    collector_to = optional_form_integer(form, "collector_to")
    if (
        collector_from is not None
        and collector_to is not None
        and collector_from > collector_to
    ):
        raise GoalManifestError("Collector number from cannot exceed collector number to.")

    expansion = form.get("cardmarket_expansion", "").strip() or None
    market_version = form.get("cardmarket_version", "").strip() or None
    if (expansion is None) != (market_version is None):
        raise GoalManifestError(
            "Provide both Cardmarket expansion and version, or leave both blank."
        )

    filter_lines = form.get("metadata_filters", "").splitlines()
    try:
        filters = tuple(parse_filter(line.strip()) for line in filter_lines if line.strip())
    except ValueError as exc:
        raise GoalManifestError(str(exc)) from exc

    lookup = load_bulk_lookup(refresh=False)
    if lookup is None:
        raise GoalManifestError(
            "No local Scryfall bulk data exists. Refresh it before finding cards."
        )
    cards = candidate_cards(
        lookup,
        set_code=required["set_code"],
        language=required["language"],
        collector_from=collector_from,
        collector_to=collector_to,
        filters=filters,
    )
    if not cards:
        raise GoalManifestError("No Scryfall cards matched those filters.")
    manifest = build_candidate_manifest(
        **required,
        cards=cards,
        cardmarket_expansion=expansion,
        cardmarket_version=market_version,
    )
    selected_json = form.get("selected_entry_keys")
    if selected_json is not None:
        try:
            selected_keys = json.loads(selected_json)
        except (TypeError, ValueError) as exc:
            raise GoalManifestError("The selected-card preview is invalid.") from exc
        if not isinstance(selected_keys, list) or not all(
            isinstance(key, str) for key in selected_keys
        ):
            raise GoalManifestError("The selected-card preview is invalid.")
        selected_keys = set(selected_keys)
        manifest["entries"] = [
            entry for entry in manifest["entries"] if entry["key"] in selected_keys
        ]
        if not manifest["entries"]:
            raise GoalManifestError("Select at least one card for the goal.")
        manifest["image_url"] = manifest["entries"][0].get("image_url")
    return manifest


def optional_form_integer(form, key):
    raw_value = form.get(key, "").strip()
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError as exc:
        raise GoalManifestError(
            f"{key.replace('_', ' ').title()} must be a whole number."
        ) from exc


def goal_draft_or_404(draft_id):
    try:
        draft = load_goal_draft(draft_id)
    except GoalManifestError:
        abort(404)
    if draft is None:
        abort(404)
    return draft


@bp.route("/goals/<slug>")
def goal_detail(slug):
    goal = CollectionGoal.query.filter_by(slug=slug).first_or_404()
    selected_filter = request.args.get("filter", "all")
    if selected_filter not in GOAL_FILTERS:
        selected_filter = "all"
    cards = goal.cards
    if selected_filter == "owned":
        cards = [card for card in cards if card.is_owned]
    elif selected_filter == "missing":
        cards = [card for card in cards if not card.is_owned]

    total_cards = len(cards)
    total_pages = max(1, ceil(total_cards / GOAL_PAGE_SIZE))
    page = max(1, request.args.get("page", 1, type=int))
    page = min(page, total_pages)
    page_start = (page - 1) * GOAL_PAGE_SIZE
    page_cards = cards[page_start:page_start + GOAL_PAGE_SIZE]
    price_index = {}
    rate_info = None
    if current_app.config["MARKET_PRICING_ENABLED"]:
        price_index = load_goal_price_index()
        if price_index:
            rate_info = load_eur_to_gbp_rate()
    price_summary = goal_price_summary(goal.cards, price_index, rate_info)
    card_views = [goal_card_view(card, price_index, rate_info) for card in page_cards]
    return render_template(
        "goal_detail.html",
        goal=goal,
        card_views=card_views,
        selected_filter=selected_filter,
        page=page,
        total_pages=total_pages,
        total_cards=total_cards,
        rate_info=rate_info,
        price_summary=price_summary,
    )


@bp.route("/goals/<slug>/exports/cardmarket-wants.txt")
def export_cardmarket_wants(slug):
    goal = CollectionGoal.query.filter_by(slug=slug).first_or_404()
    definition = goal_definition(slug)
    if definition is None:
        return Response("Cardmarket export is not configured for this goal.\n", 404)

    missing_cards = [card for card in goal.cards if not card.is_owned]
    lines = []
    for card in missing_cards:
        entry = goal_entry_definition(slug, card.stable_key)
        mapping = cardmarket_wants_mapping(definition, entry) if entry else None
        if mapping is None:
            return Response(
                "Cardmarket export is not configured for this goal.\n", 404
            )
        market_version, expansion = mapping
        lines.append(f"1x {card.name} ({market_version}) ({expansion})")
    body = "\r\n".join(lines)
    if body:
        body += "\r\n"
    return Response(
        body,
        content_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{goal.slug}-cardmarket-wants.txt"'
            )
        },
    )


def goal_card_view(card, price_index, rate_info):
    versions = versions_for_goal_card(card)
    selected_version = versions[0]
    active_printing = next(
        (printing for printing in card.printings if printing.quantity > 0),
        None,
    )
    if active_printing:
        selected_version = next(
            (
                version
                for version in versions
                if version.scryfall_id == active_printing.scryfall_id
                and version.finish == active_printing.finish
                and version.language == active_printing.language
            ),
            selected_version,
        )
    version_prices = {
        version.key: price_for_version(version, price_index, rate_info)
        for version in versions
    }
    return {
        "card": card,
        "versions": versions,
        "selected_version": selected_version,
        "version_prices": version_prices,
        "selected_price": version_prices[selected_version.key],
    }


def goal_price_summary(cards, price_index, rate_info):
    buckets = {
        "owned": {"card_count": 0, "priced_count": 0, "total": Decimal("0")},
        "missing": {"card_count": 0, "priced_count": 0, "total": Decimal("0")},
    }
    for card in cards:
        is_owned = card.is_owned
        bucket = buckets["owned" if is_owned else "missing"]
        bucket["card_count"] += 1
        price = (
            owned_card_price(card, price_index, rate_info)
            if is_owned
            else cheapest_missing_card_price(card, price_index, rate_info)
        )
        if price is None:
            continue
        bucket["priced_count"] += 1
        bucket["total"] += price

    for bucket in buckets.values():
        bucket["gbp"] = (
            f"{bucket['total']:.2f}"
            if bucket["priced_count"] or not bucket["card_count"]
            else None
        )
        del bucket["total"]
    return buckets


def owned_card_price(card, price_index, rate_info):
    versions = {
        (version.scryfall_id, version.finish, version.language): version
        for version in versions_for_goal_card(card)
    }
    total = Decimal("0")
    active_printings = [
        printing for printing in card.printings if printing.quantity > 0
    ]
    if not active_printings:
        return None

    for printing in active_printings:
        version = versions.get(
            (printing.scryfall_id, printing.finish, printing.language)
        )
        if version is None:
            return None
        price = price_for_version(version, price_index, rate_info)
        if price["gbp"] is None:
            return None
        total += Decimal(price["gbp"]) * printing.quantity
    return total


def cheapest_missing_card_price(card, price_index, rate_info):
    cheapest = cheapest_price_for_versions(
        versions_for_goal_card(card), price_index, rate_info
    )
    return Decimal(cheapest["gbp"]) if cheapest else None


def versions_for_goal_card(card):
    versions = goal_entry_versions(card.goal.slug, card.stable_key)
    if not versions:
        accepted_ids = tuple(
            value for value in card.accepted_scryfall_ids.split(",") if value
        )
        versions = (
            GoalVersionDefinition(
                "nonfoil",
                "Non-foil",
                accepted_ids[0] if accepted_ids else "",
                card.expected_collector_number or "",
                "nonfoil",
                "en",
            ),
        )
    return versions


@bp.route("/goals/<slug>/cards/<int:goal_card_id>/edit")
def edit_goal_card(slug, goal_card_id):
    goal_card = goal_card_for_slug(slug, goal_card_id)
    inventory = Card.query.order_by(Card.name).all()
    printing = next(
        (printing for printing in goal_card.printings if printing.quantity > 0),
        goal_card.printings[0] if goal_card.printings else None,
    )
    return render_template(
        "edit_goal_card.html", goal=goal_card.goal, goal_card=goal_card,
        printing=printing, inventory=inventory
    )


@bp.route("/goals/<slug>/cards/<int:goal_card_id>", methods=["POST"])
def update_goal_card(slug, goal_card_id):
    goal_card = goal_card_for_slug(slug, goal_card_id)
    if request.form.get("status") == "missing":
        for printing in goal_card.printings:
            db.session.delete(printing)
    else:
        required_fields = ("scryfall_id", "set_code", "collector_number", "language", "finish")
        if any(not request.form.get(field, "").strip() for field in required_fields):
            flash("Complete all printing fields before marking this card owned.", "error")
            return redirect(url_for("main.edit_goal_card", slug=slug, goal_card_id=goal_card_id))

        printing = (
            goal_card.printings[0]
            if goal_card.printings
            else GoalCardPrinting(goal_card=goal_card)
        )
        selected_card = None
        if request.form.get("card_id"):
            selected_card = db.session.get(Card, int(request.form["card_id"]))
        printing.card = selected_card
        printing.scryfall_id = request.form["scryfall_id"].strip()
        printing.set_code = (
            selected_card.set_code if selected_card else request.form["set_code"].strip()
        )
        printing.collector_number = (
            selected_card.collector_number if selected_card else request.form["collector_number"].strip()
        )
        printing.language = request.form["language"].strip()
        printing.finish = (
            selected_card.finish if selected_card else request.form["finish"].strip()
        )
        printing.quantity = (
            selected_card.quantity if selected_card else int(request.form["quantity"])
        )
        acquired_at = request.form.get("acquired_at")
        printing.acquired_at = date.fromisoformat(acquired_at) if acquired_at else None
        printing.notes = request.form.get("notes", "").strip() or None
        db.session.add(printing)
    db.session.commit()
    flash("Ownership updated.", "success")
    return redirect(url_for("main.goal_detail", slug=slug))


@bp.route("/goals/<slug>/cards/<int:goal_card_id>/quick-update", methods=["POST"])
def quick_update_goal_card(slug, goal_card_id):
    goal_card = goal_card_for_slug(slug, goal_card_id)
    selected_filter = request.form.get("filter", "all")
    if selected_filter not in GOAL_FILTERS:
        selected_filter = "all"
    page = max(1, request.form.get("page", 1, type=int))

    if request.form.get("status") == "missing":
        for printing in goal_card.printings:
            db.session.delete(printing)
    elif request.form.get("status") == "owned":
        versions = {version.key: version for version in versions_for_goal_card(goal_card)}
        version = versions.get(request.form.get("version"))
        if version is None:
            flash("Choose a valid card version.", "error")
            return redirect(
                url_for(
                    "main.goal_detail",
                    slug=slug,
                    filter=selected_filter,
                    page=page,
                )
            )

        printing = next(
            (
                printing
                for printing in goal_card.printings
                if printing.scryfall_id == version.scryfall_id
                and printing.finish == version.finish
                and printing.language == version.language
            ),
            None,
        )
        for existing_printing in goal_card.printings:
            existing_printing.quantity = 0
        if printing is None:
            printing = GoalCardPrinting(goal_card=goal_card)
        printing.scryfall_id = version.scryfall_id
        printing.set_code = version.set_code or goal_card.expected_set_code
        printing.collector_number = version.collector_number
        printing.finish = version.finish
        printing.language = version.language
        printing.quantity = max(printing.quantity or 0, 1)
        db.session.add(printing)
    else:
        flash("Choose whether the card is owned or missing.", "error")
        return redirect(
            url_for(
                "main.goal_detail",
                slug=slug,
                filter=selected_filter,
                page=page,
            )
        )

    db.session.commit()
    flash("Collection updated.", "success")
    return redirect(
        url_for(
            "main.goal_detail",
            slug=slug,
            filter=selected_filter,
            page=page,
        )
    )


def goal_card_for_slug(slug, goal_card_id):
    return (
        GoalCard.query.join(CollectionGoal)
        .filter(CollectionGoal.slug == slug, GoalCard.id == goal_card_id)
        .first_or_404()
    )


@bp.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file:
            flash("Choose a CSV file to upload.", "error")
            return redirect(url_for("main.upload"))

        try:
            result = import_cards(file)
            flash(
                f"Imported {result.imported} cards; enriched {result.enriched} with Scryfall data; "
                f"used {result.fallbacks} fallback lookups; updated {result.goal_matches} goal entries.",
                "success",
            )
            for warning in result.warnings[:5]:
                flash(warning, "warning")
            if len(result.warnings) > 5:
                flash(f"{len(result.warnings) - 5} more import warnings were hidden.", "warning")
            return redirect(url_for("main.inventory"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "error")

    return render_template("upload.html")


@bp.route("/cards/<int:card_id>")
def card_detail(card_id):
    card = Card.query.get_or_404(card_id)
    prices = PriceSnapshot.query.filter_by(card_id=card.id).order_by(PriceSnapshot.checked_at.desc()).all()
    return render_template("card_detail.html", card=card, prices=prices)


@bp.route("/cards/<int:card_id>/refresh", methods=["POST"])
def refresh_prices(card_id):
    card = Card.query.get_or_404(card_id)
    ebay_listings = scrape_ebay_sold(card.ebay_query or card.name)
    cardmarket_listings = scrape_cardmarket(card.cardmarket_url)

    save_best_price(card, "ebay_uk_sold", ebay_listings)
    save_best_price(card, "cardmarket_uk", cardmarket_listings)
    db.session.commit()

    flash("Refreshed pricing data.", "success")
    return redirect(url_for("main.card_detail", card_id=card.id))


def save_best_price(card, source, listings):
    if not listings:
        return

    best = min(listings, key=lambda listing: listing["price_gbp"])
    db.session.add(
        PriceSnapshot(
            card=card,
            source=source,
            price_gbp=best["price_gbp"],
            source_url=best["url"],
            title=best["title"],
        )
    )
