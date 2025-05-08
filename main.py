import dash
from dash import dcc, html, Input, Output, State, callback, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import threading
import asyncio
import json
import time
from dash.exceptions import PreventUpdate
from prediction_market_tools.kalshi_ingest import load_kalshi_bundles
from prediction_market_tools.polymarket_ingest import load_polymarket_bundles

# Global data store
shared_data = {
    'kalshi': [],
    'polymarket': []
}

def update_data_loop():
    while True:
        try:
            with open("config.json", "r") as f:
                config = json.load(f)

            event_tickers = config.get("kalshi_event_tickers", [])
            kalshi_data = asyncio.run(load_kalshi_bundles(event_tickers))
            shared_data['kalshi'] = [b for b in kalshi_data if b is not None]

            polymarket_slugs = config.get("polymarket_event_slugs", [])

            if not polymarket_slugs:
                print("No event slugs specified in config.json")
                return

            polymarket_data = asyncio.run(load_polymarket_bundles(params={"slug": polymarket_slugs}))
            shared_data['polymarket'] = [b for b in polymarket_data if b is not None]
            
        except Exception as e:
            print(f"Error updating data: {e}")

        time.sleep(5)

# Start data update loop
threading.Thread(target=update_data_loop, daemon=True).start()

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
server = app.server

app.layout = html.Div([
    dcc.Interval(id='refresh-interval', interval=5*1000, n_intervals=0),
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])

# Route handler
@app.callback(Output('page-content', 'children'), [Input('url', 'pathname'), Input('refresh-interval', 'n_intervals')])
def display_page(pathname, n):
    if pathname == '/' or pathname is None:
        return render_landing_page()
    elif pathname.startswith("/event/"):
        ticker = pathname.split("/event/")[1]
        return render_event_page(ticker)
    elif pathname.startswith("/market/"):
        ticker = pathname.split("/market/")[1]
        return render_market_page(ticker)
    else:
        return html.H3("404 - Page Not Found")


def render_landing_page():
    tiles = []
    for source in ['kalshi', 'polymarket']:
        for bundle in shared_data[source]:
            tiles.append(
                dbc.Card([
                    dbc.CardBody([
                        html.H5(bundle.event.title),
                        html.P(bundle.event.ticker),
                        dcc.Link("View Event", href=f"/event/{bundle.event.ticker}")
                    ])
                ], className="m-2")
            )
    return dbc.Container([html.H2("All Events"), dbc.Row(tiles, className="g-4")], fluid=True)


def render_event_page(ticker):
    for source in ['kalshi', 'polymarket']:
        for bundle in shared_data[source]:
            if bundle.event.ticker == ticker:
                markets = []
                for contract in bundle.contracts:
                    markets.append(
                        dbc.Card([
                            dbc.CardBody([
                                html.H5(contract.title),
                                html.P(f"Ticker: {contract.ticker}"),
                                dcc.Link("View Market", href=f"/market/{contract.ticker}")
                            ])
                        ], className="m-2")
                    )
                return dbc.Container([
                    html.H2(f"Event: {bundle.event.title}"),
                    html.P(f"Subtitle: {bundle.event.sub_title}"),
                    html.P(f"Strike Date: {bundle.event.strike_date}"),
                    dbc.Button("Back to All Events", href="/", color="secondary", className="mb-3"),
                    dbc.Row(markets)
                ], fluid=True)
    return html.H3("Event Not Found")


def render_market_page(ticker):
    for source in ['kalshi', 'polymarket']:
        for bundle in shared_data[source]:
            for contract in bundle.contracts:
                if contract.ticker == ticker:
                    details = [
                        html.H4(f"Market: {contract.title}"),
                        html.P(f"Ticker: {contract.ticker}"),
                        html.P(f"Open Time: {contract.open_time}"),
                        html.P(f"Close Time: {contract.close_time}"),
                        html.P(f"Yes Bid/Ask: {contract.yes_bid} / {contract.yes_ask}"),
                        html.P(f"No Bid/Ask: {contract.no_bid} / {contract.no_ask}"),
                        html.P(f"Last Price: {contract.last_price}"),
                        html.P(f"Volume: {contract.volume}"),
                        html.P(f"Rules: {contract.rules_primary}"),
                        dbc.Button("Back to Event", href=f"/event/{contract.event.ticker}", color="primary", className="me-2 mt-2"),
                        dbc.Button("Back to All Events", href="/", color="secondary", className="mt-2")
                    ]
                    return dbc.Container(details, fluid=True)
    return html.H3("Market Not Found")


if __name__ == '__main__':
    app.run(debug=True)
