from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from node_api.settings import Settings, get_settings


def _settings(monkeypatch, tmp_path: Path) -> Settings:
    db_path = tmp_path / "translator_blocks_found.sqlite3"
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev_token")
    monkeypatch.setenv("AZ_API_DEV_TOKEN", "testtoken")
    monkeypatch.setenv("TRANSLATOR_BLOCKS_FOUND_DB_PATH", str(db_path))
    monkeypatch.setenv("TRANSLATOR_LOG_PATH", "")
    get_settings.cache_clear()
    return get_settings()


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    _settings(monkeypatch, tmp_path)
    from node_api import main as main_module

    return TestClient(main_module.create_app())


def _reward_response(
    blocks: list[dict],
    *,
    maturity_confirmations: int = 100,
) -> dict:
    return {
        "maturity_confirmations": maturity_confirmations,
        "blocks": blocks,
    }


def _insert_event(client: TestClient, monkeypatch, tmp_path: Path, *, detected_time: int) -> None:
    from node_api.services.translator_blocks_found_store import TranslatorBlocksFoundStore

    settings = _settings(monkeypatch, tmp_path)
    store = TranslatorBlocksFoundStore.from_settings(settings)
    created = store.insert_event(
        {
            "identity_key": "worker-a",
            "detected_time": detected_time,
            "channel_id": 2,
            "worker_identity": "worker-a",
            "authorized_worker_name": "worker-a",
            "downstream_user_identity": "worker-a",
            "upstream_user_identity": "upstream.worker-a",
            "blocks_found_before": 0,
            "blocks_found_after": 1,
            "blocks_found_delta": 1,
            "share_work_sum_at_detection": "1000",
            "shares_acknowledged_at_detection": 10,
            "shares_submitted_at_detection": 10,
            "shares_rejected_at_detection": 0,
            "blockhash": None,
            "blockhash_status": "unresolved",
            "correlation_status": "counter_delta_only",
            "raw_snapshot_json": None,
        }
    )
    assert created is True


