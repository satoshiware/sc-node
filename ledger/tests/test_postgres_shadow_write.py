from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import Base, make_engine, make_session_factory
from app.main import app
from app.models import MetricSnapshot, Settlement, UserPayout
from app.sender import SenderStats
from app.settlement import SettlementResult, run_settlement as sqlite_run_settlement


class FakeShadowRepository:
    def __init__(self) -> None:
        self._next_ids = {
            "user": 1,
            "settlement": 1,
            "credit": 1,
            "ledger_entry": 1,
            "block": 1,
            "block_reward": 1,
            "user_work": 1,
            "identity": 1,
        }
        self.users_by_username: dict[str, dict[str, object]] = {}
        self.identities_by_value: dict[str, dict[str, object]] = {}
        self.settlements_by_window: dict[tuple[datetime, datetime], dict[str, object]] = {}
        self.blocks_by_hash: dict[str, dict[str, object]] = {}
        self.block_rewards_by_hash: dict[str, dict[str, object]] = {}
        self.settlement_blocks_by_hash: dict[str, dict[str, object]] = {}
        self.user_work_by_key: dict[tuple[int, int], dict[str, object]] = {}
        self.credits_by_key: dict[tuple[int, int], dict[str, object]] = {}
        self.ledger_entries_by_credit_id: dict[int, dict[str, object]] = {}
        self.balances_by_user_id: dict[int, dict[str, object]] = {}

    def _next_id(self, key: str) -> int:
        value = self._next_ids[key]
        self._next_ids[key] += 1
        return value

    def upsert_user(self, username: str, **kwargs) -> dict[str, object]:
        existing = self.users_by_username.get(username)
        if existing is not None:
            existing.update({"status": kwargs.get("status", "active")})
            return existing
        row = {
            "id": self._next_id("user"),
            "username": username,
            "status": kwargs.get("status", "active"),
        }
        self.users_by_username[username] = row
        return row

    def upsert_miner_identity(self, user_id: int, identity: str, **kwargs) -> dict[str, object]:
        existing = self.identities_by_value.get(identity)
        if existing is not None:
            existing.update(
                {
                    "user_id": user_id,
                    "worker_name": kwargs.get("worker_name"),
                    "status": kwargs.get("status", "active"),
                }
            )
            return existing
        row = {
            "id": self._next_id("identity"),
            "user_id": user_id,
            "identity": identity,
            "worker_name": kwargs.get("worker_name"),
            "status": kwargs.get("status", "active"),
        }
        self.identities_by_value[identity] = row
        return row

    def upsert_settlement_window(self, **kwargs) -> dict[str, object]:
        key = (kwargs["work_window_start"], kwargs["work_window_end"])
        existing = self.settlements_by_window.get(key)
        if existing is not None:
            existing.update(kwargs)
            return existing
        row = {"id": self._next_id("settlement"), **kwargs}
        self.settlements_by_window[key] = row
        return row

    def upsert_block_found(self, **kwargs) -> dict[str, object]:
        blockhash = kwargs["blockhash"]
        existing = self.blocks_by_hash.get(blockhash)
        if existing is not None:
            existing.update(kwargs)
            return existing
        row = {"id": self._next_id("block"), **kwargs}
        self.blocks_by_hash[blockhash] = row
        return row

    def upsert_block_reward(self, **kwargs) -> dict[str, object]:
        blockhash = kwargs["blockhash"]
        existing = self.block_rewards_by_hash.get(blockhash)
        if existing is not None:
            existing.update(kwargs)
            return existing
        row = {"id": self._next_id("block_reward"), **kwargs}
        self.block_rewards_by_hash[blockhash] = row
        return row

    def link_settlement_block(self, **kwargs) -> dict[str, object]:
        blockhash = kwargs["blockhash"]
        existing = self.settlement_blocks_by_hash.get(blockhash)
        if existing is not None:
            return existing
        row = kwargs.copy()
        self.settlement_blocks_by_hash[blockhash] = row
        return row

    def upsert_settlement_user_work(self, **kwargs) -> dict[str, object]:
        key = (kwargs["settlement_id"], kwargs["user_id"])
        existing = self.user_work_by_key.get(key)
        if existing is not None:
            existing.update(kwargs)
            return existing
        row = {"id": self._next_id("user_work"), **kwargs}
        self.user_work_by_key[key] = row
        return row

    def upsert_settlement_user_credit(self, **kwargs) -> dict[str, object]:
        key = (kwargs["settlement_id"], kwargs["user_id"])
        existing = self.credits_by_key.get(key)
        if existing is not None:
            existing.update(kwargs)
            return existing
        row = {"id": self._next_id("credit"), **kwargs}
        self.credits_by_key[key] = row
        return row

    def get_account_ledger_entry_by_settlement_credit_id(
        self,
        settlement_credit_id: int,
    ) -> dict[str, object] | None:
        return self.ledger_entries_by_credit_id.get(settlement_credit_id)

    def create_account_ledger_entry(self, **kwargs) -> dict[str, object]:
        settlement_credit_id = int(kwargs["settlement_credit_id"])
        row = {"id": self._next_id("ledger_entry"), **kwargs}
        self.ledger_entries_by_credit_id[settlement_credit_id] = row
        return row

    def set_account_balance(self, **kwargs) -> dict[str, object]:
        user_id = int(kwargs["user_id"])
        row = kwargs.copy()
        self.balances_by_user_id[user_id] = row
        return row


