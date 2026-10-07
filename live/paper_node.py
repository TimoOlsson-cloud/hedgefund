"""Paper-Trading-Node: Binance-Spot-TESTNET oder Interactive-Brokers-Paper-Konto.

Wird von der Web-App als eigener Prozess gestartet, z. B.:
    python -m live.paper_node --venue binance --symbol BTCUSDT --interval 1m --fast 10 --slow 20 --size 0.001 --state data/paper/state.json
    python -m live.paper_node --venue ib --symbol AAPL.NASDAQ --interval 1m --fast 10 --slow 20 --size 1 --state data/paper/state.json

Sicherheitsnetz: Binance ist fest auf TESTNET verdrahtet, bei IB werden nur Paper-Konten (Kennung beginnt
mit "DU") akzeptiert. Echter Handel braucht bewusst eigenen Code und deine Freigabe.
"""

from __future__ import annotations

import argparse
import os
import socket
from decimal import Decimal

from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LiveRiskEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.examples.strategies.ema_cross import EMACross
from nautilus_trader.examples.strategies.ema_cross import EMACrossConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId

from live.status_reporter import StatusReporter
from live.status_reporter import StatusReporterConfig

BAR_SPECS = {"1m": "1-MINUTE", "5m": "5-MINUTE", "15m": "15-MINUTE", "1h": "1-HOUR", "4h": "4-HOUR", "1d": "1-DAY"}
MAX_NOTIONAL_PER_ORDER = 1_000  # in Quote-Währung (USDT bzw. USD)
MAX_ORDER_RATE = "5/00:00:01"


def assert_ib_paper_account(account_id: str | None) -> str:
    if not account_id or not account_id.upper().startswith("DU"):
        raise SystemExit(
            f"IB_ACCOUNT_ID={account_id!r} ist kein Paper-Konto (muss mit 'DU' beginnen). Abbruch zur Sicherheit.",
        )
    return account_id


def _binance_clients(instrument_id: InstrumentId):
    from nautilus_trader.adapters.binance import BINANCE
    from nautilus_trader.adapters.binance import BinanceAccountType
    from nautilus_trader.adapters.binance import BinanceDataClientConfig
    from nautilus_trader.adapters.binance import BinanceExecClientConfig
    from nautilus_trader.adapters.binance import BinanceLiveDataClientFactory
    from nautilus_trader.adapters.binance import BinanceLiveExecClientFactory
    from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
    from nautilus_trader.config import InstrumentProviderConfig

    provider = InstrumentProviderConfig(load_ids=frozenset([instrument_id]))
    env = BinanceEnvironment.TESTNET
    data = BinanceDataClientConfig(account_type=BinanceAccountType.SPOT, environment=env, instrument_provider=provider)
    exec_ = BinanceExecClientConfig(
        account_type=BinanceAccountType.SPOT, environment=env, instrument_provider=provider, max_retries=3,
    )
    return BINANCE, data, exec_, BinanceLiveDataClientFactory, BinanceLiveExecClientFactory, "BINANCE"


