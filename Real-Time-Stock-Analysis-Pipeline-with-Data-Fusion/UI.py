# analysis_dashboard.py

import os
import logging
from datetime import datetime

import plotly.graph_objects as go
import requests
import pandas as pd
import streamlit as st

COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com, Inc.",
    "META": "Meta Platforms, Inc.",
    "TSLA": "Tesla, Inc.",
    "NVDA": "NVIDIA Corporation",
    "AMD": "Advanced Micro Devices, Inc.",
    "NFLX": "Netflix, Inc.",
    "META": "Meta Platforms, Inc.",
}

def display_name(ticker: str) -> str:
    """
    Return a nice label like 'Apple Inc. (AAPL)'.
    Falls back to just '(TICKER)' if not in COMPANY_NAMES.
    """
    company = COMPANY_NAMES.get(ticker, "")
    if company:
        return f"{company} ({ticker})"
    return f"({ticker})"


# -----------------------------
# Config & logging
# -----------------------------
st.set_page_config(
    page_title="Real-Time Stock Analysis Dashboard",
    layout="wide",
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)

PRICE_SERVICE_URL = os.getenv("PRICE_SERVICE_URL", "http://realtimeprice-service:8000")
FUNDAMENTAL_SERVICE_URL = os.getenv(
    "FUNDAMENTAL_SERVICE_URL", "http://fundamentaldata-service:8000"
)

REQUEST_TIMEOUT = 5  # seconds


# -----------------------------
# Helper functions (API calls)
# -----------------------------
@st.cache_data(ttl=300)
def fetch_tickers():
    url = f"{PRICE_SERVICE_URL}/tickers"
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("tickers", [])


@st.cache_data(ttl=300)
def fetch_price_data(ticker: str) -> pd.DataFrame:
    url = f"{PRICE_SERVICE_URL}/prices/{ticker}"
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    candles = data.get("data", [])
    if not candles:
        return pd.DataFrame(columns=["timestamp", "price"])

    df = pd.DataFrame(candles)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp")
    df.rename(columns={"close": "price"}, inplace=True)

    df["SMA_20"] = df["price"].rolling(window=20, min_periods=1).mean()

    return df


@st.cache_data(ttl=300)
def fetch_fundamentals(ticker: str) -> dict:
    url = f"{FUNDAMENTAL_SERVICE_URL}/fundamentals/{ticker}"
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data


# -----------------------------
# Formatting helpers
# -----------------------------
def format_number(x, decimals=2, default="N/A"):
    if x is None:
        return default
    try:
        return f"{float(x):.{decimals}f}"
    except (TypeError, ValueError):
        return default


def format_market_cap(x):
    if x is None:
        return "N/A"
    try:
        n = float(x)
    except (TypeError, ValueError):
        return "N/A"

    if n >= 1_000_000_000_000:
        return f"{n / 1_000_000_000_000:.2f}T"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.2f}K"
    return f"{n:.2f}"


