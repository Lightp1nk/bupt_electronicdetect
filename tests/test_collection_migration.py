from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def _config(path: Path) -> Config:
    config = Config(str((Path(__file__).parents[1] / "alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    return config


def test_collection_settings_migration_preserves_unowned_legacy_data(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, bupt_username VARCHAR(64) NOT NULL);
        CREATE TABLE collection_settings (
            id INTEGER PRIMARY KEY, area_id VARCHAR(32), building_id VARCHAR(128), building_name VARCHAR(255),
            floor_id VARCHAR(128), floor_name VARCHAR(255), room_id VARCHAR(128), room_name VARCHAR(255),
            enabled BOOLEAN NOT NULL, status VARCHAR(32) NOT NULL, message VARCHAR(512),
            last_attempt_time DATETIME, last_success_time DATETIME, last_source_time DATETIME
        );
        INSERT INTO collection_settings VALUES (1, '2', 'building', '旧楼', 'floor', '旧层', 'room', '旧宿舍', 1, 'success', 'legacy', NULL, NULL, NULL);
    """)
    connection.commit()
    connection.close()

    command.upgrade(_config(path), "head")

    connection = sqlite3.connect(path)
    legacy = connection.execute("SELECT area_id, room_id, message FROM collection_settings_legacy_unassigned").fetchone()
    assert legacy == ("2", "room", "legacy")
    assert connection.execute("SELECT count(*) FROM collection_settings").fetchone() == (0,)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(collection_settings)")}
    assert {"id", "user_id", "area_name", "room_id"} <= columns
    connection.execute("INSERT INTO users (id, bupt_username) VALUES (7, 'new-user')")
    connection.execute("INSERT INTO collection_settings (user_id, area_id, area_name, enabled, status) VALUES (7, '2', '沙河', 1, 'never_run')")
    connection.commit()
    assert connection.execute("SELECT user_id, area_name FROM collection_settings").fetchone() == (7, "沙河")
    connection.close()
