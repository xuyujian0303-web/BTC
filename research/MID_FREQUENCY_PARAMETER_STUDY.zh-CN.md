# BTC 中频参数与策略筛选（二）

## 结论

本轮没有找到同时满足年 100–1,000 笔和稳定正收益的版本。4h regime 放宽和固定止盈能把交易频率推到目标边缘，但验证/留出结果转弱或为负。当前研究里风险收益较平衡的候选仍是 `BtcTrendV10StateNoMacd`：五年 168 笔（约 34 笔/年），训练、验证、留出均为正，但样本外收益薄且频率低。它不是中频最终版。

新实验策略均在 `../strategies/BtcTrendIntradayExperiments.py`，专用回测配置为 `../config-btc-futures-15m-backtest.json`。未切换当前运行 bot。

## 口径

Freqtrade 2026.10 官方 backtesting；BTC/USDT Binance USD-M 永续，15m 信号、1m detail；1x isolated，1,000 USDT 初始钱包、100 USDT stake、最多一笔同时持仓，每边手续费 0.05%。回测有效训练期约 2021-11-21 至 2024-11-05，验证 2024-11-05 至 2025-11-05，留出 2025-11-05 至 2026-11-05。Startup candle 使训练起点比 timerange 晚约 16 天。

资金费率只有从 2025-07 才有部分历史，早期永久合约费用未准确反映；没有加额外滑点。15m 行情是 Binance 官方下载数据，1m 包中的 2026-10-28 单日由先前数据准备记录标记为 Bitget 替代数据。完整数据摘要见 `../data/binance/futures/btc_futures_1m_archive_summary.json` 和 `btc_futures_archive_summary.json`。

## 训练段筛选

所有变体都做多，15m 收盘价在 EMA20 上方作为状态触发；保留 1h close > EMA50、EMA20 > EMA50，并移除 1h MACD（同一入场方向确认的弱去重项）；止损 -4%，趋势退出不变。原有活动过滤（24h效率/成交额）已移除。

| 变体 | 4h regime 变化 | 训练笔数 | 收益 | 最大回撤 | 胜率 | PF |
|---|---|---:|---:|---:|---:|---:|
| V10 状态基线 | EMA50>EMA200、斜率>0、ADX≥20 | 100 | +4.82% | 1.85% | 34.0% | 1.45 |
| V11 ADX15 | EMA50>EMA200、斜率>0、ADX≥15 | 111 | +3.50% | 2.35% | 30.6% | 1.26 |
| V11 ADX15，无斜率 | EMA50>EMA200、ADX≥15 | 113 | +4.37% | 2.45% | 30.1% | 1.32 |
| V12 Price200+Slope | close>EMA200、斜率>0、ADX≥15 | 125 | +3.77% | 2.43% | 30.4% | 1.24 |
| V12 Price200 | close>EMA200，无斜率、无ADX | 152 | +5.42% | 2.25% | 28.9% | 1.33 |
| V12 EMA order | EMA50>EMA200，无斜率、无ADX | 118 | +4.94% | 2.15% | 29.7% | 1.37 |

简化 1h 对齐（仍要求 1h close>EMA50）没有增加交易或改变结果：V12 price-only-1h 的训练、验证、留出与 V12 Price200 相同。完全取消 1h 确认也没有改变 V12 Price200 的信号与结果，因此不计作有效改进。

## 样本外与频率实验

V12 Price200 即 4h close>EMA200、无 4h ADX/斜率过滤，保留已有 1h 趋势确认。

| 规则 | 区间 | 笔数 | 年化约笔数 | 收益 | 最大回撤 | PF |
|---|---|---:|---:|---:|---:|---:|
| V12 Price200 | 训练约 2.95 年 | 152 | 51 | +5.42% | 2.25% | 1.33 |
| V12 Price200 | 验证 1 年 | 73 | 73 | +0.27% | 3.28% | 1.04 |
| V12 Price200 | 留出 1 年 | 53 | 53 | +0.22% | 1.45% | 1.05 |
| V14 固定 ROI 2% | 训练约 2.95 年 | 383 | 130 | +3.74% | 2.94% | 1.10 |
| V14 固定 ROI 2% | 验证 | 139 | 139 | -0.55% | 3.67% | 0.96 |
| V14 固定 ROI 2% | 留出 | 98 | 98 | -0.48% | 1.67% | 0.95 |
| V14 固定 ROI 3% | 训练约 2.95 年 | 296 | 100 | +4.09% | 2.72% | 1.12 |
| V14 固定 ROI 3% | 验证 | 112 | 112 | -0.09% | 3.21% | 0.99 |
| V14 固定 ROI 3% | 留出 | 77 | 77 | -0.43% | 1.66% | 0.94 |
| V15 止损 3% | 训练约 2.95 年 | 156 | 53 | +4.75% | 2.42% | 1.28 |
| V15 止损 2% | 训练约 2.95 年 | 166 | 56 | +4.36% | 2.74% | 1.25 |

固定止盈能把策略推到目标交易频率下限附近，但两个样本外阶段都是负收益。这说明单靠把退出目标设小以增加周转并不合理。止损 2%/3% 在训练段也劣于 4% 基线，尚无理由投入验证段。

## 建议

没有达标策略时，不应为了数字而宣称已完成中频策略。下一轮应重构入场/再入场：把每次趋势腿拆为有限次数的回踩入场，加入 ATR 风险单位和趋势破坏退出，设置退出后的冷却期；随后按固定滚动窗口评估收益、回撤、PF、胜率和笔数，至少要求多个 OOS 窗口为正，并显式加入资金费率和保守滑点。若仍只交易 BTC，100 笔/年对应平均每 3.65 天一笔，当前慢周期过滤器本身已经接近限制。

## 产物

- 训练 regime 比较：`../backtest_results/backtest-result-2026-11-06_06-21-50.zip`、`backtest-result-2026-11-06_06-24-44.zip`
- V12 验证：`backtest-result-2026-11-06_06-31-07.zip`
- V12 留出：`backtest-result-2026-11-06_06-34-48.zip`
- 固定 ROI 训练 / 验证 / 留出：`backtest-result-2026-11-06_06-37-*.zip`、`backtest-result-2026-11-06_06-40-*.zip`、`backtest-result-2026-11-06_06-43-*.zip`
- 收紧止损训练：`../backtest_results/backtest-result-2026-11-06_06-47-08.zip`

复现示例：

```sh
docker compose run --rm --no-deps freqtrade backtesting \
  --config user_data/config-btc-futures-15m-backtest.json \
  --strategy-path user_data/strategies \
  --strategy BtcTrendV12Price200 BtcTrendV14Target2 BtcTrendV14Target3 \
  --timerange 20211105-20241105 \
  --timeframe-detail 1m --fee 0.0005 --export trades
```
