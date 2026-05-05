from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException

from node_api.routes.v1 import az_blocks as az_blocks_route
from node_api.services import translator_logs as tl
from node_api.settings import Settings

_BLOCK_FOUND_PHRASE = "block found"
_MONEY_BAG = "\U0001f4b0"
_HEX_64_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_JOURNALCTL_TIMEOUT_SECONDS = 3.0
_AZTRANSLATOR_SERVICE = "aztranslator.service"


class TranslatorBlockRewardEventsConfigError(RuntimeError):
    """Translator block-found proof source is unavailable."""


@dataclass(frozen=True)
class TranslatorBlockFoundProof:
    found_time: int
    found_time_iso: str
    raw_share_hash: str
    source: Literal["aztranslator_journal", "translator_log"]
    raw_log_line: str


def _parse_timestamp(value: str) -> tuple[int, str] | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return int(parsed.timestamp()), parsed.isoformat().replace("+00:00", "Z")


def parse_block_found_proof_line(
    raw_line: str,
    *,
    source: Literal["aztranslator_journal", "translator_log"] = "translator_log",
) -> TranslatorBlockFoundProof | None:
    line = raw_line.rstrip("\r\n")
    if _BLOCK_FOUND_PHRASE not in line.lower() or _MONEY_BAG not in line:
        return None

    hashes = _HEX_64_RE.findall(line)
    if len(hashes) != 1:
        return None

    record = tl.parse_log_line(line)
    ts = record.ts if record is not None else line.split(maxsplit=1)[0]
    parsed_ts = _parse_timestamp(ts)
    if parsed_ts is None:
        return None

    found_time, found_time_iso = parsed_ts
    return TranslatorBlockFoundProof(
        found_time=found_time,
        found_time_iso=found_time_iso,
        raw_share_hash=hashes[0].lower(),
        source=source,
        raw_log_line=line,
    )


