from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .importer import import_cards
from .models import Card, CollectionGoal, GoalCard, GoalCardPrinting, PriceSnapshot, db
from .scrapers import scrape_cardmarket, scrape_ebay_sold

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return redirect(url_for("main.goals"))


@bp.route("/inventory")
def inventory():
    cards = Card.query.order_by(Card.name).all()
    return render_template("index.html", cards=cards)


@bp.route("/goals")
def goals():
    goals = CollectionGoal.query.order_by(CollectionGoal.name).all()
    return render_template("goals.html", goals=goals)


@bp.route("/goals/<slug>")
def goal_detail(slug):
    goal = CollectionGoal.query.filter_by(slug=slug).first_or_404()
    selected_filter = request.args.get("filter", "all")
    cards = goal.cards
    if selected_filter == "owned":
        cards = [card for card in cards if card.is_owned]
    elif selected_filter == "missing":
        cards = [card for card in cards if not card.is_owned]
    return render_template(
        "goal_detail.html", goal=goal, cards=cards, selected_filter=selected_filter
    )


@bp.route("/goals/<slug>/cards/<int:goal_card_id>/edit")
def edit_goal_card(slug, goal_card_id):
    goal_card = goal_card_for_slug(slug, goal_card_id)
    inventory = Card.query.order_by(Card.name).all()
    printing = goal_card.printings[0] if goal_card.printings else None
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
