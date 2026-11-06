#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$repo_root/data/binance/futures"
gunzip -kf "$repo_root"/data/binance/futures/*.json.gz

docker run --rm \
  -v "$repo_root:/workspace" \
  freqtradeorg/freqtrade:stable \
  backtesting \
  --config /workspace/config/btc-usdt-futures-15m.json \
  --strategy-path /workspace/strategies \
  --strategy-list BtcTrendV10Optimized BtcTrendV453 BtcTrendV71 BtcTrendV72 \
  --timerange 20211105-20261105 \
  --timeframe-detail 1m \
  --fee 0.0005 \
  --export trades \
  --backtest-directory /workspace/backtests/generated
