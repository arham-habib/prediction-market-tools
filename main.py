import asyncio
import json

from prediction_market_tools.kalshi_ingest import load_kalshi_bundles
from prediction_market_tools.polymarket_ingest import main as polymarket_main

def main():
    with open("config.json", "r") as f:
        config = json.load(f)
    
    event_tickers = config["kalshi_event_tickers"]
    bundles = asyncio.run(load_kalshi_bundles(event_tickers))

    # for bundle in bundles:
    #     print(bundle)

    polymarket_main()

if __name__ == "__main__":
    main()