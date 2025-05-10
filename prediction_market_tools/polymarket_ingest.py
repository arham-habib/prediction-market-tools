import httpx
import asyncio
import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from prediction_market_tools.models import (
    PredictionMarketBundle,
    OrderBookData
)


POLYMARKET_BASE_URL = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_URL = "https://clob.polymarket.com"


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


async def extract_polymarket_bundles(raw_events: List[dict]) -> List[PredictionMarketBundle]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        bundles = []
        for event in raw_events:
            if "markets" not in event or not event["markets"]:
                continue

            bundle = PredictionMarketBundle.from_polymarket_event_payload(event)
            await enrich_with_orderbooks(bundle, client)
            if bundle:
                bundles.append(bundle)

        return bundles


async def fetch_orderbook(token_id: str, client: httpx.AsyncClient):
    try:
        url = f"{POLYMARKET_CLOB_URL}/book?token_id={token_id}"
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return OrderBookData.from_polymarket_json(data)
    except:
        return OrderBookData(yes=[], no=[])


async def enrich_with_orderbooks(bundle: PredictionMarketBundle, client: httpx.AsyncClient):
    for contract in bundle.contracts:
        try:
            token_ids_raw = contract.misc_data.get("clobTokenIds")
            if not token_ids_raw:
                continue
            try:
                token_ids = tuple(json.loads(token_ids_raw))
            except json.JSONDecodeError:
                print(f"Failed to parse token IDs for {contract.ticker}: {token_ids_raw}")
                continue
            orderbook = await fetch_orderbook(token_ids[0], client)
            contract.order_book = orderbook
        except httpx.HTTPError as e:
            print(f"Failed to fetch orderbook for {contract.ticker}: {e}")


async def load_polymarket_bundles(
    params: Optional[Dict[str, Any]] = None
) -> List[PredictionMarketBundle]:
    raw_events = await fetch_polymarket_events(params=params)
    bundles = await extract_polymarket_bundles(raw_events)
    return bundles


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


if __name__ == "__main__":
    main()
