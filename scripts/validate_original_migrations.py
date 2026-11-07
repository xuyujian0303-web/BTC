"""Validate that the Freqtrade bridge exposes the original target signals.

This is a signal-contract check, not an execution-equivalence claim.  It
loads the same 1h OHLCV file used by Freqtrade, runs each vendored generator,
and verifies that the bridge target is exactly the original signed signal
clipped to the requested 1x account exposure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

from BtcOriginalFreqtrade import (
    V453FreqtradeExact1x,
    V71FreqtradeExact1x,
    V72FreqtradeExact1x,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/binance/futures/BTC_USDT_USDT-1h-futures.json"


def load_data() -> pd.DataFrame:
    raw = pd.read_json(DATA)
    raw.columns = ["date", "open", "high", "low", "close", "volume"]
    raw["date"] = pd.to_datetime(raw["date"], unit="ms", utc=True)
    # Match Freqtrade's continuous strategy dataframe around the documented
    # Binance Vision gap.  The inserted row remains NaN; no price is carried
    # forward into the source signal engine.
    return raw.set_index("date").asfreq("1h").reset_index()


def main() -> None:
    frame = load_data()
    rows = []
    for cls in (V453FreqtradeExact1x, V71FreqtradeExact1x, V72FreqtradeExact1x):
        strategy = cls({})
        result = strategy._make_signal_frame(frame)
        expected = result["signal"].astype(float).clip(-1.0, 1.0).fillna(0.0)
        target = result["target"].astype(float)
        error = (target - expected).abs()
        side = target.mask(target.abs() < 1e-12, 0.0).map(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
        rows.append(
            {
                "strategy": cls.__name__,
                "bars": int(len(result)),
                "source_nonzero_bars": int((result["signal"].abs() > 1e-12).sum()),
                "target_nonzero_bars": int((target.abs() > 1e-12).sum()),
                "side_transitions": int(side.ne(side.shift(fill_value=0)).sum()),
                "max_abs_target": float(target.abs().max()),
                "max_abs_contract_error": float(error.max()),
                "stop_rows": int(result["stop_price"].notna().sum()),
                "take_profit_rows": int(result["take_profit_price"].notna().sum()),
            }
        )
    report = {
        "input": str(DATA.relative_to(ROOT)),
        "contract": "target = clip(original signal, -1, 1), leverage = 1.0",
        "strategies": rows,
    }
    output = ROOT / "reports/original_migration_signal_validation.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
