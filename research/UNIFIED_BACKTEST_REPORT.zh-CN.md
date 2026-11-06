# 四策略统一 Freqtrade 回测报告

## 命令与环境

```bash
docker compose run --rm --no-deps freqtrade backtesting \
  --config user_data/config-btc-futures-15m-backtest.json \
  --strategy-path user_data/strategies \
  --strategy-list BtcTrendV10StateNoMacd BtcTrendV453 BtcTrendV71 BtcTrendV72 \
  --timerange 20211105-20261105 \
  --timeframe-detail 1m --fee 0.0005 --export trades
```

- Freqtrade `2026.10`，Binance USD-M BTC/USDT:USDT，isolated futures。
- 初始钱包 1,000 USDT，stake 100 USDT，最大一个仓位，策略杠杆限制为 1x。
- 15m 策略 K 线，1m detail K 线用于仓内模拟；单边手续费 0.05%。
- 命令指定 2021-11-05，但 1600 根 startup candles 使有效交易起点为 2021-11-21 16:00 UTC。

## 结果

| 策略 | 交易 | 净收益 | 最大回撤 | 胜率 | PF | CAGR | Sharpe | 平均持仓 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| BtcTrendV10StateNoMacd | 168 | +6.91% | 2.14% | 32.1% | 1.41 | 1.36% | 0.17 | 2d 5h |
| BtcTrendV453 | 237 | -5.73% | 6.45% | 30.8% | 0.82 | -1.18% | -0.20 | 1d 4h |
| BtcTrendV71 | 89 | +0.65% | 1.47% | 34.8% | 1.09 | 0.13% | 0.03 | 1d 4h |
| BtcTrendV72 | 110 | -0.47% | 1.45% | 36.4% | 0.94 | -0.10% | -0.02 | 19h |

原始结果位于 `backtests/four_strategy_15m_1m_result.json`，官方导出归档位于 `backtests/backtest-result-2026-11-06_10-46-21.zip`。

## 解释

V10 是当前统一口径下相对最好的候选，但其优势较薄，且交易频率约 34 笔/年。V7.1 接近持平，V7.2 和 V4.5.3 为负。这个结果不能证明 V10 有稳定 alpha，也不能用于推断上游 V4.5.3 报告；上游版本使用了不同的信号实现、动态 sizing、资金费和自研 1m execution。

数据的 funding 覆盖不完整，1m OHLCV 不包含真实订单簿排队和逐笔滑点，且 2026-10-28 使用 Bitget 替代日数据。继续优化时应使用滚动 walk-forward、保守滑点和完整资金费，避免在留出段反复选择参数。
