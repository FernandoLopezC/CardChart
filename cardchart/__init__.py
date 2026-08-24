import os
import uuid
from pathlib import Path

from flask import Flask
from sqlalchemy import inspect

from .models import db
from .routes import bp


def create_app(config=None):
    app = Flask(__name__)
    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)

    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{instance_path / 'cardchart.sqlite'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MARKET_PRICING_ENABLED"] = True

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or uuid.uuid4().hex
    if config:
        app.config.update(config)

    db.init_app(app)
    app.register_blueprint(bp)

    from .goal_cli import register_goal_commands

    register_goal_commands(app)

    with app.app_context():
        ensure_database()

    @app.cli.command("init-db")
    def init_db_command():
        ensure_database()
        print("Database is ready.")

    return app


def ensure_database():
    """Create absent tables non-destructively and synchronize curated goals."""
    existing_tables = set(inspect(db.engine).get_table_names())
    missing_tables = set(db.metadata.tables) - existing_tables
    if missing_tables:
        db.create_all()

    from .goal_definitions import synchronize_goals

    synchronize_goals()
    return missing_tables
