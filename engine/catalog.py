"""Gemeinsame Ablage heruntergeladener Datensätze: ein ParquetDataCatalog pro Datensatz + Index-Datei."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from nautilus_trader.model.data import Bar
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.catalog import ParquetDataCatalog

CATALOG_DIR = Path(__file__).resolve().parents[1] / "data" / "catalog"


def load_index(catalog_dir: Path | None = None) -> dict:
    index_file = (catalog_dir or CATALOG_DIR) / "datasets.json"
    return json.loads(index_file.read_text()) if index_file.exists() else {}


def save_dataset(key: str, label: str, instrument: Instrument, bars: list[Bar], catalog_dir: Path | None = None) -> dict:
    if not bars:
        raise ValueError("Keine Kerzen im gewählten Zeitraum gefunden")
    root = catalog_dir or CATALOG_DIR
    # Ein Katalog pro Datensatz: erneuter Download ersetzt ihn, keine überlappenden Intervalle
    ds_dir = root / key
    if ds_dir.exists():
        shutil.rmtree(ds_dir)
    catalog = ParquetDataCatalog(str(ds_dir))
    catalog.write_data([instrument])
    catalog.write_data(bars)

    entry = {
        "kind": "bars",
        "catalog": key,
        "label": label,
        "instrument_id": str(instrument.id),
        "bar_type": str(bars[0].bar_type),
        "start": bars[0].ts_event,
        "end": bars[-1].ts_event,
        "bars": len(bars),
    }
    index = load_index(root)
    index[key] = entry
    (root / "datasets.json").write_text(json.dumps(index, indent=2))
    return {"key": key, **entry}


def dataset_dir(key: str) -> Path:
    return CATALOG_DIR / key
