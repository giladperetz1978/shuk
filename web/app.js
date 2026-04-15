const fmtMoney = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(Number(value));
};

const fmtNum = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
};

const connection = document.getElementById("connection");
const valueEl = document.getElementById("value");
const cashEl = document.getElementById("cash");
const pnlEl = document.getElementById("pnl");
const cycleEl = document.getElementById("cycle");
const tradesBody = document.getElementById("trades-body");
const lastUpdateEl = document.getElementById("last-update");
const apiBaseInput = document.getElementById("api-base");
const saveApiBtn = document.getElementById("save-api");

function normalizeBase(value) {
  if (!value) {
    return "";
  }
  return value.trim().replace(/\/+$/, "");
}

function getApiBase() {
  const qs = new URLSearchParams(window.location.search).get("api");
  if (qs) {
    return normalizeBase(qs);
  }
  const saved = localStorage.getItem("apiBaseUrl");
  return normalizeBase(saved || "");
}

let apiBase = getApiBase();

if (apiBaseInput) {
  apiBaseInput.value = apiBase;
}

if (saveApiBtn) {
  saveApiBtn.addEventListener("click", () => {
    apiBase = normalizeBase(apiBaseInput ? apiBaseInput.value : "");
    localStorage.setItem("apiBaseUrl", apiBase);
    refresh();
  });
}

function apiPath(path) {
  if (!apiBase) {
    return path;
  }
  return `${apiBase}${path}`;
}

function setConnection(ok, text) {
  connection.textContent = text;
  connection.className = ok ? "badge badge-ok" : "badge badge-warn";
}

function renderTrades(items) {
  tradesBody.innerHTML = "";
  if (!items || !items.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="5">אין עסקאות להצגה כרגע</td>';
    tradesBody.appendChild(row);
    return;
  }

  for (const trade of items.slice(0, 20)) {
    const row = document.createElement("tr");
    const ts = new Date(trade.ts);
    row.innerHTML = `
      <td>${ts.toLocaleString("he-IL")}</td>
      <td class="${String(trade.action).toUpperCase() === "BUY" ? "up" : "down"}">${trade.action}</td>
      <td>${trade.symbol}</td>
      <td>${fmtNum(trade.qty, 3)}</td>
      <td>${fmtMoney(trade.price)}</td>
    `;
    tradesBody.appendChild(row);
  }
}

async function refresh() {
  try {
    const [summaryRes, tradesRes] = await Promise.all([
      fetch(apiPath("/api/summary")),
      fetch(apiPath("/api/trades?limit=20")),
    ]);

    if (!summaryRes.ok || !tradesRes.ok) {
      throw new Error("API error");
    }

    const summary = await summaryRes.json();
    const trades = await tradesRes.json();
    const latest = summary.latest_snapshot;

    if (latest) {
      valueEl.textContent = fmtMoney(latest.value);
      cashEl.textContent = fmtMoney(latest.cash);
      pnlEl.textContent = `${fmtNum(latest.pnl_pct, 2)}%`;
      pnlEl.className = `big ${Number(latest.pnl_pct) >= 0 ? "up" : "down"}`;
      cycleEl.textContent = fmtNum(latest.cycle, 0);
      setConnection(true, apiBase ? "מחובר ל-VPS ומתעדכן אוטומטית" : "מחובר ומתעדכן אוטומטית");
    } else {
      valueEl.textContent = "-";
      cashEl.textContent = "-";
      pnlEl.textContent = "-";
      cycleEl.textContent = "-";
      setConnection(false, "אין עדיין snapshots ב-DB");
    }

    renderTrades(trades.items || []);
    lastUpdateEl.textContent = `עודכן: ${new Date().toLocaleTimeString("he-IL")}`;
  } catch (error) {
    setConnection(false, "אין חיבור ל-API. בדוק כתובת VPS");
  }
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Silent fail: PWA still works without offline cache.
    });
  });
}

refresh();
setInterval(refresh, 15000);
