from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_DOWN

from app.config import load_settings
from app.postgres_delta import compute_user_contribution_deltas_postgres
from app.delta import UserContribution
from app.pool_client import PoolApiError, fetch_pool_reward
from app.postgres_repositories import PostgresLedgerRepository
from app.settlement import SettlementResult

ZERO = Decimal("0")


def _q(value: Decimal, decimals: int) -> Decimal:
    quantum = Decimal("1").scaleb(-decimals)
    return value.quantize(quantum, rounding=ROUND_DOWN)


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _get_or_create_carry_postgres(
    repository: PostgresLedgerRepository,
    bucket: str = "default",
) -> dict:
    carry = repository.get_carry_state(bucket=bucket)
    if carry is None:
        carry = repository.upsert_carry_state(
            bucket=bucket,
            carry_btc=ZERO,
            updated_at=_as_utc_aware(datetime.now(UTC)),
        )
    return carry


def _get_or_create_accrual_bucket_postgres(
    repository: PostgresLedgerRepository,
    user_id: int,
) -> dict:
    bucket = repository.get_work_accrual_bucket(user_id)
    if bucket is None:
        bucket = repository.upsert_work_accrual_bucket(
            user_id=user_id,
            accumulated_work=ZERO,
            updated_at=_as_utc_aware(datetime.now(UTC)),
        )
    return bucket


def _add_work_to_accrual_postgres(
    repository: PostgresLedgerRepository,
    user_contributions: dict[str, UserContribution],
    now: datetime,
    decimals: int,
) -> None:
    now_aware = _as_utc_aware(now)
    for username, contribution in user_contributions.items():
        if contribution.work_delta <= ZERO:
            continue
        user = repository.upsert_user(username, created_at=now_aware)
        accrual = _get_or_create_accrual_bucket_postgres(repository, int(user["id"]))
        accumulated = _q(
            Decimal(str(accrual.get("accumulated_work") or 0)) + contribution.work_delta,
            decimals,
        )
        repository.upsert_work_accrual_bucket(
            user_id=int(user["id"]),
            accumulated_work=accumulated,
            updated_at=now_aware,
        )


def _apply_accrual_to_contributions_postgres(
    repository: PostgresLedgerRepository,
    user_contributions: dict[str, UserContribution],
) -> dict[str, UserContribution]:
    enhanced: dict[str, UserContribution] = {
        username: UserContribution(
            username=username,
            share_delta=contribution.share_delta,
            work_delta=contribution.work_delta,
        )
        for username, contribution in user_contributions.items()
    }

    accrual_rows = repository.list_all_work_accrual_buckets()
    for bucket in accrual_rows:
        accrued = Decimal(str(bucket.get("accumulated_work") or 0))
        if accrued <= ZERO:
            continue

        user = repository.get_user_by_id(int(bucket["user_id"]))
        if user is None:
            continue

        existing = enhanced.get(user["username"])
        if existing is None:
            enhanced[user["username"]] = UserContribution(
                username=user["username"],
                share_delta=0,
                work_delta=accrued,
            )
            continue

        enhanced[user["username"]] = UserContribution(
            username=user["username"],
            share_delta=existing.share_delta,
            work_delta=existing.work_delta + accrued,
        )

    return enhanced


def _clear_accrual_for_users_postgres(
    repository: PostgresLedgerRepository,
    usernames: list[str],
    now: datetime,
) -> None:
    now_aware = _as_utc_aware(now)
    for username in usernames:
        user = repository.get_user_by_username(username)
        if user is None:
            continue
        bucket = repository.get_work_accrual_bucket(int(user["id"]))
        if bucket is not None and Decimal(str(bucket.get("accumulated_work") or 0)) > ZERO:
            repository.upsert_work_accrual_bucket(
                user_id=int(user["id"]),
                accumulated_work=ZERO,
                updated_at=now_aware,
            )


def _summarize_contributions(
    user_contributions: dict[str, UserContribution],
) -> tuple[int, Decimal]:
    total_shares = sum(item.share_delta for item in user_contributions.values())
    total_work = sum((item.work_delta for item in user_contributions.values()), ZERO)
    return total_shares, total_work


