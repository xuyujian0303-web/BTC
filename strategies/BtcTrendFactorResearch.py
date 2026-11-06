"""BTC perpetual trend and range factor variants for research backtests."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import numpy as np
import talib.abstract as ta
from pandas import DataFrame, Series

from freqtrade.strategy import IStrategy, merge_informative_pair


class _BtcTrendBase(ABC):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    startup_candle_count = 900
    minimal_roi = {}
    stoploss = -0.04
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    process_only_new_candles = True

    @abstractmethod
    def trend_factor_confirmation(self, dataframe: DataFrame) -> tuple[Series, Series]:
        """Return long and short confirmation masks for this factor variant."""

    def informative_pairs(self) -> list[tuple[str, str]]:
        if self.dp is None:
            return []
        return [(pair, "4h") for pair in self.dp.current_whitelist()]

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
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd_hist"] = macd["macdhist"]
        bands = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bands["upperband"]
        dataframe["bb_lower"] = bands["lowerband"]

        dataframe["turnover"] = dataframe["close"] * dataframe["volume"]
        dataframe["turnover_mean20"] = dataframe["turnover"].rolling(20).mean()
        dataframe["turnover_relative24"] = (
            dataframe["turnover"] / dataframe["turnover"].rolling(24).mean().replace(0, np.nan)
        )
        dataframe["momentum12"] = dataframe["close"].pct_change(12)
        log_return = np.log(dataframe["close"]).diff()
        realized_vol24 = log_return.rolling(24).std() * np.sqrt(24)
        dataframe["vol_adjusted_momentum24"] = (
            np.log(dataframe["close"] / dataframe["close"].shift(24))
            / realized_vol24.replace(0, np.nan)
        )
        high24 = dataframe["high"].rolling(24).max().shift(1)
        low24 = dataframe["low"].rolling(24).min().shift(1)
        channel_width = (high24 - low24).replace(0, np.nan)
        dataframe["donchian_position24"] = (dataframe["close"] - low24) / channel_width
        signed_turnover = np.sign(dataframe["close"].diff()) * dataframe["turnover"]
        dataframe["volume_flow12"] = (
            signed_turnover.rolling(12).sum()
            / dataframe["turnover"].rolling(12).sum().replace(0, np.nan)
        )
        path_length24 = dataframe["close"].diff().abs().rolling(24).sum()
        dataframe["efficiency24"] = (
            dataframe["close"].diff(24).abs() / path_length24.replace(0, np.nan)
        )

        if self.dp is None:
            dataframe["regime_up"] = False
            dataframe["regime_down"] = False
            dataframe["regime_range"] = False
            return dataframe

        informative = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe="4h").copy()
        informative["ema50"] = ta.EMA(informative, timeperiod=50)
        informative["ema200"] = ta.EMA(informative, timeperiod=200)
        informative["adx14"] = ta.ADX(informative, timeperiod=14)
        informative["ema200_slope24h"] = informative["ema200"].pct_change(6)
        dataframe = merge_informative_pair(
            dataframe,
            informative[["date", "ema50", "ema200", "adx14", "ema200_slope24h"]],
            self.timeframe,
            "4h",
            ffill=True,
        )

        ema50_4h = dataframe["ema50_4h"]
        ema200_4h = dataframe["ema200_4h"]
        adx_4h = dataframe["adx14_4h"]
        slope_4h = dataframe["ema200_slope24h_4h"]
        dataframe["regime_up"] = (ema50_4h > ema200_4h) & (slope_4h > 0) & (adx_4h >= 20)
        dataframe["regime_down"] = (ema50_4h < ema200_4h) & (slope_4h < 0) & (adx_4h >= 20)
        dataframe["regime_range"] = (adx_4h < 18) & (slope_4h.abs() <= 0.005)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict[str, Any]) -> DataFrame:
        long_factor, short_factor = self.trend_factor_confirmation(dataframe)
        crossed_up = (dataframe["close"] > dataframe["ema20"]) & (
            dataframe["close"].shift(1) <= dataframe["ema20"].shift(1)
        )
        crossed_down = (dataframe["close"] < dataframe["ema20"]) & (
            dataframe["close"].shift(1) >= dataframe["ema20"].shift(1)
        )
        liquid = dataframe["volume"] > 0
        turnover_ok = dataframe["turnover"] > dataframe["turnover_mean20"]
        long_trend = (
            dataframe["regime_up"]
            & crossed_up
            & (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["macd_hist"] > 0)
            & turnover_ok
            & liquid
            & long_factor
        )
        short_trend = (
            dataframe["regime_down"]
            & crossed_down
            & (dataframe["ema20"] < dataframe["ema50"])
            & (dataframe["macd_hist"] < 0)
            & turnover_ok
            & liquid
            & short_factor
        )
        range_long = (
            dataframe["regime_range"]
            & (dataframe["low"].shift(1) <= dataframe["bb_lower"].shift(1))
            & (dataframe["close"] > dataframe["bb_lower"])
            & liquid
        )

        dataframe.loc[long_trend, ["enter_long", "enter_tag"]] = (1, "trend")
        dataframe.loc[range_long, ["enter_long", "enter_tag"]] = (1, "range")
        dataframe.loc[short_trend, ["enter_short", "enter_tag"]] = (1, "trend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict[str, Any]) -> DataFrame:
        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs: Any,
    ) -> str | None:
        if self.dp is None:
            return None
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        candle = dataframe.iloc[-1]
        if trade.enter_tag == "range":
            if not candle["regime_range"]:
                return "range_regime_changed"
            if not trade.is_short and current_rate >= candle["bb_upper"]:
                return "range_upper_band"
            return None
        if trade.is_short:
            if not candle["regime_down"]:
                return "trend_regime_changed"
            return "ema_reversal" if candle["ema20"] > candle["ema50"] else None
        if not candle["regime_up"]:
            return "trend_regime_changed"
        return "ema_reversal" if candle["ema20"] < candle["ema50"] else None


class BtcTrendBaseline(_BtcTrendBase, IStrategy):
    def trend_factor_confirmation(self, dataframe: DataFrame) -> tuple[Series, Series]:
        valid = Series(True, index=dataframe.index)
        return valid, valid


class BtcTrendMom12(_BtcTrendBase, IStrategy):
    def trend_factor_confirmation(self, dataframe: DataFrame) -> tuple[Series, Series]:
        return dataframe["momentum12"] > 0, dataframe["momentum12"] < 0


class BtcTrendVolAdjustedMom24(_BtcTrendBase, IStrategy):
    def trend_factor_confirmation(self, dataframe: DataFrame) -> tuple[Series, Series]:
        score = dataframe["vol_adjusted_momentum24"]
        return score > 0, score < 0


class BtcTrendDonchianPos24(_BtcTrendBase, IStrategy):
    def trend_factor_confirmation(self, dataframe: DataFrame) -> tuple[Series, Series]:
        position = dataframe["donchian_position24"]
        return position >= 0.7, position <= 0.3


class BtcTrendVolumeFlow12(_BtcTrendBase, IStrategy):
    def trend_factor_confirmation(self, dataframe: DataFrame) -> tuple[Series, Series]:
        flow = dataframe["volume_flow12"]
        return flow >= 0.1, flow <= -0.1


class BtcTrendEfficiency24(_BtcTrendBase, IStrategy):
    def trend_factor_confirmation(self, dataframe: DataFrame) -> tuple[Series, Series]:
        efficiency = dataframe["efficiency24"]
        directional = np.sign(dataframe["momentum12"])
        return (efficiency >= 0.25) & (directional > 0), (efficiency >= 0.25) & (directional < 0)


class BtcTrendEfficiencyTurnover(_BtcTrendBase, IStrategy):
    def trend_factor_confirmation(self, dataframe: DataFrame) -> tuple[Series, Series]:
        efficiency = dataframe["efficiency24"] >= 0.25
        active_turnover = dataframe["turnover_relative24"] >= 1.1
        directional = np.sign(dataframe["momentum12"])
        return efficiency & active_turnover & (directional > 0), efficiency & active_turnover & (directional < 0)
