import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlalchemy import inspect

from cardchart import create_app
from cardchart.goal_definitions import GOAL_DEFINITIONS
from cardchart.models import CollectionGoal, db


class StartupDatabaseTests(unittest.TestCase):
    def database_uri(self, path):
        return f"sqlite:///{path.as_posix()}"

    def test_startup_creates_an_absent_database_and_populates_goals(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "cardchart.sqlite"
            app = None
            try:
                app = create_app(
                    {
                        "TESTING": True,
                        "SQLALCHEMY_DATABASE_URI": self.database_uri(database_path),
                        "MARKET_PRICING_ENABLED": False,
                    }
                )

                self.assertTrue(database_path.exists())
                with app.app_context():
                    self.assertEqual(
                        set(db.metadata.tables),
                        set(inspect(db.engine).get_table_names()),
                    )
                    self.assertEqual(
                        CollectionGoal.query.count(), len(GOAL_DEFINITIONS)
                    )
            finally:
                self.dispose_database(app)

    def test_startup_adds_missing_tables_without_removing_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "cardchart.sqlite"
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("CREATE TABLE preserved_data (value TEXT NOT NULL)")
                connection.execute("INSERT INTO preserved_data VALUES ('keep me')")
                connection.commit()
            app = None
            try:
                app = create_app(
                    {
                        "TESTING": True,
                        "SQLALCHEMY_DATABASE_URI": self.database_uri(database_path),
                        "MARKET_PRICING_ENABLED": False,
                    }
                )

                with app.app_context():
                    table_names = set(inspect(db.engine).get_table_names())
                    self.assertTrue(set(db.metadata.tables).issubset(table_names))
                    self.assertIn("preserved_data", table_names)
                    self.assertEqual(
                        CollectionGoal.query.count(), len(GOAL_DEFINITIONS)
                    )

                with closing(sqlite3.connect(database_path)) as connection:
                    preserved = connection.execute(
                        "SELECT value FROM preserved_data"
                    ).fetchone()
                self.assertEqual(preserved, ("keep me",))
            finally:
                self.dispose_database(app)

    def dispose_database(self, app):
        if app is None:
            return
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
