"""Erster Smoke-Test: EMA-Cross auf ETHUSDT-Trade-Ticks (lokale CSV, keine Netzwerkzugriffe)."""

from decimal import Decimal
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
from nautilus_trader.test_kit.providers import TestInstrumentProvider

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "ethusdt-trades.csv"
OUT = ROOT / "reports"


def main() -> None:
    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id=TraderId("BACKTESTER-001"),
            logging=LoggingConfig(log_level="WARNING"),
        ),
    )
    engine.add_venue(
        venue=BINANCE_VENUE,
        oms_type=OmsType.NETTING,
        book_type=BookType.L1_MBP,
        account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=[Money(1_000_000.0, USDT), Money(10.0, ETH)],
        trade_execution=True,
    )

    instrument = TestInstrumentProvider.ethusdt_binance()
    engine.add_instrument(instrument)
    ticks = TradeTickDataWrangler(instrument=instrument).process(CSVTickDataLoader.load(DATA))
    engine.add_data(ticks)

    engine.add_strategy(
        EMACross(
            EMACrossConfig(
                instrument_id=instrument.id,
                bar_type=BarType.from_str("ETHUSDT.BINANCE-250-TICK-LAST-INTERNAL"),
                trade_size=Decimal("0.10"),
                fast_ema_period=10,
                slow_ema_period=20,
            ),
        ),
    )

    engine.run()

    OUT.mkdir(exist_ok=True)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(engine.trader.generate_account_report(BINANCE_VENUE).tail(3))
        positions = engine.trader.generate_positions_report()
        print(f"\nPositionen: {len(positions)}, Fills: {len(engine.trader.generate_order_fills_report())}")
    stats = engine.portfolio.analyzer
    print("\nPnL-Statistiken (USDT):")
    for k, v in stats.get_performance_stats_pnls(USDT).items():
        print(f"  {k}: {v}")
    print("Return-Statistiken:")
    for k, v in stats.get_performance_stats_returns().items():
        print(f"  {k}: {v}")

    try:
        from nautilus_trader.analysis.tearsheet import create_tearsheet

        create_tearsheet(engine=engine, output_path=str(OUT / "ema_cross_ethusdt_tearsheet.html"))
        print(f"\nTearsheet: {OUT / 'ema_cross_ethusdt_tearsheet.html'}")
    except ImportError:
        print("plotly fehlt: pip install 'plotly>=6.3.1' fuer den Tearsheet")

    engine.dispose()


if __name__ == "__main__":
    main()
