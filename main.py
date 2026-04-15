import argparse
import copy
import math
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import pandas as pd
import requests


TOP_10_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "JPM",
    "LLY",
    "AVGO",
]

RISK_POOL = ["PLTR", "SOFI", "UPST", "IONQ", "RIOT", "MARA", "RKLB", "HIMS"]
FEATURE_KEYS = [
    "momentum",
    "swing",
    "volatility",
    "mean_reversion",
    "breakout",
    "quality",
    "news_sentiment",
    "news_volume",
    "news_urgency",
    "macro_pressure",
    "peer_momentum",
]
MARKET_REGIMES = ["bull_trend", "risk_off", "range_bound", "volatile_trend", "mixed"]
ACTION_THRESHOLD = 0.60
FAST_ACTION_THRESHOLD = 0.46
# Tradier pricing model (stocks):
# - Pro plan: $10/month subscription + $0 per stock trade.
# - Regular plan: $0.35 per trade.
TRADIER_PRO_ENABLED = True
TRADIER_PRO_MONTHLY_FEE_USD = 10.0
TRADIER_REGULAR_FEE_PER_TRADE_USD = 0.35
SECONDS_PER_30_DAY_MONTH = 30 * 24 * 60 * 60
DECISION_INTERVAL_CYCLES = 3  # 3 vote rounds x 5m = 15m final trading decision
NEWS_CACHE_SECONDS = 900
MACRO_CACHE_SECONDS = 1800
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

PERSONALITY_WEIGHTS = {
    "risk_seeker": 0.14,
    "risk_averse": 0.14,
    "trend_follower": 0.14,
    "contrarian": 0.13,
    "mean_reversion": 0.13,
    "breakout_chaser": 0.12,
    "volatility_surfer": 0.10,
    "balanced": 0.10,
}

PERSONALITY_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "risk_seeker": {
        "risk_appetite": 0.86,
        "discipline": 0.40,
        "adaptability": 0.82,
        "confidence": 0.86,
        "exploration": 0.16,
        "learning_rate": 0.09,
        "strategy_weights": {
            "momentum": 1.35,
            "swing": 0.95,
            "volatility": 0.70,
            "mean_reversion": -0.20,
            "breakout": 1.15,
            "quality": 0.25,
            "news_sentiment": 0.55,
            "news_volume": 0.12,
            "news_urgency": 0.30,
            "macro_pressure": -0.20,
            "peer_momentum": 0.70,
        },
    },
    "risk_averse": {
        "risk_appetite": 0.24,
        "discipline": 0.92,
        "adaptability": 0.58,
        "confidence": 0.54,
        "exploration": 0.07,
        "learning_rate": 0.06,
        "strategy_weights": {
            "momentum": 0.55,
            "swing": 0.90,
            "volatility": -1.45,
            "mean_reversion": 0.35,
            "breakout": 0.15,
            "quality": 1.05,
            "news_sentiment": 0.35,
            "news_volume": 0.08,
            "news_urgency": -0.55,
            "macro_pressure": -0.75,
            "peer_momentum": 0.25,
        },
    },
    "trend_follower": {
        "risk_appetite": 0.62,
        "discipline": 0.72,
        "adaptability": 0.74,
        "confidence": 0.66,
        "exploration": 0.10,
        "learning_rate": 0.08,
        "strategy_weights": {
            "momentum": 1.20,
            "swing": 1.10,
            "volatility": -0.20,
            "mean_reversion": -0.35,
            "breakout": 0.85,
            "quality": 0.60,
            "news_sentiment": 0.42,
            "news_volume": 0.10,
            "news_urgency": 0.10,
            "macro_pressure": -0.25,
            "peer_momentum": 0.95,
        },
    },
    "contrarian": {
        "risk_appetite": 0.50,
        "discipline": 0.76,
        "adaptability": 0.72,
        "confidence": 0.58,
        "exploration": 0.11,
        "learning_rate": 0.08,
        "strategy_weights": {
            "momentum": -0.85,
            "swing": 0.30,
            "volatility": -0.15,
            "mean_reversion": 1.15,
            "breakout": -0.35,
            "quality": 0.55,
            "news_sentiment": -0.18,
            "news_volume": 0.05,
            "news_urgency": -0.12,
            "macro_pressure": 0.10,
            "peer_momentum": -0.35,
        },
    },
    "mean_reversion": {
        "risk_appetite": 0.46,
        "discipline": 0.78,
        "adaptability": 0.76,
        "confidence": 0.62,
        "exploration": 0.10,
        "learning_rate": 0.08,
        "strategy_weights": {
            "momentum": -0.45,
            "swing": 0.15,
            "volatility": -0.30,
            "mean_reversion": 1.30,
            "breakout": -0.20,
            "quality": 0.50,
            "news_sentiment": -0.10,
            "news_volume": 0.05,
            "news_urgency": -0.18,
            "macro_pressure": 0.05,
            "peer_momentum": -0.28,
        },
    },
    "breakout_chaser": {
        "risk_appetite": 0.78,
        "discipline": 0.52,
        "adaptability": 0.80,
        "confidence": 0.82,
        "exploration": 0.15,
        "learning_rate": 0.09,
        "strategy_weights": {
            "momentum": 1.00,
            "swing": 0.70,
            "volatility": 0.20,
            "mean_reversion": -0.50,
            "breakout": 1.40,
            "quality": 0.25,
            "news_sentiment": 0.60,
            "news_volume": 0.22,
            "news_urgency": 0.35,
            "macro_pressure": -0.15,
            "peer_momentum": 0.88,
        },
    },
    "volatility_surfer": {
        "risk_appetite": 0.72,
        "discipline": 0.48,
        "adaptability": 0.84,
        "confidence": 0.72,
        "exploration": 0.18,
        "learning_rate": 0.10,
        "strategy_weights": {
            "momentum": 0.70,
            "swing": 0.45,
            "volatility": 1.20,
            "mean_reversion": -0.20,
            "breakout": 0.85,
            "quality": 0.10,
            "news_sentiment": 0.22,
            "news_volume": 0.28,
            "news_urgency": 0.52,
            "macro_pressure": -0.35,
            "peer_momentum": 0.55,
        },
    },
    "balanced": {
        "risk_appetite": 0.52,
        "discipline": 0.78,
        "adaptability": 0.70,
        "confidence": 0.60,
        "exploration": 0.09,
        "learning_rate": 0.07,
        "strategy_weights": {
            "momentum": 0.75,
            "swing": 0.75,
            "volatility": -0.45,
            "mean_reversion": 0.30,
            "breakout": 0.35,
            "quality": 0.85,
            "news_sentiment": 0.35,
            "news_volume": 0.08,
            "news_urgency": 0.05,
            "macro_pressure": -0.30,
            "peer_momentum": 0.45,
        },
    },
}

