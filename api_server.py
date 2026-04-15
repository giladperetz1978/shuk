"""HTTP API + PWA host for the trading simulator.

Run with:
    uvicorn api_server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "trading_history.db"
WEB_DIR = BASE_DIR / "web"

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


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(str(WEB_DIR / "sw.js"), media_type="application/javascript")
