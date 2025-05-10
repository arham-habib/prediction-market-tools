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

"""
========================================
TODO
- [ ] Polymarket you need to multiply price by 100, and fix the "no" order book"
- [ ] Make the price be the price to take 100 contracts instead of the price to take 1 contract
========================================
"""

"""
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
    yes_avg_price_100: Optional[float] = None  # Average price to take 100 contracts on yes side
    no_avg_price_100: Optional[float] = None   # Average price to take 100 contracts on no side

    def __init__(self, **data):
        super().__init__(**data)
        self.yes_avg_price_100 = self._calculate_avg_price(self.no, 100)
        self.no_avg_price_100 = self._calculate_avg_price(self.yes, 100)

    def _calculate_avg_price(self, orders: List[Tuple[float, float]], target_qty: float) -> Optional[float]:
        if not orders:
            return None
                        
        remaining = target_qty
        weighted_sum = 0
        
        # For asks, we need to convert bid prices to ask prices (100 - bid)
        for price, qty in orders:
            fill_qty = min(remaining, qty)
            weighted_sum += (100 - price) * fill_qty  # Convert to ask space
            remaining -= fill_qty
            if remaining <= 0:
                break
                
        if remaining > 0:  # Could not fill full target quantity
            return None
            
        return weighted_sum / target_qty


    @classmethod
    def from_kalshi_json(cls, data: dict):
        def parse_side(side):
            if not isinstance(side, list):
                return []
            return sorted(
                [tuple(map(float, x)) for x in side if isinstance(x, (list, tuple)) and len(x) == 2],
                key = lambda x: x[0],
                reverse=True
            )

        return cls(
            yes=parse_side(data.get("yes")),
            no=parse_side(data.get("no")),
        )

    @classmethod 
    def from_polymarket_json(cls, data: dict):
        if "error" in data:
            return cls(yes=[], no=[])

        def parse_side(side, is_asks=False):
            if not isinstance(side, list):
                return []
            prices = [(float(x["price"]) * 100, float(x["size"])) for x in side]  # multiply by 100
            if is_asks:
                prices = [(100 - p, s) for p, s in prices]
            return sorted(prices, key=lambda x: x[0], reverse=True)

        # For Polymarket, bids are "yes" orders and asks are "no" orders (1-ask for no)
        return cls(
            yes=parse_side(data.get("bids", [])),
            no=parse_side(data.get("asks", []), is_asks=True),
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
    
    @classmethod
    def from_polymarket_json(cls, data: dict) -> "PredictionMarketEvent":
        return cls(
            title=data["title"],
            ticker=data["ticker"],
            category=None,
            strike_date=safe_parse_datetime("endDate", source=data),
            mutually_exclusive=True,
            sub_title=data.get("description"),
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
    volume_24h: Optional[float]

    strike_type: Optional[str]
    strike_upper: Optional[float]
    strike_lower: Optional[float]

    rules_primary: Optional[str]
    rules_secondary: Optional[str]

    response_price_units: Optional[Literal["usd_cent"]]
    order_book: Optional[OrderBookData]
    platform: Platform

    misc_data: Optional[Dict] = None

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
            volume_24h=market.get("volume_24h"),

            strike_type=market.get("strike_type"),
            strike_upper=market.get("cap_strike") if market.get("strike_type")=="less" else np.inf,
            strike_lower=market.get("floor_strike") if market.get("strike_type")=="greater" else -np.inf,

            rules_primary=market.get("rules_primary"),
            rules_secondary=market.get("rules_secondary"),

            order_book=None,
            response_price_units=market.get("response_price_units", "usd_cent"),
            platform=Platform.KALSHI,
        )
    
    @classmethod
    def from_polymarket_market_json(cls, market: dict, event: PredictionMarketEvent) -> "PredictionMarketContract":
        try:
            best_bid = float(market.get("bestBid", 0)) if market.get("bestBid") else None
            best_ask = float(market.get("bestAsk", 0)) if market.get("bestAsk") else None

            return cls(
                ticker=market["conditionId"],
                title=market["question"],
                category=None,
                event=event,

                open_time=safe_parse_datetime("startDate", source=market),
                close_time=safe_parse_datetime("endDate", source=market),
                expiration_time=safe_parse_datetime("endDateIso", "endDate", source=market),
                expected_expiration_time=None,

                yes_bid=best_bid * 100 if isinstance(best_bid, float) else None,
                yes_ask=best_ask * 100 if isinstance(best_ask, float) else None,
                no_bid=(1-best_ask) * 100 if isinstance(best_ask, float) else None,
                no_ask=(1-best_bid) * 100 if isinstance(best_bid, float) else None,
                last_price=float(market.get("lastTradePrice", 0)) * 100,

                open_interest=None,
                volume=float(market.get("volume", 0)),
                volume_24h=float(market.get("volume24hrClob", 0)),

                strike_type=None,
                strike_upper=None,
                strike_lower=None,

                rules_primary=market.get("description"),
                rules_secondary=None,

                order_book=None,
                response_price_units="usd_cent",
                platform=Platform.POLYMARKET,
                
                misc_data= {
                    "clobTokenIds": market.get("clobTokenIds", "")
                }
            )
        except Exception as e:
            raise ValueError(f"Failed to parse polymarket contract: {e}")
    
    def attach_order_book(self, orderbook_json: dict, platform: Platform):
        if platform == Platform.KALSHI:
            self.order_book = OrderBookData.from_kalshi_json(orderbook_json.get("orderbook", {}))
        elif platform == Platform.POLYMARKET:
            warnings.warn("Polymarket order book not supported yet")
        else:
            warnings.warn("Platform order book not supported yet")


class PredictionMarketBundle(BaseModel):
    platform: Platform
    event: PredictionMarketEvent
    contracts: List[PredictionMarketContract]

    @classmethod
    def from_kalshi_event_payload(cls, data: dict):
        try:
            event = PredictionMarketEvent.from_kalshi_json(data["event"])
        except Exception as e:
            print(f"Failed to parse Kalshi event: {e}")
            return None

        contracts = []
        for mkt in data.get("markets", []):
            try:
                contract = PredictionMarketContract.from_kalshi_market_json(mkt, event)
                contracts.append(contract)
            except Exception as e:
                print(f"Failed to parse market in event {event.ticker}: {e}")
                continue

        return cls(platform=Platform.KALSHI, event=event, contracts=contracts)
    
    @classmethod
    def from_polymarket_event_payload(cls, event_data: dict):
        try:
            event = PredictionMarketEvent.from_polymarket_json(event_data)
            contracts = []

            for market in event_data.get("markets", []):
                try:
                    contract = PredictionMarketContract.from_polymarket_market_json(market, event)
                    contracts.append(contract)
                except Exception as e:
                    print(f"Failed to parse market in event {event.ticker}: {e}")
                    continue

            return cls(platform=Platform.POLYMARKET, event=event, contracts=contracts)

        except Exception as e:
            print(f"Failed to parse polymarket event payload: {e}")
            return None


"""
=================================================
Underlying Extensions
=================================================
"""

class ContinuousUnderlyingPredictionMarket(PredictionMarketEvent):
    """"""
    pass

class BinaryUnderlyingPredictionMarket(PredictionMarketEvent):
    pass