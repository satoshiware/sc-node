import pytest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.db import Base, make_engine, make_session_factory
from app.models import User, Settlement, UserPayout, CarryState, WorkAccrualBucket
from app.postgres_repositories import PostgresLedgerRepository
from app.postgres_settlement import (
    run_settlement_postgres,
    _get_or_create_carry_postgres,
    _get_or_create_accrual_bucket_postgres,
)
from app.settlement import run_settlement, SettlementResult
from app.delta import UserContribution


@pytest.fixture
def sqlite_session(tmp_path: Path):
    """Create SQLite session for testing."""
    db_file = tmp_path / "settlement_test.db"
    engine = make_engine(str(db_file))
    Base.metadata.create_all(engine)
    SessionFactory = make_session_factory(engine)
    with SessionFactory() as s:
        yield s


@pytest.fixture
def postgres_session_factory(tmp_path: Path):
    """Create PostgreSQL session factory for testing (mock via SQLite for CI)."""
    db_file = tmp_path / "postgres_settlement_test.db"
    engine = make_engine(str(db_file))
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def setup_carry_state(postgres_session_factory):
    """Initialize carry state to zero."""
    repository = PostgresLedgerRepository(postgres_session_factory)
    repository.upsert_carry_state(
        bucket="default",
        carry_btc=Decimal("0"),
        updated_at=datetime.now(UTC),
    )
    return repository


class TestPostgresCarryState:
    """Tests for carry state management in Postgres."""
    
    def test_get_or_create_carry_state_new(self, setup_carry_state):
        """Create new carry state when it doesn't exist."""
        repo = setup_carry_state
        
        # Verify initial state
        carry = repo.get_carry_state(bucket="default")
        assert carry is not None
        assert Decimal(str(carry["carry_btc"])) == Decimal("0")
    
    def test_upsert_carry_state_update(self, setup_carry_state):
        """Update existing carry state."""
        repo = setup_carry_state
        
        # Update carry
        repo.upsert_carry_state(
            bucket="default",
            carry_btc=Decimal("0.5"),
            updated_at=datetime.now(UTC),
        )
        
        carry = repo.get_carry_state(bucket="default")
        assert Decimal(str(carry["carry_btc"])) == Decimal("0.5")
    
    def test_carry_state_uniqueness(self, setup_carry_state):
        """Verify bucket uniqueness constraint."""
        repo = setup_carry_state
        
        # Create two carry states with same bucket
        repo.upsert_carry_state(
            bucket="default",
            carry_btc=Decimal("1.0"),
            updated_at=datetime.now(UTC),
        )
        
        repo.upsert_carry_state(
            bucket="default",
            carry_btc=Decimal("2.0"),
            updated_at=datetime.now(UTC),
        )
        
        # Should return only one row
        carry = repo.get_carry_state(bucket="default")
        assert Decimal(str(carry["carry_btc"])) == Decimal("2.0")


class TestPostgresSettlementBasics:
    """Basic sanity tests for settlement module."""

    def test_postgres_settlement_module_imports(self):
        """Verify postgres_settlement module can be imported."""
        from app.postgres_settlement import run_settlement_postgres
        assert callable(run_settlement_postgres)

    def test_next_window_uses_previous_end_as_baseline(self):
        """Ensure consecutive settlements chain windows without resetting baseline."""

        class _FakeRepo:
            def __init__(self, latest_end):
                self.latest_end = latest_end
                self.range_calls = []

            def get_latest_settlement_window(self):
                return {
                    "id": 100,
                    "status": "completed",
                    "work_window_start": self.latest_end - timedelta(minutes=10),
                    "work_window_end": self.latest_end,
                    "total_shares": 10,
                    "total_work": Decimal("100"),
                    "total_reward_sats": 1000,
                    "sqlite_settlement_id": None,
                }

            def get_settlement_window_by_range(self, *, work_window_start, work_window_end):
                self.range_calls.append((work_window_start, work_window_end))
                return {
                    "id": 101,
                    "status": "completed",
                    "work_window_start": work_window_start,
                    "work_window_end": work_window_end,
                    "total_shares": 5,
                    "total_work": Decimal("50"),
                    "total_reward_sats": 500,
                    "sqlite_settlement_id": None,
                }

            def list_settlement_user_credits_with_users(self, _settlement_id):
                return []

            def get_carry_state(self, *, bucket="default"):
                return {"bucket": bucket, "carry_btc": Decimal("0")}

        latest_end = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        now = datetime(2026, 1, 1, 12, 5, tzinfo=UTC)
        repo = _FakeRepo(latest_end)

        result = run_settlement_postgres(
            repo,
            now,
            interval_minutes=10,
            payout_decimals=8,
        )

        assert len(repo.range_calls) == 1
        called_start, called_end = repo.range_calls[0]
        assert called_start == latest_end
        assert called_end == now
        assert result.period_start == latest_end
        assert result.period_end == now

    def test_next_window_with_lag_still_starts_from_previous_end(self):
        """Ensure scheduler lag does not create a sliding overlapping contribution window."""

        class _FakeRepo:
            def __init__(self, latest_end):
                self.latest_end = latest_end
                self.range_calls = []

            def get_latest_settlement_window(self):
                return {
                    "id": 200,
                    "status": "completed",
                    "work_window_start": self.latest_end - timedelta(minutes=10),
                    "work_window_end": self.latest_end,
                    "total_shares": 10,
                    "total_work": Decimal("100"),
                    "total_reward_sats": 1000,
                    "sqlite_settlement_id": None,
                }

            def get_settlement_window_by_range(self, *, work_window_start, work_window_end):
                self.range_calls.append((work_window_start, work_window_end))
                return {
                    "id": 201,
                    "status": "completed",
                    "work_window_start": work_window_start,
                    "work_window_end": work_window_end,
                    "total_shares": 5,
                    "total_work": Decimal("50"),
                    "total_reward_sats": 500,
                    "sqlite_settlement_id": None,
                }

            def list_settlement_user_credits_with_users(self, _settlement_id):
                return []

            def get_carry_state(self, *, bucket="default"):
                return {"bucket": bucket, "carry_btc": Decimal("0")}

        latest_end = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        # Deliberately later than interval to emulate scheduler drift.
        now = datetime(2026, 1, 1, 12, 12, tzinfo=UTC)
        repo = _FakeRepo(latest_end)

        result = run_settlement_postgres(
            repo,
            now,
            interval_minutes=10,
            payout_decimals=8,
        )

        assert len(repo.range_calls) == 1
        called_start, called_end = repo.range_calls[0]
        assert called_start == latest_end
        assert called_end == now
        assert result.period_start == latest_end
        assert result.period_end == now