BASE_REGIME_SKILL = {
    "risk_seeker": {"bull_trend": 0.55, "risk_off": -0.35, "range_bound": -0.05, "volatile_trend": 0.60, "mixed": 0.10},
    "risk_averse": {"bull_trend": 0.10, "risk_off": 0.55, "range_bound": 0.25, "volatile_trend": -0.50, "mixed": 0.15},
    "trend_follower": {"bull_trend": 0.70, "risk_off": -0.30, "range_bound": -0.15, "volatile_trend": 0.35, "mixed": 0.15},
    "contrarian": {"bull_trend": -0.10, "risk_off": 0.10, "range_bound": 0.60, "volatile_trend": -0.20, "mixed": 0.25},
    "mean_reversion": {"bull_trend": -0.10, "risk_off": 0.20, "range_bound": 0.75, "volatile_trend": -0.25, "mixed": 0.20},
    "breakout_chaser": {"bull_trend": 0.60, "risk_off": -0.45, "range_bound": -0.30, "volatile_trend": 0.70, "mixed": 0.10},
    "volatility_surfer": {"bull_trend": 0.20, "risk_off": -0.15, "range_bound": -0.20, "volatile_trend": 0.85, "mixed": 0.10},
    "balanced": {"bull_trend": 0.25, "risk_off": 0.10, "range_bound": 0.20, "volatile_trend": -0.05, "mixed": 0.30},
}

SYMBOL_NEWS_QUERIES = {
    "AAPL": "Apple stock",
    "MSFT": "Microsoft stock",
    "NVDA": "NVIDIA stock AI chips",
    "AMZN": "Amazon stock cloud retail",
    "GOOGL": "Alphabet Google stock",
    "META": "Meta Platforms stock",
    "TSLA": "Tesla stock",
    "JPM": "JPMorgan stock banking",
    "LLY": "Eli Lilly stock",
    "AVGO": "Broadcom stock",
    "PLTR": "Palantir stock",
    "SOFI": "SoFi stock",
    "UPST": "Upstart stock",
    "IONQ": "IonQ stock",
    "RIOT": "Riot Platforms stock bitcoin mining",
    "MARA": "MARA stock bitcoin mining",
    "RKLB": "Rocket Lab stock",
    "HIMS": "Hims stock",
}
SECTOR_BENCHMARKS = {
    "AAPL": "XLK",
    "MSFT": "XLK",
    "NVDA": "XLK",
    "AMZN": "XLY",
    "GOOGL": "XLK",
    "META": "XLC",
    "TSLA": "XLY",
    "JPM": "XLF",
    "LLY": "XLV",
    "AVGO": "SOXX",
    "PLTR": "XLK",
    "SOFI": "XLF",
    "UPST": "XLF",
    "IONQ": "XLK",
    "RIOT": "IBIT",
    "MARA": "IBIT",
    "RKLB": "ITA",
    "HIMS": "XLV",
}
MACRO_SYMBOLS = ["SPY", "QQQ", "IWM", "TLT", "GLD", "XLK", "XLF", "XLV", "XLY", "SOXX", "IBIT", "ITA", "^VIX"]
POSITIVE_NEWS_TERMS = {
    "beat", "beats", "surge", "surges", "growth", "upgrade", "upgrades", "profit", "profits", "record",
    "strong", "bullish", "win", "wins", "partnership", "launch", "approval", "approved", "guidance raised",
    "buyback", "expands", "expansion", "rebound", "outperform",
}
NEGATIVE_NEWS_TERMS = {
    "miss", "misses", "drop", "drops", "fall", "falls", "downgrade", "downgrades", "lawsuit", "probe",
    "investigation", "recall", "layoffs", "weak", "warning", "cuts", "cut", "plunge", "fraud", "delay",
    "bankruptcy", "risk", "loss", "losses", "decline", "declines", "antitrust", "tariff",
}
URGENT_NEWS_TERMS = {
    "breaking", "urgent", "halts", "halt", "guidance", "sec", "fda", "lawsuit", "probe", "recall",
    "merger", "acquisition", "earnings", "tariff", "ceasefire", "war", "ban", "approval",
}
MACRO_NEWS_QUERY = "stock market inflation rates federal reserve recession earnings when:1d"


def sign(value: float) -> float:
    if value > 0:
        return 1.0
    if value < 0:
        return -1.0
    return 0.0


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class Signal:
    symbol: str
    price: float
    ret_1: float
    ret_6: float
    vol: float
    distance_to_sma20: float
    news_sentiment: float = 0.0
    news_volume: float = 0.0
    news_urgency: float = 0.0
    macro_pressure: float = 0.0
    peer_momentum: float = 0.0
    headline_count: int = 0


@dataclass
class NewsSnapshot:
    sentiment: float = 0.0
    volume_score: float = 0.0
    urgency_bias: float = 0.0
    headline_count: int = 0
    top_headline: str = ""


@dataclass
class MacroSnapshot:
    market_pressure: float = 0.0
    benchmark_returns: Dict[str, float] = field(default_factory=dict)
    headline_bias: float = 0.0
    summary: str = "neutral"


@dataclass
class Holding:
    qty: float
    avg_price: float


@dataclass
class TradeRecord:
    action: str
    symbol: str
    qty: float
    amount: float
    price: float
    vote_ratio: float
    fee: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class CycleResult:
    cycle: int
    timestamp: datetime
    trades: List[TradeRecord]
    portfolio_value: float
    cash: float
    holdings: Dict[str, Holding]
    prices: Dict[str, float]
    vote_summary: Dict[str, Dict[str, float]]
    messages: List[str]
    universe: List[str] = field(default_factory=list)
    market_regime: str = "mixed"
    learning_summary: Dict[str, Any] = field(default_factory=dict)
    performance_summary: Dict[str, float] = field(default_factory=dict)
    agent_state: List[Dict[str, Any]] = field(default_factory=list)


class Portfolio:
    def __init__(self, cash: float) -> None:
        self.cash = cash
        self.holdings: Dict[str, Holding] = {}

    def buy(self, symbol: str, price: float, amount_usd: float) -> float:
        amount_usd = min(amount_usd, self.cash)
        if amount_usd <= 0 or price <= 0:
            return 0.0

        qty = amount_usd / price
        self.cash -= amount_usd

        if symbol in self.holdings:
            holding = self.holdings[symbol]
            total_cost = holding.qty * holding.avg_price + amount_usd
            total_qty = holding.qty + qty
            holding.qty = total_qty
            holding.avg_price = total_cost / total_qty
        else:
            self.holdings[symbol] = Holding(qty=qty, avg_price=price)
        return qty

    def sell(self, symbol: str, price: float, qty: float) -> float:
        if symbol not in self.holdings or price <= 0 or qty <= 0:
            return 0.0

        holding = self.holdings[symbol]
        qty = min(qty, holding.qty)
        proceeds = qty * price
        holding.qty -= qty
        self.cash += proceeds

        if holding.qty <= 1e-8:
            del self.holdings[symbol]
        return proceeds

    def total_value(self, prices: Dict[str, float]) -> float:
        holdings_value = 0.0
        for symbol, holding in self.holdings.items():
            if symbol in prices:
                holdings_value += holding.qty * prices[symbol]
        return self.cash + holdings_value


