import os
from pathlib import Path

from flask import Flask

import uuid

from .models import db
from .routes import bp


def create_app():
    app = Flask(__name__)
    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)

    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{instance_path / 'cardchart.sqlite'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or uuid.uuid4().hex

    db.init_app(app)
    app.register_blueprint(bp)

    @app.cli.command("init-db")
    def init_db_command():
        db.create_all()
        print("Initialized the database.")

    return app
