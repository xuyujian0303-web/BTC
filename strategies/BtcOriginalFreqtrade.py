"""Freqtrade bridges for the original V4.5.3, V7.1 and V7.2 engines.

The signal engines are vendored under ``src/btc_regime`` and are called on
completed 1-hour candles.  The engines produce a signed target exposure.  A
Freqtrade trade is then rebalanced toward that target, clipped to one account
unit because these adapters deliberately run at exactly 1x leverage.

This preserves the original signal state machines and sizing decisions as far
as Freqtrade's candle execution model permits.  It cannot reproduce a maker
queue, order-book fills, or the original minute-level simulator.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, stoploss_from_absolute


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from btc_regime.v452 import V452Params  # noqa: E402
from btc_regime.v453 import generate_v453_signals  # noqa: E402
from btc_regime.v7 import V7Params, generate_v7_signals  # noqa: E402
from btc_regime.v71_live import V71LiveParams, generate_v71_live_signals  # noqa: E402


def _json(name: str) -> dict[str, Any]:
    with (REPO_ROOT / "config" / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _v453_params() -> V452Params:
    return V452Params(**_json("v4_5_3_params.json")["signal_params"])


def _v71_params() -> V7Params:
    return V7Params(**_json("v71_params.json"))


def _v72_params() -> V71LiveParams:
    return V71LiveParams(**_json("wzy_v72_tp_refined_params.json"))


def _hourly_input(dataframe: DataFrame) -> DataFrame:
    """Normalize Freqtrade OHLCV columns to the standalone engine contract."""

    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in dataframe]
    if missing:
        raise ValueError(f"Freqtrade dataframe is missing columns: {missing}")
    frame = dataframe[required].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    frame = frame.sort_values("date").drop_duplicates("date").set_index("date")
    frame["quote_volume"] = frame["close"] * frame["volume"]
    # Funding is not part of Binance Vision OHLCV files.  Zero is the causal
    # neutral value and keeps the original engine's optional factor disabled.
    frame["funding_rate"] = 0.0
    return frame


def _cycle_ids(signal: pd.Series, prefix: str) -> pd.Series:
    side = np.sign(signal.fillna(0.0))
    changed = side.ne(side.shift(fill_value=0.0))
    cycle = changed.cumsum().astype(int)
    return prefix + "_" + cycle.astype(str)


class _OriginalTargetBase(IStrategy):
    """Common target-exposure and protective-order adapter."""

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    startup_candle_count = 1000
    minimal_roi: dict[str, float] = {}
    stoploss = -0.99
    use_custom_stoploss = True
    use_custom_roi = True
    use_exit_signal = True
    trailing_stop = False
    position_adjustment_enable = True
    max_entry_position_adjustment = -1
    process_only_new_candles = True
    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}
    signal_prefix = "original"

    _generator: Callable[[DataFrame], DataFrame]

    def bot_start(self, **kwargs: Any) -> None:
        self._records: dict[str, dict[int, dict[str, Any]]] = {}
        self._blocked_cycles: dict[str, str] = {}

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        **kwargs: Any,
    ) -> float:
        if max_leverage < 1.0:
            raise ValueError(f"Exchange maximum leverage is below required 1x: {max_leverage}")
        return 1.0

    def _make_signal_frame(self, dataframe: DataFrame) -> DataFrame:
        source = _hourly_input(dataframe)
        result = self._generator(source)
        if not result.index.equals(source.index):
            result = result.reindex(source.index)
        if "signal" not in result:
            raise ValueError(f"{self.__class__.__name__} engine did not return signal")

        # The original engines express exposure as signed leverage.  One unit
        # is the maximum permitted by this adapter, while retaining direction
        # and every sub-unit target for position adjustment.
        result["target"] = result["signal"].astype(float).clip(-1.0, 1.0).fillna(0.0)
        result["cycle_id"] = result.get(
            "cycle_id", _cycle_ids(result["target"], self.signal_prefix)
        ).astype(str)
        if "stop_price" not in result:
            result["stop_price"] = np.nan
        if "take_profit_price" not in result:
            result["take_profit_price"] = np.nan
        if "entry_price" not in result:
            result["entry_price"] = np.nan
        if "regime" not in result:
            result["regime"] = "signal"
        result["target_changed"] = result["target"].ne(result["target"].shift())
        return result

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        result = self._make_signal_frame(dataframe)
        pair = metadata["pair"]
        records: dict[int, dict[str, Any]] = {}
        # A signal made on candle t becomes available to execution on t + 1h.
        # This is the same completed-bar availability rule used by the source
        # backtests and prevents a close-to-close lookahead.
        for timestamp, row in result.iterrows():
            available = int((timestamp + pd.Timedelta(hours=1)).timestamp())
            records[available] = row.to_dict()
        self._records[pair] = records

        for column in ("target", "signal", "stop_price", "take_profit_price", "entry_price"):
            dataframe[f"{self.signal_prefix}_{column}"] = result[column].to_numpy()
        dataframe[f"{self.signal_prefix}_cycle_id"] = result["cycle_id"].to_numpy()
        dataframe[f"{self.signal_prefix}_regime"] = result["regime"].astype(str).to_numpy()
        return dataframe

    def _record(self, pair: str, current_time: datetime) -> dict[str, Any] | None:
        records = getattr(self, "_records", {}).get(pair, {})
        timestamp = pd.Timestamp(current_time)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        key = int(timestamp.floor("h").timestamp())
        return records.get(key)

    @staticmethod
    def _finite(value: Any) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    def _equity(self, fallback: float) -> float:
        try:
            value = float(self.wallets.get_total_stake_amount())
        except (AttributeError, TypeError, ValueError):
            value = float(fallback)
        return value if math.isfinite(value) and value > 0 else float(fallback)

    def _target_stake(self, row: dict[str, Any], current_rate: float, fallback: float) -> float:
        target = abs(float(row.get("target", 0.0)))
        return target * self._equity(fallback)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        target = dataframe[f"{self.signal_prefix}_target"]
        previous = target.shift().fillna(0.0)
        dataframe["enter_long"] = ((target > 0) & (previous <= 0) & (dataframe["volume"] > 0)).astype(int)
        dataframe["enter_short"] = ((target < 0) & (previous >= 0) & (dataframe["volume"] > 0)).astype(int)
        dataframe["enter_tag"] = dataframe[f"{self.signal_prefix}_cycle_id"].astype(str)
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        target = dataframe[f"{self.signal_prefix}_target"]
        dataframe["exit_long"] = (target <= 0).astype(int)
        dataframe["exit_short"] = (target >= 0).astype(int)
        dataframe["exit_tag"] = f"{self.signal_prefix}_target_flat_or_reverse"
        return dataframe

    def confirm_trade_entry(self, pair: str, current_time: datetime, side: str, **kwargs: Any) -> bool:
        row = self._record(pair, current_time)
        if row is None:
            return False
        target = float(row.get("target", 0.0))
        if side == "long" and target <= 0:
            return False
        if side == "short" and target >= 0:
            return False
        return str(row.get("cycle_id", "")) != self._blocked_cycles.get(pair)

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> float:
        row = self._record(pair, current_time)
        if row is None or str(row.get("cycle_id", "")) == self._blocked_cycles.get(pair):
            return 0.0
        target = float(row.get("target", 0.0))
        if (side == "long" and target <= 0) or (side == "short" and target >= 0):
            return 0.0
        stake = min(self._target_stake(row, current_rate, proposed_stake), float(max_stake))
        if min_stake is not None and stake < float(min_stake):
            return 0.0
        return max(0.0, stake)

    def adjust_trade_position(
        self,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stake: float | None,
        max_stake: float,
        **kwargs: Any,
    ) -> float | tuple[float, str] | None:
        row = self._record(trade.pair, current_time)
        if row is None:
            return None
        target = float(row.get("target", 0.0))
        if target == 0 or (target < 0) != bool(trade.is_short):
            return None
        desired = min(self._target_stake(row, current_rate, trade.stake_amount), float(max_stake))
        delta = desired - float(trade.stake_amount)
        threshold = float(min_stake or 0.0)
        if abs(delta) < max(threshold, 1e-8):
            return None
        if delta > 0:
            return min(delta, float(max_stake)), f"{self.signal_prefix}_target_increase"
        return delta, f"{self.signal_prefix}_target_reduce"

    def custom_stoploss(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs: Any,
    ) -> float | None:
        row = self._record(pair, current_time)
        if row is None or not self._finite(row.get("stop_price")):
            return None
        return stoploss_from_absolute(
            float(row["stop_price"]),
            current_rate,
            is_short=bool(trade.is_short),
            leverage=float(trade.leverage),
        )

    def custom_roi(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        trade_duration: int,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> float | None:
        row = self._record(pair, current_time)
        if row is None or not self._finite(row.get("take_profit_price")):
            return None
        return max(0.0, float(trade.calc_profit_ratio(float(row["take_profit_price"]))))

    def custom_exit(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs: Any,
    ) -> str | None:
        row = self._record(pair, current_time)
        if row is None:
            return None
        target = float(row.get("target", 0.0))
        if target == 0 or (target < 0) != bool(trade.is_short):
            return f"{self.signal_prefix}_target_exit"
        stop = row.get("stop_price")
        take = row.get("take_profit_price")
        if self._finite(stop):
            crossed = current_rate <= float(stop) if not trade.is_short else current_rate >= float(stop)
            if crossed:
                return f"{self.signal_prefix}_absolute_stop"
        if self._finite(take):
            reached = current_rate >= float(take) if not trade.is_short else current_rate <= float(take)
            if reached:
                return f"{self.signal_prefix}_absolute_take"
        return None

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        exit_reason: str,
        **kwargs: Any,
    ) -> bool:
        if any(token in exit_reason for token in ("stop", "roi", "take", "protective")):
            row = self._record(pair, current_time)
            if row is not None:
                self._blocked_cycles[pair] = str(row.get("cycle_id", ""))
        return True


class V453FreqtradeExact1x(_OriginalTargetBase):
    """V4.5.3 frozen signal and target exposure, forced to 1x."""

    signal_prefix = "v453"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config or {})
        params = _v453_params()
        self._generator = lambda frame: generate_v453_signals(frame, params)


class V71FreqtradeExact1x(_OriginalTargetBase):
    """V7.1 branch signal state machine, forced to 1x."""

    signal_prefix = "v71"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config or {})
        params = _v71_params()
        self._generator = lambda frame: generate_v7_signals(frame, params)


class V72FreqtradeExact1x(_OriginalTargetBase):
    """WZY V7.2 live signal, permission layer and protection, forced to 1x."""

    signal_prefix = "v72"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config or {})
        params = _v72_params()
        self._generator = lambda frame: generate_v71_live_signals(frame, params)


__all__ = ["V453FreqtradeExact1x", "V71FreqtradeExact1x", "V72FreqtradeExact1x"]
