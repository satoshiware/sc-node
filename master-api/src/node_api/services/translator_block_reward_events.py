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

_ISO_TS_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)
_SUBMIT_RE = re.compile(
    r"Received\s+mining\.submit\s+from\s+SV1\s+downstream\s+for\s+channel\s+id:\s*(\d+)",
    re.IGNORECASE,
)
_SHARE_VALIDATION_RE = re.compile(
    r"share\s+validation\s+share:\s*([0-9a-fA-F]{64})\s+downstream\s+target:\s*"
    r"[0-9a-fA-F]{64}",
    re.IGNORECASE,
)
_FORWARDED_RE = re.compile(
    r"SubmitSharesExtended:\s*valid\s+share,\s*forwarding\s+it\s+to\s+upstream\s*\|\s*"
    r"channel_id:\s*(\d+),\s*sequence_number:\s*(\d+)",
    re.IGNORECASE,
)
_EXCLUDED_MARKERS = ("setnewprevhash", "prev_hash", "blocks_found")
_JOURNALCTL_TIMEOUT_SECONDS = 3.0
_AZTRANSLATOR_SERVICE = "aztranslator.service"


class TranslatorBlockRewardEventsConfigError(RuntimeError):
    """Translator share-candidate proof source is unavailable."""


@dataclass(frozen=True)
class TranslatorBlockFoundProof:
    """Translator-computed share/header hash, not accepted-chain block status."""

    found_time: int
    found_time_iso: str
    blockhash: str
    source: Literal["aztranslator_journal", "translator_log"]
    channel_id: int
    sequence_number: int
    raw_log_lines: list[str]


@dataclass(frozen=True)
class _PendingSubmit:
    channel_id: int
    ts: tuple[int, str] | None
    line_index: int
    raw_log_line: str


@dataclass(frozen=True)
class _PendingValidation:
    channel_id: int
    submit_ts: tuple[int, str] | None
    validation_ts: tuple[int, str] | None
    share_header_hash: str
    raw_log_lines: list[str]


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
    """Retained for compatibility; single log lines are no longer sufficient proof.

    The block-reward-events endpoint now requires ordered translator-only
    evidence from mining.submit, share validation, and upstream forwarding
    lines. The hash returned as ``blockhash`` is the translator-computed
    share/candidate header hash, not accepted-chain status.
    """
    del raw_line, source
    return None


def _line_is_excluded(raw_line: str) -> bool:
    lowered = raw_line.lower()
    return any(marker in lowered for marker in _EXCLUDED_MARKERS)


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
            "Translator share-candidate proof source is unavailable. Set "
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


def _within_time_filter(
    found_time: int,
    *,
    start_time: int | None,
    end_time: int | None,
) -> bool:
    if start_time is not None and found_time < start_time:
        return False
    if end_time is not None and found_time >= end_time:
        return False
    return True


def parse_block_found_proofs_from_lines(
    lines: list[str],
    *,
    source: Literal["aztranslator_journal", "translator_log"],
    limit: int,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[TranslatorBlockFoundProof]:
    latest_submit: _PendingSubmit | None = None
    pending_validation_by_channel: dict[int, _PendingValidation] = {}
    proofs: list[TranslatorBlockFoundProof] = []

    for line_index, raw_line in enumerate(lines):
        line = raw_line.rstrip("\r\n")
        if not line or _line_is_excluded(line):
            continue

        submit_match = _SUBMIT_RE.search(line)
        if submit_match:
            channel_id = int(submit_match.group(1))
            latest_submit = _PendingSubmit(
                channel_id=channel_id,
                ts=_extract_translator_timestamp(line),
                line_index=line_index,
                raw_log_line=line,
            )
            continue

        validation_match = _SHARE_VALIDATION_RE.search(line)
        if validation_match:
            if latest_submit is None:
                continue
            share_header_hash = validation_match.group(1).lower()
            validation = _PendingValidation(
                channel_id=latest_submit.channel_id,
                submit_ts=latest_submit.ts,
                validation_ts=_extract_translator_timestamp(line),
                share_header_hash=share_header_hash,
                raw_log_lines=[latest_submit.raw_log_line, line],
            )
            pending_validation_by_channel[latest_submit.channel_id] = validation
            latest_submit = None
            continue

        forwarded_match = _FORWARDED_RE.search(line)
        if not forwarded_match:
            continue

        channel_id = int(forwarded_match.group(1))
        sequence_number = int(forwarded_match.group(2))
        validation = pending_validation_by_channel.pop(channel_id, None)
        if validation is None:
            continue

        found_ts = validation.validation_ts or validation.submit_ts
        if found_ts is None:
            continue
        found_time, found_time_iso = found_ts
        if not _within_time_filter(found_time, start_time=start_time, end_time=end_time):
            continue

        # ``blockhash`` is kept in the response for compatibility, but it is
        # the translator-computed share/candidate header hash. It is not a
        # statement that the hash was accepted on chain.
        proofs.append(
            TranslatorBlockFoundProof(
                found_time=found_time,
                found_time_iso=found_time_iso,
                blockhash=validation.share_header_hash,
                source=source,
                channel_id=channel_id,
                sequence_number=sequence_number,
                raw_log_lines=[*validation.raw_log_lines, line],
            )
        )

    return list(reversed(proofs))[:limit]


def load_block_found_proofs_with_source(
    settings: Settings,
    *,
    limit: int,
    start_time: int | None = None,
    end_time: int | None = None,
) -> tuple[list[TranslatorBlockFoundProof], Literal["aztranslator_journal", "translator_log"]]:
    scan_lines = max(int(limit) * 30, settings.translator_log_default_lines)
    scan_lines = max(1, min(scan_lines, settings.translator_log_max_lines))
    lines, source = _load_proof_lines(settings, scan_lines)

    proofs = parse_block_found_proofs_from_lines(
        lines,
        source=source,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
    )
    return proofs, source


def load_block_found_proofs(settings: Settings, *, limit: int) -> list[TranslatorBlockFoundProof]:
    proofs, _source = load_block_found_proofs_with_source(settings, limit=limit)
    return proofs


def _event_from_proof(proof: TranslatorBlockFoundProof) -> dict[str, Any]:
    return {
        "found_time": proof.found_time,
        "found_time_iso": proof.found_time_iso,
        "blockhash": proof.blockhash,
        "proof_type": "translator_validated_share_forwarded_upstream",
        "source": proof.source,
        "channel_id": proof.channel_id,
        "sequence_number": proof.sequence_number,
        "raw_log_lines": proof.raw_log_lines,
    }


def block_reward_events_payload(
    settings: Settings,
    *,
    limit: int,
    start_time: int | None = None,
    end_time: int | None = None,
    time_field: Literal["time", "mediantime"] = "time",
) -> dict[str, Any]:
    del time_field
    try:
        proofs, proof_source = load_block_found_proofs_with_source(
            settings,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )
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
