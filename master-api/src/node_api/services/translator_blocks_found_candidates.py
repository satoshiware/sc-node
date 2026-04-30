from __future__ import annotations

from typing import Any, Literal

from node_api.routes.v1 import az_blocks as az_blocks_route


def _selected_time(block: dict[str, Any], time_field: Literal["time", "mediantime"]) -> int | None:
    value = block.get(time_field)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _candidate_blocks_for_event(
    event: dict[str, Any],
    blocks: list[dict[str, Any]],
    *,
    candidate_window_seconds: int,
    candidate_time_field: Literal["time", "mediantime"],
    candidate_limit_per_event: int,
) -> dict[str, Any]:
    detected_time = event["detected_time"]
    matches: list[dict[str, Any]] = []

    for block in blocks:
        selected_time = _selected_time(block, candidate_time_field)
        if selected_time is None:
            continue
        signed_delta_seconds = selected_time - detected_time
        abs_delta_seconds = abs(signed_delta_seconds)
        if abs_delta_seconds > candidate_window_seconds:
            continue
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
            }
        )

    matches.sort(
        key=lambda item: (
            item["abs_delta_seconds"],
            -(item["height"] if isinstance(item.get("height"), int) else -1),
        )
    )
    returned_matches = matches[:candidate_limit_per_event]

    enriched = dict(event)
    enriched["candidate_window_seconds"] = candidate_window_seconds
    enriched["candidate_time_field"] = candidate_time_field
    enriched["candidate_count"] = len(matches)
    enriched["nearest_candidate_blockhash"] = (
        returned_matches[0]["blockhash"] if returned_matches else None
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
    candidate_query_end = max(detected_times) + candidate_window_seconds

    rewards = az_blocks_route.block_rewards(
        limit=50,
        owned_only=False,
        start_time=candidate_query_start,
        end_time=candidate_query_end,
        time_field=candidate_time_field,
        blockhash=None,
        blockhashes=None,
    )
    blocks_raw = rewards.get("blocks")
    blocks = [block for block in blocks_raw if isinstance(block, dict)] if isinstance(blocks_raw, list) else []

    return [
        _candidate_blocks_for_event(
            item,
            blocks,
            candidate_window_seconds=candidate_window_seconds,
            candidate_time_field=candidate_time_field,
            candidate_limit_per_event=candidate_limit_per_event,
        )
        for item in items
    ]
