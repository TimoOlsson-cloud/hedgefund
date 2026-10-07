"""Startet/stoppt den Paper-Trading-Node als Unterprozess und liest seinen Zustand."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "data" / "paper"
REQUIRED_KEYS = {
    "binance": ("BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET"),
    "ib": ("IB_ACCOUNT_ID",),
}
ENVIRONMENTS = {"binance": "BINANCE SPOT TESTNET", "ib": "INTERACTIVE BROKERS PAPER"}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def load_dotenv(path: Path = ROOT / ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class PaperManager:
    def __init__(self, paper_dir: Path = PAPER_DIR, python: str = sys.executable, module: str = "live.paper_node") -> None:
        self.dir = paper_dir
        self.python = python
        self.module = module
        self._proc: subprocess.Popen | None = None
        self._params: dict | None = None
        self._started: float | None = None
        self._lock = threading.Lock()

    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    @property
    def log_path(self) -> Path:
        return self.dir / "node.log"

    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, params: dict) -> dict:
        with self._lock:
            if self.running():
                raise RuntimeError("Paper-Trading läuft bereits")
            env = {**os.environ, **load_dotenv()}
            venue = params.get("venue", "binance")
            missing = [k for k in REQUIRED_KEYS[venue] if not env.get(k)]
            if missing:
                raise PermissionError(
                    "Zugangsdaten fehlen: " + ", ".join(missing)
                    + ". Lege sie in der Datei .env im Projektordner ab (Vorlage: .env.example).",
                )
            if venue == "ib" and not env["IB_ACCOUNT_ID"].upper().startswith("DU"):
                raise PermissionError("IB_ACCOUNT_ID ist kein Paper-Konto (Paper-Konten beginnen mit 'DU').")
            self.dir.mkdir(parents=True, exist_ok=True)
            self.state_path.unlink(missing_ok=True)
            cmd = [
                self.python, "-m", self.module, "--venue", venue,
                "--symbol", params["symbol"], "--interval", params["interval"],
                "--fast", str(params["fast_ema_period"]), "--slow", str(params["slow_ema_period"]),
                "--size", str(params["trade_size"]), "--state", str(self.state_path),
            ]
            log = self.log_path.open("w")
            self._proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            self._params = params
            self._started = time.time()
            return self.status()

    def stop(self, timeout: float = 20.0) -> dict:
        with self._lock:
            if self.running():
                self._proc.send_signal(signal.SIGINT)
                try:
                    self._proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait()
            return self.status()

    def status(self) -> dict:
        state = None
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text())
            except json.JSONDecodeError:
                state = None
        log_tail: list[str] = []
        if self.log_path.exists():
            lines = self.log_path.read_text(errors="replace").splitlines()[-60:]
            log_tail = [_ANSI.sub("", ln) for ln in lines]
        return {
            "running": self.running(),
            "exit_code": None if self._proc is None or self.running() else self._proc.returncode,
            "params": self._params,
            "started": self._started,
            "environment": ENVIRONMENTS[(self._params or {}).get("venue", "binance")],
            "state": state,
            "log": log_tail,
        }
