# real-time-price.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import threading
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("price-service")

app = FastAPI(title="Real-Time Price Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tickers to support
TICKERS = ["AAPL", "MSFT", "GOOGL"]

API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

# In-memory store: ticker -> list of OHLCV bars
price_data: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TICKERS}

DATA_INTERVAL_MINUTES = 5
MAX_POINTS = 200  # keep payload manageable


def fetch_from_alpha_vantage(ticker: str):
    """
    Example Alpha Vantage intraday price fetch.
    If no API key, this won't be used (we simulate instead).
    """
    if not API_KEY:
        raise RuntimeError("No API key set for Alpha Vantage")

    url = (
        "https://www.alphavantage.co/query"
        "?function=TIME_SERIES_INTRADAY"
        f"&symbol={ticker}"
        "&interval=5min"
        "&outputsize=compact"
        f"&apikey={API_KEY}"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    ts_key = next((k for k in data.keys() if "Time Series" in k), None)
    if not ts_key:
        raise RuntimeError(f"Unexpected API response for {ticker}: {data}")

    ts = data[ts_key]
    bars = []
    for ts_str, values in ts.items():
        bars.append(
            {
                "timestamp": ts_str,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "volume": int(float(values["5. volume"])),
            }
        )
    bars.sort(key=lambda x: x["timestamp"])
    return bars


def simulate_prices(ticker: str):
    """
    Fallback: generate synthetic near-real-time data.
    This keeps running without any external API.
    """
    now = datetime.utcnow().replace(second=0, microsecond=0)
    series = price_data[ticker]

    if not series:
        # Seed with 20 fake candles
        base_price = random.uniform(150, 300)
        bar_time = now - timedelta(minutes=DATA_INTERVAL_MINUTES * 20)
        for _ in range(20):
            base_price += random.uniform(-1, 1)
            bar = {
                "timestamp": bar_time.isoformat() + "Z",
                "open": base_price - 0.5,
                "high": base_price + 0.5,
                "low": base_price - 1.0,
                "close": base_price,
                "volume": random.randint(10_000, 50_000),
            }
            series.append(bar)
            bar_time += timedelta(minutes=DATA_INTERVAL_MINUTES)
    else:
        last_ts = datetime.fromisoformat(series[-1]["timestamp"].replace("Z", ""))
        # Only add a new bar if enough time has "passed"
        if now - last_ts >= timedelta(minutes=DATA_INTERVAL_MINUTES):
            last_close = series[-1]["close"]
            new_close = last_close + random.uniform(-1, 1)
            bar = {
                "timestamp": now.isoformat() + "Z",
                "open": last_close,
                "high": max(last_close, new_close) + 0.5,
                "low": min(last_close, new_close) - 0.5,
                "close": new_close,
                "volume": random.randint(10_000, 50_000),
            }
            series.append(bar)

    # Trim older data
    if len(series) > MAX_POINTS:
        price_data[ticker] = series[-MAX_POINTS:]


def polling_loop():
    """
    Background loop: for each ticker, fetch or simulate new data,
    log errors, but never crash the service.
    """
    while True:
        for ticker in TICKERS:
            try:
                if API_KEY:
                    bars = fetch_from_alpha_vantage(ticker)
                    price_data[ticker] = bars[-MAX_POINTS:]
                    logger.info(f"Updated prices from Alpha Vantage for {ticker}")
                else:
                    simulate_prices(ticker)
                    logger.info(f"Simulated prices for {ticker}")
            except requests.HTTPError as e:
                logger.error(
                    f"HTTP error fetching prices for {ticker}: {e.response.status_code}"
                )
            except requests.RequestException as e:
                logger.error(f"Network error fetching prices for {ticker}: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error fetching prices for {ticker}: {e}")

        # For production: 5 min; for testing you can lower this
        time.sleep(DATA_INTERVAL_MINUTES * 60)


@app.on_event("startup")
def on_startup():
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()


@app.get("/tickers")
def get_tickers():
    return {"tickers": TICKERS}


@app.get("/prices/{ticker}")
def get_prices(ticker: str):
    ticker = ticker.upper()
    if ticker not in TICKERS:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    return {
        "ticker": ticker,
        "interval_minutes": DATA_INTERVAL_MINUTES,
        "data": price_data[ticker],
    }