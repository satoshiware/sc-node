from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

PASS = 0
WARN = 1
FAIL = 2

HEALTH_PATH = "/v1/health"
TRANSLATOR_STATUS_PATH = "/v1/translator/status"
MINER_SNAPSHOT_PATH = "/v1/translator/miner-work/snapshot"
BLOCKS_FOUND_PATH = "/v1/translator/blocks-found"
AZ_REWARDS_PATH = "/v1/az/blocks/rewards?owned_only=false&limit=10"


def _severity_name(value: int) -> str:
    return {PASS: "PASS", WARN: "WARN", FAIL: "FAIL"}[value]


def _normalize_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    if not normalized:
        return None
    if not (normalized.startswith("http://") or normalized.startswith("https://")):
        return None
    return normalized


def _print_report(report: dict[str, Any]) -> None:
    print("Ledger Input Readiness")
    print(f"Base URL: {report['base_url']}")
    print(
        "Summary: "
        f"{_severity_name(report['overall'])} "
        f"({report['pass_count']} pass, {report['warn_count']} warn, {report['fail_count']} fail)"
    )
    print("")
    for check in report["checks"]:
        print(f"[{_severity_name(check['severity'])}] {check['message']}")


def _add_check(report: dict[str, Any], severity: int, message: str) -> None:
    report["checks"].append({"severity": severity, "message": message})
    report["overall"] = max(report["overall"], severity)
    if severity == PASS:
        report["pass_count"] += 1
    elif severity == WARN:
        report["warn_count"] += 1
    else:
        report["fail_count"] += 1


def _request_json(base_url: str, token: str, path: str, timeout: float) -> dict[str, Any]:
    url = f"{base_url}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except (urllib.error.URLError, OSError) as exc:
        return {
            "path": path,
            "url": url,
            "status": None,
            "json": None,
            "transport_error": f"{type(exc).__name__}: {exc}",
        }

    payload = None
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            payload = None
    return {
        "path": path,
        "url": url,
        "status": status,
        "json": payload,
        "transport_error": None,
    }


def _json_status(response: dict[str, Any]) -> str | None:
    payload = response.get("json")
    if isinstance(payload, dict):
        value = payload.get("status")
        if isinstance(value, str):
            return value
    return None


def _json_items(response: dict[str, Any], *path: str) -> list[dict[str, Any]] | None:
    payload = response.get("json")
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if not isinstance(current, list):
        return None
    items: list[dict[str, Any]] = []
    for item in current:
        if isinstance(item, dict):
            items.append(item)
    return items


def _is_auth_failure(response: dict[str, Any]) -> bool:
    return response.get("status") in {401, 403}


def _summarize_http_error(response: dict[str, Any]) -> str:
    transport_error = response.get("transport_error")
    if transport_error:
        return transport_error
    status = response.get("status")
    if status is None:
        return "no_http_status"
    return f"HTTP {status}"