class Agent:
    def __init__(self, personality: str, agent_id: int, state: Optional[Dict[str, Any]] = None) -> None:
        self.agent_id = agent_id
        self.personality = personality

        if state is not None:
            self._load_state(state)
        else:
            self._init_from_template()

    def _init_from_template(self) -> None:
        template = PERSONALITY_TEMPLATES[self.personality]
        self.base_risk = template["risk_appetite"]
        self.risk_appetite = clamp(template["risk_appetite"] + random.uniform(-0.05, 0.05), 0.15, 0.95)
        self.discipline = clamp(template["discipline"] + random.uniform(-0.08, 0.08), 0.20, 1.00)
        self.adaptability = clamp(template["adaptability"] + random.uniform(-0.07, 0.07), 0.20, 1.00)
        self.confidence = clamp(template["confidence"] + random.uniform(-0.10, 0.10), 0.25, 1.75)
        self.exploration = clamp(template["exploration"] + random.uniform(-0.03, 0.03), 0.02, 0.35)
        self.learning_rate = clamp(template["learning_rate"] + random.uniform(-0.015, 0.015), 0.02, 0.15)
        self.strategy_weights = {
            key: clamp(value + random.uniform(-0.18, 0.18), -2.5, 2.5)
            for key, value in template["strategy_weights"].items()
        }
        self.regime_skill = {
            regime: clamp(value + random.uniform(-0.10, 0.10), -1.5, 1.5)
            for regime, value in BASE_REGIME_SKILL[self.personality].items()
        }
        self.symbol_memory: Dict[str, float] = {}
        self.edge_score = 0.0
        self.memory_count = 0

    def _load_state(self, state: Dict[str, Any]) -> None:
        self.base_risk = float(state.get("base_risk", PERSONALITY_TEMPLATES[self.personality]["risk_appetite"]))
        self.risk_appetite = float(state.get("risk_appetite", self.base_risk))
        self.discipline = float(state.get("discipline", PERSONALITY_TEMPLATES[self.personality]["discipline"]))
        self.adaptability = float(state.get("adaptability", PERSONALITY_TEMPLATES[self.personality]["adaptability"]))
        self.confidence = float(state.get("confidence", PERSONALITY_TEMPLATES[self.personality]["confidence"]))
        self.exploration = float(state.get("exploration", PERSONALITY_TEMPLATES[self.personality]["exploration"]))
        self.learning_rate = float(state.get("learning_rate", PERSONALITY_TEMPLATES[self.personality]["learning_rate"]))
        state_weights = state.get("strategy_weights", {})
        self.strategy_weights = {
            key: float(state_weights.get(key, PERSONALITY_TEMPLATES[self.personality]["strategy_weights"][key]))
            for key in FEATURE_KEYS
        }
        state_regimes = state.get("regime_skill", {})
        self.regime_skill = {
            regime: float(state_regimes.get(regime, BASE_REGIME_SKILL[self.personality][regime]))
            for regime in MARKET_REGIMES
        }
        raw_symbol_memory = state.get("symbol_memory", {})
        self.symbol_memory = {str(symbol): float(edge) for symbol, edge in raw_symbol_memory.items()}
        self.edge_score = float(state.get("edge_score", 0.0))
        self.memory_count = int(state.get("memory_count", 0))

    def to_state(self) -> Dict[str, Any]:
        trimmed_memory = dict(sorted(self.symbol_memory.items(), key=lambda item: abs(item[1]), reverse=True)[:20])
        return {
            "agent_id": self.agent_id,
            "personality": self.personality,
            "base_risk": self.base_risk,
            "risk_appetite": self.risk_appetite,
            "discipline": self.discipline,
            "adaptability": self.adaptability,
            "confidence": self.confidence,
            "exploration": self.exploration,
            "learning_rate": self.learning_rate,
            "strategy_weights": self.strategy_weights,
            "regime_skill": self.regime_skill,
            "symbol_memory": trimmed_memory,
            "edge_score": self.edge_score,
            "memory_count": self.memory_count,
        }

    def feature_vector(self, signal: Signal) -> Dict[str, float]:
        momentum = clamp(signal.ret_1 * 220.0, -2.5, 2.5)
        swing = clamp(signal.ret_6 * 120.0, -2.5, 2.5)
        volatility = clamp(signal.vol * 250.0, 0.0, 2.5)
        mean_reversion = clamp(-signal.distance_to_sma20 * 140.0, -2.5, 2.5)
        breakout = clamp(signal.distance_to_sma20 * 140.0, -2.5, 2.5)
        quality = clamp((signal.ret_6 - signal.vol * 0.7) * 120.0, -2.5, 2.5)
        news_sentiment = clamp(signal.news_sentiment * 2.4, -2.5, 2.5)
        news_volume = clamp(signal.news_volume * 1.8, 0.0, 2.5)
        news_urgency = clamp(signal.news_urgency * 2.2, -2.5, 2.5)
        macro_pressure = clamp(signal.macro_pressure * 2.2, -2.5, 2.5)
        peer_momentum = clamp(signal.peer_momentum * 180.0, -2.5, 2.5)
        return {
            "momentum": momentum,
            "swing": swing,
            "volatility": volatility,
            "mean_reversion": mean_reversion,
            "breakout": breakout,
            "quality": quality,
            "news_sentiment": news_sentiment,
            "news_volume": news_volume,
            "news_urgency": news_urgency,
            "macro_pressure": macro_pressure,
            "peer_momentum": peer_momentum,
        }

    def evaluate(self, signal: Signal, market_regime: str, holding_qty: float) -> Dict[str, Any]:
        features = self.feature_vector(signal)
        score = sum(self.strategy_weights[key] * features[key] for key in FEATURE_KEYS)
        score += self.regime_skill.get(market_regime, 0.0)
        score += self.symbol_memory.get(signal.symbol, 0.0)

        risk_drive = self.risk_appetite * (
            0.22 * features["momentum"]
            + 0.22 * features["breakout"]
            + 0.18 * features["news_sentiment"]
            + 0.14 * features["peer_momentum"]
        )
        discipline_drive = self.discipline * (0.20 * features["quality"] - 0.28 * max(features["volatility"] - 0.6, 0.0))
        caution = (1.0 - self.risk_appetite) * (
            max(features["volatility"] - 0.5, 0.0) * 0.45 + max(-features["macro_pressure"], 0.0) * 0.22
        )
        exploration_noise = random.uniform(-self.exploration, self.exploration)

        raw_score = (score + risk_drive + discipline_drive - caution + exploration_noise) * (0.75 + 0.40 * self.confidence)
        buy_prob = sigmoid(raw_score / 1.9)

        inventory_pressure = 0.0
        if holding_qty > 0:
            inventory_pressure += 0.85 * max(-features["momentum"], 0.0)
            inventory_pressure += 0.55 * max(features["volatility"] - 0.5, 0.0)
            inventory_pressure += 0.65 * max(-features["news_urgency"], 0.0)
            inventory_pressure += 0.35 * max(-features["macro_pressure"], 0.0)
            inventory_pressure += (1.0 - self.confidence) * 0.40

        sell_score = (
            -raw_score
            + inventory_pressure
            + (1.0 - self.risk_appetite) * 0.15 * features["volatility"]
            + 0.18 * max(-features["news_sentiment"], 0.0)
        )
        sell_prob = sigmoid(sell_score / 1.9)
        action_strength = clamp(buy_prob - sell_prob, -1.0, 1.0)

        return {
            "buy_prob": buy_prob,
            "sell_prob": sell_prob,
            "action_strength": action_strength,
            "raw_score": raw_score,
            "features": features,
        }

    def learn_from_feedback(
        self,
        symbol: str,
        market_regime: str,
        features: Dict[str, float],
        action_strength: float,
        realized_return: float,
    ) -> float:
        reward = clamp(action_strength * realized_return * 120.0, -2.5, 2.5)

        for key in FEATURE_KEYS:
            feature_value = clamp(features.get(key, 0.0), -2.5, 2.5)
            self.strategy_weights[key] = clamp(
                self.strategy_weights[key] + self.learning_rate * reward * feature_value * 0.12,
                -2.5,
                2.5,
            )

        self.regime_skill[market_regime] = clamp(
            self.regime_skill.get(market_regime, 0.0) + self.learning_rate * reward * 0.09,
            -1.5,
            1.5,
        )
        self.symbol_memory[symbol] = clamp(
            self.symbol_memory.get(symbol, 0.0) + self.learning_rate * reward * 0.11,
            -1.5,
            1.5,
        )

        self.confidence = clamp(self.confidence + reward * 0.03, 0.25, 1.75)
        self.exploration = clamp(self.exploration - reward * 0.01, 0.02, 0.35)
        self.risk_appetite = clamp(
            0.97 * self.risk_appetite + 0.03 * self.base_risk + reward * 0.01 * self.adaptability,
            0.15,
            0.95,
        )
        self.edge_score = 0.95 * self.edge_score + 0.05 * reward
        self.memory_count += 1
        return reward


