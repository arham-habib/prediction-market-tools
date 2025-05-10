import dash
from dash import dcc, html, Input, Output, State, callback, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import threading
import asyncio
import json
import time
from dash.exceptions import PreventUpdate
from prediction_market_tools.kalshi_ingest import load_kalshi_bundles, enrich_with_orderbooks
from prediction_market_tools.polymarket_ingest import load_polymarket_bundles

# Global data store
shared_data = {
    'kalshi': [],
    'polymarket': []
}

# Thread-safe data store
shared_data_lock = threading.Lock()
shared_data = {
    'kalshi': [],
    'polymarket': []
}

def update_data_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            # Load config
            with open("config.json", "r") as f:
                config = json.load(f)

            # Fetch Kalshi data
            kalshi_tickers = config.get("kalshi_event_tickers", [])
            if not kalshi_tickers:
                print("No Kalshi tickers specified in config.json")
                time.sleep(5)
                continue
            kalshi_data = loop.run_until_complete(load_kalshi_bundles(kalshi_tickers))
            kalshi_filtered = [b for b in kalshi_data if b is not None]

            # Fetch Polymarket data
            polymarket_slugs = config.get("polymarket_event_slugs", [])
            if not polymarket_slugs:
                print("No Polymarket event slugs specified in config.json")
                time.sleep(5)
                continue

            polymarket_data = loop.run_until_complete(load_polymarket_bundles(params={"slug": polymarket_slugs}))
            polymarket_filtered = [b for b in polymarket_data if b is not None]

            # Update shared data in a thread-safe way
            with shared_data_lock:
                shared_data['kalshi'] = kalshi_filtered
                shared_data['polymarket'] = polymarket_filtered

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
@app.callback(
    Output('page-content', 'children'), 
    [Input('url', 'pathname'), Input('refresh-interval', 'n_intervals')]
)
def display_page(pathname, n):
    if pathname == '/' or pathname is None:
        return render_landing_page()
    elif pathname.startswith("/event/"):
        ticker = pathname.split("/event/")[1]
        return render_event_page(ticker)
    elif pathname.startswith("/market/"):
        ticker = pathname.split("/market/")[1]
        return render_market_page(ticker)
    elif pathname == '/config':
        return render_config_page()
    else:
        return html.H3("404 - Page Not Found")


def render_landing_page():
    # Events section
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

    return dbc.Container([
        html.H2("Dashboard", className="mt-4 mb-4"),
        dbc.Button("Configuration", href="/config", color="primary", className="mb-4"),
        html.H2("All Events", className="mb-4"),
        dbc.Row(tiles, className="g-4"),
    ], fluid=True)


def render_config_page():
    with open("config.json", "r") as f:
        config = json.load(f)
    
    kalshi_tickers = config.get("kalshi_event_tickers", [])
    polymarket_slugs = config.get("polymarket_event_slugs", [])

    return dbc.Container([
        dbc.Button("Back to Dashboard", href="/", color="secondary", className="mb-4"),
        html.H2("Configuration", className="mb-4"),
        dbc.Card([
            dbc.CardBody([
                html.H5("Kalshi Event Tickers"),
                dbc.Input(id="new-kalshi-ticker", placeholder="Add new Kalshi ticker...", className="mb-2"),
                dbc.Button("Add Kalshi Ticker", id="add-kalshi-ticker", color="primary", className="mb-3"),
                html.Div([
                    dbc.Badge(
                        [
                            ticker,
                            html.Button(
                                "✕",
                                id={"type": "remove-kalshi", "index": ticker},
                                className="ms-2 btn-close btn-close-white",
                                style={"padding": "0.25rem", "fontSize": "0.75rem"}
                            )
                        ],
                        className="me-1 mb-1"
                    ) for ticker in kalshi_tickers
                ], id="kalshi-tickers-container"),
                
                html.H5("Polymarket Event Slugs", className="mt-3"),
                dbc.Input(id="new-polymarket-slug", placeholder="Add new Polymarket slug...", className="mb-2"),
                dbc.Button("Add Polymarket Slug", id="add-polymarket-slug", color="primary", className="mb-3"),
                html.Div([
                    dbc.Badge(
                        [
                            slug,
                            html.Button(
                                "✕",
                                id={"type": "remove-polymarket", "index": slug}, 
                                className="ms-2 btn-close btn-close-white",
                                style={"padding": "0.25rem", "fontSize": "0.75rem"}
                            )
                        ],
                        className="me-1 mb-1"
                    ) for slug in polymarket_slugs
                ], id="polymarket-slugs-container"),
                
                # Add stores for config management
                dcc.Store(id='config-store'),
                html.Div(id='config-update-trigger')
            ])
        ])
    ], fluid=True)


