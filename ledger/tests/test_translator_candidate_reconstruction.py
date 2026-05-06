from __future__ import annotations

import re
from datetime import UTC, datetime

from app.translator_candidate_reconstruction import (
    build_block_header,
    candidate_blockhash_from_header,
    compute_merkle_root,
    decode_nbits_target,
    parse_mining_authorize,
    parse_mining_notify,
    parse_mining_submit,
    reconstruct_coinbase,
    reconstruct_submit_candidate,
)


FOUND_TIME = datetime(2026, 5, 6, 17, 47, 45, tzinfo=UTC)
EXTRANONCE1 = "01020304"


def _notify(nbits: str = "2200ffff") -> dict:
    return {
        "id": None,
        "method": "mining.notify",
        "params": [
            "job-1",
            "00" * 32,
            "0100000001",
            "ffffffff",
            ["11" * 32, "22" * 32],
            "20000000",
            nbits,
            "65000000",
            True,
        ],
    }


def _submit(nonce: str = "00000000") -> dict:
    return {
        "id": 9,
        "method": "mining.submit",
        "params": ["baveetstudy.miner2", "job-1", "0a0b0c0d", "65000001", nonce],
    }


def test_mining_authorize_captures_worker_identity() -> None:
    parsed = parse_mining_authorize(
        {"id": 1, "method": "mining.authorize", "params": ["baveetstudy.miner2", "x"]}
    )

    assert parsed is not None
    assert parsed.worker_identity == "baveetstudy.miner2"


def test_mining_notify_parses_job_state() -> None:
    parsed = parse_mining_notify(_notify())

    assert parsed is not None
    assert parsed.job_id == "job-1"
    assert parsed.prev_hash == "00" * 32
    assert parsed.coinbase1 == "0100000001"
    assert parsed.coinbase2 == "ffffffff"
    assert parsed.merkle_branches == ("11" * 32, "22" * 32)
    assert parsed.version == "20000000"
    assert parsed.clean_jobs is True


def test_mining_submit_reconstructs_candidate_blockhash() -> None:
    job = parse_mining_notify(_notify())
    submit = parse_mining_submit(_submit())
    assert job is not None
    assert submit is not None

    result = reconstruct_submit_candidate(
        job=job,
        submit=submit,
        extranonce1=EXTRANONCE1,
        found_time=FOUND_TIME,
    )
    coinbase = reconstruct_coinbase(job, EXTRANONCE1, submit.extranonce2)
    merkle_root = compute_merkle_root(coinbase, job.merkle_branches)
    header = build_block_header(
        version=job.version,
        prev_hash=job.prev_hash,
        merkle_root=merkle_root,
        ntime=submit.ntime,
        nbits=job.nbits,
        nonce=submit.nonce,
    )

    assert result.candidate_hash == candidate_blockhash_from_header(header)
    assert re.fullmatch(r"[0-9a-f]{64}", result.candidate_hash)


def test_nbits_target_comparison_identifies_block_found() -> None:
    job = parse_mining_notify(_notify(nbits="2200ffff"))
    submit = parse_mining_submit(_submit())
    assert job is not None
    assert submit is not None

    result = reconstruct_submit_candidate(
        job=job,
        submit=submit,
        extranonce1=EXTRANONCE1,
        found_time=FOUND_TIME,
        channel_id=3,
    )

    assert result.block_found is True
    assert result.event is not None
    assert int(result.event.blockhash, 16) <= decode_nbits_target("2200ffff")


def test_non_block_share_is_not_classified_as_block_found() -> None:
    job = parse_mining_notify(_notify(nbits="01010000"))
    submit = parse_mining_submit(_submit())
    assert job is not None
    assert submit is not None

    result = reconstruct_submit_candidate(
        job=job,
        submit=submit,
        extranonce1=EXTRANONCE1,
        found_time=FOUND_TIME,
    )

    assert result.block_found is False
    assert result.event is None


def test_reconstructed_event_includes_worker_identity_and_safe_fields() -> None:
    job = parse_mining_notify(_notify())
    submit = parse_mining_submit(_submit())
    assert job is not None
    assert submit is not None

    result = reconstruct_submit_candidate(
        job=job,
        submit=submit,
        extranonce1=EXTRANONCE1,
        found_time=FOUND_TIME,
        worker_identity="authorized.worker",
    )

    assert result.event is not None
    event = result.event.as_repository_event()
    assert event["worker_identity"] == "authorized.worker"
    assert event["found_time_unix"] == 1778089665
    assert event["source"] == "sv1_capture_proxy"
    assert event["proof_type"] == "translator_submit_reconstructed_block_hash"
    assert re.fullmatch(r"[0-9a-f]{64}", event["blockhash"])
    assert {
        "payout_readiness",
        "confirmations",
        "maturity_status",
        "coinbase_total_sats",
        "ownership",
        "accepted",
        "rejected",
    }.isdisjoint(event)
