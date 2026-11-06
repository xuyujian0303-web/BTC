# 15m 趋势入场与退出实验

## 当前判断

值得继续研究的方向是：将 1h 的 V9 趋势侧触发下沉到 15m，同时用 1h 和 4h 过滤方向；保留较慢的趋势退出。它比 1h V9 增加了交易数，但仍远未达到每年 100–1,000 笔的目标，且收益提升不稳定。当前最佳研究候选为 `BtcTrendV10StateNoMacd`，暂不替换运行中的 bot。

策略定义：`../strategies/BtcTrendIntradayExperiments.py`。

## 规则

- 15m：做多触发为收盘价高于 EMA20；保留 EMA20 > EMA50 和过去 24h 动量为正。
- 1h：收盘价高于 EMA50，EMA20 > EMA50；比较版可要求 MACD 柱为正。
- 4h：EMA50 > EMA200、EMA200 过去 24h 斜率为正、ADX14 ≥ 20。
- 可比较的效率/成交额门槛为 24h 效率 ≥ 0.15、相对成交额 ≥ 1.0；移除后交易明显增多，净收益未明显变差，故最终状态版不使用这两个过滤器。
- 基线退出为 1h EMA20 下穿 EMA50，或 4h 多头 regime 失效；止损 -4%。测试的 15m EMA20 快速退出导致训练段严重亏损，已拒绝。

## 回测口径与限制

Freqtrade 2026.10 官方 backtesting，Binance BTC/USDT 永续，15m 信号、1m detail，1x isolated，1000 USDT 初始钱包、100 USDT stake、最多 1 个仓位，每边手续费 0.05%。1m 细节用于仓内撮合。15m 行情通过 Freqtrade `download-data` 下载，约覆盖 2021-11-05 至 2026-11-05；15m 缺失日由 Binance Vision 回退到官方 REST 下载。

历史资金费率文件只从 2025-07-21 开始有数据，2021 至 2025-07 大段缺失，故这段合约回测没有准确计入资金费率。日志显示 1h informative 数据有约 2.55% 缺口被 Freqtrade 自动补齐；而本地归档审计摘要称 1h 总体只有一个缺口。两者口径不一致，需要在把候选用于决策前核实 informative 数据实际加载情况。以下收益是研究性模拟，不含完整历史资金费率和滑点。

训练段 2021-11-21 至 2024-11-05（因 1600 根 15m startup candles 前移约 16 天）；验证段 2024-11-05 至 2025-11-05；留出段 2025-11-05 至 2026-11-05。完整段五年计时器范围的有效交易区间从 2021-11-21 开始至 2026-11-05。

## 对照结果

| 规则 | 区间 | 交易 | 净收益 | 最大回撤 | 胜率 | PF |
|---|---|---:|---:|---:|---:|---:|
| V9 1h EMA20 状态，只做多 | 五年既有回测 | 115 | +9.07% | 1.61% | 34.8% | 1.72 |
| 15m 收复 EMA20，保留活动过滤 | 训练 | 22 | +4.50% | 0.80% | 50.0% | 3.42 |
| 同上 | 验证 | 11 | +0.27% | 0.67% | 36.4% | 1.23 |
| 同上 | 留出 | 24 | -0.06% | 1.09% | 20.8% | 见回测归档 |
| 15m 状态触发，移除活动过滤，保留 1h MACD | 训练 | 94 | +4.49% | 1.82% | 33.0% | 1.43 |
| 同上 | 验证 | 43 | +1.34% | 1.73% | 30.2% | 见回测归档 |
| 同上 | 留出 | 24 | +0.73% | 0.88% | 29.2% | 见回测归档 |
| 同上 | 五年 | 161 | +6.56% | 2.13% | 31.7% | 1.40 |
| 15m 状态触发，移除活动过滤和 1h MACD | 训练 | 100 | +4.82% | 1.85% | 34.0% | 见回测归档 |
| 同上 | 验证 | 44 | +1.18% | 1.90% | 29.5% | 见回测归档 |
| 同上 | 留出 | 24 | +0.91% | 0.69% | 29.2% | 见回测归档 |
| 同上 | 五年 | 168 | +6.91% | 2.14% | 32.1% | 1.41 |
| 15m 状态触发，收盘跌破 EMA20 即退出 | 训练 | 660 | -4.79% | 5.15% | 20.8% | 见回测归档 |

V10 的 168 笔 / 五年约 34 笔/年，仍低于年 100 笔下限。移除 MACD 仅增加 7 笔、五年收益增加 0.35 个百分点，样本外每段结果并不一致，不能视为已证实提升。更快退出将频率提高到约 220 笔/年，但净收益转负且回撤扩大，说明单纯缩短持仓会引入大量噪声。

## 后续

不要继续在同一 BTC 留出期反复调参。下一步先修复并核对 1h/4h informative 行情及历史 funding 覆盖；之后在滚动 walk-forward 中研究波动率/ATR 自适应退出与冷却/重新入场约束。若仍要求年 100–1,000 笔，需要将信号的再入场规则与退出规则作为一组优化，而非只放宽入场因子。

## 回测归档

- 15m 数据初版训练触发比较：`../backtest_results/backtest-result-2026-11-06_04-17-25.zip`
- 移除活动过滤训练：`../backtest_results/backtest-result-2026-11-06_04-20-29.zip`
- EMA20 状态无活动过滤训练：`../backtest_results/backtest-result-2026-11-06_04-21-25.zip`
- 活动过滤移除的验证：`../backtest_results/backtest-result-2026-11-06_04-22-13.zip`
- 活动过滤移除的留出：`../backtest_results/backtest-result-2026-11-06_04-22-58.zip`
- 快速退出训练（否决）：`../backtest_results/backtest-result-2026-11-06_04-24-31.zip`
- 去 MACD 训练 / 验证 / 留出：`../backtest_results/backtest-result-2026-11-06_04-25-40.zip`、`../backtest_results/backtest-result-2026-11-06_04-26-07.zip`、`../backtest_results/backtest-result-2026-11-06_04-26-50.zip`
- 五年正式对照：`../backtest_results/backtest-result-2026-11-06_04-28-01.zip`

复现五年 V10 状态规则：

```sh
docker compose run --rm --no-deps freqtrade backtesting \
  --config user_data/config-btc-futures-15m-backtest.json \
  --strategy-path user_data/strategies \
  --strategy BtcTrendV10StateNoActivity BtcTrendV10StateNoMacd \
  --timerange 20211105-20261105 \
  --timeframe-detail 1m --fee 0.0005 --export trades
```