def _build_allocation_rows(
    user_contributions: dict[str, UserContribution],
    distributable: Decimal,
    decimals: int,
) -> list[dict[str, Decimal | str]]:
    positive_work = {
        username: contribution.work_delta
        for username, contribution in user_contributions.items()
        if contribution.work_delta > ZERO
    }
    if positive_work:
        basis = positive_work
    else:
        basis = {
            username: Decimal(contribution.share_delta)
            for username, contribution in user_contributions.items()
            if contribution.share_delta > 0
        }

    basis_total = sum(basis.values(), ZERO)
    if basis_total <= ZERO or distributable <= ZERO:
        return []

    rows: list[dict[str, Decimal | str]] = []
    for username, basis_value in sorted(basis.items(), key=lambda item: item[0]):
        raw_amount = distributable * basis_value / basis_total
        rows.append(
            {
                "username": username,
                "basis_value": _q(basis_value, decimals),
                "payout_fraction": (basis_value / basis_total),
                "payout_amount": _q(raw_amount, decimals),
            }
        )

    allocated_sum = sum((Decimal(str(row["payout_amount"])) for row in rows), ZERO)
    remainder = _q(distributable - allocated_sum, decimals)
    if remainder > ZERO and rows:
        target_index = max(
            range(len(rows)),
            key=lambda i: (
                Decimal(str(rows[i]["basis_value"])),
                str(rows[i]["username"]),
            ),
        )
        rows[target_index]["payout_amount"] = _q(
            Decimal(str(rows[target_index]["payout_amount"])) + remainder,
            decimals,
        )

    return rows


