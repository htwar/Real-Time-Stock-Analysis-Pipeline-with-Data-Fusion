# fundamental-data.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import threading
import time
from typing import Dict, Any
import logging
import random
from datetime import datetime
import math

import yfinance as yf  # NEW: Yahoo Finance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fundamental-service")

app = FastAPI(title="Fundamental Data Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# In-memory fundamentals store: ticker -> fundamentals dict
fundamentals: Dict[str, Dict[str, Any]] = {}


def _safe_float(x, default: float | None = None) -> float | None:
    """Convert to float safely, handling None and NaN."""
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def fetch_fundamentals_from_yahoo(ticker: str) -> Dict[str, Any]:
    """
    Fetch company fundamentals (PE, market cap, 52-week high/low) from Yahoo Finance.
    Uses yfinance.Ticker.info.
    """
    y = yf.Ticker(ticker)
    info = y.info  # dict-like metadata

    if not info:
        raise RuntimeError(f"No fundamentals info from Yahoo Finance for {ticker}")

    # PE ratio: prefer trailingPE, fall back to forwardPE
    pe_raw = info.get("trailingPE") or info.get("forwardPE")
    pe_ratio = _safe_float(pe_raw, default=0.0)

    # Market cap from Yahoo (already an int or float)
    market_cap = info.get("marketCap")
    if market_cap is None:
        market_cap = 0
    else:
        try:
            market_cap = int(market_cap)
        except (TypeError, ValueError):
            market_cap = 0

    # 52-week high/low
    week52_high = _safe_float(info.get("fiftyTwoWeekHigh"), default=0.0)
    week52_low = _safe_float(info.get("fiftyTwoWeekLow"), default=0.0)

    return {
        "ticker": ticker,
        "pe_ratio": pe_ratio,
        "market_cap": market_cap,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }


def simulate_fundamentals(ticker: str) -> Dict[str, Any]:
    """
    Fallback fundamentals when Yahoo Finance is unavailable.
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
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }


def refresh_loop():
    """
    Background loop to refresh fundamentals periodically (e.g., hourly).
    Tries Yahoo Finance first; on error, falls back to simulated fundamentals.
    """
    while True:
        for ticker in TICKERS:
            try:
                fundamentals[ticker] = fetch_fundamentals_from_yahoo(ticker)
                logger.info(f"Refreshed fundamentals from Yahoo Finance for {ticker}")
            except Exception as e:
                logger.exception(
                    f"Error fetching fundamentals from Yahoo Finance for {ticker}, "
                    f"falling back to simulation: {e}"
                )
                fundamentals[ticker] = simulate_fundamentals(ticker)
                logger.info(f"Simulated fundamentals for {ticker}")

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