class AgentFactory:
    @staticmethod
    def build_population(size: int, persisted_state: Optional[List[Dict[str, Any]]] = None) -> List[Agent]:
        if persisted_state and len(persisted_state) >= size:
            return [
                Agent(
                    personality=str(state.get("personality", "balanced")),
                    agent_id=index,
                    state=state,
                )
                for index, state in enumerate(persisted_state[:size])
            ]

        personalities = list(PERSONALITY_WEIGHTS.keys())
        weights = [PERSONALITY_WEIGHTS[personality] for personality in personalities]
        return [
            Agent(random.choices(personalities, weights=weights, k=1)[0], agent_id=index)
            for index in range(size)
        ]


class MarketData:
    def __init__(self) -> None:
        self._last_prices: Dict[str, float] = {}
        self._session = requests.Session()
        self._news_cache: Dict[str, tuple[float, NewsSnapshot]] = {}
        self._macro_cache: Optional[tuple[float, MacroSnapshot]] = None
        self.last_world_summary = "macro=neutral | headlines=0"

    def fetch_signals(self, symbols: List[str]) -> Dict[str, Signal]:
        signals: Dict[str, Signal] = {}
        news_map = self._fetch_news_map(symbols)
        macro = self._fetch_macro_snapshot()
        headline_total = 0

        for symbol in symbols:
            series = self._fetch_close_series(symbol)
            if series is None or len(series) < 25:
                continue

            close = series.dropna()
            if len(close) < 25:
                continue

            price = float(close.iloc[-1])
            ret_1 = float(close.iloc[-1] / close.iloc[-2] - 1.0)
            ret_6 = float(close.iloc[-1] / close.iloc[-6] - 1.0)
            vol = float(close.pct_change().dropna().tail(24).std())
            sma20 = float(close.tail(20).mean())
            distance_to_sma20 = 0.0 if sma20 == 0 else float((price - sma20) / sma20)
            news = news_map.get(symbol, NewsSnapshot())
            headline_total += news.headline_count
            peer_symbol = SECTOR_BENCHMARKS.get(symbol, "SPY")
            peer_ret = macro.benchmark_returns.get(peer_symbol, macro.benchmark_returns.get("SPY", 0.0))

            signals[symbol] = Signal(
                symbol=symbol,
                price=price,
                ret_1=ret_1,
                ret_6=ret_6,
                vol=vol,
                distance_to_sma20=distance_to_sma20,
                news_sentiment=news.sentiment,
                news_volume=news.volume_score,
                news_urgency=news.urgency_bias,
                macro_pressure=macro.market_pressure,
                peer_momentum=peer_ret,
                headline_count=news.headline_count,
            )
            self._last_prices[symbol] = price

        focus = sorted(
            ((symbol, snapshot) for symbol, snapshot in news_map.items() if snapshot.headline_count > 0),
            key=lambda item: abs(item[1].urgency_bias) + item[1].volume_score,
            reverse=True,
        )[:2]
        focus_text = ", ".join(
            f"{symbol}:{snapshot.sentiment:+.2f}/{snapshot.headline_count}h"
            for symbol, snapshot in focus
        ) or "none"
        self.last_world_summary = f"macro={macro.summary} ({macro.market_pressure:+.2f}) | headlines={headline_total} | focus={focus_text}"
        return signals

    def _fetch_news_map(self, symbols: List[str]) -> Dict[str, NewsSnapshot]:
        return {symbol: self._fetch_news_snapshot(symbol) for symbol in symbols}

    def _fetch_news_snapshot(self, symbol: str) -> NewsSnapshot:
        cached = self._news_cache.get(symbol)
        now = time.time()
        if cached and now - cached[0] < NEWS_CACHE_SECONDS:
            return cached[1]

        query = SYMBOL_NEWS_QUERIES.get(symbol, f"{symbol} stock") + " when:1d"
        url = (
            f"{GOOGLE_NEWS_RSS}?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        )
        snapshot = NewsSnapshot()
        try:
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            items = root.findall(".//item")[:8]
            weighted_sentiment = 0.0
            weighted_urgency = 0.0
            total_weight = 0.0
            top_headline = ""
            for item in items:
                raw_title = (item.findtext("title") or "").strip()
                title = re.sub(r"\s+-\s+[^-]+$", "", raw_title)
                if not top_headline and title:
                    top_headline = title
                pub_date = item.findtext("pubDate") or ""
                hours_old = 6.0
                if pub_date:
                    try:
                        published_at = parsedate_to_datetime(pub_date)
                        hours_old = max(0.25, (datetime.now(published_at.tzinfo) - published_at).total_seconds() / 3600.0)
                    except Exception:
                        hours_old = 6.0
                sentiment_score, urgency_score = self._score_news_text(title)
                weight = 1.0 / (1.0 + hours_old / 6.0)
                weighted_sentiment += sentiment_score * weight
                weighted_urgency += urgency_score * sign(sentiment_score) * weight
                total_weight += weight

            headline_count = len(items)
            if total_weight > 0:
                snapshot = NewsSnapshot(
                    sentiment=clamp(weighted_sentiment / total_weight, -1.0, 1.0),
                    volume_score=clamp(math.log1p(headline_count) / math.log(6.0), 0.0, 1.4),
                    urgency_bias=clamp(weighted_urgency / total_weight, -1.0, 1.0),
                    headline_count=headline_count,
                    top_headline=top_headline,
                )
        except Exception:
            snapshot = NewsSnapshot()

        self._news_cache[symbol] = (now, snapshot)
        return snapshot

    def _score_news_text(self, text: str) -> tuple[float, float]:
        lower_text = text.lower()
        pos_hits = sum(1 for term in POSITIVE_NEWS_TERMS if term in lower_text)
        neg_hits = sum(1 for term in NEGATIVE_NEWS_TERMS if term in lower_text)
        urgent_hits = sum(1 for term in URGENT_NEWS_TERMS if term in lower_text)

        sentiment = clamp((pos_hits - neg_hits) / 2.5, -1.0, 1.0)
        urgency = clamp(urgent_hits / 2.0, 0.0, 1.0)

        if sentiment == 0.0 and ("upgrade" in lower_text or "downgrade" in lower_text):
            sentiment = 0.5 if "upgrade" in lower_text else -0.5
        return sentiment, urgency

    def _fetch_macro_snapshot(self) -> MacroSnapshot:
        now = time.time()
        if self._macro_cache and now - self._macro_cache[0] < MACRO_CACHE_SECONDS:
            return self._macro_cache[1]

        benchmark_returns: Dict[str, float] = {}
        for symbol in MACRO_SYMBOLS:
            series = self._fetch_close_series(symbol)
            if series is None or len(series) < 6:
                continue
            close = series.dropna()
            if len(close) < 6:
                continue
            benchmark_returns[symbol] = float(close.iloc[-1] / close.iloc[-6] - 1.0)

        spy_ret = benchmark_returns.get("SPY", 0.0)
        qqq_ret = benchmark_returns.get("QQQ", 0.0)
        iwm_ret = benchmark_returns.get("IWM", 0.0)
        tlt_ret = benchmark_returns.get("TLT", 0.0)
        vix_ret = benchmark_returns.get("^VIX", 0.0)
        macro_news = self._fetch_macro_news_bias()
        pressure = clamp(
            spy_ret * 180.0 + qqq_ret * 120.0 + iwm_ret * 80.0 + tlt_ret * 40.0 - vix_ret * 90.0 + macro_news * 0.35,
            -1.0,
            1.0,
        )
        if pressure > 0.20:
            summary = "supportive"
        elif pressure < -0.20:
            summary = "risk_off"
        else:
            summary = "mixed"

        snapshot = MacroSnapshot(
            market_pressure=pressure,
            benchmark_returns=benchmark_returns,
            headline_bias=macro_news,
            summary=summary,
        )
        self._macro_cache = (now, snapshot)
        return snapshot

    def _fetch_macro_news_bias(self) -> float:
        try:
            url = f"{GOOGLE_NEWS_RSS}?q={quote_plus(MACRO_NEWS_QUERY)}&hl=en-US&gl=US&ceid=US:en"
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            items = root.findall(".//item")[:6]
            if not items:
                return 0.0

            total = 0.0
            for item in items:
                title = (item.findtext("title") or "").strip()
                sentiment, _ = self._score_news_text(title)
                total += sentiment
            return clamp(total / len(items), -1.0, 1.0)
        except Exception:
            return 0.0

    def _fetch_close_series(self, symbol: str) -> Optional[pd.Series]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            "range": "5d",
            "interval": "5m",
            "events": "div,splits",
            "includePrePost": "false",
        }
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

        try:
            response = self._session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            print(f"[WARN] Failed to fetch {symbol}: {exc}")
            return None

        chart = payload.get("chart", {})
        if chart.get("error"):
            return None

        result = chart.get("result")
        if not result:
            return None

        item = result[0]
        timestamps = item.get("timestamp", [])
        quotes = item.get("indicators", {}).get("quote", [])
        if not timestamps or not quotes:
            return None

        closes = quotes[0].get("close", [])
        if not closes:
            return None

        series = pd.Series(closes, index=pd.to_datetime(timestamps, unit="s", utc=True), dtype="float64")
        return series.dropna()


