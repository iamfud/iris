const DEFAULT_C1 = "#48B2E9";
const DEFAULT_C2 = "#B23AF6";
const STEPS = 90;          // half-cycle: palette resolution / steps one way
const STEP_MS = 333.33;    // ~3 fps tick

function resolve(cfg) {
  if (!cfg) return [DEFAULT_C1, DEFAULT_C2];
  const mode = cfg.mode || "iris";
  const neon = cfg.custom_neon || cfg.neon || "";
  const accent = cfg.custom_accent || cfg.accent || "";
  if (mode === "monochrome") return ["#FFFFFF", "#666666"];
  if (mode === "iris") return [DEFAULT_C1, DEFAULT_C2];
  if (mode === "custom" || (!cfg.mode && (neon || accent))) {
    return [neon || DEFAULT_C1, accent || DEFAULT_C2];
  }
  return [DEFAULT_C1, DEFAULT_C2];
}

function hexToRgb(hex) {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

function rgbToHex(r, g, b) {
  function c(v) {
    return Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0");
  }
  return "#" + c(r) + c(g) + c(b);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

let c1 = DEFAULT_C1;
let c2 = DEFAULT_C2;
let c1rgb = hexToRgb(c1);
let c2rgb = hexToRgb(c2);
let lastKey = "";
let acc = 0;
let lastTickTime = performance.now();
let rafId = 0;
let step = 0;
const MAX_STEP = STEPS * 2;

function renderStep(i) {
  const t = i / STEPS;
  const r = lerp(c1rgb[0], c2rgb[0], t);
  const g = lerp(c1rgb[1], c2rgb[1], t);
  const b = lerp(c1rgb[2], c2rgb[2], t);
  const stage = document.getElementById("stage");
  if (stage) stage.style.backgroundColor = rgbToHex(r, g, b);
}

function applyCssTheme(pair) {
  const c1 = pair[0];
  const c2 = pair[1];
  const [r1, g1, b1] = hexToRgb(c1);
  const [r2, g2, b2] = hexToRgb(c2);
  const lum1 = (0.299 * r1 + 0.587 * g1 + 0.114 * b1) / 255;
  const lum2 = (0.299 * r2 + 0.587 * g2 + 0.114 * b2) / 255;
  const bright = (lum1 < 0.42 && lum2 > lum1) ? c2 : c1;
  const badgeFg = ((bright === c2 ? lum2 : lum1) > 0.52) ? "#000000" : "#ffffff";
  const bgR = Math.min(255, Math.max(0, Math.round(8 + r1 * 0.05)));
  const bgG = Math.min(255, Math.max(0, Math.round(8 + g1 * 0.05)));
  const bgB = Math.min(255, Math.max(0, Math.round(10 + b1 * 0.05)));
  const bgDarkR = Math.max(0, bgR - 4);
  const bgDarkG = Math.max(0, bgG - 4);
  const bgDarkB = Math.max(0, bgB - 4);
  const root = document.documentElement;
  const glow = `rgba(${r1}, ${g1}, ${b1}, 0.35)`;
  const themeBg = `rgb(${bgR}, ${bgG}, ${bgB})`;
  const themeBgDark = `rgb(${bgDarkR}, ${bgDarkG}, ${bgDarkB})`;
  const themeBgGlow = `rgba(${r1}, ${g1}, ${b1}, 0.08)`;
  const bgCard = `linear-gradient(135deg, rgba(${Math.round(14 + r1 * 0.05)}, ${Math.round(16 + g1 * 0.05)}, ${Math.round(20 + b1 * 0.05)}, 0.9) 0%, rgba(${Math.round(10 + r1 * 0.03)}, ${Math.round(12 + g1 * 0.03)}, ${Math.round(16 + b1 * 0.03)}, 0.95) 100%)`;

  root.style.setProperty("--theme-color-1", c1);
  root.style.setProperty("--theme-color-2", c2);
  root.style.setProperty("--neon", c1);
  root.style.setProperty("--neon-text", bright);
  root.style.setProperty("--neon-bright", bright);
  root.style.setProperty("--neon-accent", c2);
  root.style.setProperty("--neon-purple", c2);
  root.style.setProperty("--theme-badge-fg", badgeFg);
  root.style.setProperty("--theme-gradient-h", `linear-gradient(90deg, ${c1} 0%, ${c2} 100%)`);
  root.style.setProperty("--theme-gradient-v", `linear-gradient(180deg, ${c1} 0%, ${c2} 100%)`);
  root.style.setProperty("--theme-gradient-conic", `conic-gradient(${c1} 0deg, ${c2} 360deg)`);
  root.style.setProperty("--scrollbar-thumb", `linear-gradient(180deg, ${c1} 0%, ${c2} 100%)`);
  root.style.setProperty("--scrollbar-thumb-hover", `linear-gradient(180deg, ${c1} 0%, ${c2} 100%)`);
  root.style.setProperty("--theme-glow", glow);
  root.style.setProperty("--theme-bg", themeBg);
  root.style.setProperty("--theme-bg-dark", themeBgDark);
  root.style.setProperty("--theme-bg-glow", themeBgGlow);
  root.style.setProperty("--bg-card", bgCard);
}

function advance(now) {
  const dt = now - lastTickTime;
  lastTickTime = now;
  if (dt <= 0) return;
  acc += dt;
  if (acc >= STEP_MS) {
    const n = Math.floor(acc / STEP_MS);
    acc -= n * STEP_MS;
    step = (step + n) % MAX_STEP;
    const i = step < STEPS ? step : MAX_STEP - step;
    renderStep(i);
  }
}

function tick(now) {
  rafId = requestAnimationFrame(tick);
  advance(now || performance.now());
}

// Background fallback timer: if rAF is throttled/paused by the browser (hidden tab or secondary screen),
// setInterval keeps the color animation alive.
setInterval(function () {
  advance(performance.now());
}, 200);

function applyTheme(theme) {
  const pair = resolve(theme);
  const key = pair[0] + "|" + pair[1];
  if (key === lastKey) return;
  lastKey = key;
  c1 = pair[0];
  c2 = pair[1];
  c1rgb = hexToRgb(c1);
  c2rgb = hexToRgb(c2);
  applyCssTheme(pair);
  renderStep(0);
}

var healthyAt = Date.now();
function markHealthy() { healthyAt = Date.now(); }

async function loadTheme() {
  try {
    // 1. Check live panel state first (cheap poll; includes active game profile theme overrides)
    const liveRes = await fetch("/api/panel/live", { headers: { "Accept": "application/json" } });
    if (liveRes.ok) {
      const liveData = await liveRes.json();
      markHealthy();
      if (liveData && liveData.config && liveData.config.theme) {
        applyTheme(liveData.config.theme);
        return;
      }
    }
  } catch (_) {}

  try {
    // 2. Fallback to /api/config
    const res = await fetch("/api/config", { headers: { "Accept": "application/json" } });
    if (res.ok) {
      const data = await res.json();
      markHealthy();
      if (data && data.theme) {
        applyTheme(data.theme);
        return;
      }
    }
  } catch (_) {}
  applyTheme(null);
}

let wsConn = null;
function connectWs() {
  try {
    if (wsConn && (wsConn.readyState === WebSocket.OPEN || wsConn.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const loc = window.location;
    const wsProto = loc.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = loc.hostname || "127.0.0.1";
    const wsPort = loc.protocol === "https:" ? 15505 : 15501;

    let tok = "";
    try { tok = localStorage.getItem("iris_session") || ""; } catch (_) {}
    if (!tok) {
      try {
        const m = document.cookie.match(/(?:^|;\s*)iris_session=([^;]+)/);
        if (m) tok = decodeURIComponent(m[1]);
      } catch (_) {}
    }
    const params = [];
    if (tok) params.push("session=" + encodeURIComponent(tok));
    if (typeof IRIS_TOKEN !== "undefined" && IRIS_TOKEN) params.push("token=" + encodeURIComponent(IRIS_TOKEN));
    const qs = params.length ? "?" + params.join("&") : "";

    wsConn = new WebSocket(wsProto + "//" + wsHost + ":" + wsPort + qs);
    wsConn.onopen = function () {
      var localToken = "";
      var session = "";
      try {
        var lm = document.cookie.match(/(?:^|;\s*)iris_local_token=([^;]+)/);
        if (lm) localToken = decodeURIComponent(lm[1]);
        var sm = document.cookie.match(/(?:^|;\s*)iris_session=([^;]+)/);
        if (sm) session = decodeURIComponent(sm[1]);
      } catch (_) {}
      try { wsConn.send(JSON.stringify({ local_token: localToken, session: session })); } catch (_) {}
      markHealthy();
      loadTheme();
    };
    wsConn.onmessage = function (e) {
      try {
        markHealthy();
        const msg = JSON.parse(e.data);
        if (!msg) return;
        if (msg.type === "theme") {
          applyTheme(msg.theme || null);
        } else if (msg.type === "config") {
          if (msg.config && msg.config.theme) {
            applyTheme(msg.config.theme);
          } else {
            loadTheme();
          }
        } else if (msg.type === "reload") {
          loadTheme();
        }
      } catch (_) {}
    };
    wsConn.onclose = function () {
      wsConn = null;
      setTimeout(connectWs, 2500);
    };
    wsConn.onerror = function () {
      try { wsConn.close(); } catch (_) {}
    };
  } catch (_) {}
}

applyTheme(null);
loadTheme();
connectWs();
requestAnimationFrame(function start(now) {
  lastTickTime = now || performance.now();
  tick(now);
});

(function () {
  var loadedAt = Date.now();
  var lastReload = 0;
  try { lastReload = Number(sessionStorage.getItem("irisLcdLastReload") || 0); } catch (_) {}

  // Periodic poll every 5s keeps theme synced even if WebSocket is disconnected
  setInterval(function () {
    loadTheme();
  }, 5000);

  // Watchdog: only reload if completely non-responsive for over 60s
  setInterval(function () {
    if (document.hidden) return;
    if (Date.now() - healthyAt < 60000) return;
    if (Date.now() - loadedAt < 15000) return;
    if (Date.now() - lastReload < 60000) return;
    lastReload = Date.now();
    try { sessionStorage.setItem("irisLcdLastReload", String(lastReload)); } catch (_) {}
    window.location.reload();
  }, 5000);
})();