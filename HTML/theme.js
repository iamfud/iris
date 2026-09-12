const DEFAULT_C1 = "#48B2E9";
const DEFAULT_C2 = "#B23AF6";
const STEPS = 90;          // half-cycle: palette resolution / steps one way
const STEP_MS = 333.33;    // ~3 fps tick

function resolve(cfg) {
  const mode = (cfg && cfg.mode) || "iris";
  const neon = (cfg && cfg.neon) || "";
  const accent = (cfg && cfg.accent) || "";
  if (mode === "monochrome") return ["#FFFFFF", "#666666"];
  if (mode === "custom") {
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
let prevTime = 0;
let rafId = 0;
let step = 0;
const MAX_STEP = STEPS * 2;

function renderStep(i) {
  const t = i / STEPS;
  const r = lerp(c1rgb[0], c2rgb[0], t);
  const g = lerp(c1rgb[1], c2rgb[1], t);
  const b = lerp(c1rgb[2], c2rgb[2], t);
  document.getElementById("stage").style.backgroundColor = rgbToHex(r, g, b);
}

function tick(now) {
  rafId = requestAnimationFrame(tick);
  if (!prevTime) prevTime = now;
  acc += now - prevTime;
  prevTime = now;
  if (acc >= STEP_MS) {
    acc -= STEP_MS;
    step = (step + 1) % MAX_STEP;
    const i = step < STEPS ? step : MAX_STEP - step;
    renderStep(i);
  }
}

function setLabels() {}

function applyTheme(theme) {
  const pair = resolve(theme);
  const key = pair[0] + "|" + pair[1];
  if (key === lastKey) return;
  lastKey = key;
  c1 = pair[0];
  c2 = pair[1];
  c1rgb = hexToRgb(c1);
  c2rgb = hexToRgb(c2);
  setLabels();
  renderStep(0);
}

async function loadTheme() {
  try {
    const res = await fetch("/api/config", { headers: { "Accept": "application/json" } });
    if (res.ok) {
      const data = await res.json();
      if (data && data.theme) { applyTheme(data.theme); return; }
    }
  } catch (e) { /* app may not be running - use defaults */ }
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
    const wsPort = 15501;

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
      loadTheme();
    };
    wsConn.onmessage = function (e) {
      try {
        const msg = JSON.parse(e.data);
        if (msg && msg.type === "theme") {
          applyTheme(msg.theme || null);
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
  prevTime = now;
  tick(now);
});