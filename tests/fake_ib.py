"""Offline-Ersatz für den HistoricInteractiveBrokersClient."""

import math

from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.test_kit.providers import TestInstrumentProvider


class FakeIBClient:
    def __init__(self, host: str, port: int, fail: bool = False) -> None:
        self.fail = fail

    async def connect(self):
        if self.fail:
            raise OSError("connection refused")

    async def request_instruments(self, instrument_ids):
        symbol, venue = instrument_ids[0].split(".")
        return [TestInstrumentProvider.equity(symbol, venue)] if symbol == "AAPL" else []

    async def request_bars(self, bar_specifications, start_date_time, end_date_time, tz_name, instrument_ids, use_rth):
        bar_type = BarType.from_str(f"{instrument_ids[0]}-{bar_specifications[0]}-EXTERNAL")
        step = 3_600_000_000_000
        t0 = int(start_date_time.timestamp() * 1e9)
        bars = []
        for i in range(int((end_date_time - start_date_time).total_seconds() // 3600)):
            mid = 190 + 8 * math.sin(i / 30) + 2 * math.sin(i / 5)
            o, c = mid - 0.2, mid + 0.3 * math.sin(i)
            ts = t0 + i * step
            bars.append(Bar(bar_type, Price(o, 2), Price(max(o, c) + 0.1, 2), Price(min(o, c) - 0.1, 2),
                            Price(c, 2), Quantity(1000, 0), ts, ts))
        return bars
