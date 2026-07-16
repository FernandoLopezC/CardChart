from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scryfall_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    set_code = db.Column(db.String(20), nullable=False)
    set_name = db.Column(db.String(200), nullable=False)
    collector_number = db.Column(db.String(50), nullable=False)
    rarity = db.Column(db.String(50), nullable=False)
    finish = db.Column(db.String(50), nullable=False)
    finish_display = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    image_url = db.Column(db.String(500))
    scryfall_uri = db.Column(db.String(500))
    cardmarket_id = db.Column(db.Integer, nullable=True)
    cardmarket_url = db.Column(db.String(500))
    ebay_query = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    prices = db.relationship("PriceSnapshot", back_populates="card", cascade="all, delete-orphan")

    @property
    def latest_prices(self):
        latest = {}
        for price in sorted(self.prices, key=lambda item: item.checked_at, reverse=True):
            latest.setdefault(price.source, price)
        return latest


class PriceSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey("card.id"), nullable=False)
    source = db.Column(db.String(50), nullable=False)
    price_gbp = db.Column(db.Float)
    source_url = db.Column(db.String(800), nullable=False)
    title = db.Column(db.String(300))
    checked_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    card = db.relationship("Card", back_populates="prices")