def _read_journalctl_lines(max_lines: int) -> list[str]:
    try:
        result = subprocess.run(
            [
                "journalctl",
                "-u",
                _AZTRANSLATOR_SERVICE,
                "-o",
                "short-iso",
                "--no-pager",
                "-n",
                str(max_lines),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=_JOURNALCTL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise TranslatorBlockRewardEventsConfigError(
            "Translator block-found proof source is unavailable. Set "
            "TRANSLATOR_LOG_PATH to a readable translator log file or provide "
            "journalctl access for aztranslator.service."
        ) from exc

    if result.returncode != 0:
        raise TranslatorBlockRewardEventsConfigError(
            "Translator journal read failed. Set TRANSLATOR_LOG_PATH to a "
            "readable translator log file "
            "or provide journalctl access for aztranslator.service."
        )
    return result.stdout.splitlines()


def _load_proof_lines(
    settings: Settings, max_lines: int
) -> tuple[list[str], Literal["aztranslator_journal", "translator_log"]]:
    path = tl.translator_log_path(settings)
    if path is not None:
        return tl.read_tail_lines(Path(path), max_lines), "translator_log"
    return _read_journalctl_lines(max_lines), "aztranslator_journal"


def load_block_found_proofs_with_source(
    settings: Settings, *, limit: int
) -> tuple[list[TranslatorBlockFoundProof], Literal["aztranslator_journal", "translator_log"]]:
    scan_lines = max(int(limit) * 20, settings.translator_log_default_lines)
    scan_lines = max(1, min(scan_lines, settings.translator_log_max_lines))
    lines, source = _load_proof_lines(settings, scan_lines)

    proofs: list[TranslatorBlockFoundProof] = []
    for line in reversed(lines):
        proof = parse_block_found_proof_line(line, source=source)
        if proof is None:
            continue
        proofs.append(proof)
        if len(proofs) >= limit:
            break
    return proofs, source


def load_block_found_proofs(settings: Settings, *, limit: int) -> list[TranslatorBlockFoundProof]:
    proofs, _source = load_block_found_proofs_with_source(settings, limit=limit)
    return proofs


def _byte_reversed_hash(blockhash: str) -> str:
    return bytes.fromhex(blockhash)[::-1].hex()


def _lookup_chain_block(
    blockhash: str,
) -> tuple[Literal["matched", "not_found", "not_main_chain"], dict[str, Any] | None]:
    response = az_blocks_route.block_rewards(
        limit=1,
        owned_only=False,
        start_time=None,
        end_time=None,
        time_field="time",
        blockhash=[blockhash],
        blockhashes=None,
    )
    blocks = response.get("blocks")
    if isinstance(blocks, list) and blocks:
        block = blocks[0]
        if isinstance(block, dict):
            return "matched", block

    stale = response.get("stale_blockhashes")
    if isinstance(stale, list) and blockhash in stale:
        return "not_main_chain", None
    return "not_found", None


def _chain_status(block: dict[str, Any] | None, lookup_status: str) -> str:
    if lookup_status == "not_main_chain":
        return "not_main_chain"
    if block is None:
        return "not_found"
    if block.get("is_on_main_chain") is not True:
        return "not_main_chain"
    if block.get("maturity_status") != "mature":
        return "immature"
    return "matched"


def _iso_from_unix(value: Any) -> str | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _is_payout_ready(blockhash: Any, block: dict[str, Any]) -> bool:
    return (
        blockhash is not None
        and block.get("is_on_main_chain") is True
        and block.get("maturity_status") == "mature"
        and block.get("coinbase_total_sats") is not None
    )


def _event_from_proof(proof: TranslatorBlockFoundProof) -> dict[str, Any]:
    lookup_status, block = _lookup_chain_block(proof.raw_share_hash)
    hash_match_method: str | None = None
    if block is not None:
        hash_match_method = "direct"
    elif lookup_status == "not_found":
        reversed_hash = _byte_reversed_hash(proof.raw_share_hash)
        lookup_status, block = _lookup_chain_block(reversed_hash)
        if block is not None:
            hash_match_method = "byte_reversed"

    matched_blockhash = block.get("blockhash") if block is not None else None
    coinbase_total_sats = block.get("coinbase_total_sats") if block is not None else None
    confirmations = block.get("confirmations") if block is not None else None
    maturity_status = block.get("maturity_status") if block is not None else None
    is_on_main_chain = block.get("is_on_main_chain") if block is not None else False
    chain_status = _chain_status(block, lookup_status)
    payout_ready = (
        matched_blockhash is not None
        and is_on_main_chain is True
        and maturity_status == "mature"
        and coinbase_total_sats is not None
    )

    return {
        "found_time": proof.found_time,
        "found_time_iso": proof.found_time_iso,
        "proof_type": "translator_block_found_share_hash",
        "raw_share_hash": proof.raw_share_hash,
        "blockhash": matched_blockhash,
        "matched_blockhash": matched_blockhash,
        "hash_match_method": hash_match_method,
        "chain_status": chain_status,
        "coinbase_total_sats": coinbase_total_sats,
        "confirmations": confirmations,
        "maturity_status": maturity_status,
        "is_on_main_chain": is_on_main_chain,
        "payout_ready": payout_ready,
        "source": proof.source,
        "raw_log_line": proof.raw_log_line,
    }


def _event_from_chain_reward_block(block: dict[str, Any]) -> dict[str, Any]:
    blockhash = block.get("blockhash")
    found_time = block.get("time")
    if not isinstance(found_time, int) or isinstance(found_time, bool):
        found_time = block.get("mediantime")

    maturity_status = block.get("maturity_status")
    chain_status = "immature" if maturity_status == "immature" else "matched"
    if block.get("is_on_main_chain") is not True:
        chain_status = "not_main_chain"

    normalized_found_time = (
        found_time if isinstance(found_time, int) and not isinstance(found_time, bool) else None
    )

    return {
        "found_time": normalized_found_time,
        "found_time_iso": _iso_from_unix(found_time),
        "proof_type": "chain_coinbase_reward",
        "raw_share_hash": None,
        "blockhash": blockhash if isinstance(blockhash, str) else None,
        "matched_blockhash": blockhash if isinstance(blockhash, str) else None,
        "hash_match_method": None,
        "chain_status": chain_status,
        "coinbase_total_sats": block.get("coinbase_total_sats"),
        "confirmations": block.get("confirmations"),
        "maturity_status": maturity_status,
        "is_on_main_chain": block.get("is_on_main_chain") is True,
        "payout_ready": _is_payout_ready(blockhash, block),
        "source": "azcoin_core_reward_ownership",
        "raw_log_line": None,
    }


def _chain_reward_ownership_blocked_payload(source_attempts: list[str]) -> dict[str, Any]:
    source_attempts.append("azcoin_core_reward_ownership:0")
    return {
        "status": "blocked",
        "source": "azcoin_core_reward_ownership",
        "blocked_reason": "reward_ownership_not_configured",
        "total": 0,
        "matched_count": 0,
        "payout_ready_count": 0,
        "not_found_count": 0,
        "immature_count": 0,
        "source_attempts": source_attempts,
        "items": [],
    }


def _chain_reward_ownership_payload(
    *,
    limit: int,
    start_time: int | None,
    end_time: int | None,
    time_field: Literal["time", "mediantime"],
    source_attempts: list[str],
) -> dict[str, Any]:
    try:
        response = az_blocks_route.block_rewards(
            limit=min(max(limit, 1), 200),
            owned_only=True,
            start_time=start_time,
            end_time=end_time,
            time_field=time_field,
            blockhash=None,
            blockhashes=None,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if detail.get("code") == "AZ_REWARD_OWNERSHIP_NOT_CONFIGURED":
            return _chain_reward_ownership_blocked_payload(source_attempts)
        raise

    blocks = response.get("blocks")
    items = [
        _event_from_chain_reward_block(block)
        for block in (blocks if isinstance(blocks, list) else [])
        if isinstance(block, dict)
    ]
    source_attempts.append(f"azcoin_core_reward_ownership:{len(items)}")
    return {
        "status": "ok",
        "source": "azcoin_core_reward_ownership",
        "blocked_reason": None,
        "total": len(items),
        "matched_count": len(items),
        "payout_ready_count": sum(1 for item in items if item["payout_ready"] is True),
        "not_found_count": 0,
        "immature_count": sum(1 for item in items if item["chain_status"] == "immature"),
        "source_attempts": source_attempts,
        "items": items,
    }


def block_reward_events_payload(
    settings: Settings,
    *,
    limit: int,
    start_time: int | None = None,
    end_time: int | None = None,
    time_field: Literal["time", "mediantime"] = "time",
) -> dict[str, Any]:
    try:
        proofs, proof_source = load_block_found_proofs_with_source(settings, limit=limit)
    except TranslatorBlockRewardEventsConfigError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "TRANSLATOR_BLOCK_REWARD_EVENTS_SOURCE_UNAVAILABLE",
                "message": str(exc),
            },
        ) from exc

    source_attempts = [f"{proof_source}:{len(proofs)}"]
    if not proofs:
        return _chain_reward_ownership_payload(
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            time_field=time_field,
            source_attempts=source_attempts,
        )

    items = [_event_from_proof(proof) for proof in proofs]
    return {
        "status": "ok",
        "source": items[0]["source"],
        "blocked_reason": None,
        "total": len(items),
        "matched_count": sum(1 for item in items if item["matched_blockhash"] is not None),
        "payout_ready_count": sum(1 for item in items if item["payout_ready"] is True),
        "not_found_count": sum(1 for item in items if item["chain_status"] == "not_found"),
        "immature_count": sum(1 for item in items if item["chain_status"] == "immature"),
        "source_attempts": source_attempts,
        "items": items,
    }