def run_settlement_postgres(
    repository: PostgresLedgerRepository,
    now: datetime,
    *,
    interval_minutes: int | None = None,
    payout_decimals: int | None = None,
    reward_fetcher=fetch_pool_reward,
    defer_on_zero_reward: bool = False,
    use_work_accrual: bool = False,
    work_window_start: datetime | None = None,
    work_window_end: datetime | None = None,
) -> SettlementResult:
    """Run one settlement cycle using Postgres as the backing store.
    
    Mirrors settlement.py semantics exactly: carry state, accrual buckets, allocation,
    and deferred settlement handling all use Postgres persistence.
    """
    settings = load_settings()
    interval = interval_minutes or settings.payout_interval_minutes
    decimals = payout_decimals or settings.payout_decimals
    now_aware = _as_utc_aware(now)

    latest_settlement = repository.get_settlement_window_by_range(
        work_window_start=None,
        work_window_end=None,
    )

    period_end = now
    if latest_settlement is None:
        period_start = period_end - timedelta(minutes=interval)
    else:
        if period_end <= latest_settlement["work_window_end"]:
            payout_rows = repository.list_settlement_user_credits_with_users(int(latest_settlement["id"]))
            carry = _get_or_create_carry_postgres(repository)
            return SettlementResult(
                settlement_id=int(latest_settlement.get("sqlite_settlement_id") or latest_settlement["id"]),
                status=latest_settlement["status"],
                user_count=len(payout_rows),
                period_start=latest_settlement["work_window_start"],
                period_end=latest_settlement["work_window_end"],
                total_shares=int(latest_settlement.get("total_shares") or 0),
                total_work=Decimal(str(latest_settlement.get("total_work") or 0)),
                pool_reward_btc=Decimal(str(latest_settlement.get("total_reward_sats") or 0)) / Decimal("100000000"),
                carry_btc=Decimal(str(carry.get("carry_btc") or 0)),
            )
        period_start = latest_settlement["work_window_end"]
        capped_start = period_end - timedelta(minutes=interval)
        if period_start < capped_start:
            period_start = capped_start

    existing_settlement = repository.get_settlement_window_by_range(
        work_window_start=_as_utc_aware(period_start),
        work_window_end=_as_utc_aware(period_end),
    )
    if existing_settlement is not None:
        payout_rows = repository.list_settlement_user_credits_with_users(int(existing_settlement["id"]))
        carry = _get_or_create_carry_postgres(repository)
        return SettlementResult(
            settlement_id=int(existing_settlement.get("sqlite_settlement_id") or existing_settlement["id"]),
            status=existing_settlement["status"],
            user_count=len(payout_rows),
            period_start=_as_utc_aware(period_start),
            period_end=_as_utc_aware(period_end),
            total_shares=int(existing_settlement.get("total_shares") or 0),
            total_work=Decimal(str(existing_settlement.get("total_work") or 0)),
            pool_reward_btc=Decimal(str(existing_settlement.get("total_reward_sats") or 0)) / Decimal("100000000"),
            carry_btc=Decimal(str(carry.get("carry_btc") or 0)),
        )

    settlement = repository.upsert_settlement_window(
        settlement_run_at=now_aware,
        work_window_start=_as_utc_aware(period_start),
        work_window_end=_as_utc_aware(period_end),
        maturity_offset_minutes=max(0, int((period_end - (work_window_end or period_end)).total_seconds() // 60)),
        status="pending",
        total_reward_sats=0,
        total_work=ZERO,
        total_shares=0,
    )

    try:
        pool_reward = Decimal(str(reward_fetcher(period_start, period_end)))
    except PoolApiError:
        repository.upsert_settlement_window(
            settlement_run_at=now_aware,
            work_window_start=_as_utc_aware(period_start),
            work_window_end=_as_utc_aware(period_end),
            maturity_offset_minutes=max(0, int((period_end - (work_window_end or period_end)).total_seconds() // 60)),
            status="blocked",
            total_reward_sats=0,
            total_work=ZERO,
            total_shares=0,
        )
        return SettlementResult(
            settlement_id=int(settlement["id"]),
            status="blocked",
            user_count=0,
            period_start=_as_utc_aware(period_start),
            period_end=_as_utc_aware(period_end),
            total_shares=0,
            total_work=ZERO,
            pool_reward_btc=ZERO,
            carry_btc=ZERO,
        )

    pool_reward = _q(pool_reward, decimals)

    contrib_start = work_window_start if work_window_start is not None else period_start
    contrib_end = work_window_end if work_window_end is not None else period_end
    user_contributions = compute_user_contribution_deltas_postgres(
        repository,
        _as_utc_aware(contrib_start),
        _as_utc_aware(contrib_end),
    )
    total_shares, total_work = _summarize_contributions(user_contributions)

    repository.upsert_settlement_window(
        settlement_run_at=now_aware,
        work_window_start=_as_utc_aware(period_start),
        work_window_end=_as_utc_aware(period_end),
        maturity_offset_minutes=max(0, int((period_end - (work_window_end or period_end)).total_seconds() // 60)),
        status="pending",
        total_reward_sats=int(pool_reward * Decimal("100000000")),
        total_work=_q(total_work, decimals),
        total_shares=total_shares,
    )

    if defer_on_zero_reward and pool_reward <= ZERO:
        if use_work_accrual:
            _add_work_to_accrual_postgres(repository, user_contributions, now, decimals)
        repository.upsert_settlement_window(
            settlement_run_at=now_aware,
            work_window_start=_as_utc_aware(period_start),
            work_window_end=_as_utc_aware(period_end),
            maturity_offset_minutes=max(0, int((period_end - (work_window_end or period_end)).total_seconds() // 60)),
            status="deferred",
            total_reward_sats=0,
            total_work=_q(total_work, decimals),
            total_shares=total_shares,
        )
        carry = _get_or_create_carry_postgres(repository)
        return SettlementResult(
            settlement_id=int(settlement["id"]),
            status="deferred",
            user_count=0,
            period_start=_as_utc_aware(period_start),
            period_end=_as_utc_aware(period_end),
            total_shares=total_shares,
            total_work=_q(total_work, decimals),
            pool_reward_btc=ZERO,
            carry_btc=_q(Decimal(str(carry.get("carry_btc") or 0)), decimals),
        )

    if use_work_accrual:
        user_contributions = _apply_accrual_to_contributions_postgres(repository, user_contributions)

    carry = _get_or_create_carry_postgres(repository)
    previous_carry = _q(Decimal(str(carry.get("carry_btc") or 0)), decimals)
    distributable = _q(pool_reward + previous_carry, decimals)

    allocated_sum = ZERO
    user_count = 0
    settled_usernames: list[str] = []

    allocation_rows = _build_allocation_rows(user_contributions, distributable, decimals)
    for row in allocation_rows:
        payout_amount = Decimal(str(row["payout_amount"]))
        if payout_amount <= ZERO:
            continue

        username = str(row["username"])
        user = repository.upsert_user(username, created_at=now_aware)
        
        repository.upsert_settlement_user_work(
            settlement_id=int(settlement["id"]),
            user_id=int(user["id"]),
            share_delta=int(user_contributions.get(username, UserContribution(username, 0, ZERO)).share_delta),
            work_delta=user_contributions.get(username, UserContribution(username, 0, ZERO)).work_delta,
            payout_fraction=_q(Decimal(str(row["payout_fraction"])), 18),
        )
        
        credit = repository.upsert_settlement_user_credit(
            settlement_id=int(settlement["id"]),
            user_id=int(user["id"]),
            amount_sats=int(payout_amount * Decimal("100000000")),
            idempotency_key=f"settlement-{settlement['id']}-user-{user['id']}",
            status="pending",
        )

        allocated_sum += payout_amount
        user_count += 1
        settled_usernames.append(username)

    if use_work_accrual and settled_usernames:
        _clear_accrual_for_users_postgres(repository, settled_usernames, now)

    new_carry = _q(distributable - allocated_sum, decimals)
    repository.upsert_carry_state(
        bucket="default",
        carry_btc=new_carry,
        updated_at=now_aware,
    )

    repository.upsert_settlement_window(
        settlement_run_at=now_aware,
        work_window_start=_as_utc_aware(period_start),
        work_window_end=_as_utc_aware(period_end),
        maturity_offset_minutes=max(0, int((period_end - (work_window_end or period_end)).total_seconds() // 60)),
        status="completed",
        total_reward_sats=int(pool_reward * Decimal("100000000")),
        total_work=_q(total_work, decimals),
        total_shares=total_shares,
        completed_at=now_aware,
    )

    return SettlementResult(
        settlement_id=int(settlement["id"]),
        status="completed",
        user_count=user_count,
        period_start=_as_utc_aware(period_start),
        period_end=_as_utc_aware(period_end),
        total_shares=total_shares,
        total_work=_q(total_work, decimals),
        pool_reward_btc=pool_reward,
        carry_btc=new_carry,
    )