def test_shadow_write_disabled_does_not_require_postgres(monkeypatch, tmp_path) -> None:
    db_file = tmp_path / "shadow_disabled.db"
    log_file = tmp_path / "shadow_disabled_audit.jsonl"
    engine = make_engine(str(db_file))
    Base.metadata.create_all(engine)

    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("PAYOUT_AUDIT_LOG_PATH", str(log_file))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("POSTGRES_LEDGER_SHADOW_WRITE_ENABLED", raising=False)
    monkeypatch.delenv("TRANSLATOR_CHANNELS_URL", raising=False)
    monkeypatch.setattr("app.main.poll_metrics_once", lambda session, api_url: 0)
    monkeypatch.setattr(
        "app.main.run_settlement",
        lambda session, now, interval_minutes, payout_decimals, reward_fetcher=None, **kwargs: SettlementResult(
            settlement_id=1,
            status="completed",
            user_count=0,
            period_start=datetime(2026, 1, 1, 0, 0, 0),
            period_end=datetime(2026, 1, 1, 0, 10, 0),
            total_shares=0,
            total_work=Decimal("0"),
            pool_reward_btc=Decimal("0"),
            carry_btc=Decimal("0"),
        ),
    )
    monkeypatch.setattr(
        "app.main.process_payout_events",
        lambda session, dry_run: SenderStats(attempted=0, sent=0, failed=0, created_events=0),
    )
    monkeypatch.setattr(
        "app.main.make_postgres_engine",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Postgres should stay unused")),
    )

    client = TestClient(app)
    response = client.post("/settlements/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["settlement"]["status"] == "completed"
    assert "postgres_shadow_write" not in payload


def test_shadow_write_enabled_runs_after_sqlite_settlement_and_stays_idempotent(
    monkeypatch,
    tmp_path,
) -> None:
    db_file = tmp_path / "shadow_enabled.db"
    log_file = tmp_path / "shadow_enabled_audit.jsonl"
    engine = make_engine(str(db_file))
    Base.metadata.create_all(engine)
    Session = make_session_factory(engine)

    fixed_now = datetime(2026, 1, 1, 0, 10, 0, tzinfo=UTC)
    with Session() as session:
        session.add(
            MetricSnapshot(
                identity="alice.rig1",
                accepted_shares_total=0,
                accepted_work_total=0,
                created_at=(fixed_now - timedelta(minutes=12)).replace(tzinfo=None),
            )
        )
        session.add(
            MetricSnapshot(
                identity="alice.rig1",
                accepted_shares_total=5,
                accepted_work_total=100,
                created_at=(fixed_now - timedelta(minutes=2)).replace(tzinfo=None),
            )
        )
        session.commit()

    fake_repository = FakeShadowRepository()

    class _FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    def _run_sqlite_settlement(session, now, interval_minutes, payout_decimals, reward_fetcher=None, **kwargs):
        _ = reward_fetcher
        return sqlite_run_settlement(
            session,
            now,
            interval_minutes=interval_minutes,
            payout_decimals=payout_decimals,
            reward_fetcher=lambda period_start, period_end: Decimal("1.00000000"),
            **kwargs,
        )

    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("PAYOUT_AUDIT_LOG_PATH", str(log_file))
    monkeypatch.setenv("POSTGRES_LEDGER_SHADOW_WRITE_ENABLED", "true")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("TRANSLATOR_CHANNELS_URL", raising=False)
    monkeypatch.setattr("app.main.datetime", _FixedDateTime)
    monkeypatch.setattr("app.main.poll_metrics_once", lambda session, api_url: 0)
    monkeypatch.setattr("app.main.run_settlement", _run_sqlite_settlement)
    monkeypatch.setattr(
        "app.main.process_payout_events",
        lambda session, dry_run: (
            session.commit() or SenderStats(attempted=0, sent=0, failed=0, created_events=0)
        ),
    )
    monkeypatch.setattr("app.main.make_postgres_engine", lambda *args, **kwargs: object())
    monkeypatch.setattr("app.main.make_postgres_session_factory", lambda engine: object())
    monkeypatch.setattr("app.main.PostgresLedgerRepository", lambda session_factory: fake_repository)

    client = TestClient(app)

    first = client.post("/settlements/run")
    second = client.post("/settlements/run")

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()

    assert first_payload["settlement"]["status"] == "completed"
    assert second_payload["settlement"]["status"] == "completed"
    assert first_payload["settlement"]["settlement_id"] == second_payload["settlement"]["settlement_id"]
    assert first_payload["postgres_shadow_write"]["status"] == "completed"
    assert second_payload["postgres_shadow_write"]["status"] == "completed"

    assert len(fake_repository.settlements_by_window) == 1
    assert len(fake_repository.credits_by_key) == 1
    assert len(fake_repository.ledger_entries_by_credit_id) == 1
    assert len(fake_repository.user_work_by_key) == 1

    credit_row = next(iter(fake_repository.credits_by_key.values()))
    ledger_entry = fake_repository.ledger_entries_by_credit_id[int(credit_row["id"])]
    balance_row = next(iter(fake_repository.balances_by_user_id.values()))
    user_work_row = next(iter(fake_repository.user_work_by_key.values()))

    assert int(credit_row["amount_sats"]) == 100_000_000
    assert int(ledger_entry["amount_sats"]) == 100_000_000
    assert int(balance_row["balance_sats"]) == 100_000_000
    assert Decimal(str(user_work_row["work_delta"])) == Decimal("100.00000000")
    assert Decimal(str(user_work_row["payout_fraction"])) == Decimal("1.000000000000")

    with Session() as session:
        assert session.query(Settlement).count() == 1
        assert session.query(UserPayout).count() == 1
