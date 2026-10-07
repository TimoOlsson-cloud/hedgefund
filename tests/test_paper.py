import time

import pytest
from fastapi.testclient import TestClient

from api import main
from live import manager as manager_mod
from live.manager import PaperManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(manager_mod, "load_dotenv", lambda: {})
    monkeypatch.setattr(main, "paper", PaperManager(paper_dir=tmp_path, module="tests.fake_node"))
    yield TestClient(main.app)
    main.paper.stop()


def test_start_without_keys_is_rejected(client, monkeypatch):
    monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_API_SECRET", raising=False)
    r = client.post("/api/paper/start", json={})
    assert r.status_code == 400
    assert "BINANCE_TESTNET_API_KEY" in r.json()["detail"]


def test_start_status_stop(client, monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "k")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "s")
    assert client.post("/api/paper/start", json={"symbol": "ETHUSDT"}).json()["running"] is True
    assert client.post("/api/paper/start", json={}).status_code == 409

    for _ in range(50):
        status = client.get("/api/paper").json()
        if status["state"]:
            break
        time.sleep(0.1)
    assert status["state"]["instrument"] == "ETHUSDT.BINANCE"
    assert status["environment"] == "BINANCE SPOT TESTNET"

    stopped = client.post("/api/paper/stop").json()
    assert stopped["running"] is False
    assert "fake node stopped" in "\n".join(stopped["log"])


def test_invalid_paper_params(client):
    assert client.post("/api/paper/start", json={"fast_ema_period": 30, "slow_ema_period": 20}).status_code == 422
    assert client.post("/api/paper/start", json={"interval": "7m"}).status_code == 422
    assert client.post("/api/paper/start", json={"trade_size": "1e9; rm"}).status_code == 422


def test_ib_requires_paper_account(client, monkeypatch):
    monkeypatch.setenv("IB_ACCOUNT_ID", "U7654321")
    r = client.post("/api/paper/start", json={"venue": "ib", "symbol": "AAPL.NASDAQ", "trade_size": "1"})
    assert r.status_code == 400
    assert "Paper-Konto" in r.json()["detail"]


def test_ib_start_stop(client, monkeypatch):
    monkeypatch.setenv("IB_ACCOUNT_ID", "DU7654321")
    r = client.post("/api/paper/start", json={"venue": "ib", "symbol": "AAPL.NASDAQ", "trade_size": "1"})
    assert r.json()["environment"] == "INTERACTIVE BROKERS PAPER"
    for _ in range(50):
        status = client.get("/api/paper").json()
        if status["state"]:
            break
        time.sleep(0.1)
    assert status["state"]["instrument"] == "AAPL.NASDAQ"
    assert client.post("/api/paper/stop").json()["running"] is False


def test_ib_symbol_needs_exchange(client):
    r = client.post("/api/paper/start", json={"venue": "ib", "symbol": "AAPL"})
    assert r.status_code == 422
