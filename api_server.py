"""HTTP API + PWA host for the trading simulator.

Run with:
    uvicorn api_server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import TradingDB
from main import (
    ACTION_THRESHOLD,
    DECISION_INTERVAL_CYCLES,
    TOP_10_SYMBOLS,
    AgentFactory,
    MarketData,
    VotingTradingEngine,
    choose_risky_symbols,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "trading_history.db"
WEB_DIR = BASE_DIR / "web"

DEFAULT_ENGINE_CONFIG: dict[str, Any] = {
    "cash": 500.0,
    "agent_count": 1000,
    "interval_seconds": 300,
    "decision_interval_cycles": DECISION_INTERVAL_CYCLES,
    "action_threshold": ACTION_THRESHOLD,
    "cycles": 0,
}

app = FastAPI(title="FPI Trading API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_snapshots(limit: int = 240) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ts, cycle, value, cash, pnl_pct FROM snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    rows = list(reversed(rows))
    return [dict(row) for row in rows]


def _fetch_trades(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ts, cycle, action, symbol, qty, amount, price, vote_ratio "
            "FROM trades ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


class EngineManager:
    def __init__(self, db_path: Path) -> None:
        self._db = TradingDB(db_path)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._config = dict(DEFAULT_ENGINE_CONFIG)
        self._last_cycle = 0
        self._last_update: str | None = None
        self._last_error: str | None = None
        self._world_summary = "engine idle"
        self._session_id: int | None = None

    def _validate(self, config: dict[str, Any]) -> None:
        if float(config["cash"]) <= 0:
            raise ValueError("cash must be positive")
        if int(config["agent_count"]) < 10:
            raise ValueError("agent_count must be at least 10")
        if int(config["interval_seconds"]) <= 0:
            raise ValueError("interval_seconds must be positive")
        if int(config["decision_interval_cycles"]) <= 0:
            raise ValueError("decision_interval_cycles must be positive")
        action_threshold = float(config["action_threshold"])
        if not math.isfinite(action_threshold) or action_threshold <= 0 or action_threshold > 1:
            raise ValueError("action_threshold must be in (0, 1]")
        if int(config["cycles"]) < 0:
            raise ValueError("cycles cannot be negative")

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "config": dict(self._config),
                "last_cycle": self._last_cycle,
                "last_update": self._last_update,
                "last_error": self._last_error,
                "world_summary": self._world_summary,
                "session_id": self._session_id,
            }

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._running:
                raise RuntimeError("engine is already running")

            config = dict(DEFAULT_ENGINE_CONFIG)
            config.update(
                {
                    "cash": float(payload.get("cash", config["cash"])),
                    "agent_count": int(payload.get("agent_count", config["agent_count"])),
                    "interval_seconds": int(payload.get("interval_seconds", config["interval_seconds"])),
                    "decision_interval_cycles": DECISION_INTERVAL_CYCLES,
                    "action_threshold": float(payload.get("action_threshold", config["action_threshold"])),
                    "cycles": int(payload.get("cycles", config["cycles"])),
                }
            )
            self._validate(config)

            self._config = config
            self._last_cycle = 0
            self._last_update = None
            self._last_error = None
            self._world_summary = "engine starting"
            self._session_id = None
            self._stop_event = threading.Event()
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, args=(dict(config), self._stop_event), daemon=True)
            self._thread.start()

        return self.status()

    def update_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            next_config = dict(self._config)
            if "cash" in payload:
                next_config["cash"] = float(payload["cash"])
            if "agent_count" in payload:
                next_config["agent_count"] = int(payload["agent_count"])
            if "interval_seconds" in payload:
                next_config["interval_seconds"] = int(payload["interval_seconds"])
            if "action_threshold" in payload:
                next_config["action_threshold"] = float(payload["action_threshold"])
            if "cycles" in payload:
                next_config["cycles"] = int(payload["cycles"])

            # Keep trading every cycle; this setting is intentionally fixed.
            next_config["decision_interval_cycles"] = DECISION_INTERVAL_CYCLES
            self._validate(next_config)
            self._config = next_config
            return self.status()

    def stop(self) -> dict[str, Any]:
        thread_to_join: threading.Thread | None
        with self._lock:
            if not self._running:
                return self.status()
            self._stop_event.set()
            thread_to_join = self._thread

        if thread_to_join is not None:
            thread_to_join.join(timeout=3)

        with self._lock:
            if self._thread is not None and not self._thread.is_alive():
                self._running = False
                self._thread = None
                self._world_summary = "engine stopped"
        return self.status()

    def _run_loop(self, config: dict[str, Any], stop_event: threading.Event) -> None:
        try:
            market = MarketData()
            persisted_agents = self._db.load_latest_learning_state(config["agent_count"])
            agents = AgentFactory.build_population(config["agent_count"], persisted_state=persisted_agents)
            engine = VotingTradingEngine(
                agents=agents,
                initial_cash=config["cash"],
                decision_interval_cycles=DECISION_INTERVAL_CYCLES,
            )
            session_id = self._db.start_session(config["cash"], config["agent_count"])

            with self._lock:
                self._session_id = session_id

            cycle_index = 0
            while not stop_event.is_set():
                cycle_index += 1
                with self._lock:
                    current_config = dict(self._config)
                risky = choose_risky_symbols(market)
                symbols = TOP_10_SYMBOLS + risky
                signals = market.fetch_signals(symbols)
                result = engine.execute_cycle(
                    signals=signals,
                    vote_threshold=float(current_config["action_threshold"]),
                    cycle_num=cycle_index,
                    universe=symbols,
                    execute_trades=True,
                )

                self._db.save_snapshot(
                    session_id=session_id,
                    cycle=result.cycle,
                    ts=result.timestamp,
                    value=result.portfolio_value,
                    cash=result.cash,
                    initial_cash=config["cash"],
                )
                self._db.save_trades(session_id=session_id, cycle=result.cycle, ts=result.timestamp, trades=result.trades)

                if cycle_index % 3 == 0 or result.trades:
                    self._db.save_learning_state(
                        session_id=session_id,
                        cycle=result.cycle,
                        ts=result.timestamp,
                        agent_state=result.agent_state,
                    )

                with self._lock:
                    self._last_cycle = result.cycle
                    self._last_update = datetime.now().isoformat()
                    self._world_summary = market.last_world_summary

                if current_config["cycles"] > 0 and cycle_index >= current_config["cycles"]:
                    break

                if stop_event.wait(current_config["interval_seconds"]):
                    break
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
        finally:
            with self._lock:
                self._running = False
                self._thread = None


engine_manager = EngineManager(DB_PATH)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary")
def summary() -> dict[str, Any]:
    snapshots = _fetch_snapshots(limit=1)
    latest = snapshots[-1] if snapshots else None

    with _connect() as conn:
        session_row = conn.execute(
            "SELECT id, started_at, initial_cash, agent_count FROM sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()

    return {
        "db_exists": DB_PATH.exists(),
        "latest_snapshot": latest,
        "latest_session": dict(session_row) if session_row else None,
    }


@app.get("/api/snapshots")
def snapshots(limit: int = Query(default=240, ge=1, le=2000)) -> dict[str, Any]:
    data = _fetch_snapshots(limit=limit)
    return {"count": len(data), "items": data}


@app.get("/api/trades")
def trades(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    data = _fetch_trades(limit=limit)
    return {"count": len(data), "items": data}


@app.get("/api/engine/status")
def engine_status() -> dict[str, Any]:
    return engine_manager.status()


@app.post("/api/engine/start")
def engine_start(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    try:
        status = engine_manager.start(payload)
        return {"ok": True, "engine": status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/engine/stop")
def engine_stop() -> dict[str, Any]:
    status = engine_manager.stop()
    return {"ok": True, "engine": status}


@app.post("/api/engine/config")
def engine_update_config(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    try:
        status = engine_manager.update_config(payload)
        return {"ok": True, "engine": status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="assets")


@app.get("/")
def root() -> FileResponse:
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise RuntimeError("Missing web/index.html")
    return FileResponse(str(index_path))


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(str(WEB_DIR / "manifest.webmanifest"), media_type="application/manifest+json")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(str(WEB_DIR / "styles.css"), media_type="text/css")


@app.get("/app.js")
def app_js() -> FileResponse:
    return FileResponse(str(WEB_DIR / "app.js"), media_type="application/javascript")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(str(WEB_DIR / "sw.js"), media_type="application/javascript")
