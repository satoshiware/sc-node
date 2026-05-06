from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

_PROOF_TYPE = "translator_submit_reconstructed_block_hash"
_SOURCE = "api_sidecar_reconstruction"


@dataclass(frozen=True)
class Sv1JobState:
    job_id: str
    prev_hash: str
    coinbase1: str
    coinbase2: str
    merkle_branches: list[str]
    version: str
    nbits: str
    ntime: str


@dataclass
class Sv1SessionState:
    worker_identity: str | None = None
    extranonce1: str | None = None


@dataclass(frozen=True)
class ReconstructedCandidate:
    found_time: int
    found_time_iso: str
    blockhash: str
    worker_identity: str | None
    channel_id: int | None
    proof_type: Literal["translator_submit_reconstructed_block_hash"]
    source: Literal["api_sidecar_reconstruction"]
    job_id: str
    extranonce2: str
    ntime: str
    nonce: str
    version: str
    prev_hash: str
    nbits: str
    target: int
    hash_int: int
    is_block_found: bool
    raw_submit_json: str

    def store_event(self) -> dict[str, Any]:
        return {
            "found_time": self.found_time,
            "found_time_iso": self.found_time_iso,
            "blockhash": self.blockhash,
            "worker_identity": self.worker_identity,
            "channel_id": self.channel_id,
            "job_id": self.job_id,
            "extranonce2": self.extranonce2,
            "ntime": self.ntime,
            "nonce": self.nonce,
            "version": self.version,
            "prev_hash": self.prev_hash,
            "nbits": self.nbits,
            "source": self.source,
            "proof_type": self.proof_type,
            "raw_submit_json": self.raw_submit_json,
        }


