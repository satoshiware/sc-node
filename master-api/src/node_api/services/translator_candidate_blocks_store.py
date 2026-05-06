from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from node_api.settings import Settings

_DEFAULT_DB_PATH = ".data/translator_candidate_blocks.sqlite3"
_PROOF_TYPE = "translator_submit_reconstructed_block_hash"
_SOURCE = "api_sidecar_reconstruction"


def utc_iso_from_unix(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TranslatorCandidateBlocksStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self.initialize()

    @classmethod
    def from_settings(cls, settings: Settings) -> "TranslatorCandidateBlocksStore":
        path = settings.translator_candidate_blocks_db_path or _DEFAULT_DB_PATH
        return cls(path)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS translator_candidate_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    found_time INTEGER NOT NULL,
                    found_time_iso TEXT NOT NULL,
                    blockhash TEXT NOT NULL,
                    worker_identity TEXT NULL,
                    channel_id INTEGER NULL,
                    job_id TEXT NULL,
                    extranonce2 TEXT NULL,
                    ntime TEXT NULL,
                    nonce TEXT NULL,
                    version TEXT NULL,
                    prev_hash TEXT NULL,
                    nbits TEXT NULL,
                    source TEXT NOT NULL,
                    proof_type TEXT NOT NULL,
                    raw_submit_json TEXT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tcb_found_time
                ON translator_candidate_blocks (found_time DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_tcb_blockhash
                ON translator_candidate_blocks (blockhash);

                CREATE INDEX IF NOT EXISTS idx_tcb_worker_identity
                ON translator_candidate_blocks (worker_identity);

                CREATE INDEX IF NOT EXISTS idx_tcb_channel_id
                ON translator_candidate_blocks (channel_id);
                """
            )

    def insert_event(self, event: dict[str, Any]) -> int:
        found_time = int(event["found_time"])
        found_time_iso = event.get("found_time_iso") or utc_iso_from_unix(found_time)
        created_at = int(time.time())
        raw_submit_json = event.get("raw_submit_json")
        if raw_submit_json is not None and not isinstance(raw_submit_json, str):
            raw_submit_json = json.dumps(raw_submit_json, separators=(",", ":"), sort_keys=True)

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO translator_candidate_blocks (
                    found_time,
                    found_time_iso,
                    blockhash,
                    worker_identity,
                    channel_id,
                    job_id,
                    extranonce2,
                    ntime,
                    nonce,
                    version,
                    prev_hash,
                    nbits,
                    source,
                    proof_type,
                    raw_submit_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    found_time,
                    found_time_iso,
                    str(event["blockhash"]).lower(),
                    event.get("worker_identity"),
                    event.get("channel_id"),
                    event.get("job_id"),
                    event.get("extranonce2"),
                    event.get("ntime"),
                    event.get("nonce"),
                    event.get("version"),
                    event.get("prev_hash"),
                    event.get("nbits"),
                    event.get("source", _SOURCE),
                    event.get("proof_type", _PROOF_TYPE),
                    raw_submit_json,
                    created_at,
                ),
            )
            return int(cur.lastrowid)

    def list_events(
        self,
        *,
        start_time: int | None,
        end_time: int | None,
        limit: int,
        order: Literal["asc", "desc"] = "desc",
        worker_identity: str | None = None,
        channel_id: int | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        where: list[str] = []
        params: list[Any] = []
        if start_time is not None:
            where.append("found_time >= ?")
            params.append(int(start_time))
        if end_time is not None:
            where.append("found_time < ?")
            params.append(int(end_time))
        if worker_identity is not None:
            where.append("worker_identity = ?")
            params.append(worker_identity)
        if channel_id is not None:
            where.append("channel_id = ?")
            params.append(int(channel_id))

        where_sql = ""
        if where:
            where_sql = "WHERE " + " AND ".join(where)
        order_sql = "ASC" if order == "asc" else "DESC"

        with self._connect() as conn:
            total_row = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM translator_candidate_blocks
                {where_sql}
                """,
                tuple(params),
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT
                    found_time,
                    found_time_iso,
                    blockhash,
                    worker_identity,
                    channel_id,
                    proof_type,
                    source
                FROM translator_candidate_blocks
                {where_sql}
                ORDER BY found_time {order_sql}, id {order_sql}
                LIMIT ?
                """,
                (*params, int(limit)),
            ).fetchall()

        total = 0 if total_row is None else int(total_row["total"])
        return total, [dict(row) for row in rows]

    def event_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM translator_candidate_blocks"
            ).fetchone()
        return 0 if row is None else int(row["total"])

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn
