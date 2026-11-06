"""Freqtrade adaptations of the V8, V7.1, WZY V7.2 and V4.5.3 candidates.

The upstream research uses 4h state and 1m execution. These strategies keep
causal 4h signals and protective rules while using Freqtrade's 1h candle fills.
"""

from datetime import datetime
from typing import Any

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, merge_informative_pair
from BtcTrendFactorResearch import BtcTrendEfficiencyTurnover


class _RegimeBase:
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    startup_candle_count = 900
    minimal_roi = {}
    stoploss = -0.04
    trailing_stop = False
    use_exit_signal = True
    process_only_new_candles = True

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs):
        return min(1.0, max_leverage)

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        if side == "short" and hasattr(self, "short_scale"):
            proposed_stake *= self.short_scale
        return max(min_stake or 0.0, min(proposed_stake, max_stake))

    @staticmethod
    def _chop(frame: DataFrame, period: int) -> DataFrame:
        tr = ta.TRANGE(frame)
        span = frame["high"].rolling(period).max() - frame["low"].rolling(period).min()
        return 100 * np.log10(tr.rolling(period).sum() / span.replace(0, np.nan)) / np.log10(period)

    @staticmethod
    def _efficiency(close, period: int):
        return close.diff(period).abs() / close.diff().abs().rolling(period).sum().replace(0, np.nan)

    def _informative(self, pair: str) -> DataFrame:
        if self.dp is None:
            return DataFrame()
        frame = self.dp.get_pair_dataframe(pair=pair, timeframe="4h").copy()
        if frame.empty:
            return frame
        frame["ema20"] = ta.EMA(frame, timeperiod=20)
        frame["ema30"] = ta.EMA(frame, timeperiod=30)
        frame["ema80"] = ta.EMA(frame, timeperiod=80)
        frame["ema120"] = ta.EMA(frame, timeperiod=120)
        frame["ema200"] = ta.EMA(frame, timeperiod=200)
        frame["adx"] = ta.ADX(frame, timeperiod=14)
        frame["atr"] = ta.ATR(frame, timeperiod=20)
        frame["rsi"] = ta.RSI(frame, timeperiod=14)
        frame["chop"] = self._chop(frame, 14)
        frame["eff"] = self._efficiency(frame["close"], 12)
        frame["aroon_up"] = ta.AROON(frame, timeperiod=25)["aroonup"]
        frame["aroon_down"] = ta.AROON(frame, timeperiod=25)["aroondown"]
        frame["range_low"] = frame["close"].rolling(90).min()
        frame["range_high"] = frame["close"].rolling(90).max()
        width = (frame["range_high"] - frame["range_low"]).replace(0, np.nan)
        frame["range_pct"] = (frame["close"] - frame["range_low"]) / width
        frame["donchian_high"] = frame["high"].shift(1).rolling(18).max()
        frame["donchian_low"] = frame["low"].shift(1).rolling(18).min()
        frame["break6_high"] = frame["high"].shift(1).rolling(6).max()
        frame["break8_low"] = frame["low"].shift(1).rolling(8).min()
        frame["turnover"] = frame["close"] * frame["volume"]
        frame["turnover_rel"] = frame["turnover"] / frame["turnover"].shift().rolling(24).median()
        daily = frame.set_index("date").resample("1D").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna(subset=["close"])
        daily["ema_fast"] = ta.EMA(daily, timeperiod=10)
        daily["ema_slow"] = ta.EMA(daily, timeperiod=30)
        daily["adx"] = ta.ADX(daily, timeperiod=14)
        daily["chop"] = self._chop(daily, 14)
        daily["daily_up"] = (
            (daily["ema_fast"] > daily["ema_slow"])
            & (daily["adx"] >= 18)
            & (daily["chop"] <= 55)
        )
        daily["daily_down"] = (
            (daily["ema_fast"] < daily["ema_slow"])
            & (daily["adx"] >= 18)
            & (daily["chop"] <= 55)
        )
        daily = daily[["daily_up", "daily_down"]].shift(1)
        daily["day_key"] = daily.index
        frame["day_key"] = frame["date"].dt.floor("1D")
        frame = frame.merge(daily, how="left", on="day_key", sort=False)
        frame["daily_up"] = frame["daily_up"].fillna(False).astype(bool)
        frame["daily_down"] = frame["daily_down"].fillna(False).astype(bool)
        frame["daily_slope"] = frame["ema120"].pct_change(6)
        frame["trend_up"] = (
            frame["daily_up"]
            &
            (frame["ema30"] > frame["ema120"])
            & (frame["ema30"] - frame["ema120"] >= 0.12 * frame["atr"])
            & (frame["adx"] >= 27)
            & (frame["chop"] <= 40)
            & (frame["aroon_up"] >= 70)
            & (frame["aroon_up"] - frame["aroon_down"] >= 15)
            & (frame["eff"] >= 0.20)
        )
        frame["trend_down"] = (
            frame["daily_down"]
            &
            (frame["ema30"] < frame["ema120"])
            & (frame["ema120"] - frame["ema30"] >= 0.12 * frame["atr"])
            & (frame["adx"] >= 27)
            & (frame["chop"] <= 40)
            & (frame["aroon_down"] >= 70)
            & (frame["aroon_down"] - frame["aroon_up"] >= 15)
            & (frame["eff"] >= 0.20)
        )
        frame["range_regime"] = (frame["chop"] >= 60) & (frame["eff"] <= 0.08)
        # Two completed 4h candles confirm a newly classified trend.
        frame["up_confirmed"] = frame["trend_up"].rolling(2).sum() >= 2
        frame["down_confirmed"] = frame["trend_down"].rolling(2).sum() >= 2
        frame["range_long"] = frame["range_regime"] & (frame["range_pct"] <= 0.08)
        return frame

    def _merge(self, dataframe: DataFrame, pair: str) -> DataFrame:
        informative = self._informative(pair)
        if informative.empty:
            return dataframe
        cols = [c for c in informative.columns if c != "date"]
        return merge_informative_pair(
            dataframe, informative[["date", *cols]], self.timeframe, "4h", ffill=True
        )

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["macdhist"] = ta.MACD(dataframe)["macdhist"]
        dataframe["bb_upper"] = ta.BBANDS(dataframe, timeperiod=20)["upperband"]
        dataframe["bb_lower"] = ta.BBANDS(dataframe, timeperiod=20)["lowerband"]
        return self._merge(dataframe, metadata["pair"])

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        if "ema30_4h" in dataframe:
            dataframe.loc[
                (dataframe["ema30_4h"] < dataframe["ema120_4h"])
                & (dataframe["daily_slope_4h"] < 0),
                "exit_long",
            ] = 1
            dataframe.loc[
                (dataframe["ema30_4h"] > dataframe["ema120_4h"])
                & (dataframe["daily_slope_4h"] > 0),
                "exit_short",
            ] = 1
        return dataframe

    def custom_exit(self, pair: str, trade: Any, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        candle = dataframe.iloc[-1]
        tag = trade.enter_tag or ""
        age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600
        atr = candle.get("atr_4h", np.nan)
        if tag == "range":
            # Keep range trades through weak regime flicker; exit on target,
            # confirmed breakout, hard loss, or the original maximum holding time.
            confirmed_breakout = bool(
                candle.get("breakout_confirm_4h", False)
                and candle.get("adx_4h", 0) >= 27
                and candle.get("eff_4h", 0) >= 0.20
            )
            if current_rate >= candle.get("bb_upper", np.inf):
                return "range_target"
            if confirmed_breakout:
                return "range_breakout_confirmed"
            if current_profit <= -0.025:
                return "range_protective_stop"
            if age_hours >= 18:
                return "range_timeout"
            return None
        if not np.isfinite(atr) or atr <= 0:
            return None
        if tag.startswith("v453"):
            direction = -1 if trade.is_short else 1
            adverse = (trade.open_rate - current_rate) * direction
            favorable = (trade.max_rate - trade.open_rate) if direction > 0 else (trade.open_rate - trade.min_rate)
            stop_atr, trail_atr, take_atr, hold_bars = (
                (1.25, 1.75, 2.5, 24) if trade.is_short else (1.5, 3.0, np.inf, 72)
            )
            if adverse >= stop_atr * atr:
                return "v453_atr_stop"
            if (direction > 0 and current_rate <= trade.max_rate - trail_atr * atr) or (
                direction < 0 and current_rate >= trade.min_rate + trail_atr * atr
            ):
                return "v453_trailing_stop"
            if favorable >= take_atr * atr and age_hours > 1:
                return "v453_take_profit"
            if age_hours >= hold_bars:
                return "v453_max_hold"
            if trade.is_short and candle["ema30_4h"] >= candle["ema120_4h"]:
                return "v453_short_trend_reversal"
        elif tag.startswith("v71") or tag.startswith("v72"):
            trail = 2.0 if tag.startswith("v71") else 1.65
            if not trade.is_short and candle["down_confirmed_4h"]:
                return "trend_reversal_confirmed"
            if trade.is_short and candle["up_confirmed_4h"]:
                return "trend_reversal_confirmed"
            if not trade.is_short and current_rate <= trade.max_rate - trail * atr:
                return "trend_atr_trail"
            if trade.is_short and current_rate >= trade.min_rate + trail * atr:
                return "trend_atr_trail"
            if age_hours >= 96:
                return "trend_max_hold"
        return None


class BtcTrendV8(BtcTrendEfficiencyTurnover):
    """Existing efficiency/turnover trend sleeve after range-leg ablation."""

    enable_range_entries = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        if not self.enable_range_entries and "enter_tag" in dataframe:
            is_range = dataframe["enter_tag"].eq("range")
            dataframe.loc[is_range, "enter_long"] = 0
            dataframe.loc[is_range, "enter_tag"] = None
        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if self.dp is None:
            return None
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        candle = dataframe.iloc[-1]
        if trade.enter_tag == "range":
            age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600
            confirmed_breakout = (
                not bool(candle["regime_range"])
                and candle["adx14_4h"] >= 27
                and candle["efficiency24"] >= 0.25
            )
            if current_rate >= candle["bb_upper"]:
                return "range_upper_band"
            if confirmed_breakout:
                return "range_breakout_confirmed"
            if current_profit <= -0.025:
                return "range_protective_stop"
            if age_hours >= 18:
                return "range_timeout"
            return None
        return super().custom_exit(
            pair, trade, current_time, current_rate, current_profit, **kwargs
        )


class _V7Adaptation(_RegimeBase):
    short_scale = 0.15
    trend_trail_atr = 2.0
    breakout_buffer_atr = 0.2

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        up = dataframe["up_confirmed_4h"] & (
            (
                (dataframe["close"] > dataframe["ema20"])
                & (dataframe["close"].shift() <= dataframe["ema20"].shift())
            )
            | (
                (dataframe["close"] > dataframe["donchian_high_4h"] + self.breakout_buffer_atr * dataframe["atr_4h"])
                & (dataframe["close"].shift() <= dataframe["donchian_high_4h"].shift())
            )
        )
        down = dataframe["down_confirmed_4h"] & (
            (
                (dataframe["close"] < dataframe["ema20"])
                & (dataframe["close"].shift() >= dataframe["ema20"].shift())
            )
            | (
                (dataframe["close"] < dataframe["donchian_low_4h"] - self.breakout_buffer_atr * dataframe["atr_4h"])
                & (dataframe["close"].shift() >= dataframe["donchian_low_4h"].shift())
            )
        )
        range_entry = dataframe["range_long_4h"] & (dataframe["rsi_4h"] <= 28)
        dataframe.loc[up & (dataframe["volume"] > 0), ["enter_long", "enter_tag"]] = (1, self.version_tag)
        dataframe.loc[down & (dataframe["volume"] > 0), ["enter_short", "enter_tag"]] = (1, self.version_tag + "_short")
        dataframe.loc[range_entry & (dataframe["volume"] > 0), ["enter_long", "enter_tag"]] = (1, "range")
        dataframe["breakout_confirm_4h"] = (
            dataframe["close"] > dataframe["donchian_high_4h"]
        ) | (dataframe["close"] < dataframe["donchian_low_4h"])
        return dataframe


class BtcTrendV71(_V7Adaptation, IStrategy):
    """V7.1 regime and risk controls adapted to Freqtrade candle execution."""
    version_tag = "v71"
    short_scale = 0.15
    trend_trail_atr = 2.0
    breakout_buffer_atr = 0.2


class BtcTrendV72(_V7Adaptation, IStrategy):
    """WZY V7.2 profile with its reduced short allocation and live protections."""
    version_tag = "v72"
    short_scale = 0.08
    trend_trail_atr = 1.65
    breakout_buffer_atr = 0.22


class BtcTrendV453(_RegimeBase, IStrategy):
    """V4.5.3 signal adaptation; maker-only fills are unavailable in OHLCV tests."""

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        long_break = (dataframe["close"] > dataframe["break6_high_4h"]) & (
            dataframe["close"].shift() <= dataframe["break6_high_4h"].shift()
        )
        long_trend = (
            (dataframe["ema20_4h"] > dataframe["ema80_4h"])
            & (dataframe["adx_4h"] >= 24)
            & (dataframe["close"] > dataframe["ema20"])
            & (dataframe["macdhist"] > 0)
            & long_break
            & (dataframe["volume"] > 0)
        )
        short_entry = (
            (dataframe["ema30_4h"] < dataframe["ema120_4h"])
            & (dataframe["daily_slope_4h"] < 0)
            & (dataframe["adx_4h"] >= 32)
            & (dataframe["close"] < dataframe["break8_low_4h"])
            & (dataframe["close"].shift() >= dataframe["break8_low_4h"].shift())
            & (dataframe["turnover_rel_4h"] >= 1.1)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[long_trend, ["enter_long", "enter_tag"]] = (1, "v453_long")
        dataframe.loc[short_entry, ["enter_short", "enter_tag"]] = (1, "v453_short")
        dataframe["breakout_confirm_4h"] = (
            (dataframe["close"] > dataframe["donchian_high_4h"])
            | (dataframe["close"] < dataframe["donchian_low_4h"])
        )
        return dataframe
