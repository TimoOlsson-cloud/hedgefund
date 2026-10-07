"""Stellt den Paper-Node in Tests nach: schreibt einen Zustand und wartet auf SIGINT."""

import argparse
import json
import time

ap = argparse.ArgumentParser()
for a in ("--venue", "--symbol", "--interval", "--fast", "--slow", "--size", "--state"):
    ap.add_argument(a)
args = ap.parse_args()
state = {"ts": int(time.time()), "stopped": False, "instrument": args.symbol if args.venue == "ib" else f"{args.symbol}.BINANCE", "bars": [],
         "balances": [{"currency": "USDT", "total": 10000.0, "free": 10000.0, "locked": 0.0}],
         "positions": [], "orders": []}
with open(args.state, "w") as f:
    json.dump(state, f)
print("fake node running", flush=True)
try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    print("fake node stopped", flush=True)
