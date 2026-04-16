# Autonomous Adaptive Trading Demo

An experimental paper-trading simulator with 1000 personality-driven agents, live market data, a desktop dashboard, and local persistence.

## Features
- Starts with a virtual balance of 500 USD.
- Uses real intraday market data from Yahoo Finance.
- Runs 1000 agents with distinct personalities such as risk seeker, risk averse, trend follower, contrarian, balanced, and more.
- Every cycle:
  - scans 10 large-cap symbols plus 2 higher-risk symbols,
  - lets all agents vote on buy/sell actions every 5 minutes,
  - executes real buy/sell decisions every vote round,
  - compares a stricter 60% threshold engine against a faster 46% threshold engine,
  - trades only when the aggregated vote passes the configured threshold (60% in the core engine, 46% in the fast engine),
  - keeps a 25%–35% cash reserve for survivability,
  - learns from the next cycle's price feedback.
- Tracks performance metrics per cycle:
  - Win rate
  - Average win / average loss
  - Max drawdown
  - Net P&L after Tradier fee model (Pro by default)
- Persists trade history and learned agent state locally in SQLite.
- Includes a live GUI with side-by-side 15-minute vs 5-minute execution comparison, portfolio chart, holdings, votes, and trade log.

## Important disclaimer
This project is a simulation for research and education. It is not financial advice.
Real-money trading involves significant risk.

## Install
```bash
pip install -r requirements.txt
```

## Console run
```bash
python main.py --cash 500 --agents 1000 --interval-seconds 300 --cycles 12
```

## GUI run
```bash
python gui.py
```

The GUI now runs two strategies side by side on the same live signals and same starting cash:
- `Core 60%`: executes every cycle with the standard 60% vote threshold.
- `Fast 46%`: executes every cycle with the lower 46% vote threshold.

The comparison view shows both P&L percentages and the current winner gap in real time.

## Useful options
- `--cycles 0` runs forever until stopped.
- `--interval-seconds 300` runs vote rounds every 5 minutes (default).
- Trade execution now happens every cycle.
- `--interval-seconds 20` is useful for fast UI tests only.
- `--seed` makes console tests reproducible.

## Fee model used in simulation
- Default: Tradier Pro (`$10/month`) with `$0` stock-trade commission.
- Monthly fee is charged pro-rata over real elapsed time and included in `fees_paid` and net P&L.
- If `TRADIER_PRO_ENABLED` is set to `False` in `main.py`, the engine uses `$0.35` per trade.

## Local files
- `trading_history.db` stores snapshots, trades, and learned agent state.
- `.gitignore` excludes runtime database files, virtualenvs, caches, and build artifacts.

## Current architecture
- `main.py`: adaptive agent engine and market-data fetcher
- `gui.py`: live desktop dashboard
- `db.py`: SQLite persistence layer

## PWA monitor (recommended for phone)
Run the trading engine on your always-on machine/server, and open a lightweight PWA on your phone for live monitoring.

### 1) Run the engine 24/7
```bash
python main.py --cash 500 --agents 1000 --interval-seconds 300 --cycles 0
```

### 2) Run API + PWA host
```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Then open:
- `http://<YOUR_SERVER_IP>:8000/`

The PWA auto-refreshes every 15 seconds and reads live data from `trading_history.db`.

### 3) Install as PWA on phone
- Open the URL in Chrome/Edge on Android.
- Tap `Add to Home screen` / `Install app`.
- Launch from the home screen like a native app.

## GitHub Pages frontend (optional)
You can publish only the static monitor UI from `web/` to GitHub Pages, while the backend API keeps running on your VPS.

- Workflow file: `.github/workflows/pages.yml`
- Trigger: every push to `main`
- Deploys: `web/` folder to Pages

After opening your Pages URL:
- Set `API VPS` URL in the input box (for example: `https://api.your-domain.com`) and click save.
- The URL is saved in local browser storage.
- You can also override with query string: `?api=https://api.your-domain.com`

## API endpoints
- `GET /api/health`
- `GET /api/summary`
- `GET /api/snapshots?limit=240`
- `GET /api/trades?limit=50`
