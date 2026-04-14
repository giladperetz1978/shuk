"""Live GUI trading dashboard — autonomous 100-agent voting demo."""

import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from db import TradingDB
from main import (
    ACTION_THRESHOLD,
    DECISION_INTERVAL_CYCLES,
    CycleResult,
    MarketData,
    TOP_10_SYMBOLS,
    AgentFactory,
    VotingTradingEngine,
    choose_risky_symbols,
)

# ── Palette ──────────────────────────────────────────────────────────────────
BG         = "#0d1117"
PANEL      = "#161b22"
BORDER     = "#30363d"
TEXT       = "#e6edf3"
MUTED      = "#8b949e"
GREEN      = "#3fb950"
RED        = "#f85149"
YELLOW     = "#d29922"
BLUE       = "#58a6ff"
ORANGE     = "#f0883e"
CHART_LINE = "#3fb950"
CHART_BASE = "#58a6ff"
SELL_COLOR = "#f85149"
BUY_COLOR  = "#3fb950"


class TradingApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Agent Trading Demo")
        self.root.configure(bg=BG)
        self.root.minsize(1050, 700)

        self._queue: queue.Queue = queue.Queue()
        self._engine_thread: threading.Thread | None = None
        self._running = False

        # State
        self._initial_cash = 500.0
        self._agent_count  = 100
        self._chart_times: list  = []
        self._chart_values: list = []
        self._session_id: int | None = None
        self._db = TradingDB()

        self._setup_style()
        self._build_ui()
        self._load_history()
        self._poll()

    # ── Style ────────────────────────────────────────────────────────────────

    def _setup_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".",
            background=BG, foreground=TEXT,
            fieldbackground=PANEL, troughcolor=PANEL,
            bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
        )
        style.configure("Treeview",
            background=PANEL, foreground=TEXT, fieldbackground=PANEL,
            rowheight=22, borderwidth=0,
        )
        style.configure("Treeview.Heading",
            background=BG, foreground=MUTED, font=("Consolas", 9, "bold"),
        )
        style.map("Treeview",
            background=[("selected", BLUE)],
            foreground=[("selected", BG)],
        )
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("TButton",
            background=PANEL, foreground=TEXT, bordercolor=BORDER, padding=6,
        )
        style.map("TButton",
            background=[("active", BORDER)],
        )
        style.configure("Start.TButton",
            background="#1a3a1a", foreground=GREEN, bordercolor=GREEN,
        )
        style.map("Start.TButton",
            background=[("active", "#243a24")],
        )
        style.configure("Stop.TButton",
            background="#3a1a1a", foreground=RED, bordercolor=RED,
        )
        style.map("Stop.TButton",
            background=[("active", "#4a2a2a")],
        )
        style.configure("TEntry",
            fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT,
            bordercolor=BORDER,
        )
        style.configure("TNotebook", background=BG, bordercolor=BORDER)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(10, 4))
        style.map("TNotebook.Tab",
            background=[("selected", BG)],
            foreground=[("selected", TEXT)],
        )

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

        self._build_header()
        self._build_body()
        self._build_footer()

    def _build_header(self) -> None:
        hdr = tk.Frame(self.root, bg=PANEL, pady=8)
        hdr.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        hdr.columnconfigure(8, weight=1)

        # Status dot
        self._dot = tk.Label(hdr, text="●", font=("Consolas", 14), bg=PANEL, fg=RED)
        self._dot.grid(row=0, column=0, padx=(14, 4))

        tk.Label(hdr, text="Agent Trading Demo", font=("Consolas", 13, "bold"),
                 bg=PANEL, fg=TEXT).grid(row=0, column=1, padx=(0, 24), sticky="w")

        # Stats
        for col, (label, attr, color) in enumerate([
            ("Portfolio", "_lbl_value", TEXT),
            ("Cash",      "_lbl_cash",  MUTED),
            ("P&L",       "_lbl_pnl",   GREEN),
            ("Cycle",     "_lbl_cycle", BLUE),
            ("Regime",    "_lbl_regime", YELLOW),
            ("Learn",     "_lbl_learn", ORANGE),
        ], start=2):
            f = tk.Frame(hdr, bg=PANEL)
            f.grid(row=0, column=col, padx=20)
            tk.Label(f, text=label, font=("Consolas", 8), bg=PANEL, fg=MUTED).pack()
            lbl = tk.Label(f, text="—", font=("Consolas", 12, "bold"), bg=PANEL, fg=color)
            lbl.pack()
            setattr(self, attr, lbl)

        # Countdown
        self._lbl_countdown = tk.Label(hdr, text="", font=("Consolas", 10),
                                       bg=PANEL, fg=YELLOW)
        self._lbl_countdown.grid(row=0, column=10, padx=14, sticky="e")

    def _build_body(self) -> None:
        body = tk.Frame(self.root, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=2)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)

        # Chart (top-left, spans both rows on left)
        chart_frame = tk.Frame(body, bg=PANEL, bd=0)
        chart_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(4, 2), pady=4)
        self._build_chart(chart_frame)

        # Right top: Holdings
        hold_frame = self._panel(body, "Holdings", row=0, col=1)
        self._build_holdings(hold_frame)

        # Right bottom: Vote snapshot
        vote_frame = self._panel(body, "Vote Snapshot", row=1, col=1)
        self._build_votes(vote_frame)

        # Trade log in chart frame bottom (notebook tab)
        # Use a notebook below chart for chart/log tabs
        nb_frame = tk.Frame(body, bg=BG)
        nb_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=4, pady=(0, 4))
        body.rowconfigure(2, weight=1)
        nb_frame.columnconfigure(0, weight=1)
        nb_frame.rowconfigure(0, weight=1)

        nb = ttk.Notebook(nb_frame)
        nb.grid(row=0, column=0, sticky="nsew")

        log_tab = tk.Frame(nb, bg=PANEL)
        nb.add(log_tab, text="  Trade Log  ")
        log_tab.rowconfigure(0, weight=1)
        log_tab.columnconfigure(0, weight=1)
        self._build_log(log_tab)

    def _panel(self, parent, title: str, row: int, col: int) -> tk.Frame:
        outer = tk.Frame(parent, bg=PANEL, bd=0)
        outer.grid(row=row, column=col, sticky="nsew", padx=(2, 4), pady=4)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)
        tk.Label(outer, text=f"  {title}", font=("Consolas", 9, "bold"),
                 bg=PANEL, fg=MUTED, anchor="w").grid(row=0, column=0, sticky="ew", pady=(6, 2))
        inner = tk.Frame(outer, bg=PANEL)
        inner.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)
        return inner

    def _build_chart(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="  Portfolio Value", font=("Consolas", 9, "bold"),
                 bg=PANEL, fg=MUTED, anchor="w").pack(fill="x", pady=(6, 0))

        self._fig = Figure(figsize=(5, 4), dpi=96, facecolor=PANEL)
        self._ax = self._fig.add_subplot(111)
        self._ax.set_facecolor(BG)
        self._fig.subplots_adjust(left=0.12, right=0.97, top=0.93, bottom=0.15)

        self._canvas = FigureCanvasTkAgg(self._fig, master=parent)
        self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._redraw_chart()

    def _build_holdings(self, parent: tk.Frame) -> None:
        cols = ("Symbol", "Qty", "Avg $", "Price $", "Value $", "P&L")
        self._tree_hold = ttk.Treeview(parent, columns=cols, show="headings", height=7)
        for c in cols:
            self._tree_hold.heading(c, text=c)
            self._tree_hold.column(c, width=60, anchor="center")
        self._tree_hold.column("Symbol", width=55, anchor="center")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._tree_hold.yview)
        self._tree_hold.configure(yscrollcommand=vsb.set)
        self._tree_hold.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

    def _build_votes(self, parent: tk.Frame) -> None:
        cols = ("Symbol", "Buy%", "Sell%", "Signal")
        self._tree_vote = ttk.Treeview(parent, columns=cols, show="headings", height=6)
        widths = {"Symbol": 60, "Buy%": 55, "Sell%": 55, "Signal": 80}
        for c in cols:
            self._tree_vote.heading(c, text=c)
            self._tree_vote.column(c, width=widths.get(c, 60), anchor="center")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._tree_vote.yview)
        self._tree_vote.configure(yscrollcommand=vsb.set)
        self._tree_vote.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        # Tag colors
        self._tree_vote.tag_configure("buy",  foreground=GREEN)
        self._tree_vote.tag_configure("sell", foreground=RED)
        self._tree_vote.tag_configure("hold", foreground=MUTED)

    def _build_log(self, parent: tk.Frame) -> None:
        self._log = tk.Text(parent, bg=BG, fg=TEXT, font=("Consolas", 9),
                            insertbackground=TEXT, wrap="none", state="disabled", relief="flat")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._log.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=self._log.xview)
        self._log.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._log.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        # Tag colours for log
        self._log.tag_configure("buy",   foreground=GREEN)
        self._log.tag_configure("sell",  foreground=RED)
        self._log.tag_configure("cycle", foreground=BLUE)
        self._log.tag_configure("muted", foreground=MUTED)
        self._log.tag_configure("warn",  foreground=YELLOW)

    def _build_footer(self) -> None:
        footer = tk.Frame(self.root, bg=PANEL, pady=8)
        footer.grid(row=3, column=0, sticky="ew")

        self._btn_start = ttk.Button(footer, text="▶  Start", style="Start.TButton",
                                     command=self._start, width=12)
        self._btn_start.pack(side="left", padx=(14, 6))

        self._btn_stop = ttk.Button(footer, text="■  Stop", style="Stop.TButton",
                                    command=self._stop, width=12, state="disabled")
        self._btn_stop.pack(side="left", padx=6)

        tk.Label(footer, text="Cash $:", font=("Consolas", 9), bg=PANEL, fg=MUTED).pack(side="left", padx=(24, 2))
        self._ent_cash = tk.Entry(footer, width=7, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                                  font=("Consolas", 9), relief="solid", bd=1)
        self._ent_cash.insert(0, "500")
        self._ent_cash.pack(side="left")

        tk.Label(footer, text="Agents:", font=("Consolas", 9), bg=PANEL, fg=MUTED).pack(side="left", padx=(14, 2))
        self._ent_agents = tk.Entry(footer, width=5, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                                    font=("Consolas", 9), relief="solid", bd=1)
        self._ent_agents.insert(0, "60")
        self._ent_agents.pack(side="left")

        tk.Label(footer, text="Interval (s):", font=("Consolas", 9), bg=PANEL, fg=MUTED).pack(side="left", padx=(14, 2))
        self._ent_interval = tk.Entry(footer, width=5, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                                      font=("Consolas", 9), relief="solid", bd=1)
        self._ent_interval.insert(0, "300")
        self._ent_interval.pack(side="left")

        tk.Label(footer, text="Cycles (0=∞):", font=("Consolas", 9), bg=PANEL, fg=MUTED).pack(side="left", padx=(14, 2))
        self._ent_cycles = tk.Entry(footer, width=5, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                                    font=("Consolas", 9), relief="solid", bd=1)
        self._ent_cycles.insert(0, "0")
        self._ent_cycles.pack(side="left")

    # ── Chart drawing ────────────────────────────────────────────────────────

    def _redraw_chart(self) -> None:
        ax = self._ax
        ax.clear()
        ax.set_facecolor(BG)

        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.xaxis.label.set_color(MUTED)
        ax.yaxis.label.set_color(MUTED)

        if len(self._chart_times) > 1:
            baseline = self._chart_values[0]
            colors = [GREEN if v >= baseline else RED for v in self._chart_values]

            # Fill under line
            ax.fill_between(self._chart_times, self._chart_values, baseline,
                            alpha=0.12,
                            color=GREEN if self._chart_values[-1] >= baseline else RED)
            ax.plot(self._chart_times, self._chart_values,
                    color=CHART_LINE if self._chart_values[-1] >= baseline else RED,
                    linewidth=1.8, zorder=5)
            ax.axhline(y=baseline, color=BORDER, linestyle="--", linewidth=0.8)
            ax.axhline(y=self._chart_values[-1], color=CHART_LINE if self._chart_values[-1] >= baseline else RED,
                       linewidth=0.5, alpha=0.4)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            self._fig.autofmt_xdate(rotation=25, ha="right")
        else:
            ax.text(0.5, 0.5, "Waiting for first cycle…", transform=ax.transAxes,
                    ha="center", va="center", color=MUTED, fontsize=10)
            ax.set_xticks([])
            ax.set_yticks([])

        self._fig.tight_layout(pad=0.6)
        self._canvas.draw_idle()

    # ── History loading ──────────────────────────────────────────────────────

    def _load_history(self) -> None:
        rows = self._db.load_snapshots(limit=500)
        if rows:
            for ts_str, cycle, value, cash, pnl_pct in rows:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    self._chart_times.append(dt)
                    self._chart_values.append(value)
                except ValueError:
                    pass
            self._redraw_chart()

        trades = self._db.load_trades(limit=200)
        for row in reversed(trades):
            self._append_trade_to_log(*row, from_history=True)

    # ── Engine thread ────────────────────────────────────────────────────────

    def _start(self) -> None:
        try:
            cash     = float(self._ent_cash.get())
            agents   = int(self._ent_agents.get())
            interval = int(self._ent_interval.get())
            cycles   = int(self._ent_cycles.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Check numeric fields.", parent=self.root)
            return

        if cash <= 0 or agents < 10 or interval <= 0 or cycles < 0:
            messagebox.showerror("Invalid input", "Cash>0, agents≥10, interval>0, cycles≥0.", parent=self.root)
            return

        self._initial_cash  = cash
        self._agent_count   = agents
        self._chart_times   = []
        self._chart_values  = []
        self._session_id    = self._db.start_session(cash, agents)

        self._running = True
        self._btn_start.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._dot.config(fg=GREEN)
        self._lbl_cycle.config(text="0")

        persisted_agents = self._db.load_latest_learning_state(agents)

        self._engine_thread = threading.Thread(
            target=self._engine_loop,
            args=(cash, agents, interval, cycles, persisted_agents),
            daemon=True,
        )
        self._engine_thread.start()

    def _stop(self) -> None:
        self._running = False
        self._btn_start.config(state="normal")
        self._btn_stop.config(state="disabled")
        self._dot.config(fg=RED)
        self._lbl_countdown.config(text="")

    def _engine_loop(
        self,
        cash: float,
        agent_count: int,
        interval: int,
        max_cycles: int,
        persisted_agents: list[dict] | None,
    ) -> None:
        market = MarketData()
        agents = AgentFactory.build_population(agent_count, persisted_state=persisted_agents)
        engine = VotingTradingEngine(agents=agents, initial_cash=cash)
        cycle_index = 0

        while self._running:
            cycle_index += 1
            risky   = choose_risky_symbols(market)
            symbols = TOP_10_SYMBOLS + risky
            signals = market.fetch_signals(symbols)

            result = engine.execute_cycle(
                signals=signals,
                vote_threshold=ACTION_THRESHOLD,
                cycle_num=cycle_index,
                universe=symbols,
                execute_trades=(cycle_index % DECISION_INTERVAL_CYCLES == 0),
            )
            self._queue.put(result)

            if max_cycles > 0 and cycle_index >= max_cycles:
                # Signal finished by stopping after putting result
                self._queue.put(("done",))
                break

            for remaining in range(interval, 0, -1):
                if not self._running:
                    break
                self._queue.put(("countdown", remaining))
                time.sleep(1)

    # ── Queue polling ────────────────────────────────────────────────────────

    def _poll(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                if isinstance(item, CycleResult):
                    self._handle_cycle(item)
                elif isinstance(item, tuple):
                    if item[0] == "countdown":
                        mins, secs = divmod(item[1], 60)
                        self._lbl_countdown.config(text=f"Next cycle: {mins:02d}:{secs:02d}")
                    elif item[0] == "done":
                        self._stop()
        except queue.Empty:
            pass
        self.root.after(300, self._poll)

    # ── Cycle handling ───────────────────────────────────────────────────────

    def _handle_cycle(self, result: CycleResult) -> None:
        # Persist
        if self._session_id is not None:
            self._db.save_snapshot(
                self._session_id, result.cycle, result.timestamp,
                result.portfolio_value, result.cash, self._initial_cash,
            )
            self._db.save_trades(self._session_id, result.cycle, result.timestamp, result.trades)
            self._db.save_learning_state(self._session_id, result.cycle, result.timestamp, result.agent_state)

        # Chart
        self._chart_times.append(result.timestamp)
        self._chart_values.append(result.portfolio_value)
        self._redraw_chart()

        # Header stats
        pnl = result.portfolio_value - self._initial_cash
        pnl_pct = pnl / max(1e-9, self._initial_cash) * 100.0
        pnl_color = GREEN if pnl >= 0 else RED
        self._lbl_value.config(text=f"${result.portfolio_value:,.2f}")
        self._lbl_cash.config(text=f"${result.cash:,.2f}")
        self._lbl_pnl.config(text=f"{'+'if pnl>=0 else ''}{pnl_pct:.2f}%", fg=pnl_color)
        self._lbl_cycle.config(text=str(result.cycle))
        self._lbl_regime.config(text=result.market_regime.replace("_", " "))
        perf = result.performance_summary
        learn_text = (
            f"W {perf.get('win_rate', 0.0):.0%} | DD {perf.get('max_drawdown', 0.0):.1%}"
        )
        self._lbl_learn.config(text=learn_text)

        # Holdings table
        self._update_holdings(result)

        # Vote table
        self._update_votes(result)

        # Log
        self._log_cycle_header(result)
        for message in result.messages:
            if message.startswith("Stats:"):
                self._log_write(f"    {message}\n", "warn")
            elif message.startswith("Mode:"):
                self._log_write(f"    {message}\n", "cycle")
            elif message.startswith("Portfolio value:"):
                self._log_write(f"    {message}\n", "muted")
        for t in result.trades:
            self._append_trade_to_log(
                result.timestamp.isoformat(), result.cycle,
                t.action, t.symbol, t.qty, t.amount, t.price, t.vote_ratio,
            )
        if not result.trades:
            self._log_write("    — no trades this cycle\n", "muted")

    def _update_holdings(self, result: CycleResult) -> None:
        for item in self._tree_hold.get_children():
            self._tree_hold.delete(item)

        for symbol, h in sorted(result.holdings.items(), key=lambda x: x[0]):
            current_price = result.prices.get(symbol, 0.0)
            value         = h.qty * current_price
            pnl_pct       = (current_price / max(1e-9, h.avg_price) - 1.0) * 100.0
            pnl_str       = f"{'+'if pnl_pct>=0 else ''}{pnl_pct:.1f}%"
            tag           = "pos" if pnl_pct >= 0 else "neg"
            self._tree_hold.insert("", "end", values=(
                symbol,
                f"{h.qty:.3f}",
                f"{h.avg_price:.2f}",
                f"{current_price:.2f}",
                f"{value:.2f}",
                pnl_str,
            ), tags=(tag,))

        self._tree_hold.tag_configure("pos", foreground=GREEN)
        self._tree_hold.tag_configure("neg", foreground=RED)

    def _update_votes(self, result: CycleResult) -> None:
        for item in self._tree_vote.get_children():
            self._tree_vote.delete(item)

        for symbol, v in sorted(result.vote_summary.items(), key=lambda x: -x[1]["buy_ratio"]):
            buy_pct  = v["buy_ratio"] * 100
            sell_pct = v["sell_ratio"] * 100
            net      = buy_pct - sell_pct

            if net > 5:
                signal, tag = "▲ BUY",  "buy"
            elif net < -5:
                signal, tag = "▼ SELL", "sell"
            else:
                signal, tag = "▶ HOLD", "hold"

            self._tree_vote.insert("", "end", values=(
                symbol,
                f"{buy_pct:.0f}%",
                f"{sell_pct:.0f}%",
                signal,
            ), tags=(tag,))

    # ── Log helpers ──────────────────────────────────────────────────────────

    def _log_cycle_header(self, result: CycleResult) -> None:
        ts  = result.timestamp.strftime("%H:%M:%S")
        uni = ", ".join(result.universe) if result.universe else "—"
        regime = result.market_regime.replace("_", " ")
        leader = result.learning_summary.get("leader_personality", "balanced")
        self._log_write(
            f"\n[{ts}] Cycle {result.cycle}  |  {regime}  |  leader={leader}  |  {uni}\n", "cycle"
        )

    def _append_trade_to_log(
        self,
        ts_str: str,
        cycle: int,
        action: str,
        symbol: str,
        qty: float,
        amount: float,
        price: float,
        vote_ratio: float,
        from_history: bool = False,
    ) -> None:
        try:
            dt  = datetime.fromisoformat(ts_str)
            hms = dt.strftime("%H:%M:%S")
        except ValueError:
            hms = ts_str[:8]

        prefix = "↺ " if from_history else "  "
        tag    = "buy" if action == "BUY" else "sell"
        line   = (
            f"{prefix}{hms}  {action:<4}  {symbol:<5}  "
            f"qty={qty:.4f}  ${amount:.2f}  @${price:.2f}  vote={vote_ratio:.0%}\n"
        )
        self._log_write(line, tag)

    def _log_write(self, text: str, tag: str = "") -> None:
        self._log.config(state="normal")
        self._log.insert("end", text, tag)
        self._log.see("end")
        self._log.config(state="disabled")


def main() -> None:
    root = tk.Tk()
    root.geometry("1200x800")
    app = TradingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
