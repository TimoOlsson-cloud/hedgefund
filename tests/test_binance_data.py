import pytest

from engine import catalog as catalog_mod
from engine import binance_data
from engine.backtest import BacktestRequest
from engine.backtest import run_backtest
from tests.fake_binance import fake_fetch


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_mod, "CATALOG_DIR", tmp_path)
    return tmp_path


def test_download_writes_catalog_and_index(catalog):
    entry = binance_data.download("btcusdt", "1h", "2024-01-01", "2024-03-01", fetch=fake_fetch, catalog_dir=catalog)
    assert entry["bar_type"] == "BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL"
    assert entry["bars"] == 60 * 24
    assert entry["key"] in catalog_mod.load_index()


def test_download_paginates(catalog):
    entry = binance_data.download("BTCUSDT", "1h", "2024-01-01", "2024-01-03", fetch=fake_fetch, catalog_dir=catalog)
    assert entry["bars"] == 48


def test_unknown_symbol(catalog):
    with pytest.raises(ValueError, match="nicht gefunden"):
        binance_data.download("NOPE", "1h", "2024-01-01", "2024-01-02", fetch=fake_fetch, catalog_dir=catalog)


def test_backtest_on_downloaded_bars(catalog):
    entry = binance_data.download("BTCUSDT", "1h", "2024-01-01", "2024-03-01", fetch=fake_fetch, catalog_dir=catalog)
    result = run_backtest(BacktestRequest(dataset=entry["key"], trade_size="0.10"))
    assert result["currency"] == "USDT"
    assert len(result["bars"]) == 60 * 24
    assert result["stats"]["Positions"] > 5
    assert result["equity"]
