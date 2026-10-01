import unittest
from uuid import UUID

from sqlalchemy import create_engine, text

from app.db.init_db import migrate_security_decision_schema, migrate_security_event_schema


class DecisionSchemaMigrationTests(unittest.TestCase):
    def test_legacy_decisions_are_backfilled_without_overwriting_review_differences(self) -> None:
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE TABLE security_decisions ("
                    "id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, action VARCHAR(16) NOT NULL, "
                    "reason TEXT NOT NULL, created_at DATETIME NOT NULL)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO security_decisions "
                    "(id, session_id, action, reason, created_at) "
                    "VALUES (1, 1, 'block', 'legacy record', CURRENT_TIMESTAMP)"
                )

            migrate_security_decision_schema(engine)
            with engine.begin() as connection:
                recommendation, request_id = connection.execute(
                    text("SELECT recommended_action, request_id FROM security_decisions WHERE id = 1")
                ).one()
                self.assertEqual(recommendation, "block")
                UUID(request_id)
                connection.execute(
                    text(
                        "UPDATE security_decisions SET action = 'allow', recommended_action = 'block' "
                        "WHERE id = 1"
                    )
                )

            migrate_security_decision_schema(engine)
            with engine.connect() as connection:
                row = connection.execute(
                    text("SELECT action, recommended_action FROM security_decisions WHERE id = 1")
                ).one()
            self.assertEqual(row, ("allow", "block"))

            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE TABLE events (id INTEGER PRIMARY KEY, occurred_at DATETIME NOT NULL)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO events (id, occurred_at) VALUES (1, '2026-10-01 12:00:00')"
                )
            migrate_security_event_schema(engine)
            with engine.connect() as connection:
                occurred_at, received_at = connection.execute(
                    text("SELECT occurred_at, received_at FROM events WHERE id = 1")
                ).one()
            self.assertEqual(received_at, occurred_at)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
