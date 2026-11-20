from __future__ import annotations

from sqlalchemy import create_engine

from app.db import _migrate_sqlite


def test_schedule_default_column_is_added_to_existing_database():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE devices (id INTEGER PRIMARY KEY, schedule_kind VARCHAR(16))"
        )

    _migrate_sqlite(engine)

    with engine.connect() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(devices)")
        }
    assert "schedule_default" in columns

    # Running it again is a no-op.
    _migrate_sqlite(engine)
    engine.dispose()
