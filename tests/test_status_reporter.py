import json
from decimal import Decimal

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
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.objects import Money

from engine.backtest import _load_ticks
from live.status_reporter import StatusReporter
from live.status_reporter import StatusReporterConfig


def test_status_reporter_writes_state(tmp_path):
    instrument, ticks = _load_ticks("ethusdt-binance-trades")
    bar_type = BarType.from_str(f"{instrument.id}-250-TICK-LAST-INTERNAL")
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(log_level="ERROR")))
    engine.add_venue(BINANCE_VENUE, OmsType.NETTING, AccountType.CASH, base_currency=None,
                     starting_balances=[Money(1_000_000, USDT), Money(10, ETH)], trade_execution=True)
    engine.add_instrument(instrument)
    engine.add_data(ticks)
    engine.add_strategy(EMACross(EMACrossConfig(instrument_id=instrument.id, bar_type=bar_type,
                                                trade_size=Decimal("0.10"), request_bars=False)))
    state_path = tmp_path / "state.json"
    engine.add_actor(StatusReporter(StatusReporterConfig(
        instrument_id=instrument.id, bar_type=bar_type, state_path=str(state_path), interval_secs=60)))
    engine.run()
    engine.dispose()

    state = json.loads(state_path.read_text())
    assert state["stopped"] is True
    assert len(state["bars"]) > 100
    assert {b["currency"] for b in state["balances"]} == {"USDT", "ETH"}
    assert any(o["status"] == "FILLED" for o in state["orders"])
