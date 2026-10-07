"""Actor, der den Zustand eines laufenden Nodes regelmäßig als JSON-Datei für die Web-App ablegt."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

from nautilus_trader.common.actor import Actor
from nautilus_trader.config import ActorConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Venue


class StatusReporterConfig(ActorConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    state_path: str
    account_venue: str | None = None  # z. B. INTERACTIVE_BROKERS; sonst Venue des Instruments
    interval_secs: float = 5.0
    max_bars: int = 500


class StatusReporter(Actor):
    def __init__(self, config: StatusReporterConfig) -> None:
        super().__init__(config)
        self._path = Path(config.state_path)
        self._venue = Venue(config.account_venue or config.instrument_id.venue.value)

    def on_start(self) -> None:
        self.subscribe_bars(self.config.bar_type)
        self.clock.set_timer(
            name="status-report",
            interval=timedelta(seconds=self.config.interval_secs),
            callback=lambda _: self.write_state(),
        )
        self.write_state()

    def on_bar(self, bar: Bar) -> None:
        pass  # Bars landen im Cache; geschrieben wird per Timer

    def on_stop(self) -> None:
        self.write_state(stopped=True)

    def write_state(self, stopped: bool = False) -> None:
        cache = self.cache
        bars = list(reversed(cache.bars(self.config.bar_type)))[-self.config.max_bars :]
        account = self.portfolio.account(self._venue)
        balances = []
        if account is not None:
            for ccy, bal in account.balances().items():
                balances.append(
                    {"currency": str(ccy), "total": float(bal.total), "free": float(bal.free), "locked": float(bal.locked)},
                )
        positions = [
            {
                "instrument": str(p.instrument_id),
                "side": p.side.name,
                "quantity": float(p.quantity),
                "avg_open": float(p.avg_px_open),
                "unrealized_pnl": _unrealized(p, cache.price(p.instrument_id, PriceType.LAST)),
                "realized_pnl": float(p.realized_pnl.as_double()) if p.realized_pnl else 0.0,
            }
            for p in cache.positions_open(instrument_id=self.config.instrument_id)
        ]
        orders = [
            {
                "time": o.ts_last // 1_000_000_000,
                "id": str(o.client_order_id),
                "side": o.side.name,
                "type": o.order_type.name,
                "quantity": float(o.quantity),
                "filled": float(o.filled_qty),
                "avg_px": float(o.avg_px) if o.avg_px else None,
                "status": o.status.name,
            }
            for o in sorted(cache.orders(instrument_id=self.config.instrument_id), key=lambda o: o.ts_last)[-50:]
        ]
        state = {
            "ts": self.clock.timestamp_ns() // 1_000_000_000,
            "stopped": stopped,
            "instrument": str(self.config.instrument_id),
            "bar_type": str(self.config.bar_type),
            "bars": [
                {"time": b.ts_event // 1_000_000_000, "open": float(b.open), "high": float(b.high),
                 "low": float(b.low), "close": float(b.close), "volume": float(b.volume)}
                for b in bars
            ],
            "balances": balances,
            "positions": positions,
            "orders": orders,
        }
        # Atomar schreiben, damit die API nie eine halbe Datei liest
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        os.replace(tmp, self._path)



def _unrealized(position, last) -> float:
    return position.unrealized_pnl(last).as_double() if last is not None else 0.0
