"""Live GUI trading dashboard with side-by-side strategy comparison."""

import math
import queue
import random
import threading
import time
import tkinter as tk
from copy import deepcopy
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
    FAST_ACTION_THRESHOLD,
    MarketData,
    TOP_10_SYMBOLS,
    AgentFactory,
    VotingTradingEngine,
    choose_risky_symbols,
)

# ── Palette ──────────────────────────────────────────────────────────────────
BG         = "#0d1117"
PANEL      = "#161b22"
PANEL_SOFT = "#11161d"
PANEL_ALT  = "#1b2330"
BORDER     = "#30363d"
TEXT       = "#e6edf3"
MUTED      = "#8b949e"
SOFT_TEXT  = "#c9d4df"
GREEN      = "#3fb950"
RED        = "#f85149"
YELLOW     = "#d29922"
BLUE       = "#58a6ff"
ORANGE     = "#f0883e"
CYAN       = "#66d9ef"
ROSE       = "#ff8f70"
CHART_LINE = "#3fb950"
CHART_BASE = "#58a6ff"
SELL_COLOR = "#f85149"
BUY_COLOR  = "#3fb950"
FAST_LINE  = "#f0883e"
PRIMARY_LABEL = "15m Exec"
FAST_LABEL = "5m Exec"
TITLE_FONT = ("Bahnschrift SemiBold", 26)
SUBTITLE_FONT = ("Segoe UI Variable Display", 11)
CARD_TITLE_FONT = ("Bahnschrift SemiBold", 11)
CARD_VALUE_FONT = ("Bahnschrift SemiBold", 20)
BODY_FONT = ("Segoe UI Variable Text", 10)
MONO_FONT = ("Consolas", 9)
SPLASH_BG = "#05070b"
SPLASH_ACCENT = "#1bd68f"
SPLASH_ALERT = "#ff6b57"
SPLASH_DURATION_MS = 4200