def parse_last_updated(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt
    except Exception:
        return None


# -----------------------------
# Main UI
# -----------------------------
def main():
    st.title("Real-Time Stock Analysis with Data Fusion")

    # ============================
    # Top control bar (no sidebar)
    # ============================
    try:
        tickers = fetch_tickers()
    except requests.exceptions.RequestException as e:
        st.error(
            "Could not load tickers from the Price Service. "
            "Verify that the container is running."
        )
        logging.exception("Error fetching tickers: %s", e)
        st.stop()

    if not tickers:
        st.error("No tickers available from the Price Service.")
        st.stop()

    ctrl_col1, ctrl_col2 = st.columns([3, 1])

    # Primary ticker selector with company names
    with ctrl_col1:
        labels = [display_name(t) for t in tickers]
        default_label = labels[0]

        selected_label = st.segmented_control(
            "Primary ticker",
            options=labels,
            default=default_label,
        )
        # Parse back to raw ticker from "Apple Inc. (AAPL)"
        ticker = selected_label.split("(")[-1].replace(")", "").strip()

    with ctrl_col2:
        st.markdown(" ")
        st.markdown(" ")
        if st.button("Clear cache and reload"):
            fetch_tickers.clear()
            fetch_price_data.clear()
            fetch_fundamentals.clear()
            st.rerun()

    # ---- Fetching data for primary ticker ----
    try:
        price_df = fetch_price_data(ticker)
    except requests.exceptions.RequestException as e:
        st.error(
            f"Error fetching price data for {ticker} from the Price Service.\n\n"
            "Details have been logged."
        )
        logging.exception("Error fetching price data for %s: %s", ticker, e)
        st.stop()

    try:
        fundamentals = fetch_fundamentals(ticker)
    except requests.exceptions.RequestException as e:
        st.error(
            f"Error fetching fundamentals for {ticker} from the Fundamental Data Service.\n\n"
            "Details have been logged."
        )
        logging.exception("Error fetching fundamentals for %s: %s", ticker, e)
        fundamentals = {}

    if price_df.empty:
        st.warning(f"No price data returned for {ticker}.")
        st.stop()

    company_label = display_name(ticker)

    # ---- Layout ----
    col_price, col_fund = st.columns([2, 1])

    # ------ Price chart ------
    with col_price:
        st.subheader(f"{company_label} - Stock Analyzer")

        fig = go.Figure()

        fig.add_trace(
            go.Candlestick(
                x=price_df["timestamp"],
                open=price_df["open"],
                high=price_df["high"],
                low=price_df["low"],
                close=price_df["price"],
                name="Price",
            )
        )

        fig.add_trace(
            go.Scatter(
                x=price_df["timestamp"],
                y=price_df["SMA_20"],
                mode="lines",
                name="SMA-20",
            )
        )

        if "volume" in price_df.columns:
            fig.add_trace(
                go.Bar(
                    x=price_df["timestamp"],
                    y=price_df["volume"],
                    name="Volume",
                    opacity=0.3,
                    yaxis="y2",
                )
            )

            fig.update_layout(
                yaxis2=dict(
                    title="Volume",
                    overlaying="y",
                    side="right",
                    showgrid=False,
                )
            )

        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="Price (USD)",
            xaxis=dict(
                range=[price_df["timestamp"].min(), price_df["timestamp"].max()],
                fixedrange=False,
            ),
            yaxis=dict(
                range=[price_df["low"].min(), price_df["high"].max()],
                fixedrange=False,
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=10, r=10, t=40, b=40),
        )

        st.plotly_chart(fig, use_container_width=True)

        latest_row = price_df.iloc[-1]
        latest_price = latest_row["price"]
        latest_sma = latest_row["SMA_20"]
        latest_time = latest_row["timestamp"].tz_convert("US/Eastern")

        st.markdown(
            f"""
            **Latest Price (close):** ${format_number(latest_price)}  
            **Latest SMA-20:** ${format_number(latest_sma)}  
            **Last Price Timestamp (US/Eastern):** {latest_time.strftime("%Y-%m-%d %I:%M %p")}
            """
        )

    # ------ Fundamentals ------
    with col_fund:
        st.subheader(f"{company_label} - Fundamentals")

        pe = fundamentals.get("pe_ratio")
        mc = fundamentals.get("market_cap")
        hi52 = fundamentals.get("week52_high")
        lo52 = fundamentals.get("week52_low")
        last_updated_raw = fundamentals.get("last_updated")

        last_updated_dt = parse_last_updated(last_updated_raw)
        if last_updated_dt is not None:
            last_updated_str = last_updated_dt.astimezone().strftime(
                "%Y-%m-%d %I:%M %p %Z"
            )
        else:
            last_updated_str = "Unknown"

        st.metric("P/E Ratio", format_number(pe))
        st.metric("Market Cap", format_market_cap(mc))
        st.metric("52-Week High", f"${format_number(hi52)}")
        st.metric("52-Week Low", f"${format_number(lo52)}")

        st.caption(f"Fundamentals last updated: {last_updated_str}")

    # ------ Fused Data ------
    st.markdown("---")
    st.subheader(f"Fused Data View: {company_label}")

    st.markdown(
        """
        Time-series price data (with SMA-20) displayed alongside
        company fundamentals on one screen.
        Download for further analysis.
        """
    )

    fused_df = price_df.copy()
    fused_df["pe_ratio"] = pe
    fused_df["market_cap"] = mc
    fused_df["week52_high"] = hi52
    fused_df["week52_low"] = lo52

    st.dataframe(
        fused_df.rename(
            columns={
                "timestamp": "Timestamp",
                "price": "Price",
                "SMA_20": "SMA-20",
                "pe_ratio": "P/E",
                "market_cap": "Market Cap",
                "week52_high": "52-Week High",
                "week52_low": "52-Week Low",
            }
        ),
        use_container_width=True,
    )

    csv = fused_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Fused Data as CSV",
        data=csv,
        file_name=f"{ticker}_fused_data.csv",
        mime="text/csv",
    )

    st.markdown(
        """
        Note: All data is fetched from backend containers via REST APIs and cached briefly (≤5 minutes)
        to ensure the dashboard remains responsive and that price data is no more than 15 minutes old.
        """
    )

    # ---- Stock Comparison Section ----
    st.markdown("---")
    st.subheader("Stock Price Comparison (Closing Prices)")

    st.markdown(
        "Compares normalized closing prices over time so that "
        "different stocks can be viewed on the same scale."
    )

    # Comparison selection lives here
    compare_options = [t for t in tickers if t != ticker]

    st.markdown("**Select tickers to compare**")

    cols = st.columns(len(compare_options)) if compare_options else []
    comparison_tickers = []

    for i, t in enumerate(compare_options):
        with cols[i]:
            label = display_name(t)
            if st.checkbox(label, key=f"cmp_{t}"):
                comparison_tickers.append(t)

    if comparison_tickers:
        compare_frames = []
        all_tickers_for_compare = [ticker] + comparison_tickers

        for t in all_tickers_for_compare:
            try:
                df_t = fetch_price_data(t)
                if not df_t.empty:
                    df_tmp = df_t[["timestamp", "price"]].copy()
                    df_tmp["ticker"] = t
                    compare_frames.append(df_tmp)
            except requests.exceptions.RequestException as e:
                logging.exception("Error fetching comparison data for %s: %s", t, e)

        if compare_frames:
            compare_df = pd.concat(compare_frames, ignore_index=True)

            compare_df = compare_df.sort_values(["ticker", "timestamp"])
            compare_df["norm_price"] = compare_df.groupby("ticker")["price"].transform(
                lambda s: s / s.iloc[0] * 100 if len(s) > 0 else s
            )

            fig_cmp = go.Figure()

            for t in all_tickers_for_compare:
                sub = compare_df[compare_df["ticker"] == t]
                if sub.empty:
                    continue

                fig_cmp.add_trace(
                    go.Scatter(
                        x=sub["timestamp"],
                        y=sub["norm_price"],
                        mode="lines",
                        name=display_name(t),
                    )
                )

            fig_cmp.update_layout(
                xaxis_title="Time",
                yaxis_title="Normalized Price (Base = 100)",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
                margin=dict(l=10, r=10, t=40, b=40),
            )

            st.plotly_chart(fig_cmp, use_container_width=True)
        else:
            st.info("No comparison data available for the selected tickers.")


if __name__ == "__main__":
    main()
