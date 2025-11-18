// main.js
let chart = null;

async function fetchTickers() {
  const resp = await fetch("/api/tickers");
  if (!resp.ok) {
    throw new Error(`Error fetching tickers: ${resp.status}`);
  }
  return resp.json();
}

async function fetchDashboardData(ticker) {
  const resp = await fetch(`/api/dashboard/${ticker}`);
  if (!resp.ok) {
    throw new Error(`Error fetching dashboard data: ${resp.status}`);
  }
  return resp.json();
}

// ----- Formatting helpers for fundamentals -----
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
    const d = new Date(ts);
    return d.toLocaleString();
  } catch {
    return ts;
  }
}

function updateFundamentalsPanel(fundamentals) {
  const dl = document.getElementById("fundamentals");
  dl.innerHTML = "";

  if (!fundamentals) {
    dl.innerHTML = "<p>No fundamentals available.</p>";
    return;
  }

  const rows = [
    ["P/E Ratio", formatNumber2(fundamentals.pe_ratio)],
    ["Market Cap", formatMarketCap(fundamentals.market_cap)],
    ["52-Week High", formatNumber2(fundamentals.week52_high)],
    ["52-Week Low", formatNumber2(fundamentals.week52_low)],
    ["Last Updated", formatTimestamp(fundamentals.updated_at)],
  ];

  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
}

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

// ----- Fallback SMA calculation on the frontend -----
function computeSMAFromPrices(priceSeries, period = 20) {
  const closes = priceSeries.map((p) => p.close);
  const sma = [];
  for (let i = 0; i < closes.length; i++) {
    if (i + 1 < period) {
      sma.push(null);
    } else {
      let sum = 0;
      for (let j = i + 1 - period; j <= i; j++) {
        sum += closes[j];
      }
      sma.push(sum / period);
    }
  }
  return sma;
}

// ----- Chart rendering -----
function renderChart(priceSeries, indicators) {
  const ctx = document.getElementById("price-chart").getContext("2d");

  const labels = priceSeries.map((p) => p.timestamp);
  const closes = priceSeries.map((p) => p.close);

  // Prefer backend indicator values, but fall back to computing SMA here
  let sma;
  if (indicators && indicators.length === priceSeries.length) {
    sma = indicators.map((p) => p.sma);
  } else {
    sma = computeSMAFromPrices(priceSeries, 20);
  }

  if (chart) {
    chart.destroy();
  }

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Close Price",
          data: closes,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
        },
        {
          label: "SMA-20",
          data: sma,
          borderWidth: 2,
          pointRadius: 0,
          borderDash: [5, 5],
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      scales: {
        x: {
          ticks: {
            display: false,
          },
        },
      },
    },
  });
}

// ----- Load data for a ticker -----
async function loadTicker(ticker) {
  try {
    const data = await fetchDashboardData(ticker);
    renderChart(data.price_series || [], data.indicators || []);
    updateFundamentalsPanel(data.fundamentals);
    updateStatusBadge(data.metadata?.is_recent);
  } catch (err) {
    console.error(err);
    alert("Error loading data. Check console for details.");
  }
}

// ----- Initial setup -----
document.addEventListener("DOMContentLoaded", async () => {
  const select = document.getElementById("ticker-select");
  try {
    const { tickers } = await fetchTickers();
    if (!tickers || tickers.length === 0) {
      select.innerHTML = "<option>No tickers available</option>";
      return;
    }

    select.innerHTML = "";
    tickers.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      select.appendChild(opt);
    });

    const initialTicker = select.value;
    await loadTicker(initialTicker);

    select.addEventListener("change", () => {
      loadTicker(select.value);
    });
  } catch (err) {
    console.error(err);
    alert("Error loading tickers. Check console for details.");
  }
});
