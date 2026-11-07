#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$repo_root/backtests/exact-full-1h"

docker run --rm \
  -v "$repo_root:/workspace" \
  -w /workspace \
  freqtradeorg/freqtrade:stable \
  backtesting \
  --config /workspace/config/btc-usdt-futures-1h-exact-1x.json \
  --datadir /workspace/data/binance \
  --strategy-path /workspace/strategies \
  --strategy-list V453FreqtradeExact1x V71FreqtradeExact1x V72FreqtradeExact1x \
  --timerange 20211105-20261105 \
  --export trades \
  --backtest-directory /workspace/backtests/exact-full-1h
