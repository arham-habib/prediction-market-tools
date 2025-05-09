import httpx
import asyncio
import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from prediction_market_tools.models import (
    PredictionMarketBundle,
)


POLYMARKET_BASE_URL = "https://gamma-api.polymarket.com"


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

        bundle = PredictionMarketBundle.from_polymarket_event_payload(event)
        if bundle:
            bundles.append(bundle)

    return bundles


async def load_polymarket_bundles(
    params: Optional[Dict[str, Any]] = None
) -> List[PredictionMarketBundle]:
    raw_events = await fetch_polymarket_events(params=params)
    return extract_polymarket_bundles(raw_events)


def main():
    config_path = Path("config.json")
    if not config_path.exists():
        raise FileNotFoundError("Missing config.json")

    with open(config_path) as f:
        config = json.load(f)

    slugs = config.get("polymarket_event_slugs", [])
    if not slugs:
        print("No event slugs specified in config.json")
        return

    bundles = asyncio.run(load_polymarket_bundles(params={"slug": slugs}))

    for bundle in bundles:
        print(bundle)

def load_polymarket_orderbook(token_ids: list[str]):
    """Load the orderbook for a market"""
    return 


if __name__ == "__main__":
    main()
