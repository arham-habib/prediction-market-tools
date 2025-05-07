import httpx
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from prediction_market_tools.models import (
    PredictionMarketEvent,
    PredictionMarketContract,
    PredictionMarketBundle,
    Platform,
    safe_parse_datetime
)


POLYMARKET_BASE_URL = "https://gamma-api.polymarket.com"


def parse_polymarket_event(event: dict) -> PredictionMarketEvent:
    return PredictionMarketEvent(
        title=event["title"],
        ticker=event["ticker"],  # used as condition_id key
        category=None,
        strike_date=datetime.fromisoformat(event["endDate"].replace("Z", "+00:00")),
        mutually_exclusive=True,
        sub_title=event.get("description"),
    )


def parse_polymarket_market(market: dict, event: PredictionMarketEvent) -> PredictionMarketContract:
    outcome_prices = eval(market.get("outcomePrices", "[]"))
    best_bid = float(market.get("bestBid", 0)) if market.get("bestBid") else None
    best_ask = float(market.get("bestAsk", 0)) if market.get("bestAsk") else None

    return PredictionMarketContract(
        ticker=market["conditionId"],  # same as event.ticker
        title=market["question"],
        category=None,
        event=event,

        open_time = safe_parse_datetime("startDate", source=market),
        close_time = safe_parse_datetime("endDate", source=market),
        expiration_time = safe_parse_datetime("endDateIso", "endDate", source=market),
        expected_expiration_time=None,

        yes_bid=best_bid,
        yes_ask=best_ask,
        no_bid=None,
        no_ask=None,
        last_price=float(market.get("lastTradePrice", 0)),

        open_interest=None,
        volume=float(market.get("volume", 0)),

        strike_type=None,
        strike_upper=None,
        strike_lower=None,

        rules_primary=market.get("description"),
        rules_secondary=None,

        response_price_units="usd_cent",
        order_book=None,  # Can be filled in later
        platform=Platform.POLYMARKET,
    )


async def fetch_polymarket_events(
    params: Optional[Dict[str, Any]] = None
) -> List[dict]:
    url = f"{POLYMARKET_BASE_URL}/events"
    default_params = {
        "closed": False
    }
    if params:
        default_params.update(params)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=default_params)
        resp.raise_for_status()
        return resp.json()


def extract_polymarket_bundles(raw_events: List[dict]) -> List[PredictionMarketBundle]:
    bundles = []

    for event in raw_events:
        if "markets" not in event or not event["markets"]:
            continue

        try:
            event_obj = parse_polymarket_event(event)
        except Exception as e:
            print(f"Failure to parse event: {event.get('ticker', '<no-ticker>')}: {e}")
            continue

        contracts = []
        for mkt in event["markets"]:
            try:
                contracts.append(parse_polymarket_market(mkt, event_obj))
            except Exception as e:
                print(f"Failure to parse market in event {event.get('ticker', '<no-ticker>')}: {e}")
                continue

        bundle = PredictionMarketBundle(
            platform=Platform.POLYMARKET,
            event=event_obj,
            contracts=contracts
        )
        bundles.append(bundle)

    return bundles


async def load_polymarket_bundles() -> List[PredictionMarketBundle]:
    raw_events = await fetch_polymarket_events()
    return extract_polymarket_bundles(raw_events)

def main():

    # Load event slugs from config.json
    config_path = Path("config.json")
    if not config_path.exists():
        raise FileNotFoundError("Missing config.json")

    with open(config_path) as f:
        config = json.load(f)

    slugs = config.get("polymarket_event_slugs", [])
    if not slugs:
        print("No event slugs specified in config.json")
        return

    # Fetch and filter events
    all_events = asyncio.run(fetch_polymarket_events(params={"slug": slugs}))
    bundles = extract_polymarket_bundles(all_events)

    for bundle in bundles:
        print(bundle)

if __name__ == "__main__":
    main()