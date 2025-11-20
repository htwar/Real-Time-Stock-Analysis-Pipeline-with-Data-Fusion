# real-time-price.py (YFinance Version)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import threading
import time
import logging
import yfinance as yf
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("price-service")

app = FastAPI(title="Real-Time Price Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supported tickers
TICKERS = ["AAPL", "MSFT", "GOOGL"]

# Data interval
INTERVAL = "5m"
DATA_INTERVAL_MINUTES = 5
MAX_POINTS = 200

# In-memory OHLCV storage
price_data = {t: [] for t in TICKERS}

# -------------------------------------------------------
# Fetch real OHLC candles from Yahoo Finance
# -------------------------------------------------------
def fetch_from_yfinance(ticker: str):
    ticker_obj = yf.Ticker(ticker)

    df = ticker_obj.history(
        period="1d",
        interval=INTERVAL,
        prepost=False
    )

    if df.empty:
        raise RuntimeError(f"No data returned for {ticker}")

    df = df.tz_convert("UTC")

    bars = []
    for ts, row in df.iterrows():
        bars.append({
            "timestamp": ts.isoformat(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })

    return bars[-MAX_POINTS:]


# -------------------------------------------------------
# Background polling loop (every 5 minutes)
# -------------------------------------------------------
def polling_loop():
    while True:
        for ticker in TICKERS:
            try:
                bars = fetch_from_yfinance(ticker)
                price_data[ticker] = bars
                logger.info(f"Fetched {len(bars)} OHLC bars for {ticker}")
            except Exception as e:
                logger.error(f"Error fetching {ticker} from yfinance: {e}")

        time.sleep(DATA_INTERVAL_MINUTES * 60)


# -------------------------------------------------------
# Lifespan handler (instead of deprecated startup event)
# -------------------------------------------------------
@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()


# -------------------------------------------------------
# API Endpoints
# -------------------------------------------------------
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
        "data": price_data[ticker]
    }