class SplashScreen:
    def __init__(self, root: tk.Tk, on_complete) -> None:
        self.root = root
        self.on_complete = on_complete
        self.start_time = time.perf_counter()
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=SPLASH_BG)

        self.screen_width = self.window.winfo_screenwidth()
        self.screen_height = self.window.winfo_screenheight()
        self.window.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        self.canvas = tk.Canvas(
            self.window,
            bg=SPLASH_BG,
            highlightthickness=0,
            width=self.screen_width,
            height=self.screen_height,
        )
        self.canvas.pack(fill="both", expand=True)

        self._build_static_scene()
        self._create_agents()
        self._animate()

    def _build_static_scene(self) -> None:
        width = self.screen_width
        height = self.screen_height
        self.canvas.create_rectangle(0, 0, width, height, fill=SPLASH_BG, outline="")
        for index in range(24):
            alpha = 18 + index * 4
            color = f"#{alpha:02x}{max(40, alpha + 10):02x}{min(90, alpha + 25):02x}"
            self.canvas.create_line(0, index * height / 24, width, index * height / 24, fill=color)

        self.canvas.create_text(
            width * 0.5,
            height * 0.16,
            text="FPI AGENT MARKET OPEN",
            fill=TEXT,
            font=("Consolas", 34, "bold"),
        )
        self.canvas.create_text(
            width * 0.5,
            height * 0.22,
            text="Autonomous agents scan the world, vote, and route trades before the dashboard opens",
            fill=MUTED,
            font=("Consolas", 15),
        )

        self.board_left = width * 0.68
        self.board_top = height * 0.20
        self.board_right = width * 0.94
        self.board_bottom = height * 0.78
        self.canvas.create_rectangle(
            self.board_left,
            self.board_top,
            self.board_right,
            self.board_bottom,
            outline=BORDER,
            width=2,
            fill="#0d1117",
        )
        self.canvas.create_text(
            (self.board_left + self.board_right) / 2,
            self.board_top + 28,
            text="LIVE ROUTING BOARD",
            fill=TEXT,
            font=("Consolas", 18, "bold"),
        )

        self.trade_rows = []
        tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "PLTR", "SOFI"]
        for index, ticker in enumerate(tickers):
            top = self.board_top + 60 + index * 58
            self.canvas.create_text(self.board_left + 38, top + 12, text=ticker, fill=TEXT, font=("Consolas", 14, "bold"))
            self.canvas.create_rectangle(self.board_left + 78, top, self.board_right - 24, top + 24, outline=BORDER, width=1)
            fill_bar = self.canvas.create_rectangle(self.board_left + 79, top + 1, self.board_left + 140, top + 23, outline="", fill=SPLASH_ACCENT)
            side_text = self.canvas.create_text(self.board_right - 68, top + 12, text="BUY", fill=SPLASH_ACCENT, font=("Consolas", 12, "bold"))
            self.trade_rows.append((fill_bar, side_text, top, ticker))

        self.progress_outline = self.canvas.create_rectangle(
            width * 0.18,
            height * 0.86,
            width * 0.82,
            height * 0.89,
            outline=BORDER,
            width=2,
        )
        self.progress_fill = self.canvas.create_rectangle(
            width * 0.18 + 2,
            height * 0.86 + 2,
            width * 0.18 + 2,
            height * 0.89 - 2,
            outline="",
            fill=SPLASH_ACCENT,
        )
        self.status_text = self.canvas.create_text(
            width * 0.5,
            height * 0.92,
            text="Booting market intelligence and agent mesh...",
            fill=TEXT,
            font=("Consolas", 14),
        )

    def _create_agents(self) -> None:
        width = self.screen_width
        height = self.screen_height
        ticker_choices = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "PLTR", "SOFI"]
        self.agents = []
        for _ in range(28):
            x = random.uniform(width * 0.08, width * 0.58)
            y = random.uniform(height * 0.28, height * 0.80)
            radius = random.uniform(14, 22)
            color = SPLASH_ACCENT if random.random() > 0.35 else BLUE
            oval = self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="")
            label = self.canvas.create_text(x, y, text="FPI", fill=BG, font=("Consolas", 10, "bold"))
            ticker = self.canvas.create_text(x, y + 28, text=random.choice(ticker_choices), fill=TEXT, font=("Consolas", 9, "bold"))
            trail = self.canvas.create_line(x, y, x + random.uniform(80, 140), y + random.uniform(-50, 50), fill="#103a2d")
            self.agents.append(
                {
                    "x": x,
                    "y": y,
                    "radius": radius,
                    "vx": random.uniform(1.2, 2.6),
                    "vy": random.uniform(-0.9, 0.9),
                    "phase": random.uniform(0.0, math.pi * 2.0),
                    "oval": oval,
                    "label": label,
                    "ticker": ticker,
                    "trail": trail,
                    "symbol": self.canvas.itemcget(ticker, "text"),
                }
            )

    def _animate(self) -> None:
        elapsed_ms = (time.perf_counter() - self.start_time) * 1000.0
        progress = min(1.0, elapsed_ms / SPLASH_DURATION_MS)
        self._draw_frame(progress)
        if progress >= 1.0:
            self.window.destroy()
            self.on_complete()
            return
        self.window.after(33, self._animate)

    def _draw_frame(self, progress: float) -> None:
        width = self.screen_width
        height = self.screen_height
        left = width * 0.18 + 2
        right = width * 0.82 - 2
        top = height * 0.86 + 2
        bottom = height * 0.89 - 2
        current = left + (right - left) * progress
        self.canvas.coords(self.progress_fill, left, top, current, bottom)

        if progress < 0.33:
            status = "Scanning news feeds, sector momentum, and market pressure..."
        elif progress < 0.66:
            status = "FPI agents are negotiating buys and sells across the board..."
        else:
            status = "Opening full-screen trading dashboard..."
        self.canvas.itemconfigure(self.status_text, text=status)

        pulse = 0.5 + 0.5 * math.sin(progress * math.pi * 10.0)
        for index, agent in enumerate(self.agents):
            drift = math.sin(progress * math.pi * 6.0 + agent["phase"]) * 1.2
            agent["x"] += agent["vx"]
            agent["y"] += agent["vy"] + drift * 0.04
            if agent["x"] > width * 0.62:
                agent["x"] = width * 0.08
            if agent["y"] < height * 0.26 or agent["y"] > height * 0.82:
                agent["vy"] *= -1
            x = agent["x"]
            y = agent["y"]
            radius = agent["radius"] + pulse * 1.5
            self.canvas.coords(agent["oval"], x - radius, y - radius, x + radius, y + radius)
            self.canvas.coords(agent["label"], x, y)
            self.canvas.coords(agent["ticker"], x, y + 28)

            target_x = self.board_left + 90 + (index % 3) * 20
            target_y = self.board_top + 70 + (index % 8) * 58
            self.canvas.coords(agent["trail"], x + radius, y, target_x, target_y)
            self.canvas.itemconfigure(agent["trail"], fill="#1b6d54" if index % 2 == 0 else "#5b2b28")

        for index, (fill_bar, side_text, row_top, _ticker) in enumerate(self.trade_rows):
            magnitude = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(progress * math.pi * 8.0 + index * 0.7))
            color = SPLASH_ACCENT if index % 3 != 0 else SPLASH_ALERT
            action = "BUY" if color == SPLASH_ACCENT else "SELL"
            self.canvas.coords(fill_bar, self.board_left + 79, row_top + 1, self.board_left + 79 + magnitude * 165, row_top + 23)
            self.canvas.itemconfigure(fill_bar, fill=color)
            self.canvas.itemconfigure(side_text, text=action, fill=color)


class TradingApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Agent Trading Compare")
        self.root.configure(bg=BG)
        self.root.minsize(1050, 700)

        self._queue: queue.Queue = queue.Queue()
        self._engine_thread: threading.Thread | None = None
        self._running = False

        # State
        self._initial_cash = 500.0
        self._agent_count  = 1000
        self._chart_times: list = []
        self._chart_values: list = []
        self._chart_values_fast: list = []
        self._latest_fast_result: CycleResult | None = None
        self._world_summary = "World feed idle"
        self._chart_view_suffixes: list[str] = []
        self._compare_suffixes: list[str] = []
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
            rowheight=24, borderwidth=0, font=MONO_FONT,
        )
        style.configure("Treeview.Heading",
            background=PANEL_ALT, foreground=SOFT_TEXT, font=("Bahnschrift SemiBold", 9),
        )
        style.map("Treeview",
            background=[("selected", BLUE)],
            foreground=[("selected", BG)],
        )
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=BODY_FONT)
        style.configure("TButton",
            background=PANEL_ALT, foreground=TEXT, bordercolor=BORDER, padding=8, font=("Bahnschrift SemiBold", 10),
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
        style.configure("TNotebook", background=BG, bordercolor=BORDER, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background=PANEL_SOFT, foreground=MUTED, padding=(16, 10), font=("Bahnschrift SemiBold", 10))
        style.map("TNotebook.Tab",
            background=[("selected", PANEL_ALT)],
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
        hdr = tk.Frame(self.root, bg=BG)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        hdr.columnconfigure(0, weight=3)
        hdr.columnconfigure(1, weight=5)

        title_card = tk.Frame(hdr, bg=PANEL_ALT, highlightbackground=BORDER, highlightthickness=1)
        title_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._dot = tk.Label(title_card, text="●", font=("Consolas", 16), bg=PANEL_ALT, fg=RED)
        self._dot.grid(row=0, column=0, padx=(18, 8), pady=(18, 4), sticky="w")
        tk.Label(title_card, text="FPI Market Theater", font=TITLE_FONT,
                 bg=PANEL_ALT, fg=TEXT).grid(row=0, column=1, padx=(0, 16), pady=(16, 2), sticky="w")
        tk.Label(
            title_card,
            text="A cinematic trading deck that compares two execution rhythms on the same market tape.",
            font=SUBTITLE_FONT,
            bg=PANEL_ALT,
            fg=SOFT_TEXT,
        ).grid(row=1, column=0, columnspan=2, padx=18, pady=(0, 12), sticky="w")
        self._lbl_countdown = tk.Label(title_card, text="", font=("Bahnschrift SemiBold", 10), bg=PANEL_ALT, fg=YELLOW)
        self._lbl_countdown.grid(row=2, column=0, columnspan=2, padx=18, pady=(0, 16), sticky="w")

        stats_wrap = tk.Frame(hdr, bg=BG)
        stats_wrap.grid(row=0, column=1, sticky="nsew")
        for col in range(3):
            stats_wrap.columnconfigure(col, weight=1)
        for row in range(2):
            stats_wrap.rowconfigure(row, weight=1)

        cards = [
            (PRIMARY_LABEL, "_lbl_value", TEXT),
            (FAST_LABEL, "_lbl_fast_value", ORANGE),
            ("Lead", "_lbl_compare", GREEN),
            ("Cycle", "_lbl_cycle", BLUE),
            ("Regime", "_lbl_regime", YELLOW),
            ("Learn", "_lbl_learn", CYAN),
        ]
        for index, (label, attr, color) in enumerate(cards):
            card = tk.Frame(stats_wrap, bg=PANEL_SOFT, highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=5, pady=5)
            tk.Label(card, text=label, font=CARD_TITLE_FONT, bg=PANEL_SOFT, fg=MUTED).pack(anchor="w", padx=14, pady=(12, 4))
            lbl = tk.Label(card, text="—", font=CARD_VALUE_FONT, bg=PANEL_SOFT, fg=color)
            lbl.pack(anchor="w", padx=14, pady=(0, 12))
            setattr(self, attr, lbl)

    def _build_body(self) -> None:
        body = tk.Frame(self.root, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        notebook = ttk.Notebook(body)
        notebook.grid(row=0, column=0, sticky="nsew")
        self._build_dashboard_tab(notebook, PRIMARY_LABEL, "_15", "_tab15")
        self._build_dashboard_tab(notebook, FAST_LABEL, "_5", "_tab5")

    def _build_dashboard_tab(self, notebook: ttk.Notebook, title: str, strategy_suffix: str, dashboard_suffix: str) -> None:
        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text=f"  {title}  ")
        tab.rowconfigure(0, weight=5)
        tab.rowconfigure(1, weight=3)
        tab.columnconfigure(0, weight=5)
        tab.columnconfigure(1, weight=4)

        chart_frame = tk.Frame(tab, bg=PANEL_ALT, bd=0, highlightbackground=BORDER, highlightthickness=1)
        chart_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        self._build_chart(chart_frame, dashboard_suffix)

        compare_frame = self._panel(tab, "Storyline", row=1, col=0)
        self._build_compare(compare_frame, dashboard_suffix)

        strategy_frame = self._panel(tab, title, row=0, col=1)
        strategy_frame.grid_configure(rowspan=2, sticky="nsew")
        tab.grid_rowconfigure(0, weight=5)
        self._build_strategy_panel(strategy_frame, title, strategy_suffix)

    def _panel(self, parent, title: str, row: int, col: int) -> tk.Frame:
        outer = tk.Frame(parent, bg=PANEL_SOFT, bd=0, highlightbackground=BORDER, highlightthickness=1)
        outer.grid(row=row, column=col, sticky="nsew", padx=(2, 4), pady=4)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)
        tk.Label(outer, text=f"  {title}", font=("Bahnschrift SemiBold", 10),
                 bg=PANEL_SOFT, fg=SOFT_TEXT, anchor="w").grid(row=0, column=0, sticky="ew", pady=(10, 4))
        inner = tk.Frame(outer, bg=PANEL_SOFT)
        inner.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)
        return inner

    def _build_chart(self, parent: tk.Frame, suffix: str) -> None:
        tk.Label(parent, text="  Portfolio Comparison", font=("Bahnschrift SemiBold", 11),
                 bg=PANEL_ALT, fg=SOFT_TEXT, anchor="w").pack(fill="x", pady=(10, 0), padx=8)
        chart_caption = tk.Label(parent, text="Two execution stories evolving on the same live market tape", font=SUBTITLE_FONT,
                                 bg=PANEL_ALT, fg=MUTED, anchor="w")
        chart_caption.pack(fill="x", padx=10, pady=(0, 6))
        setattr(self, f"_chart_caption{suffix}", chart_caption)

        fig = Figure(figsize=(5, 4), dpi=96, facecolor=PANEL_ALT)
        ax = fig.add_subplot(111)
        ax.set_facecolor(BG)
        fig.subplots_adjust(left=0.12, right=0.97, top=0.93, bottom=0.15)

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=(0, 4))
        setattr(self, f"_fig{suffix}", fig)
        setattr(self, f"_ax{suffix}", ax)
        setattr(self, f"_canvas{suffix}", canvas)
        self._chart_view_suffixes.append(suffix)
        self._redraw_chart()

    def _build_strategy_panel(self, parent: tk.Frame, title: str, suffix: str) -> None:
        parent.rowconfigure(1, weight=3)
        parent.rowconfigure(2, weight=4)
        parent.columnconfigure(0, weight=1)

        hero = tk.Frame(parent, bg=PANEL_ALT, highlightbackground=BORDER, highlightthickness=1)
        hero.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 8))
        hero.columnconfigure(0, weight=2)
        hero.columnconfigure(1, weight=3)

        tk.Label(hero, text=title, font=("Bahnschrift SemiBold", 18), bg=PANEL_ALT, fg=TEXT).grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")
        headline = tk.Label(hero, text="P&L — | Cash —", font=("Bahnschrift SemiBold", 12), bg=PANEL_ALT, fg=CYAN)
        headline.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="w")
        setattr(self, f"_strategy_headline{suffix}", headline)
        subline = tk.Label(hero, text="Waiting for first cycle", font=SUBTITLE_FONT, bg=PANEL_ALT, fg=MUTED)
        subline.grid(row=0, column=1, rowspan=2, padx=16, pady=(14, 14), sticky="e")
        setattr(self, f"_strategy_subline{suffix}", subline)

        top_grid = tk.Frame(parent, bg=PANEL_SOFT)
        top_grid.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        top_grid.rowconfigure(0, weight=1)
        top_grid.columnconfigure(0, weight=3)
        top_grid.columnconfigure(1, weight=2)

        hold_card = tk.Frame(top_grid, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        hold_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tk.Label(hold_card, text="Holdings", font=("Bahnschrift SemiBold", 10), bg=PANEL, fg=SOFT_TEXT).pack(anchor="w", padx=10, pady=(10, 4))
        hold_body = tk.Frame(hold_card, bg=PANEL)
        hold_body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_holdings(hold_body, "_tree_hold" if suffix == "_15" else "_tree_hold_fast")

        vote_card = tk.Frame(top_grid, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        vote_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        tk.Label(vote_card, text="Vote Snapshot", font=("Bahnschrift SemiBold", 10), bg=PANEL, fg=SOFT_TEXT).pack(anchor="w", padx=10, pady=(10, 4))
        vote_body = tk.Frame(vote_card, bg=PANEL)
        vote_body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_votes(vote_body, "_tree_vote" if suffix == "_15" else "_tree_vote_fast")

        log_card = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        log_card.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        tk.Label(log_card, text="Trade Narrative", font=("Bahnschrift SemiBold", 10), bg=PANEL, fg=SOFT_TEXT).pack(anchor="w", padx=10, pady=(10, 4))
        log_body = tk.Frame(log_card, bg=PANEL)
        log_body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_log(log_body, "_log" if suffix == "_15" else "_log_fast")

    def _build_holdings(self, parent: tk.Frame, attr_name: str) -> None:
        cols = ("Symbol", "Qty", "Avg $", "Price $", "Value $", "P&L")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=7)
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=60, anchor="center")
        tree.column("Symbol", width=55, anchor="center")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        setattr(self, attr_name, tree)

    def _build_compare(self, parent: tk.Frame, suffix: str) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        cards = [
            (PRIMARY_LABEL, "_cmp_15m", TEXT),
            (FAST_LABEL, "_cmp_5m", ORANGE),
            ("Winner", "_cmp_winner", GREEN),
            ("Gap", "_cmp_gap", BLUE),
        ]
        for index, (title, attr, color) in enumerate(cards):
            frame = tk.Frame(parent, bg=PANEL_ALT if index < 2 else PANEL_SOFT, highlightbackground=BORDER, highlightthickness=1)
            frame.grid(row=index // 2, column=index % 2, sticky="nsew", padx=4, pady=4)
            bg_color = PANEL_ALT if index < 2 else PANEL_SOFT
            tk.Label(frame, text=title, font=CARD_TITLE_FONT, bg=bg_color, fg=MUTED).pack(anchor="w", padx=12, pady=(10, 2))
            label = tk.Label(frame, text="—", font=("Bahnschrift SemiBold", 22), bg=bg_color, fg=color)
            label.pack(anchor="w", padx=12, pady=(0, 12))
            setattr(self, f"{attr}{suffix}", label)
        self._compare_suffixes.append(suffix)

    def _build_votes(self, parent: tk.Frame, attr_name: str) -> None:
        cols = ("Symbol", "Buy%", "Sell%", "Signal")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=6)
        widths = {"Symbol": 60, "Buy%": 55, "Sell%": 55, "Signal": 80}
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=widths.get(c, 60), anchor="center")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        tree.tag_configure("buy",  foreground=GREEN)
        tree.tag_configure("sell", foreground=RED)
        tree.tag_configure("hold", foreground=MUTED)
        setattr(self, attr_name, tree)

    def _build_log(self, parent: tk.Frame, attr_name: str) -> None:
        log_widget = tk.Text(parent, bg=BG, fg=TEXT, font=("Consolas", 9),
                             insertbackground=TEXT, wrap="none", state="disabled", relief="flat")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=log_widget.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=log_widget.xview)
        log_widget.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        log_widget.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        log_widget.tag_configure("buy",   foreground=GREEN)
        log_widget.tag_configure("sell",  foreground=RED)
        log_widget.tag_configure("cycle", foreground=BLUE)
        log_widget.tag_configure("muted", foreground=MUTED)
        log_widget.tag_configure("warn",  foreground=YELLOW)
        setattr(self, attr_name, log_widget)

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
        self._ent_agents.insert(0, "1000")
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
        for suffix in self._chart_view_suffixes:
            fig = getattr(self, f"_fig{suffix}")
            ax = getattr(self, f"_ax{suffix}")
            canvas = getattr(self, f"_canvas{suffix}")

            ax.clear()
            ax.set_facecolor(BG)

            for spine in ax.spines.values():
                spine.set_edgecolor(BORDER)
            ax.tick_params(colors=MUTED, labelsize=8)
            ax.xaxis.label.set_color(MUTED)
            ax.yaxis.label.set_color(MUTED)

            if len(self._chart_times) > 1:
                baseline = self._chart_values[0]
                ax.fill_between(self._chart_times, self._chart_values, baseline,
                                alpha=0.12,
                                color=GREEN if self._chart_values[-1] >= baseline else RED)
                ax.plot(self._chart_times, self._chart_values,
                        color=CHART_LINE if self._chart_values[-1] >= baseline else RED,
                        linewidth=2.0, zorder=5, label=PRIMARY_LABEL)
                if len(self._chart_values_fast) == len(self._chart_times):
                    ax.plot(self._chart_times, self._chart_values_fast,
                            color=FAST_LINE, linewidth=1.8, zorder=6, label=FAST_LABEL)
                ax.axhline(y=baseline, color=BORDER, linestyle="--", linewidth=0.8)
                ax.axhline(y=self._chart_values[-1], color=CHART_LINE if self._chart_values[-1] >= baseline else RED,
                           linewidth=0.5, alpha=0.4)
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
                ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                ax.legend(loc="upper left", facecolor=PANEL, edgecolor=BORDER, labelcolor=TEXT, fontsize=8)
                fig.autofmt_xdate(rotation=25, ha="right")
            else:
                ax.text(0.5, 0.5, "Waiting for first cycle…", transform=ax.transAxes,
                        ha="center", va="center", color=MUTED, fontsize=10)
                ax.set_xticks([])
                ax.set_yticks([])

            fig.tight_layout(pad=0.6)
            canvas.draw_idle()

    # ── History loading ──────────────────────────────────────────────────────

    def _load_history(self) -> None:
        rows = self._db.load_snapshots(limit=500)
        if rows:
            for ts_str, cycle, value, cash, pnl_pct in rows:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    self._chart_times.append(dt)
                    self._chart_values.append(value)
                    self._chart_values_fast.append(value)
                except ValueError:
                    pass
            self._redraw_chart()

        trades = self._db.load_trades(limit=200)
        for row in reversed(trades):
            self._append_trade_to_log(self._log, *row, from_history=True)

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
        self._chart_values_fast = []
        self._latest_fast_result = None
        self._session_id    = self._db.start_session(cash, agents)

        self._running = True
        self._btn_start.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._dot.config(fg=GREEN)
        self._lbl_cycle.config(text="0")
        self._lbl_value.config(text="—")
        self._lbl_fast_value.config(text="—")
        self._lbl_compare.config(text="—", fg=TEXT)
        for suffix in self._compare_suffixes:
            getattr(self, f"_cmp_15m{suffix}").config(text="—", fg=TEXT)
            getattr(self, f"_cmp_5m{suffix}").config(text="—", fg=ORANGE)
            getattr(self, f"_cmp_winner{suffix}").config(text="—", fg=TEXT)
            getattr(self, f"_cmp_gap{suffix}").config(text="—", fg=BLUE)
        self._strategy_headline_15.config(text="P&L — | Cash —", fg=CYAN)
        self._strategy_headline_5.config(text="P&L — | Cash —", fg=CYAN)
        self._strategy_subline_15.config(text="Waiting for first cycle")
        self._strategy_subline_5.config(text="Waiting for first cycle")
        for suffix in self._chart_view_suffixes:
            getattr(self, f"_chart_caption{suffix}").config(text="Two execution stories evolving on the same live market tape")
        self._clear_log(self._log)
        self._clear_log(self._log_fast)
        self._clear_tree(self._tree_hold)
        self._clear_tree(self._tree_hold_fast)
        self._clear_tree(self._tree_vote)
        self._clear_tree(self._tree_vote_fast)

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
        base_agents = AgentFactory.build_population(agent_count, persisted_state=persisted_agents)
        base_states = [deepcopy(agent.to_state()) for agent in base_agents]
        engine = VotingTradingEngine(
            agents=AgentFactory.build_population(agent_count, persisted_state=deepcopy(base_states)),
            initial_cash=cash,
            decision_interval_cycles=DECISION_INTERVAL_CYCLES,
        )
        fast_engine = VotingTradingEngine(
            agents=AgentFactory.build_population(agent_count, persisted_state=deepcopy(base_states)),
            initial_cash=cash,
            decision_interval_cycles=1,
        )
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
            fast_result = fast_engine.execute_cycle(
                signals=signals,
                vote_threshold=FAST_ACTION_THRESHOLD,
                cycle_num=cycle_index,
                universe=symbols,
                execute_trades=True,
            )
            self._queue.put(("cycle", result, fast_result, market.last_world_summary))

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
                if isinstance(item, tuple) and item and item[0] == "cycle":
                    self._handle_cycle(item[1], item[2], item[3])
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

    def _handle_cycle(self, result: CycleResult, fast_result: CycleResult, world_summary: str) -> None:
        self._world_summary = world_summary
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
        self._chart_values_fast.append(fast_result.portfolio_value)
        self._latest_fast_result = fast_result
        self._redraw_chart()

        # Header stats
        pnl = result.portfolio_value - self._initial_cash
        pnl_pct = pnl / max(1e-9, self._initial_cash) * 100.0
        fast_pnl = fast_result.portfolio_value - self._initial_cash
        fast_pnl_pct = fast_pnl / max(1e-9, self._initial_cash) * 100.0
        lead_pct = pnl_pct - fast_pnl_pct
        if lead_pct > 0.01:
            leader_text = f"{PRIMARY_LABEL} +{lead_pct:.2f}%"
            leader_color = GREEN
            winner_text = PRIMARY_LABEL
        elif lead_pct < -0.01:
            leader_text = f"{FAST_LABEL} +{abs(lead_pct):.2f}%"
            leader_color = ORANGE
            winner_text = FAST_LABEL
        else:
            leader_text = "Tie"
            leader_color = BLUE
            winner_text = "Tie"
        self._lbl_value.config(text=f"{pnl_pct:+.2f}%", fg=GREEN if pnl >= 0 else RED)
        self._lbl_fast_value.config(text=f"{fast_pnl_pct:+.2f}%", fg=GREEN if fast_pnl >= 0 else RED)
        self._lbl_compare.config(text=leader_text, fg=leader_color)
        self._lbl_cycle.config(text=str(result.cycle))
        self._lbl_regime.config(text=result.market_regime.replace("_", " "))
        perf = result.performance_summary
        learn_text = (
            f"W {perf.get('win_rate', 0.0):.0%} | DD {perf.get('max_drawdown', 0.0):.1%}"
        )
        self._lbl_learn.config(text=learn_text)
        for suffix in self._compare_suffixes:
            getattr(self, f"_cmp_15m{suffix}").config(text=f"{pnl_pct:+.2f}%", fg=GREEN if pnl >= 0 else RED)
            getattr(self, f"_cmp_5m{suffix}").config(text=f"{fast_pnl_pct:+.2f}%", fg=GREEN if fast_pnl >= 0 else RED)
            getattr(self, f"_cmp_winner{suffix}").config(text=winner_text, fg=leader_color)
            getattr(self, f"_cmp_gap{suffix}").config(text=f"{abs(lead_pct):.2f}%", fg=leader_color)
        self._strategy_headline_15.config(text=f"P&L {pnl_pct:+.2f}%  |  Cash ${result.cash:,.0f}", fg=GREEN if pnl >= 0 else RED)
        self._strategy_headline_5.config(text=f"P&L {fast_pnl_pct:+.2f}%  |  Cash ${fast_result.cash:,.0f}", fg=GREEN if fast_pnl >= 0 else RED)
        self._strategy_subline_15.config(text=f"Regime: {result.market_regime.replace('_', ' ')}  |  {world_summary}")
        self._strategy_subline_5.config(text=f"Regime: {fast_result.market_regime.replace('_', ' ')}  |  {world_summary}")
        for suffix in self._chart_view_suffixes:
            getattr(self, f"_chart_caption{suffix}").config(text=f"Live world context: {world_summary}")

        # Holdings table
        self._update_holdings(result, self._tree_hold)
        self._update_holdings(fast_result, self._tree_hold_fast)

        # Vote table
        self._update_votes(result, self._tree_vote)
        self._update_votes(fast_result, self._tree_vote_fast)

        # Log
        self._log_cycle_header(result, self._log)
        self._log_cycle_header(fast_result, self._log_fast)
        for message in result.messages:
            if message.startswith("Stats:"):
                self._log_write(self._log, f"    {message}\n", "warn")
            elif message.startswith("Mode:"):
                self._log_write(self._log, f"    {message}\n", "cycle")
            elif message.startswith("Portfolio value:"):
                self._log_write(self._log, f"    {message}\n", "muted")
        for message in fast_result.messages:
            if message.startswith("Stats:"):
                self._log_write(self._log_fast, f"    {message}\n", "warn")
            elif message.startswith("Mode:"):
                self._log_write(self._log_fast, f"    {message}\n", "cycle")
            elif message.startswith("Portfolio value:"):
                self._log_write(self._log_fast, f"    {message}\n", "muted")
        for t in result.trades:
            self._append_trade_to_log(
                self._log,
                result.timestamp.isoformat(), result.cycle,
                t.action, t.symbol, t.qty, t.amount, t.price, t.vote_ratio,
            )
        for t in fast_result.trades:
            self._append_trade_to_log(
                self._log_fast,
                fast_result.timestamp.isoformat(), fast_result.cycle,
                t.action, t.symbol, t.qty, t.amount, t.price, t.vote_ratio,
            )
        if not result.trades:
            self._log_write(self._log, "    — no trades this cycle\n", "muted")
        if not fast_result.trades:
            self._log_write(self._log_fast, "    — no trades this cycle\n", "muted")

    def _update_holdings(self, result: CycleResult, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

        for symbol, h in sorted(result.holdings.items(), key=lambda x: x[0]):
            current_price = result.prices.get(symbol, 0.0)
            value         = h.qty * current_price
            pnl_pct       = (current_price / max(1e-9, h.avg_price) - 1.0) * 100.0
            pnl_str       = f"{'+'if pnl_pct>=0 else ''}{pnl_pct:.1f}%"
            tag           = "pos" if pnl_pct >= 0 else "neg"
            tree.insert("", "end", values=(
                symbol,
                f"{h.qty:.3f}",
                f"{h.avg_price:.2f}",
                f"{current_price:.2f}",
                f"{value:.2f}",
                pnl_str,
            ), tags=(tag,))

        tree.tag_configure("pos", foreground=GREEN)
        tree.tag_configure("neg", foreground=RED)

    def _update_votes(self, result: CycleResult, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

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

            tree.insert("", "end", values=(
                symbol,
                f"{buy_pct:.0f}%",
                f"{sell_pct:.0f}%",
                signal,
            ), tags=(tag,))

    # ── Log helpers ──────────────────────────────────────────────────────────

    def _log_cycle_header(self, result: CycleResult, target_log: tk.Text) -> None:
        ts  = result.timestamp.strftime("%H:%M:%S")
        uni = ", ".join(result.universe) if result.universe else "—"
        regime = result.market_regime.replace("_", " ")
        leader = result.learning_summary.get("leader_personality", "balanced")
        pnl_pct = (result.portfolio_value / max(1e-9, self._initial_cash) - 1.0) * 100.0
        self._log_write(
            target_log,
            f"\n[{ts}] Cycle {result.cycle}  |  {regime}  |  leader={leader}  |  P&L={pnl_pct:+.2f}%  |  {uni}\n",
            "cycle",
        )

    def _append_trade_to_log(
        self,
        target_log: tk.Text,
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
        self._log_write(target_log, line, tag)

    def _log_write(self, target_log: tk.Text, text: str, tag: str = "") -> None:
        target_log.config(state="normal")
        target_log.insert("end", text, tag)
        target_log.see("end")
        target_log.config(state="disabled")

    def _clear_log(self, target_log: tk.Text) -> None:
        target_log.config(state="normal")
        target_log.delete("1.0", "end")
        target_log.config(state="disabled")

    def _clear_tree(self, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    root.geometry("1400x900")
    root.state("zoomed")
    root.attributes("-fullscreen", True)
    root.bind("<Escape>", lambda _event: root.attributes("-fullscreen", False))
    root.bind("<F11>", lambda _event: root.attributes("-fullscreen", not bool(root.attributes("-fullscreen"))))
    app = TradingApp(root)

    def show_main_window() -> None:
        root.deiconify()
        root.lift()
        root.focus_force()

    SplashScreen(root, show_main_window)
    root.mainloop()


if __name__ == "__main__":
    main()
