from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from app.postgres_schema import (
    account_balances,
    account_ledger_entries,
    audit_events,
    block_rewards,
    blocks_found,
    metadata,
    miner_identities,
    miner_work_deltas,
    raw_miner_snapshots,
    service_cursors,
    settlement_blocks,
    settlement_user_credits,
    settlement_user_work,
    settlement_windows,
    users,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _require_tzaware(name: str, value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _as_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def _clean_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


@dataclass
class PostgresLedgerRepository:
    session_factory: sessionmaker

    def get_metadata(self):
        return metadata

    def _execute_returning_one(self, statement) -> dict[str, Any]:
        with self.session_factory() as session:
            with session.begin():
                row = session.execute(statement).one()
            return _row_to_dict(row)

    def _select_one_or_none(self, statement: Select) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.execute(statement).first()
            return None if row is None else _row_to_dict(row)

    def upsert_user(
        self,
        username: str,
        *,
        status: str = "active",
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("created_at", created_at)
        values = _clean_values(
            {
                "username": username,
                "status": status,
                "created_at": created_at,
            }
        )
        statement = (
            pg_insert(users)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[users.c.username],
                set_={"status": status},
            )
            .returning(*users.c)
        )
        return self._execute_returning_one(statement)

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        return self._select_one_or_none(select(users).where(users.c.id == user_id))

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return self._select_one_or_none(select(users).where(users.c.username == username))

    def upsert_miner_identity(
        self,
        user_id: int,
        identity: str,
        *,
        worker_name: str | None = None,
        status: str = "active",
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("created_at", created_at)
        values = _clean_values(
            {
                "user_id": user_id,
                "identity": identity,
                "worker_name": worker_name,
                "status": status,
                "created_at": created_at,
            }
        )
        statement = (
            pg_insert(miner_identities)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[miner_identities.c.identity],
                set_={
                    "user_id": user_id,
                    "worker_name": worker_name,
                    "status": status,
                },
            )
            .returning(*miner_identities.c)
        )
        return self._execute_returning_one(statement)

    def get_miner_identity(self, identity: str) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(miner_identities).where(miner_identities.c.identity == identity)
        )

    def create_raw_miner_snapshot(
        self,
        *,
        captured_at: datetime,
        identity: str,
        accepted_shares_total: int,
        accepted_work_total: Decimal | int | str,
        channel_id: int | None = None,
        rejected_shares_total: int = 0,
        source: str = "translator",
        raw_payload: dict[str, Any] | list[Any] | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("captured_at", captured_at)
        statement = (
            raw_miner_snapshots.insert()
            .values(
                captured_at=captured_at,
                channel_id=channel_id,
                identity=identity,
                accepted_shares_total=accepted_shares_total,
                accepted_work_total=_as_decimal(accepted_work_total),
                rejected_shares_total=rejected_shares_total,
                source=source,
                raw_payload=raw_payload,
            )
            .returning(*raw_miner_snapshots.c)
        )
        return self._execute_returning_one(statement)

    def get_raw_miner_snapshot(self, snapshot_id: int) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(raw_miner_snapshots).where(raw_miner_snapshots.c.id == snapshot_id)
        )

    def create_miner_work_delta(
        self,
        *,
        identity: str,
        interval_start: datetime,
        interval_end: datetime,
        share_delta: int,
        work_delta: Decimal | int | str,
        channel_id: int | None = None,
        from_snapshot_id: int | None = None,
        to_snapshot_id: int | None = None,
        reset_detected: bool = False,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("interval_start", interval_start)
        _require_tzaware("interval_end", interval_end)
        _require_tzaware("created_at", created_at)
        statement = (
            miner_work_deltas.insert()
            .values(
                identity=identity,
                channel_id=channel_id,
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                interval_start=interval_start,
                interval_end=interval_end,
                share_delta=share_delta,
                work_delta=_as_decimal(work_delta),
                reset_detected=reset_detected,
                **({"created_at": created_at} if created_at is not None else {}),
            )
            .returning(*miner_work_deltas.c)
        )
        return self._execute_returning_one(statement)

    def get_miner_work_delta(self, delta_id: int) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(miner_work_deltas).where(miner_work_deltas.c.id == delta_id)
        )

    def upsert_block_found(
        self,
        *,
        blockhash: str,
        found_at: datetime,
        channel_id: int | None = None,
        worker_identity: str | None = None,
        source: str = "translator_blocks_found",
        status: str = "found",
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("found_at", found_at)
        _require_tzaware("created_at", created_at)
        values = _clean_values(
            {
                "blockhash": blockhash,
                "found_at": found_at,
                "channel_id": channel_id,
                "worker_identity": worker_identity,
                "source": source,
                "status": status,
                "created_at": created_at,
            }
        )
        statement = (
            pg_insert(blocks_found)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[blocks_found.c.blockhash],
                set_={
                    "found_at": found_at,
                    "channel_id": channel_id,
                    "worker_identity": worker_identity,
                    "source": source,
                    "status": status,
                },
            )
            .returning(*blocks_found.c)
        )
        return self._execute_returning_one(statement)

    def get_block_found(self, blockhash: str) -> dict[str, Any] | None:
        return self._select_one_or_none(select(blocks_found).where(blocks_found.c.blockhash == blockhash))

    def upsert_block_reward(
        self,
        *,
        blockhash: str,
        reward_sats: int,
        reward_source: str = "az_block_rewards",
        fetched_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("fetched_at", fetched_at)
        values = _clean_values(
            {
                "blockhash": blockhash,
                "reward_sats": reward_sats,
                "reward_source": reward_source,
                "fetched_at": fetched_at,
            }
        )
        statement = (
            pg_insert(block_rewards)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[block_rewards.c.blockhash],
                set_=_clean_values(
                    {
                        "reward_sats": reward_sats,
                        "reward_source": reward_source,
                        "fetched_at": fetched_at,
                    }
                ),
            )
            .returning(*block_rewards.c)
        )
        return self._execute_returning_one(statement)

    def get_block_reward(self, blockhash: str) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(block_rewards).where(block_rewards.c.blockhash == blockhash)
        )

    def upsert_settlement_window(
        self,
        *,
        settlement_run_at: datetime,
        work_window_start: datetime,
        work_window_end: datetime,
        maturity_offset_minutes: int,
        status: str = "pending",
        total_reward_sats: int = 0,
        total_work: Decimal | int | str = Decimal("0"),
        total_shares: int = 0,
        created_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("settlement_run_at", settlement_run_at)
        _require_tzaware("work_window_start", work_window_start)
        _require_tzaware("work_window_end", work_window_end)
        _require_tzaware("created_at", created_at)
        _require_tzaware("completed_at", completed_at)
        values = _clean_values(
            {
                "status": status,
                "settlement_run_at": settlement_run_at,
                "work_window_start": work_window_start,
                "work_window_end": work_window_end,
                "maturity_offset_minutes": maturity_offset_minutes,
                "total_reward_sats": total_reward_sats,
                "total_work": _as_decimal(total_work),
                "total_shares": total_shares,
                "created_at": created_at,
                "completed_at": completed_at,
            }
        )
        statement = (
            pg_insert(settlement_windows)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    settlement_windows.c.work_window_start,
                    settlement_windows.c.work_window_end,
                ],
                set_={
                    "status": status,
                    "settlement_run_at": settlement_run_at,
                    "maturity_offset_minutes": maturity_offset_minutes,
                    "total_reward_sats": total_reward_sats,
                    "total_work": _as_decimal(total_work),
                    "total_shares": total_shares,
                    "completed_at": completed_at,
                },
            )
            .returning(*settlement_windows.c)
        )
        return self._execute_returning_one(statement)

    def get_settlement_window_by_id(self, settlement_id: int) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(settlement_windows).where(settlement_windows.c.id == settlement_id)
        )

    def get_settlement_window_by_range(
        self,
        *,
        work_window_start: datetime,
        work_window_end: datetime,
    ) -> dict[str, Any] | None:
        _require_tzaware("work_window_start", work_window_start)
        _require_tzaware("work_window_end", work_window_end)
        return self._select_one_or_none(
            select(settlement_windows).where(
                settlement_windows.c.work_window_start == work_window_start,
                settlement_windows.c.work_window_end == work_window_end,
            )
        )

    def link_settlement_block(
        self,
        *,
        settlement_id: int,
        blockhash: str,
        reward_sats: int,
    ) -> dict[str, Any]:
        statement = (
            pg_insert(settlement_blocks)
            .values(
                settlement_id=settlement_id,
                blockhash=blockhash,
                reward_sats=reward_sats,
            )
            .on_conflict_do_nothing(index_elements=[settlement_blocks.c.blockhash])
            .returning(*settlement_blocks.c)
        )
        row = self._select_returned_or_none(statement)
        if row is not None:
            return row
        existing = self.get_settlement_block(blockhash)
        if existing is None:
            raise RuntimeError("settlement block insert conflicted but no existing row was found")
        if (
            existing["settlement_id"] != settlement_id
            or existing["reward_sats"] != reward_sats
        ):
            raise ValueError(
                f"blockhash {blockhash} is already linked to settlement {existing['settlement_id']}"
            )
        return existing

    def _select_returned_or_none(self, statement) -> dict[str, Any] | None:
        with self.session_factory() as session:
            with session.begin():
                row = session.execute(statement).first()
            return None if row is None else _row_to_dict(row)

    def get_settlement_block(self, blockhash: str) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(settlement_blocks).where(settlement_blocks.c.blockhash == blockhash)
        )

    def upsert_settlement_user_work(
        self,
        *,
        settlement_id: int,
        user_id: int,
        share_delta: int,
        work_delta: Decimal | int | str,
        payout_fraction: Decimal | int | str,
    ) -> dict[str, Any]:
        statement = (
            pg_insert(settlement_user_work)
            .values(
                settlement_id=settlement_id,
                user_id=user_id,
                share_delta=share_delta,
                work_delta=_as_decimal(work_delta),
                payout_fraction=_as_decimal(payout_fraction),
            )
            .on_conflict_do_update(
                index_elements=[
                    settlement_user_work.c.settlement_id,
                    settlement_user_work.c.user_id,
                ],
                set_={
                    "share_delta": share_delta,
                    "work_delta": _as_decimal(work_delta),
                    "payout_fraction": _as_decimal(payout_fraction),
                },
            )
            .returning(*settlement_user_work.c)
        )
        return self._execute_returning_one(statement)

    def get_settlement_user_work(
        self,
        *,
        settlement_id: int,
        user_id: int,
    ) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(settlement_user_work).where(
                settlement_user_work.c.settlement_id == settlement_id,
                settlement_user_work.c.user_id == user_id,
            )
        )

    def upsert_settlement_user_credit(
        self,
        *,
        settlement_id: int,
        user_id: int,
        amount_sats: int,
        idempotency_key: str,
        status: str = "pending",
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("created_at", created_at)
        values = _clean_values(
            {
                "settlement_id": settlement_id,
                "user_id": user_id,
                "amount_sats": amount_sats,
                "idempotency_key": idempotency_key,
                "status": status,
                "created_at": created_at,
            }
        )
        statement = (
            pg_insert(settlement_user_credits)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    settlement_user_credits.c.settlement_id,
                    settlement_user_credits.c.user_id,
                ],
                set_={
                    "amount_sats": amount_sats,
                    "idempotency_key": idempotency_key,
                    "status": status,
                },
            )
            .returning(*settlement_user_credits.c)
        )
        return self._execute_returning_one(statement)

    def get_settlement_user_credit(
        self,
        *,
        settlement_id: int,
        user_id: int,
    ) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(settlement_user_credits).where(
                settlement_user_credits.c.settlement_id == settlement_id,
                settlement_user_credits.c.user_id == user_id,
            )
        )

    def create_account_ledger_entry(
        self,
        *,
        user_id: int,
        entry_type: str,
        amount_sats: int,
        direction: str,
        settlement_credit_id: int | None = None,
        memo: str | None = None,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("created_at", created_at)
        values = _clean_values(
            {
                "user_id": user_id,
                "entry_type": entry_type,
                "amount_sats": amount_sats,
                "direction": direction,
                "settlement_credit_id": settlement_credit_id,
                "memo": memo,
                "created_at": created_at,
            }
        )
        statement = account_ledger_entries.insert().values(**values).returning(*account_ledger_entries.c)
        return self._execute_returning_one(statement)

    def get_account_ledger_entry(self, entry_id: int) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(account_ledger_entries).where(account_ledger_entries.c.id == entry_id)
        )

    def set_account_balance(
        self,
        *,
        user_id: int,
        balance_sats: int,
        updated_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("updated_at", updated_at)
        values = _clean_values(
            {
                "user_id": user_id,
                "balance_sats": balance_sats,
                "updated_at": updated_at or utcnow(),
            }
        )
        statement = (
            pg_insert(account_balances)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[account_balances.c.user_id],
                set_={
                    "balance_sats": balance_sats,
                    "updated_at": values["updated_at"],
                },
            )
            .returning(*account_balances.c)
        )
        return self._execute_returning_one(statement)

    def get_account_balance(self, user_id: int) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(account_balances).where(account_balances.c.user_id == user_id)
        )

    def create_audit_event(
        self,
        *,
        event_type: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | list[Any] | None = None,
        payload_hash: str | None = None,
        previous_hash: str | None = None,
        event_hash: str | None = None,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("created_at", created_at)
        values = _clean_values(
            {
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload,
                "payload_hash": payload_hash,
                "previous_hash": previous_hash,
                "event_hash": event_hash,
                "created_at": created_at,
            }
        )
        statement = audit_events.insert().values(**values).returning(*audit_events.c)
        return self._execute_returning_one(statement)

    def get_audit_event(self, event_id: int) -> dict[str, Any] | None:
        return self._select_one_or_none(select(audit_events).where(audit_events.c.id == event_id))

    def upsert_service_cursor(
        self,
        *,
        cursor_name: str,
        cursor_value: str | None,
        updated_at: datetime | None = None,
    ) -> dict[str, Any]:
        _require_tzaware("updated_at", updated_at)
        effective_updated_at = updated_at or utcnow()
        statement = (
            pg_insert(service_cursors)
            .values(
                cursor_name=cursor_name,
                cursor_value=cursor_value,
                updated_at=effective_updated_at,
            )
            .on_conflict_do_update(
                index_elements=[service_cursors.c.cursor_name],
                set_={
                    "cursor_value": cursor_value,
                    "updated_at": effective_updated_at,
                },
            )
            .returning(*service_cursors.c)
        )
        return self._execute_returning_one(statement)

    def get_service_cursor(self, cursor_name: str) -> dict[str, Any] | None:
        return self._select_one_or_none(
            select(service_cursors).where(service_cursors.c.cursor_name == cursor_name)
        )
