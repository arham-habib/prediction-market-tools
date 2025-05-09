import httpx
import asyncio
import json
from typing import List
from pathlib import Path
import time
import json


from prediction_market_tools.models import (
    PredictionMarketEvent,
    PredictionMarketContract,
    PredictionMarketBundle,
    OrderBookData,
    Platform,
)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

HEADERS = {
    "Accept": "application/json",
    # Add authorization headers if needed
}

async def fetch_event_with_markets(event_ticker: str, client: httpx.AsyncClient) -> PredictionMarketBundle:
    url = f"{BASE_URL}/events/{event_ticker}?with_nested_markets=true"
    resp = await client.get(url, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    return PredictionMarketBundle.from_kalshi_event_payload({
        "event": data["event"],
        "markets": data.get("markets") or data["event"].get("markets")
    })


async def fetch_orderbook(ticker: str, client: httpx.AsyncClient, depth: int = 5) -> OrderBookData:
    url = f"{BASE_URL}/markets/{ticker}/orderbook?depth={depth}"
    resp = await client.get(url, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    orderbook = data['orderbook']
    return OrderBookData.from_kalshi_json(orderbook)


async def enrich_with_orderbooks(bundle: PredictionMarketBundle, client: httpx.AsyncClient, depth: int = 5):
    for contract in bundle.contracts:
        try:
            orderbook = await fetch_orderbook(contract.ticker, client, depth)
            contract.order_book = orderbook
        except httpx.HTTPError as e:
            print(f"Failed to fetch orderbook for {contract.ticker}: {e}")


async def load_kalshi_bundles(event_tickers: List[str]) -> List[PredictionMarketBundle]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        bundles = []
        for ticker in event_tickers:
            try:
                bundle = await fetch_event_with_markets(ticker, client)
                await enrich_with_orderbooks(bundle, client)
                bundles.append(bundle)
            except httpx.HTTPError as e:
                print(f"Failed to process {ticker}: {e}")
        return bundles