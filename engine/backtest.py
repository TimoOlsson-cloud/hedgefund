"""Backtest-Service: kapselt NautilusTrader und liefert JSON-fähige Ergebnisse fürs Web-Frontend."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pandas as pd

from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import LoggingConfig
from nautilus_trader.examples.strategies.ema_cross import EMACross
from nautilus_trader.examples.strategies.ema_cross import EMACrossConfig
from nautilus_trader.model.currencies import ETH
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from engine.catalog import dataset_dir
from engine.catalog import load_index

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

BUILTIN_DATASETS = {
    "ethusdt-binance-trades": {
        "kind": "ticks",
        "label": "ETHUSDT Binance Trade-Ticks (14.08.2020, Beispiel)",
        "file": "ethusdt-trades.csv",
    },
}


def all_datasets() -> dict:
    """Eingebaute Beispieldaten + per Download angelegte Kerzen-Datensätze."""
    return {**BUILTIN_DATASETS, **load_index()}

STRATEGIES = {
    "ema-cross": {
        "label": "EMA-Cross (Trendfolge)",
        "params": {
            "fast_ema_period": {"type": "int", "default": 10, "min": 2, "max": 200},
            "slow_ema_period": {"type": "int", "default": 20, "min": 3, "max": 500},
            "trade_size": {"type": "decimal", "default": "0.10", "min": "0.01", "max": "10"},
            "bar_ticks": {"type": "int", "default": 250, "min": 10, "max": 5000},
        },
    },
}


@dataclass(frozen=True)
class BacktestRequest:
    dataset: str = "ethusdt-binance-trades"
    strategy: str = "ema-cross"
    fast_ema_period: int = 10
    slow_ema_period: int = 20
    trade_size: str = "0.10"
    bar_ticks: int = 250

    def validate(self) -> None:
        if self.dataset not in all_datasets():
            raise ValueError(f"Unbekannter Datensatz: {self.dataset}")
        if self.strategy not in STRATEGIES:
            raise ValueError(f"Unbekannte Strategie: {self.strategy}")
        if not 2 <= self.fast_ema_period < self.slow_ema_period <= 500:
            raise ValueError("Es muss gelten: 2 <= fast_ema_period < slow_ema_period <= 500")
        if not 10 <= self.bar_ticks <= 5000:
            raise ValueError("bar_ticks muss zwischen 10 und 5000 liegen")
        size = Decimal(self.trade_size)
        if not Decimal("0.01") <= size <= Decimal("10"):
            raise ValueError("trade_size muss zwischen 0.01 und 10 liegen")


@lru_cache(maxsize=4)
def _load_ticks(dataset: str):
    instrument = TestInstrumentProvider.ethusdt_binance()
    df = CSVTickDataLoader.load(DATA_DIR / BUILTIN_DATASETS[dataset]["file"])
    return instrument, TradeTickDataWrangler(instrument=instrument).process(df)


def _load_bars(entry: dict):
    catalog = ParquetDataCatalog(str(dataset_dir(entry["catalog"])))
    instrument = catalog.instruments(instrument_ids=[entry["instrument_id"]])[0]
    bars = catalog.bars(bar_types=[entry["bar_type"]])
    return instrument, bars


def _num(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


# Hält den Log-Guard der ersten Engine fest: wird er freigegeben, versucht die
# nächste Engine den Rust-Logger erneut zu setzen und der Prozess bricht ab
# (nautilus_trader 1.230.0: "attempted to set a logger after the logging system was already initialized").
_LOG_GUARD = None


def run_backtest(req: BacktestRequest) -> dict:
    global _LOG_GUARD
    req.validate()
    entry = all_datasets()[req.dataset]

    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id=TraderId("BACKTESTER-001"),
            logging=LoggingConfig(log_level="ERROR"),
        ),
    )
    if _LOG_GUARD is None:
        _LOG_GUARD = engine.kernel.get_log_guard()
    try:
        if entry["kind"] == "ticks":
            instrument, data = _load_ticks(req.dataset)
            bar_type = BarType.from_str(f"{instrument.id}-{req.bar_ticks}-TICK-LAST-INTERNAL")
            engine.add_venue(
                venue=BINANCE_VENUE,
                oms_type=OmsType.NETTING,
                book_type=BookType.L1_MBP,
                account_type=AccountType.CASH,
                base_currency=None,
                starting_balances=[Money(1_000_000.0, USDT), Money(10.0, ETH)],
                trade_execution=True,
            )
        else:
            instrument, data = _load_bars(entry)
            bar_type = BarType.from_str(entry["bar_type"])
            # Margin-Konto (Hebel 1), damit die Strategie auch short gehen kann
            engine.add_venue(
                venue=instrument.id.venue,
                oms_type=OmsType.NETTING,
                book_type=BookType.L1_MBP,
                account_type=AccountType.MARGIN,
                base_currency=instrument.quote_currency,
                starting_balances=[Money(1_000_000.0, instrument.quote_currency)],
                default_leverage=Decimal(1),
            )
        engine.add_instrument(instrument)
        engine.add_data(data)

        engine.add_strategy(
            EMACross(
                EMACrossConfig(
                    instrument_id=instrument.id,
                    bar_type=bar_type,
                    trade_size=Decimal(req.trade_size),
                    fast_ema_period=req.fast_ema_period,
                    slow_ema_period=req.slow_ema_period,
                    request_bars=False,
                ),
            ),
        )
        engine.run()
        chart_bars = data if entry["kind"] == "bars" else None
        return _collect(engine, bar_type, req, instrument.quote_currency, chart_bars)
    finally:
        engine.dispose()


def _collect(engine: BacktestEngine, bar_type: BarType, req: BacktestRequest, ccy, chart_bars=None) -> dict:
    # Kerzen-Datensätze direkt verwenden: der Cache hält nur die letzten 10.000 Bars, neueste zuerst
    source = chart_bars if chart_bars is not None else list(reversed(engine.cache.bars(bar_type)))
    bars = [
        {
            "time": b.ts_event // 1_000_000_000,
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume),
        }
        for b in source
    ]
    # Lightweight Charts verlangt streng steigende Zeitstempel (Sekunden)
    dedup: dict[int, dict] = {}
    for bar in bars:
        if bar["time"] in dedup:
            prev = dedup[bar["time"]]
            prev.update(high=max(prev["high"], bar["high"]), low=min(prev["low"], bar["low"]),
                        close=bar["close"], volume=prev["volume"] + bar["volume"])
        else:
            dedup[bar["time"]] = dict(bar)
    bars = list(dedup.values())

    fills_df = engine.trader.generate_order_fills_report()
    fills = []
    if not fills_df.empty:
        for _, row in fills_df.iterrows():
            fills.append(
                {
                    "time": int(pd.Timestamp(row["ts_last"]).timestamp()),
                    "side": str(row["side"]),
                    "price": _num(row["avg_px"]),
                    "quantity": _num(row["filled_qty"]),
                },
            )

    positions_df = engine.trader.generate_positions_report()
    equity = []
    positions = []
    if not positions_df.empty:
        closed = positions_df[positions_df["ts_closed"].notna()].sort_values("ts_closed")
        cum = 0.0
        for _, row in closed.iterrows():
            pnl = _num(str(row["realized_pnl"]).split(" ")[0]) or 0.0
            cum += pnl
            t = int(pd.Timestamp(row["ts_closed"]).timestamp())
            if equity and equity[-1]["time"] >= t:
                equity[-1]["value"] = round(cum, 8)
            else:
                equity.append({"time": t, "value": round(cum, 8)})
            positions.append(
                {
                    "opened": int(pd.Timestamp(row["ts_opened"]).timestamp()),
                    "closed": t,
                    "side": str(row["entry"]),
                    "avg_open": _num(row["avg_px_open"]),
                    "avg_close": _num(row["avg_px_close"]),
                    "pnl": pnl,
                },
            )

    analyzer = engine.portfolio.analyzer
    stats = {
        **{k: _num(v) for k, v in analyzer.get_performance_stats_pnls(ccy).items()},
        **{k: _num(v) for k, v in analyzer.get_performance_stats_returns().items()},
        "Positions": len(positions),
        "Fills": len(fills),
    }
    closes = pd.Series([b["close"] for b in bars], dtype="float64")
    times = [b["time"] for b in bars]

    def ema(period: int) -> list[dict]:
        values = closes.ewm(span=period, adjust=False).mean()
        return [{"time": t, "value": round(float(v), 6)} for t, v in zip(times, values, strict=True)]

    return {
        "request": req.__dict__,
        "indicators": {
            f"EMA {req.fast_ema_period}": ema(req.fast_ema_period),
            f"EMA {req.slow_ema_period}": ema(req.slow_ema_period),
        },
        "instrument": str(bar_type.instrument_id),
        "currency": str(ccy),
        "bars": bars,
        "fills": fills,
        "equity": equity,
        "positions": positions,
        "stats": stats,
    }