def probe(
    *,
    base_url: str,
    token: str,
    timeout: float,
    fetcher: Callable[[str, str, str, float], dict[str, Any]] = _request_json,
) -> dict[str, Any]:
    report = {
        "base_url": base_url,
        "overall": PASS,
        "checks": [],
        "pass_count": 0,
        "warn_count": 0,
        "fail_count": 0,
    }

    responses = {
        HEALTH_PATH: fetcher(base_url, token, HEALTH_PATH, timeout),
        TRANSLATOR_STATUS_PATH: fetcher(base_url, token, TRANSLATOR_STATUS_PATH, timeout),
        MINER_SNAPSHOT_PATH: fetcher(base_url, token, MINER_SNAPSHOT_PATH, timeout),
        BLOCKS_FOUND_PATH: fetcher(base_url, token, BLOCKS_FOUND_PATH, timeout),
        AZ_REWARDS_PATH: fetcher(base_url, token, AZ_REWARDS_PATH, timeout),
    }

    health = responses[HEALTH_PATH]
    if health["transport_error"] is not None:
        _add_check(report, FAIL, f"API unreachable at {HEALTH_PATH}: {health['transport_error']}")
    elif health["status"] != 200:
        _add_check(report, FAIL, f"{HEALTH_PATH} failed: {_summarize_http_error(health)}")
    else:
        _add_check(report, PASS, f"{HEALTH_PATH} returned HTTP 200")

    protected_paths = (
        TRANSLATOR_STATUS_PATH,
        MINER_SNAPSHOT_PATH,
        BLOCKS_FOUND_PATH,
        AZ_REWARDS_PATH,
    )
    auth_failures = [path for path in protected_paths if _is_auth_failure(responses[path])]
    if auth_failures:
        _add_check(
            report,
            FAIL,
            "Auth failure on protected endpoints: " + ", ".join(auth_failures),
        )
    else:
        _add_check(report, PASS, "Protected endpoints accepted the bearer token")

    translator_status = responses[TRANSLATOR_STATUS_PATH]
    if translator_status["transport_error"] is not None or translator_status["status"] != 200:
        _add_check(
            report,
            FAIL,
            f"{TRANSLATOR_STATUS_PATH} unavailable: {_summarize_http_error(translator_status)}",
        )
    else:
        status_value = _json_status(translator_status)
        if status_value == "unconfigured":
            _add_check(report, WARN, "Translator is unconfigured")
        elif status_value == "degraded":
            _add_check(report, WARN, "Translator is degraded")
        elif status_value == "ok":
            _add_check(report, PASS, "Translator status is ok")
        else:
            _add_check(report, FAIL, f"{TRANSLATOR_STATUS_PATH} payload missing status")

    miner_snapshot = responses[MINER_SNAPSHOT_PATH]
    if miner_snapshot["transport_error"] is not None or miner_snapshot["status"] != 200:
        _add_check(
            report,
            FAIL,
            f"{MINER_SNAPSHOT_PATH} unavailable: {_summarize_http_error(miner_snapshot)}",
        )
    else:
        snapshot_rows = _json_items(miner_snapshot, "data", "items")
        if snapshot_rows is None:
            _add_check(report, FAIL, f"{MINER_SNAPSHOT_PATH} payload missing data.items")
        else:
            if not snapshot_rows:
                _add_check(report, WARN, "Miner snapshot returned zero rows")
            else:
                _add_check(report, PASS, f"Miner snapshot returned {len(snapshot_rows)} rows")

            joined_rows = [
                row for row in snapshot_rows if row.get("join_status") == "joined"
            ]
            missing_worker_identity = [
                row.get("channel_id") for row in joined_rows if not row.get("worker_identity")
            ]
            missing_share_work_sum = [
                row.get("channel_id") for row in joined_rows if row.get("share_work_sum") is None
            ]

            if missing_worker_identity:
                _add_check(
                    report,
                    WARN,
                    "Joined rows missing worker_identity for channel_id="
                    + ",".join(str(value) for value in missing_worker_identity),
                )
            else:
                _add_check(report, PASS, "All joined rows include worker_identity")

            if missing_share_work_sum:
                _add_check(
                    report,
                    FAIL,
                    "Joined rows missing share_work_sum for channel_id="
                    + ",".join(str(value) for value in missing_share_work_sum),
                )
            else:
                _add_check(report, PASS, "All joined rows include share_work_sum")

    blocks_found = responses[BLOCKS_FOUND_PATH]
    if blocks_found["transport_error"] is not None or blocks_found["status"] != 200:
        _add_check(
            report,
            FAIL,
            f"{BLOCKS_FOUND_PATH} unavailable: {_summarize_http_error(blocks_found)}",
        )
    else:
        event_rows = _json_items(blocks_found, "items")
        if event_rows is None:
            _add_check(report, FAIL, f"{BLOCKS_FOUND_PATH} payload missing items")
        else:
            unresolved_count = sum(
                1 for item in event_rows if item.get("blockhash_status") == "unresolved"
            )
            if unresolved_count:
                _add_check(
                    report,
                    WARN,
                    f"Blocks-found evidence has {unresolved_count} unresolved blockhash event(s)",
                )
            else:
                _add_check(report, PASS, "Blocks-found evidence has no unresolved blockhash rows")

    az_rewards = responses[AZ_REWARDS_PATH]
    if az_rewards["transport_error"] is not None or az_rewards["status"] != 200:
        _add_check(
            report,
            FAIL,
            f"AZ rewards unavailable at {AZ_REWARDS_PATH}: {_summarize_http_error(az_rewards)}",
        )
    else:
        blocks = _json_items(az_rewards, "blocks")
        if blocks is None:
            _add_check(report, FAIL, f"{AZ_REWARDS_PATH} payload missing blocks")
        else:
            _add_check(report, PASS, f"AZ rewards endpoint returned {len(blocks)} block row(s)")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe SC-node ledger input readiness without performing accounting or payout."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-request timeout in seconds. Default: 10.0",
    )
    args = parser.parse_args(argv)

    raw_base_url = os.environ.get("API_BASE_URL")
    token = os.environ.get("API_TOKEN")
    base_url = _normalize_base_url(raw_base_url)

    if base_url is None:
        report = {
            "base_url": raw_base_url or "<missing>",
            "overall": FAIL,
            "checks": [],
            "pass_count": 0,
            "warn_count": 0,
            "fail_count": 0,
        }
        _add_check(report, FAIL, "API_BASE_URL must be set to an http:// or https:// URL")
        if not token:
            _add_check(report, FAIL, "API_TOKEN must be set")
        _print_report(report)
        return FAIL

    if not token:
        report = {
            "base_url": base_url,
            "overall": FAIL,
            "checks": [],
            "pass_count": 0,
            "warn_count": 0,
            "fail_count": 0,
        }
        _add_check(report, FAIL, "API_TOKEN must be set")
        _print_report(report)
        return FAIL

    report = probe(base_url=base_url, token=token, timeout=args.timeout)
    _print_report(report)
    return report["overall"]


if __name__ == "__main__":
    raise SystemExit(main())
