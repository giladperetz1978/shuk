# Autonomous Adaptive Trading Demo

An experimental paper-trading simulator with 100 personality-driven agents, live market data, a desktop dashboard, and local persistence.

## Features
- Starts with a virtual balance of 500 USD.
- Uses real intraday market data from Yahoo Finance.
- Runs 100 agents with distinct personalities such as risk seeker, risk averse, trend follower, contrarian, balanced, and more.
- Every cycle:
  - scans 10 large-cap symbols plus 2 higher-risk symbols,
  - lets all agents vote on buy/sell actions,
  - trades only when the vote passes a 60% threshold,
  - applies diversification and cash-reserve rules,
  - learns from the next cycle's price feedback.
- Persists trade history and learned agent state locally in SQLite.
- Includes a live GUI with portfolio chart, holdings, votes, regime, and trade log.

## Important disclaimer
This project is a simulation for research and education. It is not financial advice.
Real-money trading involves significant risk.

## Install
```bash
pip install -r requirements.txt
```

## Console run
```bash
python main.py --cash 500 --agents 100 --interval-seconds 300 --cycles 12
```

## GUI run
```bash
python gui.py
```

## Useful options
- `--cycles 0` runs forever until stopped.
- `--interval-seconds 20` is useful for testing the GUI quickly.
- `--seed` makes console tests reproducible.

## Local files
- `trading_history.db` stores snapshots, trades, and learned agent state.
- `.gitignore` excludes runtime database files, virtualenvs, and caches.

## Current architecture
- `main.py`: adaptive agent engine and market-data fetcher
- `gui.py`: live desktop dashboard
- `db.py`: SQLite persistence layer
