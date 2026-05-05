from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException

from node_api.services import translator_logs as tl
from node_api.settings import Settings

_BLOCK_FOUND_PHRASE = "block found"
_HEX_64_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_ISO_TS_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)
_EXCLUDED_PREV_HASH_MARKERS = ("setnewprevhash", "prev_hash")
_CANDIDATE_BLOCK_MARKERS = (
    _BLOCK_FOUND_PHRASE,
    "candidate block",
    "candidate_block",
    "submitted block",
    "submit block",
)
_JOURNALCTL_TIMEOUT_SECONDS = 3.0
_AZTRANSLATOR_SERVICE = "aztranslator.service"


class TranslatorBlockRewardEventsConfigError(RuntimeError):
    """Translator block-found proof source is unavailable."""


@dataclass(frozen=True)
class TranslatorBlockFoundProof:
    found_time: int
    found_time_iso: str
    blockhash: str
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


def _extract_translator_timestamp(line: str) -> tuple[int, str] | None:
    # journalctl lines can contain an outer journal timestamp plus an inner
    # translator timestamp. Prefer the embedded translator timestamp.
    matches = list(_ISO_TS_RE.finditer(line))
    if matches:
        candidates = [m.group(0) for m in matches if m.start() > 0] or [matches[0].group(0)]
        for candidate in candidates:
            parsed_ts = _parse_timestamp(candidate)
            if parsed_ts is not None:
                return parsed_ts

    record = tl.parse_log_line(line)
    if record is not None:
        return _parse_timestamp(record.ts)

    first_token = line.split(maxsplit=1)[0] if line.split(maxsplit=1) else ""
    return _parse_timestamp(first_token)


def parse_block_found_proof_line(
    raw_line: str,
    *,
    source: Literal["aztranslator_journal", "translator_log"] = "translator_log",
) -> TranslatorBlockFoundProof | None:
    line = raw_line.rstrip("\r\n")
    lowered = line.lower()
    if any(marker in lowered for marker in _EXCLUDED_PREV_HASH_MARKERS):
        return None
    if not any(marker in lowered for marker in _CANDIDATE_BLOCK_MARKERS):
        return None

    hashes = _HEX_64_RE.findall(line)
    if len(hashes) != 1:
        return None

    parsed_ts = _extract_translator_timestamp(line)
    if parsed_ts is None:
        return None

    found_time, found_time_iso = parsed_ts
    return TranslatorBlockFoundProof(
        found_time=found_time,
        found_time_iso=found_time_iso,
        blockhash=hashes[0].lower(),
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


def _event_from_proof(proof: TranslatorBlockFoundProof) -> dict[str, Any]:
    return {
        "found_time": proof.found_time,
        "found_time_iso": proof.found_time_iso,
        "blockhash": proof.blockhash,
        "proof_type": "translator_candidate_block_log",
        "source": proof.source,
        "raw_log_line": proof.raw_log_line,
    }


def block_reward_events_payload(
    settings: Settings,
    *,
    limit: int,
    start_time: int | None = None,
    end_time: int | None = None,
    time_field: Literal["time", "mediantime"] = "time",
) -> dict[str, Any]:
    del start_time, end_time, time_field
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

    items = [_event_from_proof(proof) for proof in proofs]
    return {
        "status": "ok",
        "source": proof_source,
        "total": len(items),
        "items": items,
    }
