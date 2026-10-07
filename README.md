# Hedgefund – eigene Trading-Plattform auf NautilusTrader

Web-App: FastAPI-Backend um NautilusTrader + React-Frontend mit TradingView Lightweight Charts.

## Starten

```bash
# Backend (Python 3.12/3.13)
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Frontend bauen (Node 20+)
cd web && npm install && npm run build && cd ..

# App starten -> http://localhost:8000
uvicorn api.main:app --port 8000
```

Entwicklung mit Hot-Reload: `uvicorn api.main:app --reload` und parallel `cd web && npm run dev`
(-> http://localhost:5173, `/api` wird an Port 8000 weitergeleitet).

Tests: `pytest` (laufen komplett offline)

## Echte Daten laden

Im Tab **Backtest** unter „Daten laden“ Quelle, Symbol, Intervall und Zeitraum wählen. Die Kerzen landen im
Nautilus-`ParquetDataCatalog` unter `data/catalog/` und stehen danach in der Datenauswahl.

- **Binance:** öffentliche API, kein Key nötig.
- **Interactive Brokers:** Symbol + Börse (z. B. `AAPL` / `NASDAQ`, `SPY` / `ARCA`). Braucht laufende TWS oder
  IB Gateway (siehe unten). Standard sind reguläre Handelszeiten. Backtests auf Kerzen laufen mit einem Margin-Konto
(Hebel 1, 1 Mio. Startkapital), damit die Strategie auch short gehen kann.

## Paper-Trading (Binance Spot Testnet)

1. Auf https://testnet.binance.vision mit GitHub anmelden und einen API-Key erzeugen (Spielgeld).
2. `.env.example` nach `.env` kopieren und `BINANCE_TESTNET_API_KEY` / `BINANCE_TESTNET_API_SECRET` eintragen.
3. Tab **Paper-Trading** → Symbol (z. B. BTCUSDT), Intervall, EMAs, Ordergröße → „Paper-Trading starten“.

## Paper-Trading (Interactive Brokers)

1. Bei IBKR das Paper-Trading-Konto aktivieren (Kontoverwaltung → Einstellungen → Paper-Trading). Die Kennung beginnt mit `DU`.
2. TWS oder IB Gateway starten, mit dem **Paper**-Login anmelden, unter Configure → API → Settings
   „Enable ActiveX and Socket Clients“ aktivieren. Ports: Gateway 4002, TWS 7497.
3. In `.env`: `IB_ACCOUNT_ID=DU…`, ggf. `IB_PORT`. Ohne Marktdaten-Abo bleibt `IB_MARKET_DATA=delayed`.
4. Tab **Paper-Trading** → Handelsplatz „Interactive Brokers Paper“, Symbol mit Börse (`AAPL.NASDAQ`), Stückzahl.

Die App nimmt nur Konten an, die mit `DU` beginnen (Paper). Ein echtes Konto wird abgelehnt.

## Wie Paper-Trading intern läuft

Die App startet `live/paper_node.py` als eigenen Prozess (Nautilus-`TradingNode`). Ein `StatusReporter`-Actor
schreibt alle 5 Sekunden Kerzen, Kontostand, Positionen und Orders nach `data/paper/state.json`, die Web-App
zeigt das zusammen mit dem Log an. Sicherheitsnetz: Binance fest auf TESTNET, IB nur Paper-Konten,
RiskEngine mit max. 1.000 USD(T) pro Order und max. 5 Orders pro Sekunde. Echtes Geld braucht bewusst eigenen Code.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `engine/` | Backtest-Service (`backtest.py`), Datendownload von Binance (`binance_data.py`) und IB (`ib_data.py`) |
| `live/` | Paper-Trading-Node (`paper_node.py`), Status-Actor, Prozess-Manager |
| `api/` | FastAPI: Datensätze, Download, Backtests, Paper-Start/-Stop/-Status |
| `web/` | React + Lightweight Charts: Tabs Backtest und Paper-Trading |
| `backtests/` | Standalone-Skripte (z. B. Tearsheet-Erzeugung) |
| `data/` | Marktdaten (aktuell Beispiel-Ticks ETHUSDT 14.08.2020) |
| `tests/` | Tests inkl. Offline-Attrappen für Binance und IB |

Version gepinnt auf `nautilus_trader==1.231.0` (der GitHub-`develop`-Branch ist bereits v2 und nicht kompatibel).
Backtest-Ergebnisse liegen vorerst nur im Speicher und sind nach einem Neustart weg.
