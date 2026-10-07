import pytest

from engine import catalog as catalog_mod
from engine import ib_data
from engine.backtest import BacktestRequest
from engine.backtest import run_backtest
from tests.fake_ib import FakeIBClient


@pytest.fixture(autouse=True)
def catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_mod, "CATALOG_DIR", tmp_path)
    return tmp_path


def test_ib_download_and_backtest():
    entry = ib_data.download("aapl", "nasdaq", "1h", "2024-01-01", "2024-03-01", client_factory=FakeIBClient)
    assert entry["instrument_id"] == "AAPL.NASDAQ"
    assert entry["bar_type"] == "AAPL.NASDAQ-1-HOUR-LAST-EXTERNAL"
    result = run_backtest(BacktestRequest(dataset=entry["key"], trade_size="10"))
    assert result["currency"] == "USD"
    assert result["stats"]["Positions"] > 5


def test_ib_unknown_symbol():
    with pytest.raises(ValueError, match="nicht gefunden"):
        ib_data.download("NOPE", "NASDAQ", "1h", "2024-01-01", "2024-01-05", client_factory=FakeIBClient)


def test_ib_gateway_unreachable():
    with pytest.raises(ConnectionError, match="IB Gateway"):
        ib_data.download("AAPL", "NASDAQ", "1h", "2024-01-01", "2024-01-05",
                         client_factory=lambda h, p: FakeIBClient(h, p, fail=True))


def test_subprocess_reports_unreachable_gateway(monkeypatch):
    monkeypatch.setenv("IB_PORT", "1")  # hier lauscht nichts
    with pytest.raises(ConnectionError):
        ib_data.download_in_subprocess("AAPL", "NASDAQ", "1h", "2024-01-01", "2024-01-05", True)
