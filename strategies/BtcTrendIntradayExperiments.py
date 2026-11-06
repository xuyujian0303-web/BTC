"""15m BTC trend-entry experiments with 1h and 4h confirmation."""

from datetime import datetime
from typing import Any

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, merge_informative_pair


class _BtcTrend15mBase(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = False
    startup_candle_count = 1600
    minimal_roi = {}
    stoploss = -0.04
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    process_only_new_candles = True
    trigger = "reclaim"
    efficiency_min = 0.15
    turnover_relative_min = 1.0
    use_activity_filters = True
    use_macd_confirmation = True
    adx_min = 20.0
    require_4h_slope = True
    require_1h_alignment = True
    require_1h_confirmation = True
    regime_mode = "ema_order"
    fast_exit = False
    use_custom_stoploss = False
    conditional_atr_stop = False
    conditional_stop_require_macd = False
    initial_atr_multiple = 2.0
    trailing_atr_multiple = 3.0
    trail_activation_profit = 0.015
    exit_on_1h_reversal = True

    def informative_pairs(self) -> list[tuple[str, str]]:
        if self.dp is None:
            return []
        return [(pair, timeframe) for pair in self.dp.current_whitelist() for timeframe in ("1h", "4h")]

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> float:
        return min(1.0, max_leverage)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict[str, Any]) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["turnover"] = dataframe["close"] * dataframe["volume"]
        dataframe["turnover_relative24"] = dataframe["turnover"] / dataframe["turnover"].rolling(96).mean()
        path = dataframe["close"].diff().abs().rolling(96).sum()
        dataframe["efficiency24"] = dataframe["close"].diff(96).abs() / path.replace(0, np.nan)
        dataframe["momentum24"] = dataframe["close"].pct_change(96)

        if self.dp is None:
            return dataframe

        one = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe="1h").copy()
        one["ema20"] = ta.EMA(one, timeperiod=20)
        one["ema50"] = ta.EMA(one, timeperiod=50)
        one["macd_hist"] = ta.MACD(one, fastperiod=12, slowperiod=26, signalperiod=9)["macdhist"]
        dataframe = merge_informative_pair(
            dataframe, one[["date", "close", "ema20", "ema50", "macd_hist"]], self.timeframe, "1h", ffill=True
        )

        four = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe="4h").copy()
        four["ema50"] = ta.EMA(four, timeperiod=50)
        four["ema200"] = ta.EMA(four, timeperiod=200)
        four["ema200_slope24h"] = four["ema200"].pct_change(6)
        four["adx14"] = ta.ADX(four, timeperiod=14)
        dataframe = merge_informative_pair(
            dataframe,
            four[["date", "close", "ema50", "ema200", "ema200_slope24h", "adx14"]],
            self.timeframe,
            "4h",
            ffill=True,
        )
        slope_ok = (dataframe["ema200_slope24h_4h"] > 0) if self.require_4h_slope else True
        if self.regime_mode == "price_ema200":
            regime_base = dataframe["close_4h"] > dataframe["ema200_4h"]
        else:
            regime_base = dataframe["ema50_4h"] > dataframe["ema200_4h"]
        adx_ok = (dataframe["adx14_4h"] >= self.adx_min) if self.adx_min is not None else True
        slope_ok = (dataframe["ema200_slope24h_4h"] > 0) if self.require_4h_slope else True
        dataframe["trend_4h_up"] = regime_base & slope_ok & adx_ok
        macd_ok = (dataframe["macd_hist_1h"] > 0) if self.use_macd_confirmation else True
        ema_alignment_ok = (dataframe["ema20_1h"] > dataframe["ema50_1h"]) if self.require_1h_alignment else True
        dataframe["trend_1h_up"] = (
            (dataframe["close_1h"] > dataframe["ema50_1h"])
            & ema_alignment_ok
            & macd_ok
        ) if self.require_1h_confirmation else True
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict[str, Any]) -> DataFrame:
        reclaim = (dataframe["close"] > dataframe["ema20"]) & (
            dataframe["close"].shift(1) <= dataframe["ema20"].shift(1)
        )
        state = dataframe["close"] > dataframe["ema20"]
        prior_high = dataframe["high"].shift(1).rolling(16).max()
        breakout = dataframe["close"] > prior_high
        trigger = reclaim if self.trigger == "reclaim" else breakout if self.trigger == "breakout" else state
        quality_filter = (
            (dataframe["efficiency24"] >= self.efficiency_min)
            & (dataframe["turnover_relative24"] >= self.turnover_relative_min)
        ) if self.use_activity_filters else True
        enter = (
            dataframe["trend_4h_up"]
            & dataframe["trend_1h_up"]
            & (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["momentum24"] > 0)
            & quality_filter
            & (dataframe["volume"] > 0)
            & trigger
        )
        dataframe["enter_long"] = enter.astype(int)
        dataframe["enter_short"] = 0
        dataframe.loc[enter, "enter_tag"] = self.trigger
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict[str, Any]) -> DataFrame:
        if self.fast_exit:
            exit_signal = (dataframe["close"] < dataframe["ema20"]) | ~dataframe["trend_4h_up"]
        else:
            exit_signal = ~dataframe["trend_4h_up"]
            if self.exit_on_1h_reversal:
                exit_signal |= dataframe["ema20_1h"] < dataframe["ema50_1h"]
        dataframe["exit_long"] = exit_signal.astype(int)
        dataframe["exit_short"] = 0
        dataframe.loc[exit_signal, "exit_tag"] = "trend_reversal"
        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs: Any,
    ) -> float | None:
        if not self.use_custom_stoploss or self.dp is None:
            return None
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        dates = dataframe["date"]
        entry_idx = dates.searchsorted(trade.open_date_utc, side="right") - 1
        current_idx = dates.searchsorted(current_time, side="right") - 1
        if entry_idx < 0 or current_idx < 0:
            return None

        entry_atr = float(dataframe.iloc[entry_idx]["atr14"])
        current_atr = float(dataframe.iloc[current_idx]["atr14"])
        if not np.isfinite(entry_atr) or entry_atr <= 0:
            return None

        initial_stop = trade.open_rate - entry_atr * self.initial_atr_multiple
        stop_price = initial_stop
        if (
            self.trailing_atr_multiple > 0
            and trade.max_rate >= trade.open_rate * (1 + self.trail_activation_profit)
            and np.isfinite(current_atr)
            and current_atr > 0
        ):
            trailing_stop = trade.max_rate - current_atr * self.trailing_atr_multiple
            stop_price = max(stop_price, trailing_stop)

        stop_price = max(stop_price, trade.open_rate * (1 + self.stoploss))
        return min(-0.0001, stop_price / current_rate - 1)

    def custom_exit(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs: Any,
    ) -> str | None:
        if not self.conditional_atr_stop or self.dp is None:
            return None
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        dates = dataframe["date"]
        entry_idx = dates.searchsorted(trade.open_date_utc, side="right") - 1
        current_idx = dates.searchsorted(current_time, side="right") - 1
        if entry_idx < 0 or current_idx < 0:
            return None
        entry_atr = float(dataframe.iloc[entry_idx]["atr14"])
        if not np.isfinite(entry_atr) or entry_atr <= 0:
            return None

        soft_stop = trade.open_rate - entry_atr * self.initial_atr_multiple
        if current_rate > soft_stop:
            return None

        candle = dataframe.iloc[current_idx]
        intact_trend = (
            candle["close_4h"] > candle["ema200_4h"]
            and candle["ema50_4h"] > candle["ema200_4h"]
            and candle["ema200_slope24h_4h"] > 0
            and candle["ema20_1h"] > candle["ema50_1h"]
        )
        if self.conditional_stop_require_macd:
            intact_trend = intact_trend and candle["macd_hist_1h"] > 0
        return None if intact_trend else "atr_soft_stop"