def render_event_page(ticker):
    for source in ['kalshi', 'polymarket']:
        for bundle in shared_data[source]:
            if bundle.event.ticker == ticker:
                markets = []
                for contract in bundle.contracts:
                    yes_ask_display = f"{contract.yes_ask:.2f}" if isinstance(contract.yes_ask, float) else "N/A"
                    no_ask_display = f"{contract.no_ask:.2f}" if isinstance(contract.no_ask, float) else "N/A"
                    markets.append(
                        dbc.Col(
                            dbc.Card([
                                dbc.CardBody([
                                    html.H5(contract.title),
                                    html.P(f"Ticker: {contract.ticker}"),
                                    html.P([
                                        "Yes Ask: ",
                                        html.Span(yes_ask_display, style={'color': 'red'} if contract.yes_ask else {}),
                                        " | No Ask: ",
                                        html.Span(no_ask_display, style={'color': 'red'} if contract.no_ask else {})
                                    ]),
                                    dcc.Link("View Market", href=f"/market/{contract.ticker}")
                                ])
                            ], className="h-100")
                        , xs=12, sm=6, md=4, lg=3)
                    )
                return dbc.Container([
                    html.H2(f"Event: {bundle.event.title}"),
                    html.P(f"Subtitle: {bundle.event.sub_title}"),
                    html.P(f"Strike Date: {bundle.event.strike_date}"),
                    dbc.Button("Back to All Events", href="/", color="secondary", className="mb-3"),
                    dbc.Row(markets, className="g-4")
                ], fluid=True)
    return html.H3("Event Not Found")


def render_market_page(ticker):
    for source in ['kalshi', 'polymarket']:
        for bundle in shared_data[source]:
            for contract in bundle.contracts:
                if contract.ticker == ticker:
                    orderbook_table = render_order_book(contract)
                    yes_bid_display = f"{contract.yes_bid:.2f}" if isinstance(contract.yes_bid, float) else "N/A"
                    yes_ask_display = f"{contract.yes_ask:.2f}" if isinstance(contract.yes_ask, float) else "N/A"
                    no_bid_display = f"{contract.no_bid:.2f}" if isinstance(contract.no_bid, float) else "N/A"
                    no_ask_display = f"{contract.no_ask:.2f}" if isinstance(contract.no_ask, float) else "N/A"
                    strike_upper_display = f"{contract.strike_upper:.2f}" if isinstance(contract.strike_upper, float) else "N/A"
                    strike_lower_display = f"{contract.strike_lower:.2f}" if isinstance(contract.strike_lower, float) else "N/A"
                    last_price_display = f"{contract.last_price:.2f}" if isinstance(contract.last_price, float) else "N/A"
                    volume_display = f"{contract.volume:.2f}" if isinstance(contract.volume, float) else "N/A"
                    
                    details = [
                        html.H4(f"Market: {contract.title}"),
                        html.P(f"Ticker: {contract.ticker}"),
                        html.P(f"Open Time: {contract.open_time}"),
                        html.P(f"Close Time: {contract.close_time}"),
                        html.P(f"Yes Bid/Ask: {yes_bid_display} / {yes_ask_display}"),
                        html.P(f"No Bid/Ask: {no_bid_display} / {no_ask_display}"),
                        html.P(f"Upper strike: {strike_upper_display}"),
                        html.P(f"Lower strike: {strike_lower_display}"),
                        html.P(f"Last Price: {last_price_display}"),
                        html.P(f"Volume: {volume_display}"),
                        html.P(f"Rules: {contract.rules_primary}"),
                        html.H5("Order Book"),
                        orderbook_table,
                        dbc.Button("Back to Event", href=f"/event/{contract.event.ticker}", color="primary", className="me-2 mt-2"),
                        dbc.Button("Back to All Events", href="/", color="secondary", className="mt-2")
                    ]
                    return dbc.Container(details, fluid=True)
    return html.H3("Market Not Found")

def render_order_book(contract):
    orderbook_table = html.Div("No order book data available")
    if contract.order_book:
        orderbook_table = dbc.Row([
            dbc.Col([
                html.H6("Yes Book"),
                html.P([
                    "Price for 100 contracts: ",
                    html.Span(
                        f"{contract.order_book.yes_avg_price_100:.2f}" if isinstance(contract.order_book.yes_avg_price_100, float) else "N/A",
                        style={'fontWeight': 'bold'}
                    )
                ]),
                dbc.Table([
                    html.Thead(html.Tr([html.Th("Price"), html.Th("Quantity")])),
                    html.Tbody([
                        html.Tr([html.Td(f"{price:.2f}"), html.Td(f"{qty:.2f}")]) for price, qty in contract.order_book.yes
                    ])
                ], bordered=True, striped=True, hover=True)
            ]),
            dbc.Col([
                html.H6("No Book"),
                html.P([
                    "Price for 100 contracts: ",
                    html.Span(
                        f"{contract.order_book.no_avg_price_100:.2f}" if isinstance(contract.order_book.no_avg_price_100, float) else "N/A",
                        style={'fontWeight': 'bold'}
                    )
                ]),
                dbc.Table([
                    html.Thead(html.Tr([html.Th("Price"), html.Th("Quantity")])),
                    html.Tbody([
                        html.Tr([html.Td(f"{price:.2f}"), html.Td(f"{qty:.2f}")]) for price, qty in contract.order_book.no
                    ])
                ], bordered=True, striped=True, hover=True)
            ])
        ])
    return orderbook_table



if __name__ == '__main__':
    app.run(debug=True)
