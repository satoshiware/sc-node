from __future__ import annotations

from typing import Any, Literal

from node_api.routes.v1 import az_blocks as az_blocks_route


def _selected_time(block: dict[str, Any], time_field: Literal["time", "mediantime"]) -> int | None:
    value = block.get(time_field)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _window_bounds(detected_time: int, candidate_window_seconds: int) -> tuple[int, int]:
    return (
        detected_time - candidate_window_seconds,
        detected_time + candidate_window_seconds + 1,
    )


def _reward_proof_sats(candidate: dict[str, Any]) -> int | None:
    for key in ("reward_sats", "coinbase_total_sats"):
        value = candidate.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _is_rejected_or_orphaned(candidate: dict[str, Any]) -> bool:
    confirmations = candidate.get("confirmations")
    if isinstance(confirmations, int) and not isinstance(confirmations, bool) and confirmations < 0:
        return True
    return candidate.get("is_on_main_chain") is False


def _is_resolved_candidate(candidate: dict[str, Any], maturity_required: int | None) -> bool:
    blockhash = candidate.get("blockhash")
    confirmations = candidate.get("confirmations")
    reward_sats = _reward_proof_sats(candidate)
    if not isinstance(blockhash, str) or not blockhash:
        return False
    if not isinstance(confirmations, int) or isinstance(confirmations, bool):
        return False
    if maturity_required is None or confirmations < maturity_required:
        return False
    if reward_sats is None:
        return False
    return not _is_rejected_or_orphaned(candidate)


def _classify_enriched_event(
    event: dict[str, Any],
    matches: list[dict[str, Any]],
    *,
    maturity_required: int | None,
) -> dict[str, Any]:
    enriched = dict(event)
    enriched["maturity_required"] = maturity_required
    enriched["candidate_confirmations"] = None
    enriched["candidate_coinbase_total_sats"] = None
    enriched["payout_ready"] = False

    if not matches:
        enriched["blockhash"] = None
        enriched["blockhash_status"] = "unresolved"
        enriched["correlation_status"] = "no_candidate_found"
        return enriched

    nearest = matches[0]
    enriched["candidate_confirmations"] = nearest.get("confirmations")
    enriched["candidate_coinbase_total_sats"] = _reward_proof_sats(nearest)

    if len(matches) > 1:
        enriched["blockhash"] = None
        enriched["blockhash_status"] = "ambiguous"
        enriched["correlation_status"] = "candidate_multiple_ambiguous"
        return enriched

    if _is_rejected_or_orphaned(nearest):
        enriched["blockhash"] = None
        enriched["blockhash_status"] = "rejected_or_orphaned"
        enriched["correlation_status"] = "rejected_or_orphaned"
        return enriched

    if _is_resolved_candidate(nearest, maturity_required):
        enriched["blockhash"] = nearest.get("blockhash")
        enriched["blockhash_status"] = "resolved"
        enriched["correlation_status"] = "resolved_to_blockhash"
        enriched["payout_ready"] = True
        return enriched

    enriched["blockhash"] = None
    enriched["blockhash_status"] = "candidate"
    enriched["correlation_status"] = "candidate_single_within_window"
    return enriched


def _candidate_blocks_for_event(
    event: dict[str, Any],
    blocks: list[dict[str, Any]],
    *,
    candidate_window_seconds: int,
    candidate_time_field: Literal["time", "mediantime"],
    candidate_limit_per_event: int,
    maturity_required: int | None,
) -> dict[str, Any]:
    detected_time = event["detected_time"]
    window_start, window_end = _window_bounds(detected_time, candidate_window_seconds)
    matches: list[dict[str, Any]] = []

    for block in blocks:
        selected_time = _selected_time(block, candidate_time_field)
        if selected_time is None:
            continue
        if not (window_start <= selected_time < window_end):
            continue
        signed_delta_seconds = selected_time - detected_time
        abs_delta_seconds = abs(signed_delta_seconds)
        matches.append(
            {
                "height": block.get("height"),
                "blockhash": block.get("blockhash"),
                "time": block.get("time"),
                "mediantime": block.get("mediantime"),
                "selected_time": selected_time,
                "signed_delta_seconds": signed_delta_seconds,
                "abs_delta_seconds": abs_delta_seconds,
                "coinbase_total_sats": block.get("coinbase_total_sats"),
                "maturity_status": block.get("maturity_status"),
                "confirmations": block.get("confirmations"),
                "is_on_main_chain": block.get("is_on_main_chain"),
            }
        )

    matches.sort(
        key=lambda item: (
            item["abs_delta_seconds"],
            item["signed_delta_seconds"],
            -(item["height"] if isinstance(item.get("height"), int) else -1),
            str(item.get("blockhash") or ""),
        )
    )
    returned_matches = matches[:candidate_limit_per_event]

    enriched = _classify_enriched_event(
        event,
        matches,
        maturity_required=maturity_required,
    )
    enriched["candidate_window_seconds"] = candidate_window_seconds
    enriched["candidate_time_field"] = candidate_time_field
    enriched["candidate_count"] = len(matches)
    enriched["nearest_candidate_blockhash"] = (
        matches[0]["blockhash"] if matches else None
    )
    enriched["candidate_blocks"] = returned_matches
    return enriched


def enrich_events_with_candidate_blocks(
    items: list[dict[str, Any]],
    *,
    candidate_window_seconds: int,
    candidate_time_field: Literal["time", "mediantime"],
    candidate_limit_per_event: int,
) -> list[dict[str, Any]]:
    if not items:
        return []

    detected_times = [item["detected_time"] for item in items]
    candidate_query_start = min(detected_times) - candidate_window_seconds
    candidate_query_end = max(detected_times) + candidate_window_seconds + 1

    rewards = az_blocks_route.block_rewards(
        limit=50,
        owned_only=False,
        start_time=candidate_query_start,
        end_time=candidate_query_end,
        time_field=candidate_time_field,
        blockhash=None,
        blockhashes=None,
    )
    maturity_required = rewards.get("maturity_confirmations")
    if not isinstance(maturity_required, int) or isinstance(maturity_required, bool):
        maturity_required = None
    blocks_raw = rewards.get("blocks")
    blocks = [block for block in blocks_raw if isinstance(block, dict)] if isinstance(blocks_raw, list) else []

    return [
        _candidate_blocks_for_event(
            item,
            blocks,
            candidate_window_seconds=candidate_window_seconds,
            candidate_time_field=candidate_time_field,
            candidate_limit_per_event=candidate_limit_per_event,
            maturity_required=maturity_required,
        )
        for item in items
    ]
