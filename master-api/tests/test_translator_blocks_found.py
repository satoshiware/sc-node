from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from node_api.services.translator_candidate_blocks_store import TranslatorCandidateBlocksStore
from node_api.settings import Settings, get_settings

AUTH = {"Authorization": "Bearer testtoken"}


def _db_path(name: str) -> Path:
    path = Path.cwd() / name
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{path}{suffix}")
        candidate.unlink(missing_ok=True)
    return path


def _settings(monkeypatch, db_name: str) -> Settings:
    db_path = _db_path(db_name)
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev_token")
    monkeypatch.setenv("AZ_API_DEV_TOKEN", "testtoken")
    monkeypatch.setenv("TRANSLATOR_CANDIDATE_BLOCKS_DB_PATH", str(db_path))
    monkeypatch.setenv("TRANSLATOR_LOG_PATH", "")
    get_settings.cache_clear()
    return get_settings()


def _client(monkeypatch, db_name: str) -> tuple[TestClient, TranslatorCandidateBlocksStore]:
    settings = _settings(monkeypatch, db_name)
    from node_api import main as main_module

    client = TestClient(main_module.create_app())
    store = TranslatorCandidateBlocksStore.from_settings(settings)
    return client, store


def _insert_event(
    store: TranslatorCandidateBlocksStore,
    *,
    found_time: int,
    blockhash: str,
    worker_identity: str | None = "baveetstudy.miner2",
    channel_id: int | None = 3,
) -> None:
    store.insert_event(
        {
            "found_time": found_time,
            "blockhash": blockhash,
            "worker_identity": worker_identity,
            "channel_id": channel_id,
            "job_id": "job-1",
            "extranonce2": "00000002",
            "ntime": "681b9451",
            "nonce": "00000001",
            "version": "20000000",
            "prev_hash": "0" * 64,
            "nbits": "2200ffff",
            "raw_submit_json": {"method": "mining.submit"},
        }
    )


def test_blocks_found_endpoint_returns_persisted_reconstructed_events(
    monkeypatch,
) -> None:
    client, store = _client(monkeypatch, ".codex_tcb_route_basic.sqlite3")
    _insert_event(store, found_time=1_778_089_665, blockhash="a" * 64)

    response = client.get("/v1/translator/blocks-found", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "source": "translator_submit_reconstruction",
        "total": 1,
        "items": [
            {
                "found_time": 1_778_089_665,
                "found_time_iso": "2026-05-06T17:47:45Z",
                "blockhash": "a" * 64,
                "worker_identity": "baveetstudy.miner2",
                "channel_id": 3,
                "proof_type": "translator_submit_reconstructed_block_hash",
                "source": "api_sidecar_reconstruction",
            }
        ],
    }


def test_blocks_found_endpoint_start_time_and_end_time_filtering(
    monkeypatch,
) -> None:
    client, store = _client(monkeypatch, ".codex_tcb_route_time.sqlite3")
    _insert_event(store, found_time=1000, blockhash="1" * 64)
    _insert_event(store, found_time=1001, blockhash="2" * 64)
    _insert_event(store, found_time=1002, blockhash="3" * 64)

    response = client.get(
        "/v1/translator/blocks-found",
        params={"start_time": 1001, "end_time": 1002},
        headers=AUTH,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["found_time"] == 1001
    assert body["items"][0]["blockhash"] == "2" * 64


def test_blocks_found_endpoint_limit_and_order(monkeypatch) -> None:
    client, store = _client(monkeypatch, ".codex_tcb_route_order.sqlite3")
    _insert_event(store, found_time=1000, blockhash="1" * 64)
    _insert_event(store, found_time=1001, blockhash="2" * 64)
    _insert_event(store, found_time=1002, blockhash="3" * 64)

    response = client.get(
        "/v1/translator/blocks-found",
        params={"limit": 2, "order": "asc"},
        headers=AUTH,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["found_time"] for item in body["items"]] == [1000, 1001]


def test_blocks_found_endpoint_worker_identity_and_channel_filters(
    monkeypatch,
) -> None:
    client, store = _client(monkeypatch, ".codex_tcb_route_filters.sqlite3")
    _insert_event(
        store,
        found_time=1000,
        blockhash="1" * 64,
        worker_identity="worker-a",
        channel_id=2,
    )
    _insert_event(
        store,
        found_time=1001,
        blockhash="2" * 64,
        worker_identity="worker-b",
        channel_id=3,
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"worker_identity": "worker-b", "channel_id": 3},
        headers=AUTH,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["worker_identity"] == "worker-b"
    assert body["items"][0]["channel_id"] == 3


def test_blocks_found_endpoint_allows_null_channel_id(monkeypatch) -> None:
    client, store = _client(monkeypatch, ".codex_tcb_route_null_channel.sqlite3")
    _insert_event(store, found_time=1000, blockhash="1" * 64, channel_id=None)

    response = client.get("/v1/translator/blocks-found", headers=AUTH)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["worker_identity"] == "baveetstudy.miner2"
    assert item["channel_id"] is None


def test_blocks_found_endpoint_invalid_time_range_returns_422(
    monkeypatch,
) -> None:
    client, _store = _client(monkeypatch, ".codex_tcb_route_invalid_range.sqlite3")

    response = client.get(
        "/v1/translator/blocks-found",
        params={"start_time": 1000, "end_time": 1000},
        headers=AUTH,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "TRANSLATOR_BLOCKS_FOUND_TIME_RANGE_INVALID"


def test_blocks_found_endpoint_returns_no_payout_reward_or_ownership_fields(
    monkeypatch,
) -> None:
    client, store = _client(monkeypatch, ".codex_tcb_route_shape.sqlite3")
    _insert_event(store, found_time=1000, blockhash="1" * 64)

    response = client.get("/v1/translator/blocks-found", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    forbidden = {
        "payout_ready",
        "confirmations",
        "maturity_status",
        "coinbase_total_sats",
        "ownership",
        "accepted",
        "rejected",
        "reward",
        "candidate_blocks",
        "nearest_candidate_blockhash",
    }
    assert forbidden.isdisjoint(body)
    assert forbidden.isdisjoint(item)
    assert set(item) == {
        "found_time",
        "found_time_iso",
        "blockhash",
        "worker_identity",
        "channel_id",
        "proof_type",
        "source",
    }


def test_blocks_found_endpoint_does_not_call_chain_rewards_lookup(
    monkeypatch,
) -> None:
    client, store = _client(monkeypatch, ".codex_tcb_route_chain_guard.sqlite3")
    _insert_event(store, found_time=1000, blockhash="1" * 64)

    def _unexpected_chain_rewards(**kwargs):
        raise AssertionError("blocks-found must not call chain rewards lookup")

    monkeypatch.setattr(
        "node_api.routes.v1.az_blocks.block_rewards",
        _unexpected_chain_rewards,
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["blockhash"] == "1" * 64