class VotingTradingEngine:
    def __init__(self, agents: List[Agent], initial_cash: float, decision_interval_cycles: int = DECISION_INTERVAL_CYCLES) -> None:
        self.agents = agents
        self.initial_cash = initial_cash
        self.decision_interval_cycles = max(1, decision_interval_cycles)
        self.portfolio = Portfolio(initial_cash)
        self.last_prices: Dict[str, float] = {}
        self.pending_feedback: List[Dict[str, Any]] = []
        self.total_fees_paid = 0.0
        self.closed_trade_pnls: List[float] = []
        self.equity_peak = initial_cash
        self.max_drawdown = 0.0
        self.vote_window: Dict[str, Dict[str, float]] = {}
        self.vote_window_rounds = 0
        self.started_at_ts = time.time()
        self.last_fee_charge_ts = self.started_at_ts

    def _accumulate_vote_window(self, vote_summary: Dict[str, Dict[str, float]]) -> None:
        for symbol, vote in vote_summary.items():
            acc = self.vote_window.setdefault(
                symbol,
                {"buy_sum": 0.0, "sell_sum": 0.0, "conv_sum": 0.0, "samples": 0.0},
            )
            acc["buy_sum"] += vote["buy_ratio"]
            acc["sell_sum"] += vote["sell_ratio"]
            acc["conv_sum"] += vote["avg_conviction"]
            acc["samples"] += 1.0
        self.vote_window_rounds += 1

    def _window_vote(self, symbol: str, fallback: Dict[str, float]) -> Dict[str, float]:
        acc = self.vote_window.get(symbol)
        if not acc or acc["samples"] <= 0:
            return fallback
        buy_ratio = acc["buy_sum"] / acc["samples"]
        sell_ratio = acc["sell_sum"] / acc["samples"]
        avg_conviction = acc["conv_sum"] / acc["samples"]
        return {
            "buy_ratio": buy_ratio,
            "sell_ratio": sell_ratio,
            "avg_conviction": avg_conviction,
            "consensus": buy_ratio - sell_ratio,
        }

    def _reset_vote_window(self) -> None:
        self.vote_window = {}
        self.vote_window_rounds = 0

    def _apply_trade_fee(self, gross_amount: float) -> float:
        if TRADIER_PRO_ENABLED:
            fee = 0.0
        else:
            fee = TRADIER_REGULAR_FEE_PER_TRADE_USD if abs(gross_amount) > 0 else 0.0
        self.total_fees_paid += fee
        self.portfolio.cash = max(0.0, self.portfolio.cash - fee)
        return fee

    def _apply_subscription_fee(self, now_ts: float) -> float:
        if not TRADIER_PRO_ENABLED:
            self.last_fee_charge_ts = now_ts
            return 0.0

        elapsed = max(0.0, now_ts - self.last_fee_charge_ts)
        if elapsed <= 0.0:
            return 0.0

        prorated_fee = (elapsed / SECONDS_PER_30_DAY_MONTH) * TRADIER_PRO_MONTHLY_FEE_USD
        charged_fee = min(self.portfolio.cash, prorated_fee)
        self.total_fees_paid += charged_fee
        self.portfolio.cash = max(0.0, self.portfolio.cash - charged_fee)
        self.last_fee_charge_ts = now_ts
        return charged_fee

    def _performance_summary(self, current_value: float) -> Dict[str, float]:
        self.equity_peak = max(self.equity_peak, current_value)
        if self.equity_peak > 0:
            drawdown = (self.equity_peak - current_value) / self.equity_peak
            self.max_drawdown = max(self.max_drawdown, drawdown)

        wins = [pnl for pnl in self.closed_trade_pnls if pnl > 0]
        losses = [pnl for pnl in self.closed_trade_pnls if pnl < 0]
        closed_count = len(self.closed_trade_pnls)
        win_rate = (len(wins) / closed_count) if closed_count else 0.0
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        net_after_fees = current_value - self.initial_cash

        return {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_drawdown": self.max_drawdown,
            "net_after_fees": net_after_fees,
            "fees_paid": self.total_fees_paid,
            "closed_trades": float(closed_count),
        }

    def _detect_market_regime(self, signals: Dict[str, Signal]) -> str:
        if not signals:
            return "mixed"

        values = list(signals.values())
        avg_ret_1 = sum(signal.ret_1 for signal in values) / len(values)
        avg_ret_6 = sum(signal.ret_6 for signal in values) / len(values)
        avg_vol = sum(signal.vol for signal in values) / len(values)
        breadth = sum(1 for signal in values if signal.ret_1 > 0) / len(values)

        if avg_vol > 0.012 and abs(avg_ret_1) > 0.0015:
            return "volatile_trend"
        if avg_ret_6 > 0.0020 and breadth >= 0.60:
            return "bull_trend"
        if avg_ret_6 < -0.0020 and breadth <= 0.40:
            return "risk_off"
        if avg_vol < 0.0085 and abs(avg_ret_1) < 0.0015:
            return "range_bound"
        return "mixed"

    def _apply_learning(self, signals: Dict[str, Signal]) -> Dict[str, float]:
        if not self.pending_feedback:
            return {"learned_events": 0.0, "avg_reward": 0.0}

        learned_events = 0
        reward_total = 0.0
        next_feedback: List[Dict[str, Any]] = []

        for feedback in self.pending_feedback:
            symbol = str(feedback["symbol"])
            if symbol not in signals:
                next_feedback.append(feedback)
                continue

            previous_price = float(feedback["price"])
            current_price = signals[symbol].price
            if previous_price <= 0 or current_price <= 0:
                continue

            realized_return = current_price / previous_price - 1.0
            agent = self.agents[int(feedback["agent_index"])]
            reward = agent.learn_from_feedback(
                symbol=symbol,
                market_regime=str(feedback["market_regime"]),
                features=dict(feedback["features"]),
                action_strength=float(feedback["action_strength"]),
                realized_return=realized_return,
            )
            learned_events += 1
            reward_total += reward

        self.pending_feedback = next_feedback
        avg_reward = reward_total / learned_events if learned_events else 0.0
        return {"learned_events": float(learned_events), "avg_reward": avg_reward}

    def _symbol_weight_cap(self, signal: Signal, market_regime: str) -> float:
        base_cap = 0.12 if signal.symbol in TOP_10_SYMBOLS else 0.07
        trend_bonus = 0.025 if market_regime in {"bull_trend", "volatile_trend"} and signal.ret_6 > 0 else 0.0
        volatility_haircut = clamp(signal.vol * 7.0, 0.0, 0.05)
        return clamp(base_cap + trend_bonus - volatility_haircut, 0.04, 0.16)

    def _build_learning_summary(self, market_regime: str, learning_report: Dict[str, float]) -> Dict[str, Any]:
        count = max(1, len(self.agents))
        avg_confidence = sum(agent.confidence for agent in self.agents) / count
        avg_exploration = sum(agent.exploration for agent in self.agents) / count
        avg_risk = sum(agent.risk_appetite for agent in self.agents) / count
        avg_memory = sum(agent.memory_count for agent in self.agents) / count

        personality_edges: Dict[str, List[float]] = {}
        for agent in self.agents:
            personality_edges.setdefault(agent.personality, []).append(agent.edge_score)

        personality_rank = sorted(
            ((personality, sum(values) / max(1, len(values))) for personality, values in personality_edges.items()),
            key=lambda item: item[1],
            reverse=True,
        )

        leader = personality_rank[0][0] if personality_rank else "balanced"
        return {
            "market_regime": market_regime,
            "avg_confidence": avg_confidence,
            "avg_exploration": avg_exploration,
            "avg_risk": avg_risk,
            "avg_memory": avg_memory,
            "learned_events": int(learning_report.get("learned_events", 0.0)),
            "avg_reward": learning_report.get("avg_reward", 0.0),
            "leader_personality": leader,
        }

    def execute_cycle(
        self,
        signals: Dict[str, Signal],
        vote_threshold: float = ACTION_THRESHOLD,
        cycle_num: int = 0,
        universe: Optional[List[str]] = None,
        execute_trades: bool = True,
    ) -> CycleResult:
        messages: List[str] = []
        trades_done: List[TradeRecord] = []
        vote_summary: Dict[str, Dict[str, float]] = {}
        timestamp = datetime.now()
        subscription_fee = self._apply_subscription_fee(time.time())

        if subscription_fee > 0:
            messages.append(f"Tradier Pro subscription fee charged: ${subscription_fee:.4f}")

        if not signals:
            portfolio_value = self.portfolio.total_value(self.last_prices)
            return CycleResult(
                cycle=cycle_num,
                timestamp=timestamp,
                trades=trades_done,
                portfolio_value=portfolio_value,
                cash=self.portfolio.cash,
                holdings=copy.deepcopy(self.portfolio.holdings),
                prices=copy.deepcopy(self.last_prices),
                vote_summary=vote_summary,
                messages=["No fresh signals. Skipping cycle."],
                universe=universe or [],
                market_regime="mixed",
                learning_summary=self._build_learning_summary("mixed", {"learned_events": 0.0, "avg_reward": 0.0}),
                performance_summary=self._performance_summary(portfolio_value),
                agent_state=[agent.to_state() for agent in self.agents],
            )

        self.last_prices.update({symbol: signal.price for symbol, signal in signals.items()})
        market_regime = self._detect_market_regime(signals)
        learning_report = self._apply_learning(signals)

        portfolio_value_before = self.portfolio.total_value(self.last_prices)
        avg_volatility = sum(signal.vol for signal in signals.values()) / max(1, len(signals))
        reserve_ratio = clamp(0.28 + avg_volatility * 4.0, 0.25, 0.35)
        reserve_cash = portfolio_value_before * reserve_ratio
        cycle_buy_budget = min(
            self.portfolio.cash * (0.34 if market_regime in {"bull_trend", "volatile_trend"} else 0.24),
            max(0.0, self.portfolio.cash - reserve_cash),
        )

        proposals: List[Dict[str, Any]] = []
        pending_feedback: List[Dict[str, Any]] = []

        for symbol, signal in signals.items():
            holding_qty = self.portfolio.holdings.get(symbol, Holding(0.0, 0.0)).qty
            buy_votes = 0
            sell_votes = 0
            conviction_sum = 0.0
            agent_views: List[Dict[str, Any]] = []

            for index, agent in enumerate(self.agents):
                decision = agent.evaluate(signal, market_regime, holding_qty)
                agent_views.append({"agent_index": index, **decision})
                if random.random() < decision["buy_prob"]:
                    buy_votes += 1
                    conviction_sum += decision["buy_prob"]
                if random.random() < decision["sell_prob"]:
                    sell_votes += 1

            buy_ratio = buy_votes / len(self.agents)
            sell_ratio = sell_votes / len(self.agents)
            avg_conviction = conviction_sum / buy_votes if buy_votes else 0.0
            consensus = buy_ratio - sell_ratio

            vote_summary[symbol] = {
                "buy_ratio": buy_ratio,
                "sell_ratio": sell_ratio,
                "avg_conviction": avg_conviction,
                "consensus": consensus,
            }

            proposals.append(
                {
                    "symbol": symbol,
                    "signal": signal,
                    "holding_qty": holding_qty,
                    "buy_ratio": buy_ratio,
                    "sell_ratio": sell_ratio,
                    "avg_conviction": avg_conviction,
                    "agent_views": agent_views,
                }
            )

            for decision in agent_views:
                if abs(float(decision["action_strength"])) < 0.05:
                    continue
                pending_feedback.append(
                    {
                        "agent_index": decision["agent_index"],
                        "symbol": symbol,
                        "market_regime": market_regime,
                        "features": decision["features"],
                        "action_strength": decision["action_strength"],
                        "price": signal.price,
                    }
                )

        learning_summary = self._build_learning_summary(market_regime, learning_report)
        self._accumulate_vote_window(vote_summary)
        window_rounds = self.vote_window_rounds
        messages.append(
            (
                f"Regime={market_regime} | Leader={learning_summary['leader_personality']} | "
                f"Confidence={learning_summary['avg_confidence']:.2f} | Exploration={learning_summary['avg_exploration']:.2f}"
            )
        )
        mode_text = "TRADE EXECUTION" if execute_trades else "LEARNING VOTES ONLY"
        messages.append(
            f"Mode: {mode_text} | Vote window={window_rounds}/{self.decision_interval_cycles} | Threshold={vote_threshold:.0%}"
        )
        if learning_summary["learned_events"] > 0:
            messages.append(
                f"Learning update: {learning_summary['learned_events']} feedback events | avg reward={learning_summary['avg_reward']:.3f}"
            )

        if not execute_trades:
            value = self.portfolio.total_value(self.last_prices)
            perf = self._performance_summary(value)
            messages.append(
                (
                    f"Stats: win={perf['win_rate']:.0%} | avgW=${perf['avg_win']:.2f} | "
                    f"avgL=${perf['avg_loss']:.2f} | MDD={perf['max_drawdown']:.1%} | "
                    f"net(after fees)=${perf['net_after_fees']:.2f}"
                )
            )
            messages.append(f"Portfolio value: ${value:.2f} | Cash: ${self.portfolio.cash:.2f}")
            return CycleResult(
                cycle=cycle_num,
                timestamp=timestamp,
                trades=trades_done,
                portfolio_value=value,
                cash=self.portfolio.cash,
                holdings=copy.deepcopy(self.portfolio.holdings),
                prices=copy.deepcopy(self.last_prices),
                vote_summary=vote_summary,
                messages=messages,
                universe=universe or [],
                market_regime=market_regime,
                learning_summary=learning_summary,
                performance_summary=perf,
                agent_state=[agent.to_state() for agent in self.agents],
            )

        for proposal in proposals:
            symbol = proposal["symbol"]
            final_vote = self._window_vote(symbol, vote_summary[symbol])
            proposal["buy_ratio"] = final_vote["buy_ratio"]
            proposal["sell_ratio"] = final_vote["sell_ratio"]
            proposal["avg_conviction"] = final_vote["avg_conviction"]
            vote_summary[symbol] = final_vote

        for proposal in proposals:
            symbol = proposal["symbol"]
            signal = proposal["signal"]
            holding_qty = proposal["holding_qty"]
            if holding_qty <= 0:
                continue

            cap = self._symbol_weight_cap(signal, market_regime)
            current_weight = holding_qty * signal.price / max(portfolio_value_before, 1e-9)
            if current_weight <= cap * 1.15:
                continue

            excess_value = (current_weight - cap) * portfolio_value_before
            qty_to_trim = min(holding_qty, excess_value / signal.price)
            avg_cost = self.portfolio.holdings.get(symbol, Holding(0.0, signal.price)).avg_price
            proceeds = self.portfolio.sell(symbol, signal.price, qty_to_trim)
            if proceeds <= 0:
                continue

            fee = self._apply_trade_fee(proceeds)
            cost_basis = avg_cost * qty_to_trim
            realized_pnl = proceeds - fee - cost_basis
            self.closed_trade_pnls.append(realized_pnl)

            trades_done.append(
                TradeRecord(
                    action="TRIM",
                    symbol=symbol,
                    qty=qty_to_trim,
                    amount=proceeds,
                    price=signal.price,
                    vote_ratio=proposal["sell_ratio"],
                    fee=fee,
                    realized_pnl=realized_pnl,
                )
            )
            messages.append(
                f"TRIM {symbol}: qty={qty_to_trim:.4f}, net=${(proceeds - fee):.2f}, cap={cap:.0%}"
            )

        for proposal in proposals:
            symbol = proposal["symbol"]
            signal = proposal["signal"]
            holding_qty = self.portfolio.holdings.get(symbol, Holding(0.0, 0.0)).qty
            sell_ratio = proposal["sell_ratio"]

            if holding_qty > 0 and sell_ratio >= vote_threshold:
                portion = min(1.0, (sell_ratio - vote_threshold) / max(1e-6, 1.0 - vote_threshold))
                qty_to_sell = holding_qty * portion
                avg_cost = self.portfolio.holdings.get(symbol, Holding(0.0, signal.price)).avg_price
                proceeds = self.portfolio.sell(symbol, signal.price, qty_to_sell)
                if proceeds > 0:
                    fee = self._apply_trade_fee(proceeds)
                    realized_pnl = proceeds - fee - (avg_cost * qty_to_sell)
                    self.closed_trade_pnls.append(realized_pnl)
                    trades_done.append(
                        TradeRecord(
                            action="SELL",
                            symbol=symbol,
                            qty=qty_to_sell,
                            amount=proceeds,
                            price=signal.price,
                            vote_ratio=sell_ratio,
                            fee=fee,
                            realized_pnl=realized_pnl,
                        )
                    )
                    messages.append(
                        f"SELL {symbol}: ratio={sell_ratio:.0%}, qty={qty_to_sell:.4f}, net=${(proceeds - fee):.2f}"
                    )

        buy_candidates: List[Dict[str, Any]] = []
        for proposal in proposals:
            signal = proposal["signal"]
            buy_ratio = proposal["buy_ratio"]
            if buy_ratio < vote_threshold:
                continue

            strength = (buy_ratio - vote_threshold) / max(1e-6, 1.0 - vote_threshold)
            conviction = max(0.10, proposal["avg_conviction"])
            quality_bonus = clamp((signal.ret_6 - signal.vol * 0.7) * 90.0, -0.5, 0.8)
            score = 0.55 * strength + 0.25 * conviction + 0.20 * max(quality_bonus, 0.0)
            buy_candidates.append({"score": score, **proposal})

        buy_candidates.sort(key=lambda item: item["score"], reverse=True)

        for candidate in buy_candidates:
            if cycle_buy_budget <= 0 or self.portfolio.cash <= reserve_cash:
                break

            symbol = candidate["symbol"]
            signal = candidate["signal"]
            cap = self._symbol_weight_cap(signal, market_regime)
            target_weight = min(cap, 0.03 + cap * clamp(candidate["score"], 0.0, 1.0))
            current_qty = self.portfolio.holdings.get(symbol, Holding(0.0, 0.0)).qty
            current_value = current_qty * signal.price
            target_value = portfolio_value_before * target_weight
            desired_add = max(0.0, target_value - current_value)
            amount = min(desired_add, cycle_buy_budget, max(0.0, self.portfolio.cash - reserve_cash))

            if amount < 2.0:
                continue

            qty = self.portfolio.buy(symbol, signal.price, amount)
            if qty > 0:
                cycle_buy_budget -= amount
                fee = self._apply_trade_fee(amount)
                trades_done.append(
                    TradeRecord(
                        action="BUY",
                        symbol=symbol,
                        qty=qty,
                        amount=amount,
                        price=signal.price,
                        vote_ratio=candidate["buy_ratio"],
                        fee=fee,
                        realized_pnl=-fee,
                    )
                )
                messages.append(
                    f"BUY  {symbol}: ratio={candidate['buy_ratio']:.0%}, qty={qty:.4f}, spent=${amount:.2f}, fee=${fee:.2f}"
                )

        self.pending_feedback = pending_feedback
        value = self.portfolio.total_value(self.last_prices)
        perf = self._performance_summary(value)
        messages.append(
            (
                f"Stats: win={perf['win_rate']:.0%} | avgW=${perf['avg_win']:.2f} | "
                f"avgL=${perf['avg_loss']:.2f} | MDD={perf['max_drawdown']:.1%} | "
                f"net(after fees)=${perf['net_after_fees']:.2f}"
            )
        )
        messages.append(f"Portfolio value: ${value:.2f} | Cash: ${self.portfolio.cash:.2f}")
        self._reset_vote_window()

        return CycleResult(
            cycle=cycle_num,
            timestamp=timestamp,
            trades=trades_done,
            portfolio_value=value,
            cash=self.portfolio.cash,
            holdings=copy.deepcopy(self.portfolio.holdings),
            prices=copy.deepcopy(self.last_prices),
            vote_summary=vote_summary,
            messages=messages,
            universe=universe or [],
            market_regime=market_regime,
            learning_summary=learning_summary,
            performance_summary=perf,
            agent_state=[agent.to_state() for agent in self.agents],
        )