def _ib_clients(instrument_id: InstrumentId):
    from nautilus_trader.adapters.interactive_brokers.common import IB
    from nautilus_trader.adapters.interactive_brokers.config import IBMarketDataTypeEnum
    from nautilus_trader.adapters.interactive_brokers.config import InteractiveBrokersDataClientConfig
    from nautilus_trader.adapters.interactive_brokers.config import InteractiveBrokersExecClientConfig
    from nautilus_trader.adapters.interactive_brokers.config import InteractiveBrokersInstrumentProviderConfig
    from nautilus_trader.adapters.interactive_brokers.config import SymbologyMethod
    from nautilus_trader.adapters.interactive_brokers.factories import InteractiveBrokersLiveDataClientFactory
    from nautilus_trader.adapters.interactive_brokers.factories import InteractiveBrokersLiveExecClientFactory
    from nautilus_trader.config import RoutingConfig

    from engine.ib_data import ib_endpoint

    account_id = assert_ib_paper_account(os.getenv("IB_ACCOUNT_ID"))
    host, port = ib_endpoint()
    try:
        socket.create_connection((host, port), timeout=3).close()
    except OSError:
        raise SystemExit(f"TWS/IB Gateway unter {host}:{port} nicht erreichbar. Läuft es im Paper-Modus mit aktivierter API?")
    provider = InteractiveBrokersInstrumentProviderConfig(
        symbology_method=SymbologyMethod.IB_SIMPLIFIED, load_ids=frozenset([str(instrument_id)]),
    )
    # Ohne Echtzeit-Abo liefert IB verzögerte Kurse; mit Abo IB_MARKET_DATA=realtime setzen
    market_data = (
        IBMarketDataTypeEnum.REALTIME if os.getenv("IB_MARKET_DATA", "delayed") == "realtime"
        else IBMarketDataTypeEnum.DELAYED_FROZEN
    )
    data = InteractiveBrokersDataClientConfig(
        ibg_host=host, ibg_port=port, ibg_client_id=101, market_data_type=market_data,
        use_regular_trading_hours=True, instrument_provider=provider,
    )
    exec_ = InteractiveBrokersExecClientConfig(
        ibg_host=host, ibg_port=port, ibg_client_id=102, account_id=account_id,
        instrument_provider=provider, routing=RoutingConfig(default=True),
    )
    return IB, data, exec_, InteractiveBrokersLiveDataClientFactory, InteractiveBrokersLiveExecClientFactory, IB


def build_node(venue: str, symbol: str, interval: str, fast: int, slow: int, size: Decimal, state_path: str) -> TradingNode:
    if venue == "binance":
        instrument_id = InstrumentId.from_str(f"{symbol}.BINANCE")
        name, data, exec_, data_factory, exec_factory, account_venue = _binance_clients(instrument_id)
    elif venue == "ib":
        instrument_id = InstrumentId.from_str(symbol)
        name, data, exec_, data_factory, exec_factory, account_venue = _ib_clients(instrument_id)
    else:
        raise SystemExit(f"Unbekannter Handelsplatz: {venue}")
    bar_type = BarType.from_str(f"{instrument_id}-{BAR_SPECS[interval]}-LAST-EXTERNAL")

    node = TradingNode(
        config=TradingNodeConfig(
            trader_id=TraderId("PAPER-001"),
            logging=LoggingConfig(log_level="INFO", log_colors=False),
            exec_engine=LiveExecEngineConfig(reconciliation=True, reconciliation_lookback_mins=1440),
            risk_engine=LiveRiskEngineConfig(
                max_order_submit_rate=MAX_ORDER_RATE,
                max_notional_per_order={str(instrument_id): MAX_NOTIONAL_PER_ORDER},
            ),
            data_clients={name: data},
            exec_clients={name: exec_},
            timeout_connection=90.0,
            timeout_reconciliation=10.0,
            timeout_portfolio=10.0,
            timeout_disconnection=10.0,
            timeout_post_stop=5.0,
        ),
    )
    node.trader.add_strategy(
        EMACross(
            EMACrossConfig(
                instrument_id=instrument_id,
                bar_type=bar_type,
                trade_size=size,
                fast_ema_period=fast,
                slow_ema_period=slow,
                request_bars=True,
            ),
        ),
    )
    node.trader.add_actor(
        StatusReporter(
            StatusReporterConfig(
                instrument_id=instrument_id, bar_type=bar_type, state_path=state_path, account_venue=account_venue,
            ),
        ),
    )
    node.add_data_client_factory(name, data_factory)
    node.add_exec_client_factory(name, exec_factory)
    node.build()
    return node


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", default="binance", choices=["binance", "ib"])
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="1m", choices=list(BAR_SPECS))
    ap.add_argument("--fast", type=int, default=10)
    ap.add_argument("--slow", type=int, default=20)
    ap.add_argument("--size", type=Decimal, default=Decimal("0.001"))
    ap.add_argument("--state", required=True)
    args = ap.parse_args()

    node = build_node(args.venue, args.symbol.upper(), args.interval, args.fast, args.slow, args.size, args.state)
    try:
        node.run()
    finally:
        node.dispose()


if __name__ == "__main__":
    main()
