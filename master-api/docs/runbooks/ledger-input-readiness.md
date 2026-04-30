# Ledger Input Readiness

## Purpose

`scripts/ledger_mvp_probe.py` is a small readiness probe for the SC-node
ledger input surface.

It checks whether the API can currently supply:

- base API health
- translator status
- joined translator miner-work rows
- translator blocks-found evidence
- AZ reward truth rows

It does **not** do ledger accounting, payout calculation, signing,
broadcasting, wallet sends, or any other money movement.

## Required Environment Variables

- `API_BASE_URL`
  Example: `http://127.0.0.1:8000`
- `API_TOKEN`
  Bearer token for the protected `/v1/translator/*` and `/v1/az/*`
  endpoints

## How To Run

```powershell
$env:API_BASE_URL = "http://127.0.0.1:8000"
$env:API_TOKEN = "replace-me"
python scripts/ledger_mvp_probe.py
```

Optional help:

```powershell
python scripts/ledger_mvp_probe.py --help
```

Exit codes:

- `0` = `PASS`
- `1` = `WARN`
- `2` = `FAIL`

## Endpoint Truth Roles

- `GET /v1/health`
  Service reachability only.
- `GET /v1/translator/status`
  Translator readiness summary.
- `GET /v1/translator/miner-work/snapshot`
  Translator local work truth for the current joined worker/channel view.
- `GET /v1/translator/blocks-found`
  Durable translator-side counter-delta evidence.
- `GET /v1/az/blocks/rewards?owned_only=false&limit=10`
  Chain reward truth.

## PASS / WARN / FAIL Rules

- `FAIL`
  API unreachable.
- `FAIL`
  Any protected endpoint returns `401` or `403`.
- `FAIL`
  AZ rewards endpoint unavailable or malformed.
- `FAIL`
  Any joined miner snapshot row is missing `share_work_sum`.
- `WARN`
  Translator status is `unconfigured`.
- `WARN`
  Translator status is `degraded`.
- `WARN`
  Miner snapshot returns zero rows.
- `WARN`
  Any joined miner snapshot row is missing `worker_identity`.
- `WARN`
  Any blocks-found event has `blockhash_status="unresolved"`.

## Fields The Ledger May Consume

From `GET /v1/translator/miner-work/snapshot`:

- `channel_id`
- `worker_identity`
- `authorized_worker_name`
- `share_work_sum`
- `shares_submitted`
- `shares_acknowledged`
- `shares_rejected`
- `blocks_found`

From `GET /v1/translator/blocks-found`:

- `detected_time`
- `worker_identity`
- `authorized_worker_name`
- `blocks_found_before`
- `blocks_found_after`
- `blocks_found_delta`
- `share_work_sum_at_detection`
- `blockhash`
- `blockhash_status`
- `correlation_status`

From `GET /v1/az/blocks/rewards`:

- `height`
- `blockhash`
- `time`
- `mediantime`
- `confirmations`
- `is_on_main_chain`
- `maturity_status`
- `blocks_until_mature`
- `maturity_height`
- `coinbase_total_sats`
- `blocks`

## Diagnostic-Only Fields

These are useful for operators and correlation debugging, but do not by
themselves prove payout eligibility:

- `translator/status.status`
- `translator/status.log_status`
- `translator/status.monitoring_status`
- `translator/status.recent_error_count`
- `miner-work/snapshot.join_status`
- `translator/blocks-found.channel_id`
- `translator/blocks-found.detected_time_iso`
- `translator/blocks-found.downstream_user_identity`
- `translator/blocks-found.upstream_user_identity`
- `translator/blocks-found.blockhash_status`
- `translator/blocks-found.correlation_status`
- `translator/blocks-found.candidate_count`
- `translator/blocks-found.nearest_candidate_blockhash`
- `translator/blocks-found.candidate_blocks`
- `az/blocks/rewards.ownership_configured`
- `az/blocks/rewards.unresolved_blockhashes`
- `az/blocks/rewards.stale_blockhashes`
- `az/blocks/rewards.filtered_out_blockhashes`

## Unresolved Block-Found Evidence

`blockhash_status="unresolved"` means the translator evidence store saw a
positive `blocks_found` counter delta but does not currently have direct
blockhash proof for that event.

Interpretation:

- it is still useful evidence that the translator observed a block-found
  counter increase
- it is **not** proof of chain inclusion
- it is **not** proof of maturity
- it is **not** proof of payout eligibility

Use `/v1/az/blocks/rewards` for chain-side reward truth before any ledger
accounting step.

If `/v1/translator/blocks-found` is called with
`include_candidate_blocks=true`, the returned `candidate_blocks` are only
nearby time-window chain candidates. They are useful for operator review,
but they are not verified payout proof and must not replace exact
translator/pool evidence in `blockhash`.

## Explicit Non-Goal Warning

This readiness probe does **not** move money and does **not** prove payout
eligibility by itself.

It only checks whether the current ledger input surfaces appear available
and internally plausible enough for later accounting work.
