authority_public_key = "9auqWEzQDVyd2oe1JVGFLMLHZtCo2FFqZwtKA5gd9xbuEu7PH72"
authority_secret_key = "mkDLTBBRxdBv998612qipDYoTK3YUrqLe8uWw7gu3iXbSrn2n"

coinbase_reward_script = "wpkh(02f9308a...bce036f9)"

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~



# AZCoin SV2 Pool Configuration

# === Security / Noise Protocol ===
# These keys are used for the secure Noise protocol handshake with SV2 miners.
# Generate a new keypair using this command: cargo run --release -p keygen --bin keygen
authority_public_key = "CHANGE_ME_PUBLIC_KEY_REPLACE_WITH_REAL_ONE"
authority_secret_key = "CHANGE_ME_SECRET_KEY_REPLACE_WITH_REAL_ONE"

# SV2 Noise certificate validity in seconds
# Controls how long the internal certificate used during handshake remains valid.
# 3600 = 1 hour (standard default). Can be increased to 86400 (24h) for lower overhead.
cert_validity_sec = 3600

# === Listener ===
# Address and port where native SV2 miners connect.
# BTC-SV1: 3333, BTC-SV2: 3334, JDP: 3335, AZCOIN-SV1: 3336, AZCOIN-SV2: 3337
listen_address = "0.0.0.0:3337"

# === Coinbase Output ===
# Coinbase payout is ALWAYS constructed by the pool using this descriptor.
# The SV2 Template Provider only supplies the block template (tx set, header data, etc.)
# and has no control over the final reward output.
#
# For AZCoin, you must use a "wpkh(...)" descriptor (with the raw pubkey in hex).
# The SRI SV2 Pool does not recognize bech32 addresses using the "addr(bc1q1...)" descriptor starting with "az1q...".
# Source new coinbase wpkh descriptor: azc getaddressinfo $(azc getnewaddress) | grep pubkey
#
# Changing this value requires a full pool restart.
coinbase_reward_script = "wpkh(02f9308a...bce036f9)"

# === Pool Identity ===
# Unique identifier for this pool instance.
# Change only if you run multiple pool instances on the same machine.
server_id = 1

# String that appears in the coinbase tag of blocks mined by this pool.
pool_signature = ""

# === Logging ===
# Enable this option to set a predefined log file path.
# When enabled, logs will always be written to this file.
log_file = "/var/log/azpool/azpool.log"

# === Difficulty / Performance ===
# Target average share submission rate per SV2 channel. In essence, it governs the pool's target/difficulty calculations per channel (per miner in non-aggregator mode).
#
# Some channels have multiple targets/difficulties (e.g. translator/proxy [vardiff enabled] between the pool and miner).
# Let's review how this setup works (miner - translator/proxy [vardiff enabled] - pool):
#   Miners submit shares to the translator that meet the target/difficulty it received from upstream (either from the translator/Proxy or pool; in this case, the translator/proxy).
#   When the translator/proxy receives shares from the miner, they are locally registered and then validated against the pool's target/difficulty where they will be either forwarded or silently dropped.
#   Note: The TARGET | DIFFICULTY | SHARES_PER_MINUTE | SHARE_WEIGHT is always HIGHER | EASIER | FASTER | SMALLER (or ALL identical) for a downstream channel compared to its upstream channel.
#         This is enforced in code and ensures no payout value is missed (payouts are always fair).
#   With regards to how the target/difficulty is changed per miner, the translator/proxy updates each miner's target/difficulty every 60 seconds based on its own shares_per_minute configuration. EACH MINER IS ALWAYS LOCALLY CONTROLLED.
#   WARNING: When the downstream shares_per_minute is configured lower (slower) than the configuration of the upstream, problems will ensue. It will work fine, but not work as intended.
#
# Recommended Value = 6.0 (Same as Translator/Proxy)
# However, with aggregator mode disabled on the translator/proxy, the pool will be hit by all miners from each SC Node. In this case, it would smart to decrease it signficantly. Recommended setting is 1.0.
shares_per_minute = 1.0

# How many shares to batch before sending acknowledgment (performance tuning).
share_batch_size = 10

# === Extensions (SV2 Protocol) ===
# supported_extensions: list of extension IDs the pool announces it supports
# required_extensions: list of extension IDs that downstreams MUST support
supported_extensions = [
    0x0000,	  # Core protocol
    0x0001,	  # Extensions Negotiation
	0x0002,   # Worker-Specific Hashrate Tracking
]
required_extensions = []

# === Monitoring ===
# Enable API endpoints on a given port
monitoring_address = "127.0.0.1:9097"
monitoring_cache_refresh_secs = 15

# === Job Declaration Server (JDS) Settings ===
# JDS is an optional component that lets miners propose their own custom block templates and transaction sets.
# It acts as a middle layer for "custom job declaration" between miners and the pool, enabling more decentralized mining and dual block propagation.
#
# Why JDS is not standalone (coupled w/ this pool):
#   - Verify coinbase outputs, enforce the pool's reward share, validate pool signatures, and correctly attribute shares for payouts.
#   - The pool needs to know about every accepted job for accounting and reward distribution.
# jd_server_address = "127.0.0.1:34264"
# jd_server_enabled = false

# === Template Provider ===
# Connection to the external local Template Provider. Uses standard RPC connection w/ AZCoin Core.
[template_provider_type.Sv2Tp]
address = "127.0.0.1:8442"
# public_key = "..." # Leave commented out for localhost connections
