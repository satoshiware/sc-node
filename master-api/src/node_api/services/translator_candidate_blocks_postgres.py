from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from node_api.settings import Settings

SOURCE = "ledger_postgres_translator_candidate_blocks"


class LedgerPostgresUnavailable(RuntimeError):
    """Ledger Postgres cannot be queried by the API read view."""


def ledger_postgres_database_url(settings: Settings) -> str | None:
    value = settings.ledger_postgres_database_url
    if value is None:
        return None
    resolved = value.get_secret_value().strip()
    return resolved or None


def blocks_found_payload(
    settings: Settings,
    *,
    start_time: int | None,
    end_time: int | None,
    limit: int,
    order: Literal["asc", "desc"],
) -> dict[str, Any]:
    database_url = ledger_postgres_database_url(settings)
    if database_url is None:
        raise LedgerPostgresUnavailable("ledger postgres database url is not configured")

    rows, total = query_translator_candidate_blocks(
        database_url,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        order=order,
    )
    return {
        "status": "ok",
        "source": SOURCE,
        "total": total,
        "items": [_row_to_item(row) for row in rows],
    }


def query_translator_candidate_blocks(
    database_url: str,
    *,
    start_time: int | None,
    end_time: int | None,
    limit: int,
    order: Literal["asc", "desc"],
) -> tuple[list[dict[str, Any]], int]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - environment packaging guard
        raise LedgerPostgresUnavailable("postgres driver is not installed") from exc

    clauses = []
    params: dict[str, Any] = {"limit": limit}
    if start_time is not None:
        clauses.append("found_time_unix >= %(start_time)s")
        params["start_time"] = start_time
    if end_time is not None:
        clauses.append("found_time_unix < %(end_time)s")
        params["end_time"] = end_time

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    direction = "ASC" if order == "asc" else "DESC"
    try:
        with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT count(*) AS total FROM translator_candidate_blocks {where_sql}",
                    params,
                )
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    f"""
                    SELECT
                        found_time,
                        found_time_unix,
                        blockhash,
                        worker_identity,
                        channel_id,
                        source,
                        proof_type
                    FROM translator_candidate_blocks
                    {where_sql}
                    ORDER BY found_time_unix {direction}, id {direction}
                    LIMIT %(limit)s
                    """,
                    params,
                )
                rows = [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        raise LedgerPostgresUnavailable("ledger postgres query failed") from exc
    return rows, total


def _row_to_item(row: dict[str, Any]) -> dict[str, Any]:
    found_time = row["found_time"]
    found_time_unix = int(row["found_time_unix"])
    return {
        "found_time": found_time_unix,
        "found_time_iso": _found_time_iso(found_time, found_time_unix),
        "blockhash": str(row["blockhash"]).lower(),
        "worker_identity": row.get("worker_identity"),
        "channel_id": row.get("channel_id"),
        "source": row["source"],
        "proof_type": row["proof_type"],
    }


def _found_time_iso(found_time: Any, found_time_unix: int) -> str:
    if isinstance(found_time, datetime):
        value = found_time
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return datetime.fromtimestamp(found_time_unix, tz=UTC).isoformat().replace("+00:00", "Z")
