from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.postgres_db import make_postgres_engine, make_postgres_session_factory, resolve_postgres_database_url
from app.postgres_repositories import PostgresLedgerRepository
from app.postgres_schema import metadata


def _make_repository() -> tuple[PostgresLedgerRepository, object, str]:
    pytest.importorskip("psycopg")

    database_url = resolve_postgres_database_url(os.getenv("POSTGRES_LEDGER_TEST_DATABASE_URL"))
    base_engine = make_postgres_engine(database_url)

    try:
        with base_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"Postgres is not reachable for repository smoke test: {exc}")

    schema_name = f"ledger_test_{uuid.uuid4().hex}"
    with base_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    schema_engine = make_postgres_engine(database_url, schema=schema_name)
    metadata.create_all(schema_engine)

    repository = PostgresLedgerRepository(make_postgres_session_factory(schema_engine))
    return repository, base_engine, schema_name


def _drop_schema(base_engine, schema_name: str) -> None:
    with base_engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))


def test_postgres_repository_smoke() -> None:
    repository, base_engine, schema_name = _make_repository()
    try:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        user = repository.upsert_user("alice")
        same_user = repository.upsert_user("alice")
        assert same_user["id"] == user["id"]

        miner = repository.upsert_miner_identity(
            user_id=user["id"],
            identity="alice.rig1",
            worker_name="rig1",
        )
        assert repository.get_miner_identity("alice.rig1")["id"] == miner["id"]

        snapshot = repository.create_raw_miner_snapshot(
            captured_at=now,
            channel_id=7,
            identity="alice.rig1",
            accepted_shares_total=25,
            accepted_work_total=Decimal("1250.5000000000000000"),
            rejected_shares_total=1,
            raw_payload={"accepted": 25},
        )
        assert repository.get_raw_miner_snapshot(snapshot["id"])["identity"] == "alice.rig1"

        work_delta = repository.create_miner_work_delta(
            identity="alice.rig1",
            channel_id=7,
            from_snapshot_id=snapshot["id"],
            to_snapshot_id=snapshot["id"],
            interval_start=now - timedelta(minutes=10),
            interval_end=now,
            share_delta=25,
            work_delta=Decimal("1250.5000000000000000"),
        )
        assert repository.get_miner_work_delta(work_delta["id"])["share_delta"] == 25

        block = repository.upsert_block_found(
            blockhash="blockhash-001",
            found_at=now + timedelta(minutes=1),
            channel_id=7,
            worker_identity="alice.rig1",
        )
        assert repository.get_block_found("blockhash-001")["id"] == block["id"]

        reward = repository.upsert_block_reward(
            blockhash="blockhash-001",
            reward_sats=187_500_000,
            fetched_at=now + timedelta(minutes=2),
        )
        assert repository.get_block_reward("blockhash-001")["reward_sats"] == 187_500_000

        settlement = repository.upsert_settlement_window(
            settlement_run_at=now + timedelta(hours=4),
            work_window_start=now - timedelta(hours=8, minutes=200),
            work_window_end=now - timedelta(minutes=200),
            maturity_offset_minutes=200,
            status="pending",
            total_reward_sats=187_500_000,
            total_work=Decimal("1250.5000000000000000"),
            total_shares=25,
        )
        same_settlement = repository.get_settlement_window_by_range(
            work_window_start=settlement["work_window_start"],
            work_window_end=settlement["work_window_end"],
        )
        assert same_settlement["id"] == settlement["id"]

        settlement_block = repository.link_settlement_block(
            settlement_id=settlement["id"],
            blockhash="blockhash-001",
            reward_sats=187_500_000,
        )
        same_settlement_block = repository.link_settlement_block(
            settlement_id=settlement["id"],
            blockhash="blockhash-001",
            reward_sats=187_500_000,
        )
        assert same_settlement_block["id"] == settlement_block["id"]

        user_work = repository.upsert_settlement_user_work(
            settlement_id=settlement["id"],
            user_id=user["id"],
            share_delta=25,
            work_delta=Decimal("1250.5000000000000000"),
            payout_fraction=Decimal("1.000000000000000000"),
        )
        assert repository.get_settlement_user_work(
            settlement_id=settlement["id"],
            user_id=user["id"],
        )["id"] == user_work["id"]

        user_credit = repository.upsert_settlement_user_credit(
            settlement_id=settlement["id"],
            user_id=user["id"],
            amount_sats=187_500_000,
            idempotency_key=f"settlement-{settlement['id']}-user-{user['id']}",
            status="pending",
        )
        assert repository.get_settlement_user_credit(
            settlement_id=settlement["id"],
            user_id=user["id"],
        )["id"] == user_credit["id"]

        ledger_entry = repository.create_account_ledger_entry(
            user_id=user["id"],
            entry_type="settlement_credit",
            amount_sats=187_500_000,
            direction="credit",
            settlement_credit_id=user_credit["id"],
            memo="initial credit",
        )
        assert repository.get_account_ledger_entry(ledger_entry["id"])["settlement_credit_id"] == user_credit["id"]

        balance = repository.set_account_balance(
            user_id=user["id"],
            balance_sats=187_500_000,
            updated_at=now + timedelta(minutes=3),
        )
        assert balance["balance_sats"] == 187_500_000
        assert repository.get_account_balance(user["id"])["balance_sats"] == 187_500_000

        audit_event = repository.create_audit_event(
            event_type="settlement_created",
            entity_type="settlement_window",
            entity_id=str(settlement["id"]),
            payload={"settlement_id": settlement["id"]},
            payload_hash="payload-1",
        )
        assert repository.get_audit_event(audit_event["id"])["event_type"] == "settlement_created"

        cursor = repository.upsert_service_cursor(
            cursor_name="translator_blocks_found",
            cursor_value="cursor-001",
            updated_at=now + timedelta(minutes=4),
        )
        assert repository.get_service_cursor("translator_blocks_found")["id"] == cursor["id"]
    finally:
        _drop_schema(base_engine, schema_name)
