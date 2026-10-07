"""Historische Kerzen von Interactive Brokers laden (über TWS oder IB Gateway) und im Katalog ablegen."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from engine.catalog import save_dataset

# Intervall -> Nautilus-Bar-Spezifikation für IB
INTERVALS = {
    "1m": "1-MINUTE-LAST",
    "5m": "5-MINUTE-LAST",
    "15m": "15-MINUTE-LAST",
    "1h": "1-HOUR-LAST",
    "1d": "1-DAY-LAST",
}
CONNECT_TIMEOUT = 20
ROOT = Path(__file__).resolve().parents[1]
RESULT_PREFIX = "@@RESULT "


def ib_endpoint() -> tuple[str, int]:
    """Host/Port aus der Umgebung. Standard: IB Gateway im Paper-Modus (Port 4002)."""
    return os.getenv("IB_HOST", "127.0.0.1"), int(os.getenv("IB_PORT", "4002"))


def _default_client(host: str, port: int):
    from nautilus_trader.adapters.interactive_brokers.historical import HistoricInteractiveBrokersClient

    # Der IB-Client versucht es sonst endlos weiter; vorher kurz prüfen, ob überhaupt etwas lauscht
    try:
        socket.create_connection((host, port), timeout=3).close()
    except OSError as e:
        raise ConnectionError(
            f"TWS/IB Gateway unter {host}:{port} nicht erreichbar. Läuft es im Paper-Modus mit aktivierter API?",
        ) from e

    return HistoricInteractiveBrokersClient(host=host, port=port, client_id=17, log_level="WARNING")


async def _download(client, instrument_id: str, interval: str, start: datetime, end: datetime, rth: bool):
    try:
        await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT)
    except (TimeoutError, OSError) as e:
        raise ConnectionError(
            "Keine Verbindung zu TWS/IB Gateway. Läuft das Gateway im Paper-Modus und ist die API freigeschaltet?",
        ) from e
    instruments = await client.request_instruments(instrument_ids=[instrument_id])
    if not instruments:
        raise ValueError(f"{instrument_id} bei Interactive Brokers nicht gefunden")
    bars = await client.request_bars(
        bar_specifications=[INTERVALS[interval]],
        start_date_time=start,
        end_date_time=end,
        tz_name="America/New_York",
        instrument_ids=[instrument_id],
        use_rth=rth,
    )
    return instruments[0], sorted(bars, key=lambda b: b.ts_event)


def download(
    symbol: str,
    exchange: str,
    interval: str,
    start: str,
    end: str,
    rth: bool = True,
    client_factory: Callable = _default_client,
    catalog_dir: Path | None = None,
) -> dict:
    symbol, exchange = symbol.upper().strip(), exchange.upper().strip()
    if interval not in INTERVALS:
        raise ValueError(f"Intervall muss eines von {list(INTERVALS)} sein")
    start_dt, end_dt = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if end_dt <= start_dt:
        raise ValueError("Ende muss nach dem Start liegen")

    instrument_id = f"{symbol}.{exchange}"
    client = client_factory(*ib_endpoint())
    instrument, bars = asyncio.run(_download(client, instrument_id, interval, start_dt, end_dt, rth))

    key = f"ib-{symbol.lower()}-{exchange.lower()}-{interval}-{start_dt:%Y%m%d}-{end_dt:%Y%m%d}"
    label = f"{instrument_id} IB {interval} ({start_dt:%d.%m.%Y} – {end_dt:%d.%m.%Y})"
    return save_dataset(key, label, instrument, bars, catalog_dir)


def download_in_subprocess(symbol: str, exchange: str, interval: str, start: str, end: str, rth: bool) -> dict:
    """Der IB-Client initialisiert Nautilus' Logging; das geht nur einmal pro Prozess. Deshalb läuft der
    Download in einem eigenen Prozess, damit die Web-App daneben weiter Backtests rechnen kann."""
    cmd = [sys.executable, "-m", "engine.ib_data", symbol, exchange, interval, start, end, "1" if rth else "0"]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600, env=os.environ.copy())
    except subprocess.TimeoutExpired as e:
        raise ConnectionError("Zeitüberschreitung beim Download von Interactive Brokers") from e
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(RESULT_PREFIX)]
    if not lines:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-3:])
        raise ConnectionError(f"IB-Download fehlgeschlagen: {tail or 'keine Ausgabe'}")
    result = json.loads(lines[-1][len(RESULT_PREFIX):])
    if "error" in result:
        raise (ValueError if result["kind"] == "value" else ConnectionError)(result["error"])
    return result


def _main() -> None:
    symbol, exchange, interval, start, end, rth = sys.argv[1:7]
    try:
        out = download(symbol, exchange, interval, start, end, rth == "1")
    except ValueError as e:
        out = {"error": str(e), "kind": "value"}
    except ConnectionError as e:
        out = {"error": str(e), "kind": "connection"}
    except Exception as e:  # Verbindungsprobleme, IB-Fehler
        out = {"error": str(e) or type(e).__name__, "kind": "connection"}
    print(RESULT_PREFIX + json.dumps(out), flush=True)
    os._exit(0)  # IB-Client-Threads nicht abwarten


if __name__ == "__main__":
    _main()