def choose_risky_symbols(market: MarketData) -> List[str]:
    risk_signals = market.fetch_signals(RISK_POOL)
    ranked = sorted(risk_signals.values(), key=lambda signal: signal.vol, reverse=True)
    selected = [signal.symbol for signal in ranked[:2]]

    while len(selected) < 2 and len(selected) < len(RISK_POOL):
        candidate = random.choice([symbol for symbol in RISK_POOL if symbol not in selected])
        selected.append(candidate)

    return selected[:2]


def run_simulation(
    cash: float,
    agent_count: int,
    interval_seconds: int,
    cycles: int,
    seed: Optional[int],
    decision_interval_cycles: int = DECISION_INTERVAL_CYCLES,
    persisted_agents: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if seed is not None:
        random.seed(seed)

    market = MarketData()
    agents = AgentFactory.build_population(agent_count, persisted_state=persisted_agents)
    engine = VotingTradingEngine(
        agents=agents,
        initial_cash=cash,
        decision_interval_cycles=decision_interval_cycles,
    )

    cycle_index = 0
    while True:
        cycle_index += 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        risky = choose_risky_symbols(market)
        symbols = TOP_10_SYMBOLS + risky
        print(f"\n[{timestamp}] Cycle {cycle_index} | Universe: {', '.join(symbols)}")

        signals = market.fetch_signals(symbols)
        execute_trades = cycle_index % max(1, decision_interval_cycles) == 0
        result = engine.execute_cycle(
            signals=signals,
            vote_threshold=ACTION_THRESHOLD,
            cycle_num=cycle_index,
            universe=symbols,
            execute_trades=execute_trades,
        )
        for line in result.messages:
            print(f"  - {line}")

        if cycles > 0 and cycle_index >= cycles:
            break

        time.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autonomous adaptive trading demo")
    parser.add_argument("--cash", type=float, default=500.0, help="Starting cash in USD")
    parser.add_argument("--agents", type=int, default=1000, help="Number of agents")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=300,
        help="Voting interval in seconds (default 300 = 5 minutes)",
    )
    parser.add_argument(
        "--decision-interval-cycles",
        type=int,
        default=DECISION_INTERVAL_CYCLES,
        help="How many vote cycles to aggregate before final trade execution (default 3 = 15 minutes)",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=12,
        help="Number of cycles to run. Use 0 for infinite loop.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible runs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.cash <= 0:
        raise ValueError("--cash must be positive")
    if args.agents < 10:
        raise ValueError("--agents should be at least 10")
    if args.interval_seconds <= 0:
        raise ValueError("--interval-seconds must be positive")
    if args.decision_interval_cycles <= 0:
        raise ValueError("--decision-interval-cycles must be positive")
    if args.cycles < 0:
        raise ValueError("--cycles cannot be negative")

    print("Starting autonomous adaptive trading demo...")
    print(
        (
            f"Agents={args.agents}, Starting cash=${args.cash:.2f}, Vote interval={args.interval_seconds}s, "
            f"Decision every {args.decision_interval_cycles} cycles, Cycles={args.cycles}"
        )
    )

    run_simulation(
        cash=args.cash,
        agent_count=args.agents,
        interval_seconds=args.interval_seconds,
        cycles=args.cycles,
        seed=args.seed,
        decision_interval_cycles=args.decision_interval_cycles,
    )


if __name__ == "__main__":
    main()
