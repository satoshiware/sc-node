from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from node_api.settings import Settings, get_settings


def _settings(monkeypatch, *, db_url: str | None = "postgresql://test") -> Settings:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev_token")
    monkeypatch.setenv("AZ_API_DEV_TOKEN", "testtoken")
    monkeypatch.setenv("TRANSLATOR_BLOCKS_FOUND_DB_PATH", ".data/unused-test.sqlite3")
    monkeypatch.setenv("TRANSLATOR_LOG_PATH", "")
    if db_url is None:
        monkeypatch.delenv("LEDGER_POSTGRES_DATABASE_URL", raising=False)
        monkeypatch.delenv("POSTGRES_LEDGER_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("LEDGER_POSTGRES_DATABASE_URL", db_url)
    get_settings.cache_clear()
    return get_settings()


def _client(monkeypatch, *, db_url: str | None = "postgresql://test") -> TestClient:
    _settings(monkeypatch, db_url=db_url)
    from node_api import main as main_module

    return TestClient(main_module.create_app())


def _row(
    *,
    found_time_unix: int,
    blockhash: str,
    worker_identity: str | None = "baveetstudy.miner2",
    channel_id: int | None = 3,
) -> dict:
    return {
        "found_time": datetime.fromtimestamp(found_time_unix, tz=UTC),
        "found_time_unix": found_time_unix,
        "blockhash": blockhash,
        "worker_identity": worker_identity,
        "channel_id": channel_id,
        "source": "sv1_capture_proxy",
        "proof_type": "translator_submit_reconstructed_block_hash",
    }


def _patch_query(monkeypatch, rows: list[dict], *, total: int | None = None) -> list[dict]:
    calls: list[dict] = []

    def _fake_query(database_url, *, start_time, end_time, limit, order):
        calls.append(
            {
                "database_url": database_url,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "order": order,
            }
        )
        selected = list(rows)
        if start_time is not None:
            selected = [row for row in selected if row["found_time_unix"] >= start_time]
        if end_time is not None:
            selected = [row for row in selected if row["found_time_unix"] < end_time]
        reverse = order == "desc"
        selected.sort(key=lambda row: row["found_time_unix"], reverse=reverse)
        count = len(selected) if total is None else total
        return selected[:limit], count

    monkeypatch.setattr(
        "node_api.services.translator_candidate_blocks_postgres.query_translator_candidate_blocks",
        _fake_query,
    )
    return calls


def test_blocks_found_returns_persisted_ledger_postgres_candidate_block_events(
    monkeypatch,
) -> None:
    client = _client(monkeypatch)
    _patch_query(
        monkeypatch,
        [
            _row(
                found_time_unix=1778089665,
                blockhash="a" * 64,
                worker_identity="baveetstudy.miner2",
                channel_id=3,
            )
        ],
    )

    response = client.get(
        "/v1/translator/blocks-found",
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "source": "ledger_postgres_translator_candidate_blocks",
        "total": 1,
        "items": [
            {
                "found_time": 1778089665,
                "found_time_iso": "2026-05-06T17:47:45Z",
                "blockhash": "a" * 64,
                "worker_identity": "baveetstudy.miner2",
                "channel_id": 3,
                "source": "sv1_capture_proxy",
                "proof_type": "translator_submit_reconstructed_block_hash",
            }
        ],
    }


def test_blocks_found_start_time_end_time_filtering_uses_found_time_unix(
    monkeypatch,
) -> None:
    client = _client(monkeypatch)
    _patch_query(
        monkeypatch,
        [
            _row(found_time_unix=999, blockhash="a" * 64),
            _row(found_time_unix=1000, blockhash="b" * 64),
            _row(found_time_unix=1001, blockhash="c" * 64),
        ],
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"start_time": 1000, "end_time": 1001, "order": "asc"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["blockhash"] for item in body["items"]] == ["b" * 64]


def test_blocks_found_limit_and_order_are_forwarded_to_postgres_read(
    monkeypatch,
) -> None:
    client = _client(monkeypatch)
    calls = _patch_query(
        monkeypatch,
        [
            _row(found_time_unix=1000, blockhash="a" * 64),
            _row(found_time_unix=1001, blockhash="b" * 64),
            _row(found_time_unix=1002, blockhash="c" * 64),
        ],
        total=3,
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"limit": 2, "order": "asc"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["blockhash"] for item in body["items"]] == ["a" * 64, "b" * 64]
    assert calls[0]["limit"] == 2
    assert calls[0]["order"] == "asc"


def test_blocks_found_defaults_to_newest_first(monkeypatch) -> None:
    client = _client(monkeypatch)
    _patch_query(
        monkeypatch,
        [
            _row(found_time_unix=1000, blockhash="a" * 64),
            _row(found_time_unix=1001, blockhash="b" * 64),
        ],
    )

    response = client.get(
        "/v1/translator/blocks-found",
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    assert [item["found_time"] for item in response.json()["items"]] == [1001, 1000]


def test_blocks_found_returns_no_payout_reward_ownership_or_maturity_fields(
    monkeypatch,
) -> None:
    client = _client(monkeypatch)
    _patch_query(monkeypatch, [_row(found_time_unix=1000, blockhash="a" * 64)])

    response = client.get(
        "/v1/translator/blocks-found",
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert {
        "payout_ready",
        "confirmations",
        "maturity_status",
        "coinbase_total_sats",
        "candidate_coinbase_total_sats",
        "ownership",
        "reward_sats",
        "blocks_found_before",
        "blocks_found_after",
        "accepted",
        "rejected",
    }.isdisjoint(item)


def test_blocks_found_missing_db_config_returns_safe_unavailable_response(
    monkeypatch,
) -> None:
    client = _client(monkeypatch, db_url=None)
    monkeypatch.setattr(
        "node_api.services.translator_candidate_blocks_postgres.query_translator_candidate_blocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DB should not be queried")),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "LEDGER_POSTGRES_UNAVAILABLE",
        "message": "Ledger Postgres unavailable",
    }
    assert "postgresql://" not in response.text


def test_blocks_found_old_az_rewards_code_path_is_not_called(
    monkeypatch,
) -> None:
    client = _client(monkeypatch)
    _patch_query(monkeypatch, [_row(found_time_unix=1000, blockhash="a" * 64)])
    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("old rewards path called")),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "ledger_postgres_translator_candidate_blocks"


def test_blocks_found_api_does_not_reconstruct_or_store_candidate_blocks(
    monkeypatch,
) -> None:
    client = _client(monkeypatch)
    _patch_query(monkeypatch, [_row(found_time_unix=1000, blockhash="a" * 64)])
    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_store.TranslatorBlocksFoundStore.from_settings",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old SQLite store called")),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["blockhash"] == "a" * 64


def test_blocks_found_invalid_time_range_returns_422(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get(
        "/v1/translator/blocks-found",
        params={"start_time": 1000, "end_time": 1000},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "TRANSLATOR_BLOCKS_FOUND_TIME_RANGE_INVALID"
