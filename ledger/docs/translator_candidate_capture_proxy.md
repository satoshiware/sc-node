# Translator Candidate Capture Proxy

This proxy is a dry-run-first ingestion path for reconstructed translator candidate block events.
It forwards SV1 TCP bytes unchanged between miners and the translator, parses line-delimited JSON-RPC opportunistically, and inserts into `translator_candidate_blocks` only when a reconstructed submit hash meets the job `nbits` target.

Do not put this inline with live mining until it has been tested with the exact SC-2 miner and translator topology.

## Required Environment

- `TRANSLATOR_CAPTURE_UPSTREAM_HOST`
- `TRANSLATOR_CAPTURE_UPSTREAM_PORT`
- `POSTGRES_LEDGER_DATABASE_URL` when `TRANSLATOR_CAPTURE_DRY_RUN=false`

Optional:

- `TRANSLATOR_CAPTURE_LISTEN_HOST`, default `127.0.0.1`
- `TRANSLATOR_CAPTURE_LISTEN_PORT`, default `3333`
- `TRANSLATOR_CAPTURE_DRY_RUN`, default `true`
- `TRANSLATOR_CAPTURE_LOG_LEVEL`, default `INFO`
- `TRANSLATOR_CAPTURE_CHANNELS_URL`, parsed for future channel lookup work but not used in this PR

## Flow

miners -> capture proxy -> translator

The proxy captures `mining.authorize`, `mining.notify`, the subscribe response `extranonce1`, and `mining.submit`.
It reconstructs the coinbase, merkle root, block header, and candidate blockhash from notify and submit data.

## Rollout

Start in dry-run mode and inspect logs for reconstructed candidate events.
Only after dry-run validation should `TRANSLATOR_CAPTURE_DRY_RUN=false` be used with a configured ledger Postgres URL.

Rollback is to stop the proxy and point miners back to the translator directly.

## Troubleshooting / correlation

Use the same wall-clock window (UTC) across systems.

1. **Pool / ubuntu01**: Locate `Block Found` or `SubmitSharesExtended` (or equivalent) lines. Note `job_id`, `nonce`, `ntime`, `version`, `extranonce` / extranonce2 span, and `blockhash`.

2. **Capture proxy journal**: For each downstream `mining_submit_seen` log, match `job_id`, `extranonce2`, `ntime`, `nonce`, and `version`. These fields come from the parsed `mining.submit` frame (version uses the submit 6th parameter when present, otherwise the cached `mining.notify` template version). Confirm `job_state_exists` and `extranonce1_exists`; if either is false, reconstruction will not run and no `candidate_reconstructed` line will appear for that submit.

3. **`candidate_reconstructed`**: For the same submit, check `reconstructed_hash` / `blockhash`, `nbits`, `target`, and `meets_target`. If the pool reported a block but `meets_target` is false here, the reconstructed header likely disagrees with what the pool evaluated (e.g. missing rolling `version` on submit, stale job, or extranonce mismatch).

4. **`translator_candidate_blocks`**: Rows appear only when `TRANSLATOR_CAPTURE_DRY_RUN=false`, a repository is configured, and insert attempted. Correlate by `blockhash` / `job_id` with `candidate_insert_succeeded`; if you see `candidate_insert_failed`, inspect the `error` field in that log line and the following exception stack.

