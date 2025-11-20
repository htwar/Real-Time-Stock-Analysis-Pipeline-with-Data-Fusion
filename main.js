// main.js
let chart = null;

// ------------------------------
// Fetch available tickers
// ------------------------------
async function fetchTickers() {
  const resp = await fetch("/api/tickers");
  if (!resp.ok) throw new Error("Error fetching tickers");
  return resp.json();
}

// ------------------------------
// Fetch dashboard bundle
// ------------------------------
async function fetchDashboardData(ticker) {
  const resp = await fetch(`/api/dashboard/${ticker}`);
  if (!resp.ok) throw new Error("Error fetching dashboard data");
  return resp.json();
}

// ------------------------------
// Format helpers
// ------------------------------
function formatNumber2(x) {
  if (x == null || isNaN(x)) return "N/A";
  return Number(x).toFixed(2);
}
function formatMarketCap(x) {
  if (x == null || isNaN(x)) return "N/A";
  const n = Number(x);
  if (n >= 1_000_000_000_000) return (n / 1_000_000_000_000).toFixed(2) + "T";
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(2) + "B";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  return n.toLocaleString("en-US");
}
function formatTimestamp(ts) {
  if (!ts) return "N/A";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

// ------------------------------
// Update fundamentals panel
// ------------------------------
function updateFundamentalsPanel(f) {
  const dl = document.getElementById("fundamentals");
  dl.innerHTML = "";

  if (!f) {
    dl.innerHTML = "<p>No fundamentals available.</p>";
    return;
  }

  const rows = [
    ["P/E Ratio", formatNumber2(f.pe_ratio)],
    ["Market Cap", formatMarketCap(f.market_cap)],
    ["52-Week High", formatNumber2(f.week52_high)],
    ["52-Week Low", formatNumber2(f.week52_low)],
    ["Last Updated", formatTimestamp(f.updated_at)],
  ];

  rows.forEach(([label, value]) => {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
  });
}

// ------------------------------
// Update freshness badge
// ------------------------------
function updateStatusBadge(isRecent) {
  const badge = document.getElementById("data-status");
  if (!badge) return;

  if (isRecent) {
    badge.textContent = "Data ≤ 15 min old";
    badge.classList.remove("stale");
  } else {
    badge.textContent = "Data > 15 min old";
    badge.classList.add("stale");
  }
}

// ------------------------------
// SMA fallback (if backend didn't compute it)
// ------------------------------
function computeSMA(priceSeries, period = 20) {
  const closes = priceSeries.map(p => p.close);
  const result = [];

  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else {
      const slice = closes.slice(i - period + 1, i + 1);
      result.push(slice.reduce((a, b) => a + b) / period);
    }
  }
  return result;
}

// ------------------------------
// Render Candlestick + SMA
// ------------------------------
function renderChart(priceSeries, indicators) {
  const ctx = document.getElementById("price-chart").getContext("2d");

  const candles = priceSeries.map(c => ({
    x: new Date(c.timestamp),
    o: c.open,
    h: c.high,
    l: c.low,
    c: c.close,
  }));

  const smaValues =
    indicators && indicators.length === priceSeries.length
      ? indicators.map(i => i.sma)
      : computeSMA(priceSeries, 20);

  const smaData = priceSeries.map((c, i) => ({
    x: new Date(c.timestamp),
    y: smaValues[i],
  }));

  if (chart) chart.destroy();

  chart = new Chart(ctx, {
    type: "candlestick",
    data: {
      datasets: [
        {
          label: "Candles",
          data: candles,
          color: {
            up: "#22c55e",
            down: "#ef4444",
            unchanged: "#e5e7eb",
          },
        },
        {
          type: "line",
          label: "SMA-20",
          data: smaData,
          borderColor: "yellow",
          borderWidth: 2,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { type: "time", time: { unit: "minute" } },
        y: { beginAtZero: false },
      },
    },
  });
}

// ------------------------------
// Load ticker
// ------------------------------
async function loadTicker(ticker) {
  try {
    const data = await fetchDashboardData(ticker);
    renderChart(data.price_series, data.indicators);
    updateFundamentalsPanel(data.fundamentals);
    updateStatusBadge(data.metadata?.is_recent);
  } catch (err) {
    console.error(err);
    alert("Error loading data.");
  }
}

// ------------------------------
// Init
// ------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  const select = document.getElementById("ticker-select");

  try {
    const { tickers } = await fetchTickers();
    select.innerHTML = "";

    tickers.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      select.appendChild(opt);
    });

    await loadTicker(select.value);

    select.addEventListener("change", () => loadTicker(select.value));

  } catch (err) {
    console.error(err);
    alert("Error loading tickers");
  }
});
