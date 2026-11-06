# BTC Perpetual Strategy Migration Comparison

## Scope and method

- Strategies: the current EfficiencyTurnover strategy with range entries disabled as V8, plus Freqtrade adaptations of the xuyujian branch V7.1, WZY branch V7.2, and main-branch V4.5.3.
- Market and interval: BTC/USDT perpetual; 1h strategy signals, completed 4h regime candles, and Freqtrade 1m detail candles for intra-trade simulation.
- Test period: 2021-11-05 00:00 UTC through 2026-11-04 23:00 UTC.
- Starting wallet: 1,000 USDT; base stake: 100 USDT; maximum one open trade; isolated; leverage callback capped at 1x.
- Freqtrade version: 2026.10. Fee: 0.05% each side. Historical funding and mark-price candles were unavailable, so funding is configured as zero.
- 1m candles are from Binance Vision USD-M archives except 2026-10-28, which was filled with Bitget USDT perpetual 1m candles because Binance's archive was missing and its REST endpoint was unreachable from this host.
- `--timeframe-detail 1m` refines intra-trade candle simulation; it does not make the strategy generate 1m signals. This still uses OHLCV assumptions, not tick/trade-level fills.

## Results

| Strategy | Net return | Trades | Max drawdown | Win rate |
|---|---:|---:|---:|---:|
| V8, trend-only ablation | +3.51% | 12 | 0.52% | 50.0% |
| V7.1 adaptation | -0.91% | 60 | 2.05% | 35.0% |
| V7.2 adaptation | -0.70% | 69 | 1.70% | 33.3% |
| V4.5.3 adaptation | -2.52% | 200 | 4.41% | 33.0% |

## Interpretation

The V8 change follows the prior loss attribution: the range sleeve was disabled because its state-change exits were the largest identified source of losses. V8 returned +3.51%, but generated only 12 trades in five years; this sample is too small to establish a reliable edge. Treat it as an experiment, not a production candidate. The older EfficiencyTurnover baseline result used 1h-only fills and is not an apples-to-apples comparator for this 1m-detail run.

The V7.1 and V7.2 migrations preserve 4h regime filters, daily confirmation, direction confirmation, breakouts, ATR protections, and their relative short exposure (15% and 8%). Dynamic volatility, funding, drawdown and quality-based sizing cannot be fairly reproduced while holding every position to a 1x cap and equal long allocation; those controls remain incomplete. V7.2 uses the WZY branch's refined live parameter profile.

V4.5.3 inherits V4.5.2 signals and changes routine execution to maker limits. This Freqtrade version maps the long and short gates, breakout windows, and ATR protection to candle signals, but does not reproduce the parent V4.4.4 stateful sizing engine or maker queue/fill simulation. Its result is a migration comparison, not the upstream strategy's reported performance.

Historical funding and mark-price candles are absent, and the 2026-10-28 gap is filled with a different exchange's data. Slippage and maker fill probability are not modelled. The current-code 1m-detail lookahead analysis is being rerun; no statistical robustness is implied by the historical returns.

## Artifacts

- Strategies: `../strategies/BtcRegimeCompare.py`
- Existing V8 factor implementation: `../strategies/BtcTrendFactorResearch.py`
- Four-strategy 1m-detail backtest: `../backtest_results/four_strategies_1m_detail-2026-11-05_10-42-55.zip`.
- 1m market data and provenance: `../data/binance/futures/BTC_USDT_USDT-1m-futures.json` and `../data/binance/futures/btc_futures_1m_archive_summary.json`.
- Baseline reference (1h-only, different fill resolution): `../backtest_results/backtest-result-2026-11-05_08-51-26.zip`.
