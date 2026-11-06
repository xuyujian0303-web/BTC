"""Frozen V10 BTC trend candidate for the repository comparison.

This class makes the selected V10 profile explicit instead of relying on
implicit inherited defaults.  The signal implementation lives in
``BtcTrendIntradayExperiments.py`` and remains compatible with Freqtrade's
strategy resolver.
"""

from BtcTrendIntradayExperiments import BtcTrendV10StateNoMacd


class BtcTrendV10Optimized(BtcTrendV10StateNoMacd):
    """Selected 15m state-entry profile after walk-forward comparison.

    The profile keeps the parameters that were positive in the training,
    validation, and holdout reports: 4h EMA50/EMA200 structure, positive
    4h EMA200 slope, ADX >= 20, 1h EMA alignment, no redundant MACD gate,
    and a 4% hard stop with slow trend invalidation exits.
    """

    timeframe = "15m"
    can_short = False
    startup_candle_count = 1600
    minimal_roi = {}
    stoploss = -0.04
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    process_only_new_candles = True

    trigger = "state"
    use_activity_filters = False
    use_macd_confirmation = False
    adx_min = 20.0
    require_4h_slope = True
    require_1h_alignment = True
    require_1h_confirmation = True
    regime_mode = "ema_order"
    fast_exit = False
    use_custom_stoploss = False
    conditional_atr_stop = False
    exit_on_1h_reversal = True
