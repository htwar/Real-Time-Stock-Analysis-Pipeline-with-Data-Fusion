# analysis.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
import requests
from typing import List, Dict, Any
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("analysis-service")

app = FastAPI(title="Analysis & Visualization Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------
# Serve static frontend (JS, CSS)
# -------------------------------------------------------
app.mount("/static", StaticFiles(directory="."), name="static")

# -------------------------------------------------------
# Microservice endpoints (Docker service names)
# -------------------------------------------------------
PRICE_SERVICE_URL = os.getenv("PRICE_SERVICE_URL", "http://price-service:8000")
FUNDAMENTAL_SERVICE_URL = os.getenv("FUNDAMENTAL_SERVICE_URL", "http://fundamental-service:8000")


# -------------------------------------------------------
# Compute SMA for 20 candles
# -------------------------------------------------------
def compute_sma(prices: List[Dict[str, Any]], period: int = 20):
    closes = [p["close"] for p in prices]
    sma_values = []

    for i in range(len(closes)):
        if i < period - 1:
            sma_values.append(None)
        else:
            window = closes[i - period + 1 : i + 1]
            sma_values.append(sum(window) / period)

    return [
        {"timestamp": p["timestamp"], "sma": sma}
        for p, sma in zip(prices, sma_values)
    ]


# -------------------------------------------------------
# Determine whether newest candle is "fresh"
# -------------------------------------------------------
def is_data_recent(prices: List[Dict[str, Any]], max_age_minutes: int = 15) -> bool:
    if not prices:
        return False

    last_ts_str = prices[-1]["timestamp"]
    try:
        last_ts = datetime.fromisoformat(last_ts_str.replace("Z", ""))
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = now - last_ts
        return diff.total_seconds() <= max_age_minutes * 60
    except Exception as e:
        logger.error(f"Timestamp parsing error: {e}")
        return False


# -------------------------------------------------------
# Serve index.html
# -------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def serve_index(request: Request):
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>index.html missing</h1>", status_code=500)


# -------------------------------------------------------
# Frontend Ticker Endpoint
# -------------------------------------------------------
@app.get("/api/tickers")
def api_tickers():
    try:
        resp = requests.get(f"{PRICE_SERVICE_URL}/tickers", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error contacting price-service: {e}")
        raise HTTPException(status_code=503, detail="Price service unavailable")


# -------------------------------------------------------
# Core: Fused Dashboard Endpoint
# -------------------------------------------------------
@app.get("/api/dashboard/{ticker}")
def dashboard_data(ticker: str):
    ticker = ticker.upper()

    # ----------------------
    # 1. Get price series
    # ----------------------
    try:
        p_resp = requests.get(f"{PRICE_SERVICE_URL}/prices/{ticker}", timeout=8)
        p_resp.raise_for_status()
        price_payload = p_resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Could not reach price-service: {e}")
        raise HTTPException(status_code=503, detail="Price service unavailable")

    prices = price_payload.get("data", [])
    prices_sorted = sorted(prices, key=lambda x: x["timestamp"])

    # ----------------------
    # 2. Get fundamentals
    # ----------------------
    try:
        f_resp = requests.get(f"{FUNDAMENTAL_SERVICE_URL}/fundamentals/{ticker}", timeout=8)
        f_resp.raise_for_status()
        fundamentals = f_resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Could not reach fundamental-service: {e}")
        raise HTTPException(status_code=503, detail="Fundamental service unavailable")

    # ----------------------
    # 3. Technical Indicators (SMA 20)
    # ----------------------
    indicators = compute_sma(prices_sorted, period=20)

    # ----------------------
    # 4. Freshness check (< 15 min old?)
    # ----------------------
    recent = is_data_recent(prices_sorted, max_age_minutes=15)

    # ----------------------
    # 5. Final fused response
    # ----------------------
    return {
        "ticker": ticker,
        "fundamentals": fundamentals,
        "price_series": prices_sorted,
        "indicators": indicators,
        "metadata": {
            "interval_minutes": price_payload.get("interval_minutes", 5),
            "is_recent": recent,
        },
    }
