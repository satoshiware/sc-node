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

## SV1 `mining.submit` version field (version rolling)

When present, the optional 6th parameter on `mining.submit` is **version-rolling bits**, not the full 32-bit block header `version`.

Those bits are combined with the **base/template `version` from `mining.notify`**:

- If `mining.notify` includes a BIP310-style `version-rolling.mask` in the extended params object, the header version is `(notify.version & ~mask) | (submit_version & mask)`.
- Otherwise, the header version is `notify.version | submit_version` (bitwise OR).
- If `mining.submit` omits the 6th parameter, the header uses `notify.version` only.

Logs use **`submit_version=`** for the raw submit bits and **`version=`** for the **final merged** header version used in the reconstruction.

## Rollout

Start in dry-run mode and inspect logs for reconstructed candidate events.
Only after dry-run validation should `TRANSLATOR_CAPTURE_DRY_RUN=false` be used with a configured ledger Postgres URL.

Rollback is to stop the proxy and point miners back to the translator directly.

## Troubleshooting / correlation

Use the same wall-clock window (UTC) across systems.

1. **Pool / ubuntu01**: Locate `Block Found` or `SubmitSharesExtended` (or equivalent) lines. Note `job_id`, `nonce`, `ntime`, `version`, `extranonce` / extranonce2 span, and `blockhash`.

2. **Capture proxy journal**: For each downstream `mining_submit_seen` log, match `job_id`, `extranonce2`, `ntime`, `nonce`, `submit_version` (raw rolling bits from submit when present), and `version` (merged header version). Confirm `job_state_exists` and `extranonce1_exists`; if either is false, reconstruction will not run and no `candidate_reconstructed` line will appear for that submit.

3. **`candidate_reconstructed`**: For the same submit, check `blockhash`, `nbits`, `target`, `meets_target`, `version` (merged), and `submit_version`. Compare `version` to the pool / translator full header version. If the pool reported a block but `meets_target` is false here, look for stale job state, extranonce mismatch, or incorrect merge of rolling bits with the notify base version.

4. **`translator_candidate_blocks`**: Rows appear only when `TRANSLATOR_CAPTURE_DRY_RUN=false`, a repository is configured, and insert attempted. Correlate by `blockhash` / `job_id` with `candidate_insert_succeeded`; if you see `candidate_insert_failed`, inspect the `error` field in that log line and the following exception stack.

## Journal / journald (auditing)

INFO messages embed key=value pairs in the log **message** (not only in structured fields), so `journalctl` and default formatters show reconstruction details.

Examples:

```bash
sudo journalctl -u azcoin-translator-capture-proxy -f | grep -E 'event=(mining_submit_seen|candidate_reconstructed|candidate_insert_)'
```

Narrow to reconstructed submits and inserts:

```bash
sudo journalctl -u azcoin-translator-capture-proxy --since today \
  | grep -E 'event=candidate_reconstructed|event=candidate_insert_'

Match a specific winning `blockhash` and merged `version` / `submit_version`:

```bash
sudo journalctl -u azcoin-translator-capture-proxy --since today \
  | grep -E 'event=candidate_reconstructed .*blockhash=0000000000000082b60487dd794fddacffa04d8c8b34c2556133b4a2b04d9b59'
```
```

