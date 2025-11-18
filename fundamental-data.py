# fundamental-data.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import threading
import time
import requests
from typing import Dict, Any
import logging
import random
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fundamental-service")

app = FastAPI(title="Fundamental Data Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TICKERS = ["AAPL", "MSFT", "GOOGL"]
API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

fundamentals: Dict[str, Dict[str, Any]] = {}


def fetch_fundamentals_from_alpha_vantage(ticker: str) -> Dict[str, Any]:
    """
    Fetch company overview (PE, market cap, etc.) from Alpha Vantage.
    """
    if not API_KEY:
        raise RuntimeError("No API key set for Alpha Vantage")
    url = (
        "https://www.alphavantage.co/query"
        "?function=OVERVIEW"
        f"&symbol={ticker}"
        f"&apikey={API_KEY}"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data or "Symbol" not in data:
        raise RuntimeError(f"Invalid ticker or API response for {ticker}")

    pe_ratio = float(data.get("PERatio", "0") or 0)
    market_cap = int(float(data.get("MarketCapitalization", "0") or 0))
    week52_high = float(data.get("52WeekHigh", "0") or 0)
    week52_low = float(data.get("52WeekLow", "0") or 0)

    return {
        "ticker": ticker,
        "pe_ratio": pe_ratio,
        "market_cap": market_cap,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


def simulate_fundamentals(ticker: str) -> Dict[str, Any]:
    """
    Fallback fundamentals when no API key is provided.
    """
    base = {
        "AAPL": (30.0, 3_000_000_000_000, 220.0, 150.0),
        "MSFT": (35.0, 2_800_000_000_000, 430.0, 280.0),
        "GOOGL": (28.0, 2_000_000_000_000, 190.0, 110.0),
    }
    pe, mc, hi, lo = base.get(ticker, (25.0, 1_000_000_000_000, 200.0, 100.0))

    # Small random jitter
    pe += random.uniform(-1, 1)
    hi += random.uniform(-1, 1)
    lo += random.uniform(-1, 1)

    return {
        "ticker": ticker,
        "pe_ratio": pe,
        "market_cap": mc,
        "week52_high": hi,
        "week52_low": lo,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


def refresh_loop():
    """
    Background loop to refresh fundamentals periodically
    (e.g., hourly). All errors are logged; service stays alive.
    """
    while True:
        for ticker in TICKERS:
            try:
                if API_KEY:
                    fundamentals[ticker] = fetch_fundamentals_from_alpha_vantage(ticker)
                    logger.info(f"Refreshed fundamentals from API for {ticker}")
                else:
                    fundamentals[ticker] = simulate_fundamentals(ticker)
                    logger.info(f"Simulated fundamentals for {ticker}")
            except requests.HTTPError as e:
                logger.error(
                    f"HTTP error fetching fundamentals for {ticker}: {e.response.status_code}"
                )
            except requests.RequestException as e:
                logger.error(f"Network error fetching fundamentals for {ticker}: {e}")
            except Exception as e:
                logger.exception(
                    f"Unexpected error fetching fundamentals for {ticker}: {e}"
                )

        # Refresh once per hour (feel free to shorten while testing)
        time.sleep(3600)


@app.on_event("startup")
def on_startup():
    thread = threading.Thread(target=refresh_loop, daemon=True)
    thread.start()


@app.get("/tickers")
def get_tickers():
    return {"tickers": TICKERS}


@app.get("/fundamentals/{ticker}")
def get_fundamentals(ticker: str):
    ticker = ticker.upper()
    if ticker not in TICKERS:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    data = fundamentals.get(ticker)
    if not data:
        raise HTTPException(status_code=503, detail="Fundamental data not ready yet")
    return data
