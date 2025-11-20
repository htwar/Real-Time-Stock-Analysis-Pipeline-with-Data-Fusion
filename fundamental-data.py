# fundamental-data.py (YFinance Version)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import threading
import time
import logging
from typing import Dict, Any
import yfinance as yf
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fundamental-service")

app = FastAPI(title="Fundamental Data Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supported tickers
TICKERS = ["AAPL", "MSFT", "GOOGL"]

# In-memory fundamental storage
fundamentals: Dict[str, Dict[str, Any]] = {}


# -------------------------------------------------------
# Fetch real fundamental metrics from YFinance
# -------------------------------------------------------
def fetch_fundamentals_from_yf(ticker: str) -> Dict[str, Any]:
    ticker_obj = yf.Ticker(ticker)

    info = ticker_obj.fast_info   # Very fast and reliable

    # Validate availability
    if not info or "last_price" not in info:
        raise RuntimeError(f"No fundamentals available for {ticker}")

    # Wider info uses .info (slower but needed for P/E)
    full = ticker_obj.get_info()

    pe_ratio = full.get("trailingPE") or full.get("forwardPE") or 0
    week52_high = full.get("fiftyTwoWeekHigh") or 0
    week52_low = full.get("fiftyTwoWeekLow") or 0
    market_cap = full.get("marketCap") or 0

    return {
        "ticker": ticker,
        "pe_ratio": float(pe_ratio or 0),
        "market_cap": int(market_cap or 0),
        "week52_high": float(week52_high or 0),
        "week52_low": float(week52_low or 0),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# -------------------------------------------------------
# Refresh loop (runs every hour)
# -------------------------------------------------------
def refresh_loop():
    while True:
        for ticker in TICKERS:
            try:
                fundamentals[ticker] = fetch_fundamentals_from_yf(ticker)
                logger.info(f"Refreshed fundamentals for {ticker}")
            except Exception as e:
                logger.error(f"Error fetching fundamentals for {ticker}: {e}")

        # Update every hour (3600 seconds)
        time.sleep(3600)


# -------------------------------------------------------
# Startup (start background thread)
# -------------------------------------------------------
@app.on_event("startup")
def on_startup():
    thread = threading.Thread(target=refresh_loop, daemon=True)
    thread.start()


# -------------------------------------------------------
# API Endpoints
# -------------------------------------------------------
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
