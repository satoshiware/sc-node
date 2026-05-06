from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from node_api.settings import Settings, get_settings


def _settings(monkeypatch) -> Settings:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev_token")
    monkeypatch.setenv("AZ_API_DEV_TOKEN", "testtoken")
    monkeypatch.setenv("LEDGER_POSTGRES_DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("TRANSLATOR_BLOCKS_FOUND_DB_PATH", ".data/unused-test.sqlite3")
    monkeypatch.setenv("TRANSLATOR_LOG_PATH", "")
    get_settings.cache_clear()
    return get_settings()


def _client(monkeypatch) -> TestClient:
    _settings(monkeypatch)
    from node_api import main as main_module

    return TestClient(main_module.create_app())


def test_include_candidate_blocks_no_longer_enriches_from_az_rewards(
    monkeypatch,
) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(
        "node_api.services.translator_candidate_blocks_postgres.query_translator_candidate_blocks",
        lambda *args, **kwargs: (
            [
                {
                    "found_time": datetime(2026, 5, 6, 17, 47, 45, tzinfo=UTC),
                    "found_time_unix": 1778089665,
                    "blockhash": "a" * 64,
                    "worker_identity": "worker-a",
                    "channel_id": None,
                    "source": "sv1_capture_proxy",
                    "proof_type": "translator_submit_reconstructed_block_hash",
                }
            ],
            1,
        ),
    )
    monkeypatch.setattr(
        "node_api.services.translator_blocks_found_candidates.az_blocks_route.block_rewards",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("old rewards path called")),
    )

    response = client.get(
        "/v1/translator/blocks-found",
        params={
            "include_candidate_blocks": "true",
            "candidate_window_seconds": 300,
            "candidate_limit_per_event": 50,
        },
        headers={"Authorization": "Bearer testtoken"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item == {
        "found_time": 1778089665,
        "found_time_iso": "2026-05-06T17:47:45Z",
        "blockhash": "a" * 64,
        "worker_identity": "worker-a",
        "channel_id": None,
        "source": "sv1_capture_proxy",
        "proof_type": "translator_submit_reconstructed_block_hash",
    }
    assert "candidate_blocks" not in item
    assert "payout_ready" not in item
    assert "candidate_coinbase_total_sats" not in item
