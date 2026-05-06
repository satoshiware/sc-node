from __future__ import annotations

from pathlib import Path

from node_api.services.translator_candidate_blocks_store import TranslatorCandidateBlocksStore
from node_api.services.translator_candidate_reconstruction import (
    Sv1CandidateReconstructor,
    build_block_header,
    candidate_hash_from_header,
    coinbase_txid,
    decode_compact_target,
    merkle_root_from_coinbase_txid,
)


def _notify(*, nbits: str = "2200ffff") -> dict:
    return {
        "id": None,
        "method": "mining.notify",
        "params": [
            "job-1",
            "00" * 32,
            "01000000",
            "",
            [],
            "20000000",
            nbits,
            "681b9451",
            True,
        ],
    }


def _authorize(worker_identity: str = "baveetstudy.miner2") -> dict:
    return {
        "id": 1,
        "method": "mining.authorize",
        "params": [worker_identity, "x"],
    }


def _submit() -> dict:
    return {
        "id": 2,
        "method": "mining.submit",
        "params": [
            "baveetstudy.miner2",
            "job-1",
            "00000002",
            "681b9451",
            "00000001",
        ],
    }


def _db_path(name: str) -> Path:
    path = Path.cwd() / name
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{path}{suffix}")
        candidate.unlink(missing_ok=True)
    return path


def test_mining_authorize_captures_worker_identity() -> None:
    reconstructor = Sv1CandidateReconstructor(default_extranonce1="00000001")

    reconstructor.process_json("session-a", _authorize())

    assert reconstructor.sessions["session-a"].worker_identity == "baveetstudy.miner2"


def test_mining_notify_stores_job_state() -> None:
    reconstructor = Sv1CandidateReconstructor(default_extranonce1="00000001")

    reconstructor.process_json("session-a", _notify())

    job = reconstructor.jobs["job-1"]
    assert job.prev_hash == "00" * 32
    assert job.coinbase1 == "01000000"
    assert job.nbits == "2200ffff"
    assert job.ntime == "681b9451"


def test_mining_subscribe_response_captures_extranonce1() -> None:
    reconstructor = Sv1CandidateReconstructor()

    reconstructor.process_json(
        "session-a",
        {
            "id": 1,
            "result": [[["mining.notify", "sub"]], "00000001", 4],
            "error": None,
        },
    )

    assert reconstructor.sessions["session-a"].extranonce1 == "00000001"


def test_mining_submit_reconstructs_candidate_blockhash() -> None:
    reconstructor = Sv1CandidateReconstructor(default_extranonce1="00000001")
    reconstructor.process_json("session-a", _authorize())
    reconstructor.process_json("session-a", _notify())

    candidate = reconstructor.process_json(
        "session-a",
        _submit(),
        received_time=1_778_089_665,
        channel_id=3,
    )

    assert candidate is not None
    txid = coinbase_txid(
        coinbase1="01000000",
        extranonce1="00000001",
        extranonce2="00000002",
        coinbase2="",
    )
    merkle_root = merkle_root_from_coinbase_txid(txid, [])
    header = build_block_header(
        version="20000000",
        prev_hash="00" * 32,
        merkle_root=merkle_root,
        ntime="681b9451",
        nbits="2200ffff",
        nonce="00000001",
    )
    assert candidate.blockhash == candidate_hash_from_header(header)
    assert len(candidate.blockhash) == 64
    assert candidate.blockhash == candidate.blockhash.lower()
    assert candidate.found_time == 1_778_089_665
    assert candidate.found_time_iso == "2026-05-06T17:47:45Z"
    assert candidate.worker_identity == "baveetstudy.miner2"
    assert candidate.channel_id == 3


def test_nbits_target_comparison_identifies_block_found() -> None:
    reconstructor = Sv1CandidateReconstructor(default_extranonce1="00000001")
    reconstructor.process_json("session-a", _authorize())
    reconstructor.process_json("session-a", _notify(nbits="2200ffff"))

    candidate = reconstructor.process_json("session-a", _submit(), received_time=1000)

    assert candidate is not None
    assert candidate.target == decode_compact_target("2200ffff")
    assert candidate.hash_int <= candidate.target
    assert candidate.is_block_found is True


def test_non_block_share_is_not_persisted() -> None:
    reconstructor = Sv1CandidateReconstructor(default_extranonce1="00000001")
    store = TranslatorCandidateBlocksStore(str(_db_path(".codex_tcb_non_block.sqlite3")))
    reconstructor.process_json("session-a", _authorize())
    reconstructor.process_json("session-a", _notify(nbits="01010000"))

    candidate = reconstructor.process_json("session-a", _submit(), received_time=1000)
    if candidate is not None and candidate.is_block_found:
        store.insert_event(candidate.store_event())

    assert candidate is not None
    assert candidate.is_block_found is False
    assert store.event_count() == 0


def test_persisted_event_includes_worker_identity() -> None:
    reconstructor = Sv1CandidateReconstructor(default_extranonce1="00000001")
    store = TranslatorCandidateBlocksStore(str(_db_path(".codex_tcb_worker.sqlite3")))
    reconstructor.process_json("session-a", _authorize())
    reconstructor.process_json("session-a", _notify())
    candidate = reconstructor.process_json("session-a", _submit(), received_time=1000)

    assert candidate is not None
    assert candidate.is_block_found is True
    store.insert_event(candidate.store_event())

    _total, items = store.list_events(start_time=None, end_time=None, limit=10)
    assert items[0]["worker_identity"] == "baveetstudy.miner2"


def test_persisted_event_includes_channel_id_when_monitoring_maps_user_identity(
) -> None:
    reconstructor = Sv1CandidateReconstructor(default_extranonce1="00000001")
    store = TranslatorCandidateBlocksStore(str(_db_path(".codex_tcb_channel.sqlite3")))
    reconstructor.process_json("session-a", _authorize())
    reconstructor.process_json("session-a", _notify())
    candidate = reconstructor.process_json(
        "session-a",
        _submit(),
        received_time=1000,
        channel_id=3,
    )

    assert candidate is not None
    store.insert_event(candidate.store_event())

    _total, items = store.list_events(start_time=None, end_time=None, limit=10)
    assert items[0]["channel_id"] == 3


def test_persisted_event_allows_channel_id_null_when_mapping_unavailable(
) -> None:
    reconstructor = Sv1CandidateReconstructor(default_extranonce1="00000001")
    store = TranslatorCandidateBlocksStore(str(_db_path(".codex_tcb_null_channel.sqlite3")))
    reconstructor.process_json("session-a", _authorize())
    reconstructor.process_json("session-a", _notify())
    candidate = reconstructor.process_json("session-a", _submit(), received_time=1000)

    assert candidate is not None
    store.insert_event(candidate.store_event())

    _total, items = store.list_events(start_time=None, end_time=None, limit=10)
    assert items[0]["channel_id"] is None
