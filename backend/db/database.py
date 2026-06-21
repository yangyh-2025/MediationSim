from __future__ import annotations


import aiosqlite

from backend.config import config


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiments (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',
    config_json TEXT NOT NULL DEFAULT '{}',
    total_runs  INTEGER NOT NULL DEFAULT 0,
    completed_runs INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    experiment_id   TEXT NOT NULL,
    condition_code  TEXT NOT NULL,
    run_index       INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    rounds_completed INTEGER NOT NULL DEFAULT 0,
    agreement_reached INTEGER NOT NULL DEFAULT 0,
    agreement_gini  REAL,
    side_payment_used REAL DEFAULT 0.0,
    result_json     TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id)
);

CREATE TABLE IF NOT EXISTS rounds (
    id                    TEXT PRIMARY KEY,
    run_id                TEXT NOT NULL,
    round_number          INTEGER NOT NULL,
    proposal_json         TEXT NOT NULL DEFAULT '{}',
    strong_response_json  TEXT NOT NULL DEFAULT '{}',
    weak_response_json    TEXT NOT NULL DEFAULT '{}',
    domestic_scores_json  TEXT NOT NULL DEFAULT '{}',
    agreement_reached     INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS evaluations (
    id              TEXT PRIMARY KEY,
    experiment_id   TEXT NOT NULL,
    batch_start     INTEGER NOT NULL,
    batch_end       INTEGER NOT NULL,
    condition_code  TEXT NOT NULL DEFAULT '',
    dimensions_json TEXT NOT NULL DEFAULT '[]',
    overall_score   REAL DEFAULT 0.0,
    adjustments_json TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id)
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id                      TEXT PRIMARY KEY,
    experiment_id           TEXT NOT NULL,
    hypothesis              TEXT NOT NULL,
    test_name               TEXT NOT NULL,
    test_statistic          REAL NOT NULL DEFAULT 0.0,
    p_value                 REAL NOT NULL DEFAULT 1.0,
    effect_size             REAL NOT NULL DEFAULT 0.0,
    confidence_interval_json TEXT NOT NULL DEFAULT '[]',
    significant             INTEGER NOT NULL DEFAULT 0,
    result_json             TEXT NOT NULL DEFAULT '{}',
    created_at              TEXT NOT NULL,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id)
);

CREATE INDEX IF NOT EXISTS idx_runs_experiment ON runs(experiment_id);
CREATE INDEX IF NOT EXISTS idx_runs_condition ON runs(experiment_id, condition_code);
CREATE INDEX IF NOT EXISTS idx_rounds_run ON rounds(run_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_experiment ON evaluations(experiment_id);
CREATE INDEX IF NOT EXISTS idx_analysis_experiment ON analysis_results(experiment_id);
"""


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: str | None = None):
        self._path = str(db_path or config.db_path)
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple | None = None) -> aiosqlite.Cursor:
        if not self._conn:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return await self._conn.execute(sql, params or ())

    async def fetch_one(self, sql: str, params: tuple | None = None) -> dict | None:
        cursor = await self.execute(sql, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, sql: str, params: tuple | None = None) -> list[dict]:
        cursor = await self.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def insert(self, table: str, data: dict) -> str:
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        await self._conn.execute(sql, tuple(data.values()))
        await self._conn.commit()
        return data.get("id", "")

    async def update(self, table: str, where: str, data: dict, params: tuple) -> None:
        sets = ", ".join(f"{k} = ?" for k in data)
        sql = f"UPDATE {table} SET {sets} WHERE {where}"
        await self._conn.execute(sql, tuple(data.values()) + params)
        await self._conn.commit()

    async def delete(self, table: str, where: str, params: tuple) -> None:
        sql = f"DELETE FROM {table} WHERE {where}"
        await self._conn.execute(sql, params)
        await self._conn.commit()
