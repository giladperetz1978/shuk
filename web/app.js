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
const countdownEl = document.getElementById("countdown");
const tradesBody = document.getElementById("trades-body");
const lastUpdateEl = document.getElementById("last-update");
const apiBaseInput = document.getElementById("api-base");
const saveApiBtn = document.getElementById("save-api");
const installBtn = document.getElementById("install-app");
const installHint = document.getElementById("install-hint");
const DEFAULT_API_BASE = "https://144-91-96-77.nip.io";
const LEGACY_PLACEHOLDER_VALUES = new Set([
  "https://your-vps-domain.com",
  "http://your-vps-domain.com",
  "your-vps-domain.com",
]);
const engineStatusEl = document.getElementById("engine-status");
const worldSummaryEl = document.getElementById("world-summary");
const agentsInput = document.getElementById("cfg-agents");
const intervalInput = document.getElementById("cfg-interval");
const decisionInput = document.getElementById("cfg-decision");
const thresholdInput = document.getElementById("cfg-threshold");
const cashInput = document.getElementById("cfg-cash");
const cyclesInput = document.getElementById("cfg-cycles");
const startEngineBtn = document.getElementById("start-engine");
const stopEngineBtn = document.getElementById("stop-engine");
const updateEngineConfigBtn = document.getElementById("update-engine-config");

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
  const savedRaw = localStorage.getItem("apiBaseUrl");
  const saved = normalizeBase(savedRaw || "");
  if (!saved || LEGACY_PLACEHOLDER_VALUES.has(saved)) {
    return DEFAULT_API_BASE;
  }
  return saved;
}

let apiBase = getApiBase();
let deferredInstallPrompt = null;
let countdownIntervalSeconds = 300;
let countdownTargetTime = null;

function startCountdown(intervalSeconds, lastUpdateIso) {
  countdownIntervalSeconds = intervalSeconds || 300;
  const intervalMs = countdownIntervalSeconds * 1000;
  if (lastUpdateIso) {
    let target = new Date(lastUpdateIso).getTime() + intervalMs;
    // advance to the next future boundary
    while (target <= Date.now()) {
      target += intervalMs;
    }
    countdownTargetTime = target;
  } else {
    countdownTargetTime = Date.now() + intervalMs;
  }
}

function tickCountdown() {
  if (!countdownEl) return;
  if (!countdownTargetTime) {
    countdownEl.textContent = "--:--";
    return;
  }
  const secsLeft = Math.max(0, Math.round((countdownTargetTime - Date.now()) / 1000));
  const mins = Math.floor(secsLeft / 60);
  const secs = secsLeft % 60;
  countdownEl.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  countdownEl.style.color = secsLeft <= 30 ? "var(--warn)" : "var(--ok)";
}

setInterval(tickCountdown, 1000);

function isStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function setInstallHint(text) {
  if (installHint) {
    installHint.textContent = text;
  }
}

function getEngineConfigFromInputs() {
  return {
    agent_count: Number(agentsInput?.value || 1000),
    interval_seconds: Number(intervalInput?.value || 300),
    decision_interval_cycles: 1,
    action_threshold: Number(thresholdInput?.value || 0.6),
    cash: Number(cashInput?.value || 500),
    cycles: Number(cyclesInput?.value || 0),
  };
}

function getPersistedEngineConfig(config) {
  if (!config) {
    return null;
  }
  return {
    ...config,
    decision_interval_cycles: 1,
    cycles: 0,
    action_threshold: Number(config.action_threshold ?? 0.6),
  };
}

function applyEngineConfigToInputs(config) {
  if (!config) {
    return;
  }
  if (agentsInput) {
    agentsInput.value = String(config.agent_count ?? 1000);
  }
  if (intervalInput) {
    intervalInput.value = String(config.interval_seconds ?? 300);
  }
  if (decisionInput) {
    decisionInput.value = String(config.decision_interval_cycles ?? 1);
  }
  if (thresholdInput) {
    thresholdInput.value = String(config.action_threshold ?? 0.6);
  }
  if (cashInput) {
    cashInput.value = String(config.cash ?? 500);
  }
  if (cyclesInput) {
    cyclesInput.value = String(config.cycles ?? 0);
  }
}

function setEngineStatus(engine) {
  if (!engineStatusEl) {
    return;
  }
  if (!engine) {
    engineStatusEl.textContent = "סטטוס מנוע לא זמין";
    return;
  }
  const running = Boolean(engine.running);
  const cycleText = engine.last_cycle ? `מחזור ${engine.last_cycle}` : "ללא מחזורים עדיין";
  engineStatusEl.textContent = running ? `רץ: ${cycleText}` : "מנוע כבוי";
  engineStatusEl.style.color = running ? "#3ecf8e" : "#f0b429";
  if (worldSummaryEl) {
    worldSummaryEl.textContent = engine.world_summary || "-";
  }
  if (startEngineBtn) {
    startEngineBtn.disabled = running;
  }
  if (stopEngineBtn) {
    stopEngineBtn.disabled = !running;
  }
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  setInstallHint("אפשר להתקין עכשיו בלחיצה על INSTALL");
});