class BtcTrendV10Reclaim(_BtcTrend15mBase):
    """15m EMA20 reclaim, confirmed by aligned 1h and 4h uptrends."""


class BtcTrendV10Breakout(_BtcTrend15mBase):
    """15m close above the prior 4h high, with the same trend confirmations."""
    trigger = "breakout"


class BtcTrendV10ReclaimNoActivity(_BtcTrend15mBase):
    """EMA20 reclaim without efficiency or relative-turnover gates."""
    use_activity_filters = False


class BtcTrendV10BreakoutNoActivity(BtcTrendV10ReclaimNoActivity):
    """Prior 4h high breakout without efficiency or relative-turnover gates."""
    trigger = "breakout"


class BtcTrendV10StateNoActivity(BtcTrendV10ReclaimNoActivity):
    """Price-side state trigger without efficiency or turnover gates."""
    trigger = "state"


class BtcTrendV10StateFastExit(BtcTrendV10StateNoActivity):
    """State entry with an earlier 15m EMA20 exit to test position turnover."""
    fast_exit = True


class BtcTrendV10StateNoMacd(BtcTrendV10StateNoActivity):
    """State entry with the overlapping 1h MACD confirmation removed."""
    use_macd_confirmation = False


class BtcTrendV11Adx15(BtcTrendV10StateNoMacd):
    """Lower the 4h ADX regime threshold from 20 to 15."""
    adx_min = 15.0