def test_include_candidate_blocks_false_preserves_existing_behavior(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("candidate enrichment should not run")

    monkeypatch.setattr(
        "node_api.routes.v1.translator.tbfc.enrich_events_with_candidate_blocks",
        _boom,
    )

    response = client.get(
        "/v1/translator/blocks-found",
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert "candidate_count" not in item
    assert item["blockhash"] is None


def test_include_candidate_blocks_true_with_zero_candidates(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: _reward_response([]),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["candidate_count"] == 0
    assert item["nearest_candidate_blockhash"] is None
    assert item["candidate_blocks"] == []
    assert item["candidate_window_seconds"] == 30
    assert item["candidate_time_field"] == "time"
    assert item["correlation_status"] == "no_candidate_found"
    assert item["blockhash_status"] == "unresolved"
    assert item["payout_ready"] is False


def test_exactly_one_candidate_returns_nearest_blockhash(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: _reward_response(
            [
                {
                    "height": 101,
                    "blockhash": "a" * 64,
                    "time": 1005,
                    "mediantime": 1004,
                    "coinbase_total_sats": 5000000000,
                    "maturity_status": "immature",
                    "confirmations": 10,
                }
            ]
        ),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["nearest_candidate_blockhash"] == "a" * 64
    assert item["candidate_count"] == 1
    assert item["candidate_blocks"][0]["blockhash"] == "a" * 64
    assert item["blockhash"] is None
    assert item["blockhash_status"] == "candidate"
    assert item["correlation_status"] == "candidate_single_within_window"
    assert item["payout_ready"] is False
    assert item["candidate_confirmations"] == 10
    assert item["candidate_coinbase_total_sats"] == 5000000000


def test_multiple_candidates_are_sorted_by_abs_delta_seconds(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: _reward_response(
            [
                {
                    "height": 90,
                    "blockhash": "c" * 64,
                    "time": 1010,
                    "mediantime": 1010,
                    "coinbase_total_sats": 1,
                    "maturity_status": "immature",
                    "confirmations": 1,
                },
                {
                    "height": 100,
                    "blockhash": "a" * 64,
                    "time": 1001,
                    "mediantime": 1001,
                    "coinbase_total_sats": 1,
                    "maturity_status": "immature",
                    "confirmations": 1,
                },
                {
                    "height": 95,
                    "blockhash": "b" * 64,
                    "time": 1005,
                    "mediantime": 1005,
                    "coinbase_total_sats": 1,
                    "maturity_status": "immature",
                    "confirmations": 1,
                },
            ]
        ),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    blocks = item["candidate_blocks"]
    assert [block["blockhash"] for block in blocks] == ["a" * 64, "b" * 64, "c" * 64]
    assert item["blockhash"] is None
    assert item["blockhash_status"] == "ambiguous"
    assert item["correlation_status"] == "candidate_multiple_ambiguous"
    assert item["payout_ready"] is False


def test_candidate_limit_per_event_truncates_candidate_blocks(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: _reward_response(
            [
                {
                    "height": 10,
                    "blockhash": "a" * 64,
                    "time": 1001,
                    "mediantime": 1001,
                    "coinbase_total_sats": 1,
                    "maturity_status": "immature",
                    "confirmations": 1,
                },
                {
                    "height": 9,
                    "blockhash": "b" * 64,
                    "time": 1002,
                    "mediantime": 1002,
                    "coinbase_total_sats": 1,
                    "maturity_status": "immature",
                    "confirmations": 1,
                },
                {
                    "height": 8,
                    "blockhash": "c" * 64,
                    "time": 1003,
                    "mediantime": 1003,
                    "coinbase_total_sats": 1,
                    "maturity_status": "immature",
                    "confirmations": 1,
                },
            ]
        ),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={
            "include_candidate_blocks": "true",
            "candidate_limit_per_event": 2,
        },
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["candidate_count"] == 3
    assert len(item["candidate_blocks"]) == 2


def test_existing_blockhash_remains_null_for_candidate_only_enrichment(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: _reward_response(
            [
                {
                    "height": 101,
                    "blockhash": "d" * 64,
                    "time": 1005,
                    "mediantime": 1005,
                    "coinbase_total_sats": 5000000000,
                    "maturity_status": "immature",
                    "confirmations": 10,
                }
            ]
        ),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["blockhash"] is None
    assert item["blockhash_status"] == "candidate"
    assert item["correlation_status"] == "candidate_single_within_window"
    assert item["payout_ready"] is False


def test_candidate_enrichment_uses_one_combined_chain_lookup(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1100)
    calls: list[dict] = []

    def _fake_block_rewards(**kwargs):
        calls.append(kwargs)
        return {"blocks": []}

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        _fake_block_rewards,
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={
            "include_candidate_blocks": "true",
            "candidate_window_seconds": 30,
            "candidate_time_field": "mediantime",
        },
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["owned_only"] is False
    assert calls[0]["start_time"] == 970
    assert calls[0]["end_time"] == 1131
    assert calls[0]["time_field"] == "mediantime"


def test_candidate_outside_default_30_seconds_but_inside_300_seconds(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: _reward_response(
            [
                {
                    "height": 200,
                    "blockhash": "e" * 64,
                    "time": 1040,
                    "mediantime": 1040,
                    "coinbase_total_sats": 5000000000,
                    "maturity_status": "immature",
                    "confirmations": 12,
                    "is_on_main_chain": True,
                }
            ]
        ),
    )

    default_response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers={"Authorization": "Bearer testtoken"},
    )
    widened_response = client.get(
        "/v1/translator/blocks-found",
        params={
            "include_candidate_blocks": "true",
            "candidate_window_seconds": 300,
        },
        headers={"Authorization": "Bearer testtoken"},
    )

    assert default_response.status_code == 200
    assert widened_response.status_code == 200
    assert default_response.json()["items"][0]["candidate_count"] == 0
    widened_item = widened_response.json()["items"][0]
    assert widened_item["candidate_count"] == 1
    assert widened_item["blockhash_status"] == "candidate"
    assert widened_item["correlation_status"] == "candidate_single_within_window"


def test_resolved_candidate_requires_confirmations_and_reward_proof(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: _reward_response(
            [
                {
                    "height": 300,
                    "blockhash": "f" * 64,
                    "time": 1004,
                    "mediantime": 1004,
                    "coinbase_total_sats": 5000000000,
                    "maturity_status": "mature",
                    "confirmations": 100,
                    "is_on_main_chain": True,
                }
            ]
        ),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["blockhash"] == "f" * 64
    assert item["blockhash_status"] == "resolved"
    assert item["correlation_status"] == "resolved_to_blockhash"
    assert item["candidate_confirmations"] == 100
    assert item["candidate_coinbase_total_sats"] == 5000000000
    assert item["maturity_required"] == 100
    assert item["payout_ready"] is True


def test_unresolved_candidate_is_not_payout_ready_without_reward_proof(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: _reward_response(
            [
                {
                    "height": 301,
                    "blockhash": "1" * 64,
                    "time": 1004,
                    "mediantime": 1004,
                    "coinbase_total_sats": None,
                    "maturity_status": "mature",
                    "confirmations": 150,
                    "is_on_main_chain": True,
                }
            ]
        ),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["blockhash"] is None
    assert item["blockhash_status"] == "candidate"
    assert item["correlation_status"] == "candidate_single_within_window"
    assert item["payout_ready"] is False


def test_rejected_orphaned_candidate_is_not_promoted(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _insert_event(client, monkeypatch, tmp_path, detected_time=1000)

    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: _reward_response(
            [
                {
                    "height": 302,
                    "blockhash": "2" * 64,
                    "time": 1002,
                    "mediantime": 1002,
                    "coinbase_total_sats": 5000000000,
                    "maturity_status": "unknown",
                    "confirmations": -1,
                    "is_on_main_chain": False,
                }
            ]
        ),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["blockhash"] is None
    assert item["blockhash_status"] == "rejected_or_orphaned"
    assert item["correlation_status"] == "rejected_or_orphaned"
    assert item["payout_ready"] is False


def test_invalid_candidate_window_seconds_returns_422(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true", "candidate_window_seconds": 0},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 422


def test_invalid_candidate_time_field_returns_422(
    monkeypatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true", "candidate_time_field": "bad"},
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 422
