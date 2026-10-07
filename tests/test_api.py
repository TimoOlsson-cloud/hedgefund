from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_backtest_roundtrip():
    r = client.post("/api/backtests", json={"fast_ema_period": 10, "slow_ema_period": 20})
    assert r.status_code == 200
    data = r.json()
    assert data["stats"]["Positions"] == 15
    assert data["stats"]["Fills"] == 30
    assert len(data["bars"]) > 100
    times = [b["time"] for b in data["bars"]]
    assert times == sorted(set(times))
    assert set(data["indicators"]) == {"EMA 10", "EMA 20"}
    assert client.get(f"/api/backtests/{data['id']}").status_code == 200


def test_invalid_params_rejected():
    r = client.post("/api/backtests", json={"fast_ema_period": 30, "slow_ema_period": 20})
    assert r.status_code == 422
