"""Historische Binance-Spot-Kerzen laden (öffentliche REST-API, kein API-Key nötig) und im
Nautilus-ParquetDataCatalog ablegen."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import requests

from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import CurrencyType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.persistence.wranglers import BarDataWrangler

from engine.catalog import save_dataset

BASE_URL = "https://api.binance.com"

# Binance-Intervall -> (Nautilus-Bar-Spec, Dauer in ms)
INTERVALS = {
    "1m": ("1-MINUTE", 60_000),
    "5m": ("5-MINUTE", 300_000),
    "15m": ("15-MINUTE", 900_000),
    "1h": ("1-HOUR", 3_600_000),
    "4h": ("4-HOUR", 14_400_000),
    "1d": ("1-DAY", 86_400_000),
}
MAX_BARS = 50_000

Fetch = Callable[[str, dict], object]


def http_get(path: str, params: dict) -> object:
    resp = requests.get(BASE_URL + path, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _currency(code: str) -> Currency:
    try:
        return Currency.from_str(code)
    except Exception:
        return Currency(code, 8, 0, code, CurrencyType.CRYPTO)


def _precision(step: str) -> int:
    d = Decimal(step).normalize()
    return max(0, -d.as_tuple().exponent)


def instrument_from_exchange_info(info: dict) -> CurrencyPair:
    filters = {f["filterType"]: f for f in info["filters"]}
    tick = filters["PRICE_FILTER"]["tickSize"]
    step = filters["LOT_SIZE"]["stepSize"]
    p_prec, s_prec = _precision(tick), _precision(step)
    quote = _currency(info["quoteAsset"])
    min_notional = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {})).get("minNotional")
    now = time.time_ns()
    return CurrencyPair(
        instrument_id=InstrumentId.from_str(f"{info['symbol']}.BINANCE"),
        raw_symbol=Symbol(info["symbol"]),
        base_currency=_currency(info["baseAsset"]),
        quote_currency=quote,
        price_precision=p_prec,
        size_precision=s_prec,
        price_increment=Price(Decimal(tick), p_prec),
        size_increment=Quantity(Decimal(step), s_prec),
        min_quantity=Quantity(Decimal(filters["LOT_SIZE"]["minQty"]), s_prec),
        max_quantity=Quantity(Decimal(filters["LOT_SIZE"]["maxQty"]), s_prec),
        min_notional=Money(Decimal(min_notional), quote) if min_notional else None,
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
        ts_event=now,
        ts_init=now,
    )


def fetch_klines(fetch: Fetch, symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    step_ms = INTERVALS[interval][1]
    rows: list[list] = []
    cursor = start_ms
    while cursor < end_ms and len(rows) < MAX_BARS:
        batch = fetch(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "startTime": cursor, "endTime": end_ms - 1, "limit": 1000},
        )
        if not batch:
            break
        rows.extend(batch)
        cursor = int(batch[-1][0]) + step_ms
        if len(batch) < 1000:
            break
    if not rows:
        raise ValueError(f"Keine Kerzen für {symbol} {interval} im Zeitraum gefunden")
    df = pd.DataFrame(
        [[int(r[0]), r[1], r[2], r[3], r[4], r[5]] for r in rows[:MAX_BARS]],
        columns=["open_time", "open", "high", "low", "close", "volume"],
    )
    # Nautilus-Konvention: Zeitstempel eines Bars = Schlusszeit
    df.index = pd.to_datetime(df["open_time"] + step_ms, unit="ms", utc=True)
    df = df[~df.index.duplicated()].drop(columns="open_time").astype("float64")
    return df


def bar_type_for(symbol: str, interval: str) -> BarType:
    return BarType.from_str(f"{symbol}.BINANCE-{INTERVALS[interval][0]}-LAST-EXTERNAL")


def download(
    symbol: str,
    interval: str,
    start: str,
    end: str,
    fetch: Fetch = http_get,
    catalog_dir: Path | None = None,
) -> dict:
    """Lädt Kerzen und schreibt Instrument + Bars in den Katalog. Gibt den Dataset-Eintrag zurück."""
    symbol = symbol.upper().strip()
    if interval not in INTERVALS:
        raise ValueError(f"Intervall muss eines von {list(INTERVALS)} sein")
    start_dt = datetime.fromisoformat(start).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=UTC)
    if end_dt <= start_dt:
        raise ValueError("Ende muss nach dem Start liegen")

    info = fetch("/api/v3/exchangeInfo", {"symbol": symbol})
    symbols = info.get("symbols", []) if isinstance(info, dict) else []
    if not symbols:
        raise ValueError(f"Symbol {symbol} bei Binance nicht gefunden")
    instrument = instrument_from_exchange_info(symbols[0])

    df = fetch_klines(fetch, symbol, interval, int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000))
    bar_type = bar_type_for(symbol, interval)
    bars = BarDataWrangler(bar_type=bar_type, instrument=instrument).process(df)

    key = f"binance-{symbol.lower()}-{interval}-{start_dt:%Y%m%d}-{end_dt:%Y%m%d}"
    label = f"{symbol} Binance {interval} ({start_dt:%d.%m.%Y} – {end_dt:%d.%m.%Y})"
    return save_dataset(key, label, instrument, bars, catalog_dir)