class BtcTrendV11Adx15Simple1h(BtcTrendV11Adx15):
    """ADX 15 with simplified 1h confirmation using close above EMA50."""
    require_1h_alignment = False


class BtcTrendV11Adx15NoSlope(BtcTrendV11Adx15):
    """ADX 15 without the 4h EMA200 slope gate."""
    require_4h_slope = False


class BtcTrendV12Price200Slope(BtcTrendV10StateNoMacd):
    """4h close above EMA200, positive EMA200 slope, ADX >= 15."""
    regime_mode = "price_ema200"
    adx_min = 15.0


class BtcTrendV12Price200(BtcTrendV10StateNoMacd):
    """4h close above EMA200 without the slow slope or ADX gates."""
    regime_mode = "price_ema200"
    adx_min = None
    require_4h_slope = False


class BtcTrendV12Price200SlopeAdx20(BtcTrendV10StateNoMacd):
    """4h close above EMA200, positive EMA200 slope and ADX >= 20."""
    regime_mode = "price_ema200"


class BtcTrendV12EmaOrder(BtcTrendV10StateNoMacd):
    """Retain 4h EMA50 > EMA200, removing ADX and slope gates."""
    adx_min = None
    require_4h_slope = False


class BtcTrendV13Price200No1h(BtcTrendV12Price200):
    """4h price regime with 1h direction confirmation removed."""
    require_1h_confirmation = False


class BtcTrendV14Target2(BtcTrendV12Price200):
    """V12 regime with a 2% minimum ROI target from entry."""
    minimal_roi = {"0": 0.02}


class BtcTrendV14Target3(BtcTrendV12Price200):
    """V12 regime with a 3% minimum ROI target from entry."""
    minimal_roi = {"0": 0.03}


class BtcTrendV15Stop3(BtcTrendV12Price200):
    """V12 regime with a tighter 3% stoploss."""
    stoploss = -0.03


class BtcTrendV15Stop2(BtcTrendV12Price200):
    """V12 regime with a tighter 2% stoploss."""
    stoploss = -0.02


class BtcTrendV16AtrHardStop(BtcTrendV12Price200):
    """V12 entries with a 2 ATR initial stop and no profit trailing."""
    use_custom_stoploss = True
    initial_atr_multiple = 2.0
    trailing_atr_multiple = 0.0


class BtcTrendV16AtrTrail(BtcTrendV12Price200):
    """V12 entries with a 2 ATR initial stop and 3 ATR peak trail."""
    use_custom_stoploss = True
    initial_atr_multiple = 2.0
    trailing_atr_multiple = 3.0
    trail_activation_profit = 0.015


class BtcTrendV16AtrTrailTrendHold(BtcTrendV16AtrTrail):
    """ATR trail manages pullbacks; exit only when the 4h regime fails."""
    exit_on_1h_reversal = False


class BtcTrendV17AtrRunner(BtcTrendV16AtrTrailTrendHold):
    """Wide peak trail activates only after a strong favorable move."""
    initial_atr_multiple = 2.0
    trailing_atr_multiple = 5.0
    trail_activation_profit = 0.04


class BtcTrendV18ConditionalStop(BtcTrendV12Price200):
    """2 ATR soft stop is deferred while strict 1h/4h trend structure holds."""
    conditional_atr_stop = True
    initial_atr_multiple = 2.0
    exit_on_1h_reversal = False


class BtcTrendV19ConditionalStopMomentum(BtcTrendV18ConditionalStop):
    """V18 only defers the soft stop while 1h MACD momentum stays positive."""
    conditional_stop_require_macd = True
