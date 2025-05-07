from enum import Enum
from dataclasses import dataclass
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Tuple, Literal
from collections import defaultdict
from datetime import datetime
import pandas as pd
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.stats import norm
from scipy.optimize import brentq, minimize
from dateutil.parser import isoparse
from typing import List
import warnings

"""pip
========================================
ENUMS
========================================
"""
class Platform(str, Enum):
    KALSHI = "Kalshi"
    POLYMARKET = "Polymarket"

class AssetType(str, Enum):
    SPORTS = "Sports"
    FINANCIAL = "Financial"
    ECONOMICS = "Economics"

class UnderlyingFinancialAsset(str, Enum):
    SPX = "SPX"
    NDX = "NDX"
    BTC = "BTC"
    ETH = "ETH"

"""
========================================
DATA STRUCTURES
========================================
"""

def safe_parse_datetime(*keys: str, source: dict) -> Optional[datetime]:
    for key in keys:
        date_str = source.get(key)
        if date_str:
            try:
                return isoparse(date_str)
            except Exception:
                continue
    return None

class OrderBookData(BaseModel):
    yes: List[Tuple[float, float]]  # (price, quantity)
    no: List[Tuple[float, float]]

    @classmethod
    def from_kalshi_json(cls, data: dict):
        return cls(
            yes=[tuple(map(float, x)) for x in data.get("yes", [])],
            no=[tuple(map(float, x)) for x in data.get("no", [])],
        )
    

class PredictionMarketEvent(BaseModel):
    title: str
    ticker: str
    category: Optional[str] = None
    strike_date: Optional[datetime] = None
    mutually_exclusive: bool = False
    sub_title: Optional[str] = None

    @classmethod
    def from_kalshi_json(cls, data: dict):
        return cls(
            title=data["title"],
            ticker=data.get("series_ticker", data.get("event_ticker", "")),
            category=data.get("category"),
            strike_date=data.get("strike_date"),
            mutually_exclusive=data.get("mutually_exclusive", False),
            sub_title=data.get("sub_title"),
        )
    
class PredictionMarketContract(BaseModel):
    ticker: str
    title: str
    category: Optional[str]
    event: Optional[PredictionMarketEvent]

    open_time: Optional[datetime]
    close_time: Optional[datetime]
    expiration_time: Optional[datetime]
    expected_expiration_time: Optional[datetime]

    yes_bid: Optional[float]
    yes_ask: Optional[float]
    no_bid: Optional[float]
    no_ask: Optional[float]
    last_price: Optional[float]

    open_interest: Optional[float]
    volume: Optional[float]

    strike_type: Optional[str]
    strike_upper: Optional[float]
    strike_lower: Optional[float]

    rules_primary: Optional[str]
    rules_secondary: Optional[str]

    response_price_units: Optional[Literal["usd_cent"]]
    order_book: Optional[OrderBookData]
    platform: Platform

    @classmethod
    def from_kalshi_market_json(cls, market: dict, event: Optional[PredictionMarketEvent] = None):
        strike_value = None
        try:
            strike_value = float(market.get("functional_strike", 0))
        except (ValueError, TypeError):
            strike_value = float(market.get("floor_strike", 0))

        return cls(
            ticker=market["ticker"],
            title=market["title"],
            category=market.get("category"),
            event=event,

            open_time=market.get("open_time"),
            close_time=market.get("close_time"),
            expiration_time=market.get("expiration_time"),
            expected_expiration_time=market.get("expected_expiration_time"),

            yes_bid=market.get("yes_bid"),
            yes_ask=market.get("yes_ask"),
            no_bid=market.get("no_bid"),
            no_ask=market.get("no_ask"),
            last_price=market.get("last_price"),

            open_interest=market.get("open_interest"),
            volume=market.get("volume"),

            strike_type=market.get("strike_type"),
            strike_upper=market.get("floor_strike") if market.get("strike_type")=="greater" else np.inf,
            strike_lower=market.get("cap_strike") if market.get("strike_type")=="less" else -np.inf,

            rules_primary=market.get("rules_primary"),
            rules_secondary=market.get("rules_secondary"),

            order_book=None,
            response_price_units=market.get("response_price_units", "usd_cent"),
            platform=Platform.KALSHI,
        )
    
    def attach_order_book(self, orderbook_json: dict):
        self.order_book = OrderBookData.from_kalshi_json(orderbook_json.get("orderbook", {}))


class PredictionMarketBundle(BaseModel):
    platform: Platform
    event: PredictionMarketEvent
    contracts: List[PredictionMarketContract]

    @classmethod
    def from_kalshi_event_payload(cls, data: dict):
        event = PredictionMarketEvent.from_kalshi_json(data["event"])
        contracts = [
            PredictionMarketContract.from_kalshi_market_json(mkt, event)
            for mkt in data.get("markets", [])
        ]
        return cls(platform=Platform.KALSHI, event=event, contracts=contracts)
    

