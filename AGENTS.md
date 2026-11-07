# Agent Instructions

## Scope

This repository contains Freqtrade strategies and reproducible research
artifacts for BTC/USDT USD-M perpetual futures. Keep strategy code compatible
with Freqtrade strategy interface version 3.

## Required backtest conventions

- Use the checked-in config in `config/btc-usdt-futures-15m.json`.
- Use Binance USD-M BTC/USDT:USDT, isolated margin, one open trade, 1x
  leverage, 1,000 USDT starting wallet, 100 USDT stake, and 0.05% per-side
  fee unless a report explicitly says otherwise.
- Use `15m` strategy candles and `1m` detail candles for the comparison.
- Record the exact Freqtrade version, timerange, data source, and any missing
  data or funding-rate limitations in every new report.
- Do not call a migration an upstream strategy reproduction unless its signal,
  sizing, funding, and execution model have been reproduced.

## Original-signal migration conventions

- `strategies/BtcOriginalFreqtrade.py` contains the 1x bridges for the original
  V4.5.3, V7.1 and WZY V7.2 engines. Keep the vendored source under
  `src/btc_regime/` in sync with the recorded parameter files in `config/`.
- The bridge contract is `target = clip(original_signal, -1, 1)` and
  `leverage() == 1.0`. Do not describe native Freqtrade OHLC results as
  identical to maker-queue or order-book simulations.
- Validate signal contract changes with
  `scripts/validate_original_migrations.py` before changing backtest results.
- The exact migration configuration is
  `config/btc-usdt-futures-1h-exact-1x.json`; its complete-history command
  uses the checked-in 1h data and no `--timeframe-detail` by default.

## Research discipline

- Select parameters on the training period, then report validation and holdout
  periods without retuning them.
- Preserve raw trades and the command used to create them.
- Treat one-asset historical results as research evidence, not a live-trading
  guarantee. Include fee, slippage, funding, and data-quality limitations.
- Do not commit API keys, exchange secrets, Docker credentials, or private
  account data.

## Data and artifacts

Compressed public-market data may be stored under `data/`; large source files
should be accompanied by a provenance manifest and download instructions.
Backtest archives belong under `backtests/`. Keep generated caches and Python
`__pycache__` directories out of commits.
