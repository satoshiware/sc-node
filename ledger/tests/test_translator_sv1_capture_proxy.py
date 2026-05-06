from __future__ import annotations

import asyncio
from dataclasses import asdict

import pytest

from app.translator_sv1_capture_proxy import (
    TranslatorSv1CaptureProxy,
    TranslatorSv1CaptureProxyConfig,
    TranslatorSv1SessionProcessor,
    load_config_from_env,
)


EXTRANONCE1_RESPONSE = (
    b'{"id":1,"result":[[["mining.set_difficulty","1"],["mining.notify","1"]],"01020304",4],"error":null}\n'
)
NOTIFY = (
    b'{"id":null,"method":"mining.notify","params":["job-1","'
    + b"00" * 32
    + b'","0100000001","ffffffff",["'
    + b"11" * 32
    + b'","'
    + b"22" * 32
    + b'"],"20000000","2200ffff","65000000",true]}\n'
)
SUBMIT = (
    b'{"id":9,"method":"mining.submit","params":["baveetstudy.miner2","job-1","0a0b0c0d","65000001","00000000"]}\n'
)
NON_BLOCK_NOTIFY = NOTIFY.replace(b'"2200ffff"', b'"01010000"')
AUTHORIZE = b'{"id":2,"method":"mining.authorize","params":["baveetstudy.miner2","x"]}\n'


class FakeRepository:
    def __init__(self, *, fail_on_duplicate: bool = False) -> None:
        self.rows = []
        self.blockhashes = set()
        self.fail_on_duplicate = fail_on_duplicate

    def insert_translator_candidate_block(self, event):
        row = event.as_repository_event() if hasattr(event, "as_repository_event") else asdict(event)
        if row["blockhash"] in self.blockhashes and self.fail_on_duplicate:
            raise RuntimeError("duplicate blockhash")
        if row["blockhash"] not in self.blockhashes:
            self.blockhashes.add(row["blockhash"])
            self.rows.append(row)
        return row


def _prime_processor(repository=None, *, dry_run=False) -> TranslatorSv1SessionProcessor:
    processor = TranslatorSv1SessionProcessor(repository=repository, dry_run=dry_run)
    processor.process_upstream_bytes(EXTRANONCE1_RESPONSE)
    processor.process_upstream_bytes(NOTIFY)
    processor.process_downstream_bytes(AUTHORIZE)
    return processor


def test_mining_authorize_associates_worker_identity_with_session() -> None:
    processor = TranslatorSv1SessionProcessor(repository=None, dry_run=True)

    processor.process_downstream_bytes(AUTHORIZE)

    assert processor.worker_identity == "baveetstudy.miner2"


def test_mining_notify_stores_job_state() -> None:
    processor = TranslatorSv1SessionProcessor(repository=None, dry_run=True)

    processor.process_upstream_bytes(NOTIFY)

    assert processor.jobs["job-1"].job_id == "job-1"
    assert processor.jobs["job-1"].nbits == "2200ffff"


def test_mining_submit_candidate_event_triggers_insert_when_target_is_met() -> None:
    repository = FakeRepository()
    processor = _prime_processor(repository)

    processor.process_downstream_bytes(SUBMIT)

    assert len(repository.rows) == 1
    row = repository.rows[0]
    assert row["worker_identity"] == "baveetstudy.miner2"
    assert row["source"] == "sv1_capture_proxy"
    assert row["proof_type"] == "translator_submit_reconstructed_block_hash"
    assert row["raw_submit_json"]["method"] == "mining.submit"
    assert row["raw_job_json"]["method"] == "mining.notify"


def test_non_block_share_does_not_insert() -> None:
    repository = FakeRepository()
    processor = TranslatorSv1SessionProcessor(repository=repository, dry_run=False)
    processor.process_upstream_bytes(EXTRANONCE1_RESPONSE)
    processor.process_upstream_bytes(NON_BLOCK_NOTIFY)
    processor.process_downstream_bytes(AUTHORIZE)

    processor.process_downstream_bytes(SUBMIT)

    assert repository.rows == []


def test_dry_run_does_not_insert() -> None:
    repository = FakeRepository()
    processor = _prime_processor(repository, dry_run=True)

    processor.process_downstream_bytes(SUBMIT)

    assert repository.rows == []


def test_duplicate_blockhash_insert_does_not_crash() -> None:
    repository = FakeRepository(fail_on_duplicate=True)
    processor = _prime_processor(repository)

    processor.process_downstream_bytes(SUBMIT)
    processor.process_downstream_bytes(SUBMIT)

    assert len(repository.rows) == 1


def test_channel_id_null_when_mapping_unavailable() -> None:
    repository = FakeRepository()
    processor = _prime_processor(repository)

    processor.process_downstream_bytes(SUBMIT)

    assert repository.rows[0]["channel_id"] is None


def test_no_payout_reward_ownership_maturity_fields_are_inserted() -> None:
    repository = FakeRepository()
    processor = _prime_processor(repository)

    processor.process_downstream_bytes(SUBMIT)

    assert {
        "payout_readiness",
        "confirmations",
        "maturity_status",
        "coinbase_total_sats",
        "ownership",
        "accepted",
        "rejected",
    }.isdisjoint(repository.rows[0])


def test_config_defaults_to_dry_run_and_requires_postgres_only_for_insert_mode() -> None:
    dry_config = load_config_from_env(
        {
            "TRANSLATOR_CAPTURE_UPSTREAM_HOST": "127.0.0.1",
            "TRANSLATOR_CAPTURE_UPSTREAM_PORT": "4444",
        }
    )
    assert dry_config.listen_host == "127.0.0.1"
    assert dry_config.listen_port == 3333
    assert dry_config.dry_run is True

    with pytest.raises(ValueError, match="POSTGRES_LEDGER_DATABASE_URL"):
        load_config_from_env(
            {
                "TRANSLATOR_CAPTURE_UPSTREAM_HOST": "127.0.0.1",
                "TRANSLATOR_CAPTURE_UPSTREAM_PORT": "4444",
                "TRANSLATOR_CAPTURE_DRY_RUN": "false",
            }
        )


def test_proxy_forwards_bytes_even_if_parser_errors() -> None:
    asyncio.run(_assert_proxy_forwards_bytes_even_if_parser_errors())


async def _assert_proxy_forwards_bytes_even_if_parser_errors() -> None:
    received_by_upstream = bytearray()

    async def upstream_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(1024)
        received_by_upstream.extend(data)
        writer.write(b"upstream-response\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    upstream_server = await asyncio.start_server(upstream_handler, "127.0.0.1", 0)
    upstream_port = upstream_server.sockets[0].getsockname()[1]
    proxy_config = TranslatorSv1CaptureProxyConfig(
        listen_host="127.0.0.1",
        listen_port=0,
        upstream_host="127.0.0.1",
        upstream_port=upstream_port,
        postgres_database_url=None,
        dry_run=True,
        log_level="INFO",
    )
    proxy = TranslatorSv1CaptureProxy(config=proxy_config, repository=None)
    proxy_server = await asyncio.start_server(proxy._handle_client, "127.0.0.1", 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        invalid_json = b'{"method": "mining.submit", "params": [bad-json]}\n'
        writer.write(invalid_json)
        await writer.drain()
        response = await reader.readline()
        writer.close()
        await writer.wait_closed()

        assert bytes(received_by_upstream) == invalid_json
        assert response == b"upstream-response\n"
    finally:
        proxy_server.close()
        upstream_server.close()
        await proxy_server.wait_closed()
        await upstream_server.wait_closed()