def utc_iso_from_unix(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def _clean_hex(value: Any, *, field: str, even: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a hex string")
    text = value.strip().lower()
    if even and len(text) % 2 != 0:
        raise ValueError(f"{field} must have even hex length")
    try:
        bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be hex") from exc
    return text


def _uint32_le_from_hex(value: str, *, field: str) -> bytes:
    text = _clean_hex(value, field=field)
    if len(text) != 8:
        raise ValueError(f"{field} must be 4 bytes")
    return int(text, 16).to_bytes(4, byteorder="little", signed=False)


def _hash_display_to_header_bytes(value: str, *, field: str) -> bytes:
    text = _clean_hex(value, field=field)
    if len(text) != 64:
        raise ValueError(f"{field} must be 32 bytes")
    return bytes.fromhex(text)[::-1]


def decode_compact_target(nbits: str) -> int:
    text = _clean_hex(nbits, field="nbits")
    if len(text) != 8:
        raise ValueError("nbits must be 4 bytes")
    compact = int(text, 16)
    exponent = compact >> 24
    mantissa = compact & 0x007FFFFF
    if compact & 0x00800000:
        raise ValueError("negative compact targets are unsupported")
    if exponent <= 3:
        return mantissa >> (8 * (3 - exponent))
    return mantissa << (8 * (exponent - 3))


def coinbase_txid(
    *,
    coinbase1: str,
    extranonce1: str,
    extranonce2: str,
    coinbase2: str,
) -> bytes:
    coinbase_hex = (
        _clean_hex(coinbase1, field="coinbase1")
        + _clean_hex(extranonce1, field="extranonce1")
        + _clean_hex(extranonce2, field="extranonce2")
        + _clean_hex(coinbase2, field="coinbase2")
    )
    return double_sha256(bytes.fromhex(coinbase_hex))


def merkle_root_from_coinbase_txid(txid: bytes, merkle_branches: list[str]) -> bytes:
    if len(txid) != 32:
        raise ValueError("coinbase txid must be 32 bytes")
    root = txid
    for branch in merkle_branches:
        branch_bytes = bytes.fromhex(_clean_hex(branch, field="merkle_branch"))
        if len(branch_bytes) != 32:
            raise ValueError("merkle branches must be 32 bytes")
        root = double_sha256(root + branch_bytes)
    return root


def build_block_header(
    *,
    version: str,
    prev_hash: str,
    merkle_root: bytes,
    ntime: str,
    nbits: str,
    nonce: str,
) -> bytes:
    if len(merkle_root) != 32:
        raise ValueError("merkle_root must be 32 bytes")
    return b"".join(
        [
            _uint32_le_from_hex(version, field="version"),
            _hash_display_to_header_bytes(prev_hash, field="prev_hash"),
            merkle_root,
            _uint32_le_from_hex(ntime, field="ntime"),
            _uint32_le_from_hex(nbits, field="nbits"),
            _uint32_le_from_hex(nonce, field="nonce"),
        ]
    )


def candidate_hash_from_header(header: bytes) -> str:
    if len(header) != 80:
        raise ValueError("block header must be 80 bytes")
    return double_sha256(header)[::-1].hex()


def hash_display_to_int(blockhash: str) -> int:
    return int(_clean_hex(blockhash, field="blockhash"), 16)


def parse_sv1_json_line(line: bytes | str) -> dict[str, Any] | None:
    text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
    text = text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class Sv1CandidateReconstructor:
    def __init__(self, *, default_extranonce1: str | None = None) -> None:
        self.sessions: dict[str, Sv1SessionState] = {}
        self.jobs: dict[str, Sv1JobState] = {}
        self.default_extranonce1 = default_extranonce1.lower() if default_extranonce1 else None

    def process_json(
        self,
        session_id: str,
        message: dict[str, Any],
        *,
        received_time: int | None = None,
        channel_id: int | None = None,
    ) -> ReconstructedCandidate | None:
        method = message.get("method")
        params = message.get("params")
        session = self.sessions.setdefault(session_id, Sv1SessionState())
        if not isinstance(method, str):
            self._handle_subscribe_response(session, message)
            return None
        if not isinstance(params, list):
            return None

        if method == "mining.authorize":
            self._handle_authorize(session, params)
            return None
        if method == "mining.set_extranonce":
            self._handle_set_extranonce(session, params)
            return None
        if method == "mining.notify":
            self._handle_notify(params)
            return None
        if method == "mining.submit":
            return self._handle_submit(
                session,
                params,
                message=message,
                received_time=received_time,
                channel_id=channel_id,
            )
        return None

    def process_line(
        self,
        session_id: str,
        line: bytes | str,
        *,
        received_time: int | None = None,
        channel_id: int | None = None,
    ) -> ReconstructedCandidate | None:
        message = parse_sv1_json_line(line)
        if message is None:
            return None
        return self.process_json(
            session_id,
            message,
            received_time=received_time,
            channel_id=channel_id,
        )

    def _handle_authorize(self, session: Sv1SessionState, params: list[Any]) -> None:
        if params and isinstance(params[0], str):
            session.worker_identity = params[0]

    def _handle_set_extranonce(self, session: Sv1SessionState, params: list[Any]) -> None:
        if params and isinstance(params[0], str):
            session.extranonce1 = _clean_hex(params[0], field="extranonce1")

    def _handle_subscribe_response(
        self,
        session: Sv1SessionState,
        message: dict[str, Any],
    ) -> None:
        result = message.get("result")
        if not isinstance(result, list) or len(result) < 2:
            return
        if isinstance(result[1], str):
            session.extranonce1 = _clean_hex(result[1], field="extranonce1")

    def _handle_notify(self, params: list[Any]) -> None:
        if len(params) < 8:
            return
        merkle_branches = params[4]
        if not isinstance(merkle_branches, list):
            return
        job = Sv1JobState(
            job_id=str(params[0]),
            prev_hash=_clean_hex(params[1], field="prev_hash"),
            coinbase1=_clean_hex(params[2], field="coinbase1"),
            coinbase2=_clean_hex(params[3], field="coinbase2"),
            merkle_branches=[
                _clean_hex(branch, field="merkle_branch") for branch in merkle_branches
            ],
            version=_clean_hex(params[5], field="version"),
            nbits=_clean_hex(params[6], field="nbits"),
            ntime=_clean_hex(params[7], field="ntime"),
        )
        self.jobs[job.job_id] = job

    def _handle_submit(
        self,
        session: Sv1SessionState,
        params: list[Any],
        *,
        message: dict[str, Any],
        received_time: int | None,
        channel_id: int | None,
    ) -> ReconstructedCandidate | None:
        if len(params) < 5:
            return None
        submit_worker_identity = params[0] if isinstance(params[0], str) else None
        worker_identity = session.worker_identity or submit_worker_identity
        job_id = str(params[1])
        job = self.jobs.get(job_id)
        if job is None:
            return None

        extranonce1 = session.extranonce1 or self.default_extranonce1
        if extranonce1 is None:
            return None

        extranonce2 = _clean_hex(params[2], field="extranonce2")
        ntime = _clean_hex(params[3], field="ntime")
        nonce = _clean_hex(params[4], field="nonce")
        txid = coinbase_txid(
            coinbase1=job.coinbase1,
            extranonce1=extranonce1,
            extranonce2=extranonce2,
            coinbase2=job.coinbase2,
        )
        merkle_root = merkle_root_from_coinbase_txid(txid, job.merkle_branches)
        header = build_block_header(
            version=job.version,
            prev_hash=job.prev_hash,
            merkle_root=merkle_root,
            ntime=ntime,
            nbits=job.nbits,
            nonce=nonce,
        )
        candidate_hash = candidate_hash_from_header(header)
        target = decode_compact_target(job.nbits)
        hash_int = hash_display_to_int(candidate_hash)
        found_time = int(received_time if received_time is not None else time.time())
        return ReconstructedCandidate(
            found_time=found_time,
            found_time_iso=utc_iso_from_unix(found_time),
            blockhash=candidate_hash,
            worker_identity=worker_identity,
            channel_id=channel_id,
            proof_type=_PROOF_TYPE,
            source=_SOURCE,
            job_id=job.job_id,
            extranonce2=extranonce2,
            ntime=ntime,
            nonce=nonce,
            version=job.version,
            prev_hash=job.prev_hash,
            nbits=job.nbits,
            target=target,
            hash_int=hash_int,
            is_block_found=hash_int <= target,
            raw_submit_json=json.dumps(message, separators=(",", ":"), sort_keys=True),
        )
