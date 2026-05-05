from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from node_api.services.translator_block_reward_events import (
    parse_block_found_proof_line,
)
from node_api.settings import get_settings


AUTH = {"Authorization": "Bearer testtoken"}


def _client(monkeypatch, tmp_path: Path, log_text: str) -> TestClient:
    log_path = tmp_path / "aztranslator.log"
    log_path.write_text(log_text, encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev_token")
    monkeypatch.setenv("AZ_API_DEV_TOKEN", "testtoken")
    monkeypatch.setenv("TRANSLATOR_LOG_PATH", str(log_path))
    get_settings.cache_clear()

    from node_api import main as main_module

    return TestClient(main_module.create_app())


def _block(blockhash: str, *, confirmations: int = 120, maturity_status: str = "mature") -> dict:
    return {
        "height": 1000,
        "blockhash": blockhash,
        "time": 1_774_000_005,
        "mediantime": 1_774_000_004,
        "coinbase_total_sats": 625_000_000,
        "maturity_status": maturity_status,
        "confirmations": confirmations,
        "is_on_main_chain": True,
    }


def _proof_line(share_hash: str) -> str:
    return (
        "2026-03-20T12:26:40.000000Z INFO jd_client::downstream: "
        f"SubmitSharesStandard on downstream channel: \U0001f4b0 Block Found!!! \U0001f4b0{share_hash}"
    )


def test_parser_extracts_timestamp_and_share_hash() -> None:
    share_hash = "a" * 64

    proof = parse_block_found_proof_line(_proof_line(share_hash))

    assert proof is not None
    assert proof.found_time_iso == "2026-03-20T12:26:40Z"
    assert proof.raw_share_hash == share_hash
    assert proof.source == "translator_log"


def test_direct_hash_match_verifies_chain_reward(monkeypatch, tmp_path: Path) -> None:
    share_hash = "b" * 64
    client = _client(monkeypatch, tmp_path, _proof_line(share_hash))
    calls: list[dict] = []

    def _fake_rewards(**kwargs):
        calls.append(kwargs)
        assert kwargs["blockhash"] == [share_hash]
        assert kwargs["start_time"] is None
        assert kwargs["end_time"] is None
        return {"blocks": [_block(share_hash)], "stale_blockhashes": [], "unresolved_blockhashes": []}

    monkeypatch.setattr(
        "node_api.services.translator_block_reward_events.az_blocks_route.block_rewards",
        _fake_rewards,
    )

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    assert len(calls) == 1
    assert body["source"] == "translator_log"
    assert body["matched_count"] == 1
    assert body["payout_ready_count"] == 1
    assert item["raw_share_hash"] == share_hash
    assert item["matched_blockhash"] == share_hash
    assert item["hash_match_method"] == "direct"
    assert item["chain_status"] == "matched"
    assert item["coinbase_total_sats"] == 625_000_000
    assert item["payout_ready"] is True


def test_byte_reversed_hash_match_verifies_chain_reward(monkeypatch, tmp_path: Path) -> None:
    share_hash = "00" * 31 + "01"
    reversed_hash = "01" + "00" * 31
    client = _client(monkeypatch, tmp_path, _proof_line(share_hash))
    requested: list[str] = []

    def _fake_rewards(**kwargs):
        requested.append(kwargs["blockhash"][0])
        if kwargs["blockhash"] == [share_hash]:
            return {"blocks": [], "stale_blockhashes": [], "unresolved_blockhashes": [share_hash]}
        return {"blocks": [_block(reversed_hash)], "stale_blockhashes": [], "unresolved_blockhashes": []}

    monkeypatch.setattr(
        "node_api.services.translator_block_reward_events.az_blocks_route.block_rewards",
        _fake_rewards,
    )

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert requested == [share_hash, reversed_hash]
    assert item["matched_blockhash"] == reversed_hash
    assert item["hash_match_method"] == "byte_reversed"
    assert item["chain_status"] == "matched"
    assert item["payout_ready"] is True


def test_unmatched_hash_is_not_payout_ready(monkeypatch, tmp_path: Path) -> None:
    share_hash = "c" * 64
    client = _client(monkeypatch, tmp_path, _proof_line(share_hash))

    monkeypatch.setattr(
        "node_api.services.translator_block_reward_events.az_blocks_route.block_rewards",
        lambda **kwargs: {
            "blocks": [],
            "stale_blockhashes": [],
            "unresolved_blockhashes": kwargs["blockhash"],
        },
    )

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    assert body["not_found_count"] == 1
    assert item["matched_blockhash"] is None
    assert item["hash_match_method"] is None
    assert item["chain_status"] == "not_found"
    assert item["payout_ready"] is False


def test_immature_matched_block_is_not_payout_ready(monkeypatch, tmp_path: Path) -> None:
    share_hash = "d" * 64
    client = _client(monkeypatch, tmp_path, _proof_line(share_hash))

    monkeypatch.setattr(
        "node_api.services.translator_block_reward_events.az_blocks_route.block_rewards",
        lambda **kwargs: {
            "blocks": [_block(share_hash, confirmations=12, maturity_status="immature")],
            "stale_blockhashes": [],
            "unresolved_blockhashes": [],
        },
    )

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    assert body["immature_count"] == 1
    assert body["payout_ready_count"] == 0
    assert item["matched_blockhash"] == share_hash
    assert item["chain_status"] == "immature"
    assert item["payout_ready"] is False


def test_timestamp_candidate_correlation_is_not_used_when_log_proof_exists(
    monkeypatch,
    tmp_path: Path,
) -> None:
    share_hash = "e" * 64
    client = _client(monkeypatch, tmp_path, _proof_line(share_hash))
    calls: list[dict] = []

    def _fake_rewards(**kwargs):
        calls.append(kwargs)
        assert kwargs["blockhash"] == [share_hash]
        assert kwargs["blockhashes"] is None
        assert kwargs["start_time"] is None
        assert kwargs["end_time"] is None
        return {"blocks": [_block(share_hash)], "stale_blockhashes": [], "unresolved_blockhashes": []}

    monkeypatch.setattr(
        "node_api.services.translator_block_reward_events.az_blocks_route.block_rewards",
        _fake_rewards,
    )

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["blockhash"] == [share_hash]
    assert calls[0]["start_time"] is None
    assert calls[0]["end_time"] is None
    assert response.json()["items"][0]["payout_ready"] is True
