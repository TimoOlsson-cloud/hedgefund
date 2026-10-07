"""Offline-Ersatz für die Binance-REST-API in Tests."""

import math

EXCHANGE_INFO = {
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000", "maxQty": "9000.00000000"},
                {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
            ],
        },
    ],
}


def fake_fetch(path: str, params: dict):
    if path == "/api/v3/exchangeInfo":
        return EXCHANGE_INFO if params["symbol"] == "BTCUSDT" else {"symbols": []}
    assert path == "/api/v3/klines"
    step = 3_600_000
    start, end, limit = params["startTime"], params["endTime"], params["limit"]
    out = []
    t = start - start % step
    while t <= end and len(out) < limit:
        i = t // step
        mid = 60_000 + 3_000 * math.sin(i / 40) + 800 * math.sin(i / 7)
        o, c = mid - 50, mid + 50 * math.sin(i)
        out.append([t, f"{o:.2f}", f"{max(o, c) + 40:.2f}", f"{min(o, c) - 40:.2f}", f"{c:.2f}", "12.5", t + step - 1])
        t += step
    return out
