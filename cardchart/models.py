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
    goal_printings = db.relationship("GoalCardPrinting", back_populates="card")

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


class CollectionGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    scryfall_set_code = db.Column(db.String(20))
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    cards = db.relationship(
        "GoalCard",
        back_populates="goal",
        cascade="all, delete-orphan",
        order_by="GoalCard.position",
    )

    @property
    def owned_count(self):
        return sum(card.is_owned for card in self.cards)

    @property
    def total_count(self):
        return len(self.cards)

    @property
    def percentage(self):
        return round(self.owned_count * 100 / self.total_count) if self.total_count else 0

    @property
    def state(self):
        if self.total_count and self.owned_count == self.total_count:
            return "Complete"
        if self.owned_count:
            return "In progress"
        return "Not started"


class GoalCard(db.Model):
    __table_args__ = (db.UniqueConstraint("goal_id", "stable_key"),)

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("collection_goal.id"), nullable=False)
    stable_key = db.Column(db.String(200), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    oracle_id = db.Column(db.String(64))
    expected_set_code = db.Column(db.String(20))
    expected_collector_number = db.Column(db.String(50))
    image_url = db.Column(db.String(500))
    notes = db.Column(db.Text)
    accepted_scryfall_ids = db.Column(db.Text, nullable=False, default="")

    goal = db.relationship("CollectionGoal", back_populates="cards")
    printings = db.relationship(
        "GoalCardPrinting", back_populates="goal_card", cascade="all, delete-orphan"
    )

    @property
    def accepted_printing_ids(self):
        return {value for value in self.accepted_scryfall_ids.split(",") if value}

    @property
    def is_owned(self):
        return any(printing.quantity > 0 for printing in self.printings)


class GoalCardPrinting(db.Model):
    __table_args__ = (
        db.UniqueConstraint("goal_card_id", "scryfall_id", "finish", "language"),
    )

    id = db.Column(db.Integer, primary_key=True)
    goal_card_id = db.Column(db.Integer, db.ForeignKey("goal_card.id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("card.id"))
    scryfall_id = db.Column(db.String(64), nullable=False)
    set_code = db.Column(db.String(20), nullable=False)
    collector_number = db.Column(db.String(50), nullable=False)
    finish = db.Column(db.String(50), nullable=False)
    language = db.Column(db.String(20), nullable=False, default="en")
    quantity = db.Column(db.Integer, nullable=False, default=1)
    acquired_at = db.Column(db.Date)
    notes = db.Column(db.Text)

    goal_card = db.relationship("GoalCard", back_populates="printings")
    card = db.relationship("Card", back_populates="goal_printings")
