# real-time-price.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
import random
import logging
import math

import yfinance as yf  # <-- NEW: Yahoo Finance wrapper

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
TICKERS = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "NVDA",
    "AMD",
    "NFLX",
]

# In-memory store: ticker -> list of OHLCV bars
price_data: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TICKERS}

DATA_INTERVAL_MINUTES = 5
MAX_POINTS = 200  # keep payload manageable


def fetch_from_yahoo(ticker: str) -> List[Dict[str, Any]]:
    """
    Fetch intraday OHLCV candles from Yahoo Finance using yfinance.
    Uses a 1-day window with 5-minute interval to mimic "real-time" updates.
    """
    df = yf.download(
        tickers=ticker,
        period="1d",                         # last trading day
        interval=f"{DATA_INTERVAL_MINUTES}m",
        auto_adjust=False,
        progress=False,
    )

    if df.empty:
        raise RuntimeError(f"No data from Yahoo Finance for {ticker}")

    bars: List[Dict[str, Any]] = []
    for ts, row in df.iterrows():
        # Skip rows with missing close price
        close = row.get("Close")
        if close is None:
            continue
        if isinstance(close, float) and math.isnan(close):
            continue

        open_ = row.get("Open", close)
        high = row.get("High", close)
        low = row.get("Low", close)
        volume = row.get("Volume", 0)

        bars.append(
            {
                "timestamp": ts.isoformat(),         # ISO timestamp
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": int(volume) if volume is not None else 0,
            }
        )

    if not bars:
        raise RuntimeError(f"No usable OHLCV rows from Yahoo Finance for {ticker}")

    # Already sorted by time, but sort just in case
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
    Background loop: for each ticker, fetch fresh data from Yahoo Finance.
    On error, fall back to simulated prices, log errors, but never crash the service.
    """
    while True:
        for ticker in TICKERS:
            try:
                bars = fetch_from_yahoo(ticker)
                price_data[ticker] = bars[-MAX_POINTS:]
                logger.info(f"Updated prices from Yahoo Finance for {ticker}")
            except Exception as e:
                logger.exception(
                    f"Error fetching prices from Yahoo Finance for {ticker}, "
                    f"falling back to simulation: {e}"
                )
                simulate_prices(ticker)
                logger.info(f"Simulated prices for {ticker}")

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

    # If no data yet (e.g., polling thread not populated), seed it
    if not price_data[ticker]:
        try:
            # Try real data first
            bars = fetch_from_yahoo(ticker)
            price_data[ticker] = bars[-MAX_POINTS:]
            logger.info(f"Seeded prices from Yahoo Finance for {ticker} via on-demand call.")
        except Exception as e:
            logger.exception(
                f"On-demand fetch from Yahoo Finance failed for {ticker}, "
                f"falling back to simulation: {e}"
            )
            simulate_prices(ticker)
            logger.info(f"Seeded simulated prices for {ticker} via on-demand call.")

    return {
        "ticker": ticker,
        "interval_minutes": DATA_INTERVAL_MINUTES,
        "data": price_data[ticker],
    }