window.addEventListener("appinstalled", () => {
  deferredInstallPrompt = null;
  if (installBtn) {
    installBtn.disabled = true;
  }
  setInstallHint("ההתקנה הושלמה בהצלחה");
});

if (apiBaseInput) {
  apiBaseInput.value = apiBase;
}

// Persist normalized base so old placeholders are replaced automatically.
localStorage.setItem("apiBaseUrl", apiBase);

if (saveApiBtn) {
  saveApiBtn.addEventListener("click", () => {
    apiBase = normalizeBase(apiBaseInput ? apiBaseInput.value : "");
    localStorage.setItem("apiBaseUrl", apiBase);
    refresh();
  });
}

if (installBtn) {
  if (isStandalone()) {
    installBtn.disabled = true;
    setInstallHint("האפליקציה כבר מותקנת במכשיר זה");
  }

  installBtn.addEventListener("click", async () => {
    try {
      if (!deferredInstallPrompt) {
        const ua = navigator.userAgent || "";
        if (ua.includes("Edg")) {
          setInstallHint("אם לא נפתח חלון: בתפריט הדפדפן בחר Apps ואז Install this site as an app");
          alert("Edge: פתח ⋯ > Apps > Install this site as an app");
        } else if (ua.includes("Chrome")) {
          setInstallHint("אם לא נפתח חלון: בתפריט הדפדפן בחר Install app");
          alert("Chrome: פתח ⋮ > Install app");
        } else {
          setInstallHint("בדפדפן זה ההתקנה נעשית דרך תפריט הדפדפן (Add to Home Screen/Install)");
        }
        return;
      }
      deferredInstallPrompt.prompt();
      const choice = await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null;
      installBtn.disabled = true;
      if (choice && choice.outcome === "accepted") {
        setInstallHint("ההתקנה אושרה");
      } else {
        setInstallHint("ההתקנה בוטלה");
        installBtn.disabled = false;
      }
    } catch (_error) {
      setInstallHint("לא ניתן היה לפתוח חלון התקנה כרגע");
    }
  });
}

if (startEngineBtn) {
  startEngineBtn.addEventListener("click", async () => {
    try {
      const config = getEngineConfigFromInputs();
      localStorage.setItem("engineConfig", JSON.stringify(getPersistedEngineConfig(config)));
      const res = await fetch(apiPath("/api/engine/start"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail || "failed to start engine");
      }
      const payload = await res.json();
      setEngineStatus(payload.engine);
      refresh();
    } catch (error) {
      setConnection(false, `שגיאה בהפעלת מנוע: ${error.message}`);
    }
  });
}

if (stopEngineBtn) {
  stopEngineBtn.addEventListener("click", async () => {
    try {
      const res = await fetch(apiPath("/api/engine/stop"), {
        method: "POST",
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail || "failed to stop engine");
      }
      const payload = await res.json();
      setEngineStatus(payload.engine);
      refresh();
    } catch (error) {
      setConnection(false, `שגיאה בעצירת מנוע: ${error.message}`);
    }
  });
}

if (updateEngineConfigBtn) {
  updateEngineConfigBtn.addEventListener("click", async () => {
    try {
      const payload = {
        interval_seconds: Number(intervalInput?.value || 300),
        action_threshold: Number(thresholdInput?.value || 0.6),
        cycles: Number(cyclesInput?.value || 0),
      };
      const res = await fetch(apiPath("/api/engine/config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const responsePayload = await res.json().catch(() => ({}));
        throw new Error(responsePayload.detail || "failed to update engine config");
      }
      const responsePayload = await res.json();
      localStorage.setItem(
        "engineConfig",
        JSON.stringify(getPersistedEngineConfig(responsePayload.engine?.config || getEngineConfigFromInputs())),
      );
      setEngineStatus(responsePayload.engine);
      setConnection(true, "ההגדרות עודכנו וייכנסו לפני הסייקל הבא");
      refresh();
    } catch (error) {
      setConnection(false, `שגיאה בעדכון הגדרות מנוע: ${error.message}`);
    }
  });
}

const savedConfig = localStorage.getItem("engineConfig");
if (savedConfig) {
  try {
    applyEngineConfigToInputs(getPersistedEngineConfig(JSON.parse(savedConfig)));
  } catch (_) {
    // ignore malformed persisted config
  }
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
    const [summaryRes, tradesRes, engineRes] = await Promise.all([
      fetch(apiPath("/api/summary")),
      fetch(apiPath("/api/trades?limit=20")),
      fetch(apiPath("/api/engine/status")),
    ]);

    if (!summaryRes.ok || !tradesRes.ok || !engineRes.ok) {
      throw new Error("API error");
    }

    const summary = await summaryRes.json();
    const trades = await tradesRes.json();
    const engine = await engineRes.json();
    const latest = summary.latest_snapshot;
    if (engine.running) {
      applyEngineConfigToInputs(engine.config);
    }
    setEngineStatus(engine);
    if (engine.running && engine.last_update) {
      startCountdown(
        engine.config?.interval_seconds || 300,
        engine.last_update,
      );
    }

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
    navigator.serviceWorker.register("sw.js").catch(() => {
      // Silent fail: PWA still works without offline cache.
    });
  });
}

refresh();
setInterval(refresh, 15000);
