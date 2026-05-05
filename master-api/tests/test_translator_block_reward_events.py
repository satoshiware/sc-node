from __future__ import annotations

import atexit
from pathlib import Path

from fastapi.testclient import TestClient

from node_api.services.translator_block_reward_events import (
    parse_block_found_proof_line,
)
from node_api.settings import get_settings

AUTH = {"Authorization": "Bearer testtoken"}


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


def _proof_line(raw_hash: str) -> str:
    return (
        "2026-05-05T22:09:12.000000Z INFO jd_client::downstream: "
        "SubmitSharesStandard on downstream channel: "
        f"\U0001f4b0 Block Found!!! \U0001f4b0{raw_hash}"
    )


def test_parser_extracts_timestamp_and_hash_from_translator_block_found_line() -> None:
    raw_hash = "a" * 64

    proof = parse_block_found_proof_line(_proof_line(raw_hash))

    assert proof is not None
    assert proof.found_time == 1_778_018_952
    assert proof.found_time_iso == "2026-05-05T22:09:12Z"
    assert proof.blockhash == raw_hash
    assert proof.source == "translator_log"


def test_parser_prefers_inner_iso_timestamp_from_journal_line() -> None:
    raw_hash = "b" * 64
    line = (
        "2026-05-05T22:10:00+00:00 host aztranslator[123]: "
        f"{_proof_line(raw_hash)}"
    )

    proof = parse_block_found_proof_line(line, source="aztranslator_journal")

    assert proof is not None
    assert proof.found_time_iso == "2026-05-05T22:09:12Z"
    assert proof.blockhash == raw_hash
    assert proof.source == "aztranslator_journal"


def test_parser_extracts_explicit_candidate_block_line() -> None:
    blockhash = "f" * 64
    line = (
        "2026-05-05T22:09:12.000000Z INFO jd_client::upstream: "
        f"submitted candidate block blockhash={blockhash}"
    )

    proof = parse_block_found_proof_line(line)

    assert proof is not None
    assert proof.found_time_iso == "2026-05-05T22:09:12Z"
    assert proof.blockhash == blockhash


def test_parser_ignores_set_new_prev_hash_prev_hash() -> None:
    prev_hash = "e" * 64
    line = (
        "2026-05-05T22:09:12.000000Z INFO jd_client::upstream: "
        f"SetNewPrevHash prev_hash: {prev_hash}"
    )

    assert parse_block_found_proof_line(line) is None


def test_parser_ignores_valid_share_forwarding_line_without_blockhash() -> None:
    line = (
        "2026-05-05T22:09:12.000000Z INFO jd_client::downstream: "
        "SubmitSharesExtended: valid share, forwarding it to upstream | "
        "channel_id: 2, sequence_number: 133723"
    )

    assert parse_block_found_proof_line(line) is None


def test_parser_ignores_blocks_found_counter_line() -> None:
    line = (
        "2026-05-05T22:09:12.000000Z INFO translator: "
        "blocks_found counter increased from 1 to 2"
    )

    assert parse_block_found_proof_line(line) is None


def test_endpoint_returns_total_zero_when_no_block_found_lines_exist(
    monkeypatch,
) -> None:
    client = _client(
        monkeypatch,
        "2026-05-05T22:09:12Z INFO no block here",
        log_name=".codex_tbre_empty.log",
    )

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "source": "translator_log",
        "total": 0,
        "items": [],
    }


def test_endpoint_does_not_require_reward_ownership_config(
    monkeypatch,
) -> None:
    client = _client(monkeypatch, "", log_name=".codex_tbre_no_ownership.log")

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["total"] == 0


def test_endpoint_ignores_prev_hash_and_hashless_forwarding_lines(
    monkeypatch,
) -> None:
    blockhash = "1" * 64
    prev_hash = "2" * 64
    log_text = "\n".join(
        [
            (
                "2026-05-05T22:09:10.000000Z INFO jd_client::upstream: "
                f"SetNewPrevHash prev_hash: {prev_hash}"
            ),
            (
                "2026-05-05T22:09:11.000000Z INFO jd_client::downstream: "
                "SubmitSharesExtended: valid share, forwarding it to upstream | "
                "channel_id: 2, sequence_number: 133723"
            ),
            (
                "2026-05-05T22:09:12.000000Z INFO jd_client::upstream: "
                f"submitted candidate block blockhash={blockhash}"
            ),
        ]
    )
    client = _client(monkeypatch, log_text, log_name=".codex_tbre_mixed.log")

    response = client.get("/v1/translator/block-reward-events", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["blockhash"] == blockhash


def test_endpoint_does_not_call_chain_rewards_lookup(
    monkeypatch,
) -> None:
    raw_hash = "c" * 64
    client = _client(
        monkeypatch,
        _proof_line(raw_hash),
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
    item = response.json()["items"][0]
    assert item["blockhash"] == raw_hash
    assert item["proof_type"] == "translator_candidate_block_log"


def test_endpoint_response_does_not_include_payout_fields(
    monkeypatch,
) -> None:
    raw_hash = "d" * 64
    client = _client(
        monkeypatch,
        _proof_line(raw_hash),
        log_name=".codex_tbre_shape.log",
    )

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
        "raw_log_line",
    }
