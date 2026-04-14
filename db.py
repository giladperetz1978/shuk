"""SQLite persistence layer for the trading demo."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple


DB_PATH = Path(__file__).with_name("trading_history.db")


class TradingDB:
    def __init__(self, path: str | Path = DB_PATH) -> None:
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at    TEXT    NOT NULL,
                    initial_cash  REAL    NOT NULL,
                    agent_count   INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    ts         TEXT    NOT NULL,
                    cycle      INTEGER NOT NULL,
                    value      REAL    NOT NULL,
                    cash       REAL    NOT NULL,
                    pnl_pct    REAL    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    ts         TEXT    NOT NULL,
                    cycle      INTEGER NOT NULL,
                    action     TEXT    NOT NULL,
                    symbol     TEXT    NOT NULL,
                    qty        REAL    NOT NULL,
                    amount     REAL    NOT NULL,
                    price      REAL    NOT NULL,
                    vote_ratio REAL    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS learning_state (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  INTEGER NOT NULL,
                    ts          TEXT    NOT NULL,
                    cycle       INTEGER NOT NULL,
                    agent_count INTEGER NOT NULL,
                    payload     TEXT    NOT NULL
                );
            """)

    def start_session(self, initial_cash: float, agent_count: int) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (started_at, initial_cash, agent_count) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), initial_cash, agent_count),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def save_snapshot(
        self,
        session_id: int,
        cycle: int,
        ts: datetime,
        value: float,
        cash: float,
        initial_cash: float,
    ) -> None:
        pnl_pct = (value - initial_cash) / max(1e-9, initial_cash) * 100.0
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO snapshots (session_id, ts, cycle, value, cash, pnl_pct) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, ts.isoformat(), cycle, value, cash, pnl_pct),
            )

    def save_trades(self, session_id: int, cycle: int, ts: datetime, trades: list) -> None:
        if not trades:
            return
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO trades "
                "(session_id, ts, cycle, action, symbol, qty, amount, price, vote_ratio) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (session_id, ts.isoformat(), cycle, t.action, t.symbol, t.qty, t.amount, t.price, t.vote_ratio)
                    for t in trades
                ],
            )

    def load_snapshots(self, session_id: int | None = None, limit: int = 1000) -> List[Tuple]:
        """Returns rows as (ts_str, cycle, value, cash, pnl_pct) oldest-first."""
        with self._connect() as conn:
            if session_id is not None:
                rows = conn.execute(
                    "SELECT ts, cycle, value, cash, pnl_pct FROM snapshots "
                    "WHERE session_id=? ORDER BY id ASC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT ts, cycle, value, cash, pnl_pct FROM snapshots "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                rows = list(reversed(rows))
        return rows

    def load_trades(self, session_id: int | None = None, limit: int = 300) -> List[Tuple]:
        """Returns rows as (ts_str, cycle, action, symbol, qty, amount, price, vote_ratio) newest-first."""
        with self._connect() as conn:
            if session_id is not None:
                rows = conn.execute(
                    "SELECT ts, cycle, action, symbol, qty, amount, price, vote_ratio "
                    "FROM trades WHERE session_id=? ORDER BY id DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT ts, cycle, action, symbol, qty, amount, price, vote_ratio "
                    "FROM trades ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return rows

    def save_learning_state(
        self,
        session_id: int,
        cycle: int,
        ts: datetime,
        agent_state: List[dict[str, Any]],
    ) -> None:
        payload = json.dumps(agent_state)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO learning_state (session_id, ts, cycle, agent_count, payload) VALUES (?, ?, ?, ?, ?)",
                (session_id, ts.isoformat(), cycle, len(agent_state), payload),
            )

    def load_latest_learning_state(self, agent_count: int) -> Optional[List[dict[str, Any]]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM learning_state WHERE agent_count=? ORDER BY id DESC LIMIT 1",
                (agent_count,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def last_session_id(self) -> int | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
        return row[0] if row else None
