"""REST-API der Hedgefund-Web-App."""

from __future__ import annotations

import threading
from typing import Literal
import uuid
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic import Field

from engine import binance_data
from engine import ib_data
from engine.backtest import STRATEGIES
from engine.backtest import BacktestRequest
from engine.backtest import all_datasets
from engine.backtest import run_backtest
from live.manager import PaperManager

app = FastAPI(title="Hedgefund API", version="0.2.0")

_results: dict[str, dict] = {}
_lock = threading.Lock()  # Nautilus-Engines nacheinander laufen lassen
paper = PaperManager()


class BacktestIn(BaseModel):
    dataset: str = "ethusdt-binance-trades"
    strategy: str = "ema-cross"
    fast_ema_period: int = Field(10, ge=2, le=200)
    slow_ema_period: int = Field(20, ge=3, le=500)
    trade_size: str = "0.10"
    bar_ticks: int = Field(250, ge=10, le=5000)


class DownloadIn(BaseModel):
    symbol: str = Field("BTCUSDT", min_length=5, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    interval: str = "1h"
    start: str = "2024-01-01"
    end: str = "2024-07-01"


class IBDownloadIn(BaseModel):
    symbol: str = Field("AAPL", min_length=1, max_length=12, pattern=r"^[A-Za-z0-9.^/ ]+$")
    exchange: str = Field("NASDAQ", min_length=2, max_length=12, pattern=r"^[A-Za-z0-9]+$")
    interval: str = "1h"
    start: str = "2024-01-01"
    end: str = "2024-07-01"
    rth: bool = True


class PaperIn(BaseModel):
    venue: Literal["binance", "ib"] = "binance"
    # Binance: BTCUSDT, IB: AAPL.NASDAQ
    symbol: str = Field("BTCUSDT", min_length=3, max_length=24, pattern=r"^[A-Za-z0-9./^]+$")
    interval: str = "1m"
    fast_ema_period: int = Field(10, ge=2, le=200)
    slow_ema_period: int = Field(20, ge=3, le=500)
    trade_size: str = Field("0.001", pattern=r"^\d+(\.\d+)?$")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/datasets")
def datasets() -> dict:
    return {key: {"label": v["label"], "kind": v["kind"]} for key, v in all_datasets().items()}


@app.post("/api/data/binance")
def download_binance(body: DownloadIn) -> dict:
    try:
        with _lock:
            return binance_data.download(body.symbol, body.interval, body.start, body.end)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502, detail=f"Binance nicht erreichbar ({type(e).__name__}). Internetverbindung prüfen.",
        ) from e


@app.post("/api/data/ib")
def download_ib(body: IBDownloadIn) -> dict:
    try:
        return ib_data.download_in_subprocess(body.symbol, body.exchange, body.interval, body.start, body.end, body.rth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/api/strategies")
def strategies() -> dict:
    return STRATEGIES


@app.post("/api/backtests")
def create_backtest(body: BacktestIn) -> dict:
    req = BacktestRequest(**body.model_dump())
    try:
        req.validate()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    with _lock:
        result = run_backtest(req)
    run_id = uuid.uuid4().hex[:12]
    result["id"] = run_id
    _results[run_id] = result
    return result


@app.get("/api/backtests")
def list_backtests() -> list[dict]:
    return [
        {"id": r["id"], "request": r["request"], "pnl": r["stats"].get("PnL (total)")}
        for r in reversed(_results.values())
    ]


@app.get("/api/backtests/{run_id}")
def get_backtest(run_id: str) -> dict:
    if run_id not in _results:
        raise HTTPException(status_code=404, detail="Backtest nicht gefunden")
    return _results[run_id]


@app.get("/api/paper")
def paper_status() -> dict:
    return paper.status()


@app.post("/api/paper/start")
def paper_start(body: PaperIn) -> dict:
    if body.interval not in binance_data.INTERVALS:
        raise HTTPException(status_code=422, detail=f"Intervall muss eines von {list(binance_data.INTERVALS)} sein")
    if body.venue == "ib" and "." not in body.symbol:
        raise HTTPException(status_code=422, detail="IB-Symbole mit Börse angeben, z. B. AAPL.NASDAQ")
    if body.fast_ema_period >= body.slow_ema_period:
        raise HTTPException(status_code=422, detail="Die schnelle EMA muss kürzer sein als die langsame")
    try:
        return paper.start(body.model_dump())
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@app.post("/api/paper/stop")
def paper_stop() -> dict:
    return paper.stop()


_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
