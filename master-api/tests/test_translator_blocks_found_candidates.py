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

    return TestClient(main_module.create_app()), TranslatorCandidateBlocksStore.from_settings(
        settings
    )


def test_legacy_include_candidate_blocks_query_does_not_call_chain_lookup(
    monkeypatch,
) -> None:
    client, store = _client(monkeypatch, ".codex_tcb_legacy_candidate_query.sqlite3")
    store.insert_event(
        {
            "found_time": 1000,
            "blockhash": "a" * 64,
            "worker_identity": "worker-a",
            "channel_id": 2,
        }
    )

    def _boom(**kwargs):
        raise AssertionError("blocks-found must not call /v1/az/blocks/rewards")

    monkeypatch.setattr("node_api.routes.v1.az_blocks.block_rewards", _boom)

    response = client.get(
        "/v1/translator/blocks-found",
        params={"include_candidate_blocks": "true", "candidate_window_seconds": 0},
        headers=AUTH,
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["blockhash"] == "a" * 64
    assert "candidate_blocks" not in item
    assert "payout_ready" not in item
