from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
import os

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import load_settings
from app.models import Settlement, SnapshotBlock, User, UserPayout
from app.postgres_db import make_postgres_engine, make_postgres_session_factory
from app.postgres_repositories import PostgresLedgerRepository
from app.reward_contract import compute_matured_window


SATS_PER_BTC = Decimal("100000000")
SQLITE_WORK_QUANTUM = Decimal("0.00000001")


class PostgresShadowCompareError(RuntimeError):
    pass


@dataclass(frozen=True)
class _SQLiteSettlementContext:
    settlement: Settlement
    work_window_start: datetime
    work_window_end: datetime
    payout_rows: list[tuple[UserPayout, User]]
    block_rows: list[SnapshotBlock]


def _to_decimal_str(value: Decimal | int | str) -> str:
    return f"{Decimal(str(value)):.8f}"


def _normalize_work(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(SQLITE_WORK_QUANTUM, rounding=ROUND_HALF_UP)


def _btc_to_sats(value: Decimal | int | str) -> int:
    btc = Decimal(str(value))
    sats = (btc * SATS_PER_BTC).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(sats)


def get_postgres_shadow_compare_repository() -> PostgresLedgerRepository:
    database_url = os.getenv("POSTGRES_LEDGER_DATABASE_URL", "").strip()
    if not database_url:
        raise PostgresShadowCompareError("POSTGRES_LEDGER_DATABASE_URL is not configured")

    try:
        engine = make_postgres_engine(database_url)
        return PostgresLedgerRepository(make_postgres_session_factory(engine))
    except SQLAlchemyError as exc:
        raise PostgresShadowCompareError(f"Failed to initialize Postgres repository: {exc}") from exc


def _load_sqlite_settlement_context(session: Session, settlement_id: int) -> _SQLiteSettlementContext | None:
    settlement = session.get(Settlement, settlement_id)
    if settlement is None:
        return None

    settings = load_settings()
    if settings.enable_block_event_rewards:
        work_window_start, work_window_end = compute_matured_window(
            settlement.period_end,
            interval_minutes=settings.payout_interval_minutes,
            maturity_window_minutes=settings.maturity_window_minutes,
        )
    else:
        work_window_start, work_window_end = settlement.period_start, settlement.period_end

    payout_rows = session.execute(
        select(UserPayout, User)
        .join(User, User.id == UserPayout.user_id)
        .where(UserPayout.settlement_id == settlement_id)
        .order_by(User.username.asc(), UserPayout.id.asc())
    ).all()
    block_rows = session.execute(
        select(SnapshotBlock)
        .where(SnapshotBlock.settlement_id == settlement_id)
        .order_by(SnapshotBlock.found_at.asc(), SnapshotBlock.id.asc())
    ).scalars().all()

    return _SQLiteSettlementContext(
        settlement=settlement,
        work_window_start=work_window_start,
        work_window_end=work_window_end,
        payout_rows=payout_rows,
        block_rows=block_rows,
    )


def _sqlite_summary(context: _SQLiteSettlementContext) -> dict[str, object]:
    rewarded_blocks = [row for row in context.block_rows if row.reward_sats is not None and int(row.reward_sats) > 0]
    payout_rows = [
        {
            "username": user.username,
            "amount_sats": _btc_to_sats(payout.amount_btc),
            "status": payout.status,
            "idempotency_key": payout.idempotency_key,
        }
        for payout, user in context.payout_rows
    ]
    return {
        "settlement_id": int(context.settlement.id),
        "status": context.settlement.status,
        "period_start": context.settlement.period_start.isoformat(),
        "period_end": context.settlement.period_end.isoformat(),
        "work_window_start": context.work_window_start.isoformat(),
        "work_window_end": context.work_window_end.isoformat(),
        "total_reward_sats": _btc_to_sats(context.settlement.pool_reward_btc),
        "total_work": _to_decimal_str(_normalize_work(context.settlement.total_work)),
        "total_shares": int(context.settlement.total_shares or 0),
        "user_payout_count": len(payout_rows),
        "user_payouts": payout_rows,
        "rewarded_block_count": len(rewarded_blocks),
        "rewarded_block_total_sats": sum(int(row.reward_sats or 0) for row in rewarded_blocks),
    }


def _postgres_summary(repository: PostgresLedgerRepository, context: _SQLiteSettlementContext) -> dict[str, object] | None:
    settlement_row = repository.get_settlement_window_by_range(
        work_window_start=context.work_window_start.replace(tzinfo=UTC),
        work_window_end=context.work_window_end.replace(tzinfo=UTC),
    )
    if settlement_row is None:
        return None

    credits = repository.list_settlement_user_credits_with_users(int(settlement_row["id"]))
    blocks = repository.list_settlement_blocks(int(settlement_row["id"]))
    payout_rows = [
        {
            "username": str(row["username"]),
            "amount_sats": int(row["amount_sats"] or 0),
            "status": row["status"],
            "idempotency_key": row["idempotency_key"],
        }
        for row in credits
    ]
    return {
        "settlement_window_id": int(settlement_row["id"]),
        "status": settlement_row["status"],
        "settlement_run_at": settlement_row["settlement_run_at"].isoformat(),
        "work_window_start": settlement_row["work_window_start"].isoformat(),
        "work_window_end": settlement_row["work_window_end"].isoformat(),
        "total_reward_sats": int(settlement_row["total_reward_sats"] or 0),
        "total_work": _to_decimal_str(_normalize_work(settlement_row["total_work"] or 0)),
        "total_shares": int(settlement_row["total_shares"] or 0),
        "user_payout_count": len(payout_rows),
        "user_payouts": payout_rows,
        "rewarded_block_count": len(blocks),
        "rewarded_block_total_sats": sum(int(row["reward_sats"] or 0) for row in blocks),
    }


def _mismatch(field: str, sqlite_value: object, postgres_value: object, message: str) -> dict[str, object]:
    return {
        "field": field,
        "sqlite": sqlite_value,
        "postgres": postgres_value,
        "message": message,
    }


def compare_postgres_shadow_settlement(
    session: Session,
    settlement_id: int,
) -> tuple[dict[str, object], int]:
    checked_at = datetime.now(UTC).isoformat()
    context = _load_sqlite_settlement_context(session, settlement_id)
    if context is None:
        return (
            {
                "status": "ok",
                "settlement_id": settlement_id,
                "comparison_status": "not_found",
                "sqlite_summary": None,
                "postgres_summary": None,
                "mismatches": [
                    {
                        "field": "sqlite_settlement",
                        "message": f"SQLite settlement {settlement_id} was not found.",
                    }
                ],
                "checked_at": checked_at,
            },
            404,
        )

    sqlite_summary = _sqlite_summary(context)

    try:
        repository = get_postgres_shadow_compare_repository()
        postgres_summary = _postgres_summary(repository, context)
    except PostgresShadowCompareError as exc:
        return (
            {
                "status": "error",
                "settlement_id": settlement_id,
                "comparison_status": "error",
                "sqlite_summary": sqlite_summary,
                "postgres_summary": None,
                "mismatches": [],
                "error": str(exc),
                "checked_at": checked_at,
            },
            503,
        )
    except SQLAlchemyError as exc:
        return (
            {
                "status": "error",
                "settlement_id": settlement_id,
                "comparison_status": "error",
                "sqlite_summary": sqlite_summary,
                "postgres_summary": None,
                "mismatches": [],
                "error": f"Postgres comparison query failed: {exc}",
                "checked_at": checked_at,
            },
            503,
        )

    if postgres_summary is None:
        return (
            {
                "status": "ok",
                "settlement_id": settlement_id,
                "comparison_status": "not_found",
                "sqlite_summary": sqlite_summary,
                "postgres_summary": None,
                "mismatches": [],
                "checked_at": checked_at,
            },
            200,
        )

    mismatches: list[dict[str, object]] = []
    if int(sqlite_summary["total_reward_sats"]) != int(postgres_summary["total_reward_sats"]):
        mismatches.append(
            _mismatch(
                "total_reward_sats",
                sqlite_summary["total_reward_sats"],
                postgres_summary["total_reward_sats"],
                "SQLite reward total does not match Postgres settlement reward total.",
            )
        )
    if sqlite_summary["total_work"] != postgres_summary["total_work"]:
        mismatches.append(
            _mismatch(
                "total_work",
                sqlite_summary["total_work"],
                postgres_summary["total_work"],
                "SQLite total_work does not match Postgres total_work after SQLite precision normalization.",
            )
        )
    if int(sqlite_summary["total_shares"]) != int(postgres_summary["total_shares"]):
        mismatches.append(
            _mismatch(
                "total_shares",
                sqlite_summary["total_shares"],
                postgres_summary["total_shares"],
                "SQLite total_shares does not match Postgres total_shares.",
            )
        )
    if int(sqlite_summary["user_payout_count"]) != int(postgres_summary["user_payout_count"]):
        mismatches.append(
            _mismatch(
                "user_payout_count",
                sqlite_summary["user_payout_count"],
                postgres_summary["user_payout_count"],
                "SQLite payout row count does not match Postgres settlement_user_credits count.",
            )
        )
    if int(sqlite_summary["rewarded_block_count"]) != int(postgres_summary["rewarded_block_count"]):
        mismatches.append(
            _mismatch(
                "rewarded_block_count",
                sqlite_summary["rewarded_block_count"],
                postgres_summary["rewarded_block_count"],
                "SQLite rewarded block count does not match Postgres settlement block count.",
            )
        )
    if int(sqlite_summary["rewarded_block_total_sats"]) != int(postgres_summary["rewarded_block_total_sats"]):
        mismatches.append(
            _mismatch(
                "rewarded_block_total_sats",
                sqlite_summary["rewarded_block_total_sats"],
                postgres_summary["rewarded_block_total_sats"],
                "SQLite rewarded block total does not match Postgres settlement block reward total.",
            )
        )

    sqlite_payouts_by_username = {
        str(row["username"]): int(row["amount_sats"]) for row in sqlite_summary["user_payouts"]
    }
    postgres_payouts_by_username = {
        str(row["username"]): int(row["amount_sats"]) for row in postgres_summary["user_payouts"]
    }
    for username in sorted(set(sqlite_payouts_by_username) | set(postgres_payouts_by_username)):
        sqlite_amount = sqlite_payouts_by_username.get(username)
        postgres_amount = postgres_payouts_by_username.get(username)
        if sqlite_amount != postgres_amount:
            mismatches.append(
                _mismatch(
                    f"user_payouts.{username}",
                    sqlite_amount,
                    postgres_amount,
                    f"SQLite payout amount does not match Postgres credit amount for user {username}.",
                )
            )

    comparison_status = "matched" if not mismatches else "mismatched"
    return (
        {
            "status": "ok",
            "settlement_id": settlement_id,
            "comparison_status": comparison_status,
            "sqlite_summary": sqlite_summary,
            "postgres_summary": postgres_summary,
            "mismatches": mismatches,
            "checked_at": checked_at,
        },
        200,
    )
