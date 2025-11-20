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
    allow_origins=["*"],  # dashboard hits this same service, so this is safe
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static so /static/main.js works
# We just serve from current directory for simplicity.
app.mount("/static", StaticFiles(directory="."), name="static")

PRICE_SERVICE_URL = os.getenv("PRICE_SERVICE_URL", "http://price-service:8000")
FUNDAMENTAL_SERVICE_URL = os.getenv(
    "FUNDAMENTAL_SERVICE_URL", "http://fundamental-service:8000"
)


def compute_sma(prices: List[Dict[str, Any]], period: int = 20):
    """Compute SMA over close prices; returns list with timestamps + sma."""
    closes = [p["close"] for p in prices]
    sma_values = []
    for i in range(len(closes)):
        if i + 1 < period:
            sma_values.append(None)
        else:
            window = closes[i + 1 - period : i + 1]
            sma = sum(window) / period
            sma_values.append(sma)

    result = []
    for p, sma in zip(prices, sma_values):
        result.append({"timestamp": p["timestamp"], "sma": sma})
    return result


def is_data_recent(prices: List[Dict[str, Any]], max_age_minutes: int = 15) -> bool:
    """Check if last price point is within max_age_minutes of now."""
    if not prices:
        return False
    last_ts_str = prices[-1]["timestamp"].replace("Z", "")
    try:
        last_ts = datetime.fromisoformat(last_ts_str)
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age = now - last_ts
        return age.total_seconds() <= max_age_minutes * 60
    except Exception:
        return False


@app.get("/", response_class=HTMLResponse)
def serve_index(request: Request):
    """Serve the dashboard HTML."""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(content=html)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>index.html not found in container</h1>", status_code=500
        )


@app.get("/api/tickers")
def api_tickers():
    """
    Relay tickers from price-service so frontend only talks to analysis-service.
    """
    try:
        resp = requests.get(f"{PRICE_SERVICE_URL}/tickers", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Error contacting price-service for /tickers: {e}")
        raise HTTPException(status_code=503, detail="Price service unavailable")


@app.get("/api/dashboard/{ticker}")
def dashboard_data(ticker: str):
    ticker = ticker.upper()

    # 1. Get prices
    try:
        p_resp = requests.get(f"{PRICE_SERVICE_URL}/prices/{ticker}", timeout=10)
        if p_resp.status_code != 200:
            raise HTTPException(
                status_code=p_resp.status_code,
                detail=f"Error from price-service: {p_resp.text}",
            )
        price_payload = p_resp.json()
    except requests.RequestException as e:
        logger.error(f"Network error contacting price-service: {e}")
        raise HTTPException(status_code=503, detail="Price service unavailable")

    prices = price_payload.get("data", [])
    prices_sorted = sorted(prices, key=lambda x: x["timestamp"])

    # 2. Get fundamentals
    try:
        f_resp = requests.get(
            f"{FUNDAMENTAL_SERVICE_URL}/fundamentals/{ticker}", timeout=10
        )
        if f_resp.status_code != 200:
            raise HTTPException(
                status_code=f_resp.status_code,
                detail=f"Error from fundamental-service: {f_resp.text}",
            )
        fundamentals = f_resp.json()
    except requests.RequestException as e:
        logger.error(f"Network error contacting fundamental-service: {e}")
        raise HTTPException(
            status_code=503, detail="Fundamental service unavailable"
        )

    # 3. Compute SMA
    indicators = compute_sma(prices_sorted, period=20)
    recent = is_data_recent(prices_sorted, max_age_minutes=15)

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