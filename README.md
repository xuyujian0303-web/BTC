# BTC Freqtrade Research Bundle

这是 BTC/USDT USD-M 永续的 Freqtrade 研究仓库，包含一个冻结的 V10 趋势候选和三个迁移版本 V4.5.3、V7.1、V7.2。仓库用于复现、比较和继续研究，不是实盘收益承诺。

## 当前比较结果

四个策略使用同一条官方 Freqtrade 回测命令和同一份数据：15m 策略信号、1m detail 撮合、Binance USD-M BTC/USDT、isolated、1x、1,000 USDT 初始资金、100 USDT stake、最多一个持仓、每边 0.05% 手续费。

有效回测区间为 `2021-11-21 16:00 UTC` 至 `2026-11-05 00:00 UTC`。由于 15m 策略的 1600 根 startup candles，实际起点晚于命令指定的 `20211105`。

| 策略 | 交易数 | 净收益 | 最大回撤 | 胜率 | Profit Factor | 平均持仓 |
|---|---:|---:|---:|---:|---:|---|
| `BtcTrendV10Optimized`（等价于 `BtcTrendV10StateNoMacd`） | 168 | +6.91% | 2.14% | 32.1% | 1.41 | 2天5小时 |
| `BtcTrendV71` | 89 | +0.65% | 1.47% | 34.8% | 1.09 | 1天4小时 |
| `BtcTrendV72` | 110 | -0.47% | 1.45% | 36.4% | 0.94 | 19小时 |
| `BtcTrendV453` | 237 | -5.73% | 6.45% | 30.8% | 0.82 | 1天4小时 |

这些是同一 15m 配置下的迁移比较，不应与上游仓库的自研 micro-backtest 结果直接比较。V4.5.3、V7.1、V7.2 在这里是 Freqtrade 适配版本；它们不复现上游的动态杠杆、风险预算、资金费和真实 Maker 队列。

## 目录

- `strategies/`：Freqtrade 策略文件。`BtcTrendV10Optimized.py` 是冻结的最佳候选；其基础信号实现位于 `BtcTrendIntradayExperiments.py`。四版本比较类位于 `BtcRegimeCompare.py`。
- `config/`：统一的 BTC 永续 15m 回测配置，无 API 密钥。
- `backtests/`：官方 Freqtrade 导出的结果 ZIP、JSON 结果和实际配置。
- `data/binance/futures/`：压缩后的 1m、15m、1h、4h 行情和来源摘要。`data/SHA256SUMS` 用于校验文件。
- `research/`：参数筛选、V10 实验和历史版本比较报告。
- `AGENTS.md`：后续自动化代理和贡献者必须遵守的回测、数据和安全约定。

## 复现

从仓库根目录运行：

```bash
mkdir -p user_data/data/binance/futures
gunzip -k data/binance/futures/*.json.gz
docker run --rm -v "$PWD:/workspace" freqtradeorg/freqtrade:stable \
  backtesting \
  --config /workspace/config/btc-usdt-futures-15m.json \
  --strategy-path /workspace/strategies \
  --strategy-list BtcTrendV10Optimized BtcTrendV453 BtcTrendV71 BtcTrendV72 \
  --timerange 20211105-20261105 \
  --timeframe-detail 1m \
  --fee 0.0005 \
  --export trades \
  --backtest-directory /workspace/backtests/generated
```

如果使用本机已有的 Docker Compose Freqtrade，也可以把 `config/`、`strategies/` 和 `data/` 映射到容器的 `/freqtrade/user_data` 后执行同样的 `backtesting` 子命令。回测结果会因 Freqtrade 版本、数据文件、资金费率和交易撮合假设变化而变化。

## 数据说明

行情来自 Binance Vision USD-M futures kline archives。1m 数据覆盖 `2021-11-05` 至 `2026-11-04 23:59 UTC`；官方 Binance Vision 缺少 `2026-10-28`，该日 1m 数据使用 Bitget USDT perpetual 历史 K 线替代。1h/4h 摘要中另记录了 2026-10-28 的缺口信息。

本回测使用了 1m detail OHLCV，而不是逐笔成交或订单簿。历史 funding rate 文件只覆盖较晚时期，配置中的 `futures_funding_rate` 为 0；因此早期合约资金费未完整计入。策略结果应视为研究性估计。

## V10 参数选择

V10 采用 15m 价格处于 EMA20 上方的状态触发，4h EMA50/EMA200 结构、EMA200 24h 正斜率、ADX >= 20，1h 收盘价和 EMA20/EMA50 同向确认；移除与其他价格趋势条件重复的 MACD 和活动过滤；使用 -4% 硬止损，并在 4h 趋势失效或 1h EMA20 下破 EMA50 时退出。参数先在训练段筛选，再固定到验证和留出段；没有根据留出段继续调参。

V10 的五年收益为正但年均约 34 笔，仍低于此前设定的 100 笔/年中频目标，且单一 BTC 样本的统计证据有限。部署前应补齐 funding、滑点和独立前向数据，并先做 dry-run。
