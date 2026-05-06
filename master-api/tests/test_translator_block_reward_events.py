from __future__ import annotations

import atexit
from pathlib import Path

from fastapi.testclient import TestClient

from node_api.services.translator_block_reward_events import (
    parse_block_found_proofs_from_lines,
)
from node_api.settings import get_settings

AUTH = {"Authorization": "Bearer testtoken"}
SHARE_HASH = "a" * 64
TARGET_HASH = "f" * 64
PREV_HASH = "b" * 64


def _client(
    monkeypatch,
    log_text: str | None,
    *,
    translator_log_path: bool = True,
    log_name: str = ".codex_translator_block_reward_events.log",
) -> TestClient:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev_token")
    monkeypatch.setenv("AZ_API_DEV_TOKEN", "testtoken")
    monkeypatch.delenv("AZ_REWARD_OWNERSHIP_ADDRESSES", raising=False)
    monkeypatch.delenv("AZ_REWARD_OWNERSHIP_SCRIPT_PUBKEYS", raising=False)
    if translator_log_path:
        log_path = (Path.cwd() / log_name).resolve()
        log_path.write_text(log_text or "", encoding="utf-8")
        atexit.register(log_path.unlink, missing_ok=True)
        monkeypatch.setenv("TRANSLATOR_LOG_PATH", str(log_path))
    else:
        monkeypatch.setenv("TRANSLATOR_LOG_PATH", "")
    get_settings.cache_clear()

    from node_api import main as main_module

    return TestClient(main_module.create_app())


def _correlated_log(
    *,
    channel_id: int = 2,
    sequence_number: int = 133723,
    share_hash: str = SHARE_HASH,
    submit_ts: str = "2026-05-05T22:09:11.000000Z",
    validation_ts: str = "2026-05-05T22:09:12.000000Z",
    forward_ts: str = "2026-05-05T22:09:13.000000Z",
) -> str:
    return "\n".join(
        [
            (
                f"{submit_ts} DEBUG jd_client::downstream: "
                "Received mining.submit from SV1 downstream for channel id: "
                f"{channel_id}"
            ),
            (
                f"{validation_ts} DEBUG jd_client::downstream: "
                f"share validation share: {share_hash} downstream target: {TARGET_HASH}"
            ),
            (
                f"{forward_ts} INFO jd_client::downstream: "
                "SubmitSharesExtended: valid share, forwarding it to upstream | "
                f"channel_id: {channel_id}, sequence_number: {sequence_number}"
            ),
        ]
    )


def test_parser_correlates_submit_share_validation_and_forwarded_upstream() -> None:
    proofs = parse_block_found_proofs_from_lines(
        _correlated_log().splitlines(),
        source="translator_log",
        limit=10,
    )

    assert len(proofs) == 1
    proof = proofs[0]
    assert proof.found_time == 1_778_018_952
    assert proof.found_time_iso == "2026-05-05T22:09:12Z"
    assert proof.blockhash == SHARE_HASH
    assert proof.source == "translator_log"
    assert proof.channel_id == 2
    assert proof.sequence_number == 133723
    assert len(proof.raw_log_lines) == 3


def test_endpoint_uses_share_validation_hash_as_blockhash(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        _correlated_log(share_hash="c" * 64),
        log_name=".codex_tbre_share_hash.log",
    )

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["blockhash"] == "c" * 64
    assert item["proof_type"] == "translator_validated_share_forwarded_upstream"
    assert item["channel_id"] == 2
    assert item["sequence_number"] == 133723
    assert len(item["raw_log_lines"]) == 3


def test_endpoint_ignores_set_new_prev_hash_prev_hash(monkeypatch) -> None:
    log_text = "\n".join(
        [
            (
                "2026-05-05T22:09:10.000000Z INFO jd_client::upstream: "
                f"SetNewPrevHash prev_hash: {PREV_HASH}"
            ),
            _correlated_log(share_hash=SHARE_HASH),
        ]
    )
    client = _client(monkeypatch, log_text, log_name=".codex_tbre_prev_hash.log")

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["blockhash"] == SHARE_HASH
    assert body["items"][0]["blockhash"] != PREV_HASH


def test_endpoint_ignores_blocks_found_counters(monkeypatch) -> None:
    log_text = "\n".join(
        [
            (
                "2026-05-05T22:09:10.000000Z INFO translator: "
                "blocks_found counter increased from 1 to 2"
            ),
            _correlated_log(share_hash=SHARE_HASH),
        ]
    )
    client = _client(monkeypatch, log_text, log_name=".codex_tbre_blocks_found.log")

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["blockhash"] == SHARE_HASH


