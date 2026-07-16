from flask import Blueprint, flash, redirect, render_template, request, url_for

from .importer import import_cards
from .models import Card, PriceSnapshot, db
from .scrapers import scrape_cardmarket, scrape_ebay_sold

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    cards = Card.query.order_by(Card.name).all()
    return render_template("index.html", cards=cards)


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
                f"used {result.fallbacks} fallback lookups.",
                "success",
            )
            for warning in result.warnings[:5]:
                flash(warning, "warning")
            if len(result.warnings) > 5:
                flash(f"{len(result.warnings) - 5} more import warnings were hidden.", "warning")
            return redirect(url_for("main.index"))
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