def test_endpoint_ignores_forwarding_only_lines_without_share_validation_hash(
    monkeypatch,
) -> None:
    log_text = (
        "2026-05-05T22:09:13.000000Z INFO jd_client::downstream: "
        "SubmitSharesExtended: valid share, forwarding it to upstream | "
        "channel_id: 2, sequence_number: 133723"
    )
    client = _client(monkeypatch, log_text, log_name=".codex_tbre_forward_only.log")

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "source": "translator_log",
        "total": 0,
        "items": [],
    }


def test_endpoint_response_does_not_include_payout_reward_or_ownership_fields(
    monkeypatch,
) -> None:
    client = _client(monkeypatch, _correlated_log(), log_name=".codex_tbre_shape.log")

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    forbidden_top_level = {
        "blocked_reason",
        "matched_count",
        "payout_ready_count",
        "not_found_count",
        "immature_count",
        "source_attempts",
    }
    forbidden_item_fields = {
        "payout_ready",
        "coinbase_total_sats",
        "confirmations",
        "maturity_status",
        "is_on_main_chain",
        "ownership",
        "accepted",
        "rejected",
        "reward",
        "blocked_reason",
        "matched_blockhash",
        "hash_match_method",
        "chain_status",
        "raw_share_hash",
        "raw_hash",
    }
    assert forbidden_top_level.isdisjoint(body)
    assert forbidden_item_fields.isdisjoint(item)
    assert set(item) == {
        "found_time",
        "found_time_iso",
        "blockhash",
        "proof_type",
        "source",
        "channel_id",
        "sequence_number",
        "raw_log_lines",
    }


def test_endpoint_respects_start_time_and_end_time(monkeypatch) -> None:
    log_text = "\n".join(
        [
            _correlated_log(
                channel_id=2,
                sequence_number=100,
                share_hash="1" * 64,
                submit_ts="2026-05-05T22:09:09.000000Z",
                validation_ts="2026-05-05T22:09:10.000000Z",
                forward_ts="2026-05-05T22:09:11.000000Z",
            ),
            _correlated_log(
                channel_id=3,
                sequence_number=101,
                share_hash="2" * 64,
                submit_ts="2026-05-05T22:09:11.000000Z",
                validation_ts="2026-05-05T22:09:12.000000Z",
                forward_ts="2026-05-05T22:09:13.000000Z",
            ),
            _correlated_log(
                channel_id=4,
                sequence_number=102,
                share_hash="3" * 64,
                submit_ts="2026-05-05T22:09:13.000000Z",
                validation_ts="2026-05-05T22:09:14.000000Z",
                forward_ts="2026-05-05T22:09:15.000000Z",
            ),
        ]
    )
    client = _client(monkeypatch, log_text, log_name=".codex_tbre_time_filter.log")

    response = client.get(
        "/v1/translator/block-reward-events?start_time=1778018952&end_time=1778018954",
        headers=AUTH,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["blockhash"] == "2" * 64
    assert body["items"][0]["found_time"] == 1_778_018_952


def test_endpoint_returns_total_zero_when_debug_share_validation_lines_are_absent(
    monkeypatch,
) -> None:
    log_text = "\n".join(
        [
            (
                "2026-05-05T22:09:11.000000Z DEBUG jd_client::downstream: "
                "Received mining.submit from SV1 downstream for channel id: 2"
            ),
            (
                "2026-05-05T22:09:13.000000Z INFO jd_client::downstream: "
                "SubmitSharesExtended: valid share, forwarding it to upstream | "
                "channel_id: 2, sequence_number: 133723"
            ),
        ]
    )
    client = _client(monkeypatch, log_text, log_name=".codex_tbre_no_validation.log")

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_endpoint_does_not_call_chain_rewards_lookup(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        _correlated_log(),
        log_name=".codex_tbre_chain_guard.log",
    )

    def _unexpected_chain_rewards(**kwargs):
        raise AssertionError("block-reward-events must not call chain rewards lookup")

    monkeypatch.setattr(
        "node_api.routes.v1.az_blocks.block_rewards",
        _unexpected_chain_rewards,
    )

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["items"][0]["blockhash"] == SHARE_HASH
