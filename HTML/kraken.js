(function () {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";

  // Iris theme colours (mirrors applyTheme in script.js).
  var DEFAULT_C1 = "#48B2E9"; // theme-color-1 / primary neon
  var DEFAULT_C2 = "#B23AF6"; // theme-color-2 / neon accent

  var TRACK = "rgba(255,255,255,0.10)";
  var TEXT = "#FFFFFF";
  var LABEL = "#9aa0a6";

  var screenEl = document.getElementById("screen");
  var svg;

  // Ring gauge geometry (640 space, centre 320,320). The rings are sized to
  // reach the very edge of the circular LCD (inscribed circle radius 320), so
  // the gauge arcs line up with the visible screen circumference.
  var C = 320;
  var R = 296;
  var STROKE = 46;
  var ARC_LEN = Math.PI * R; // semicircle arc length for dash fractions

  // top semicircle (CPU) 180deg -> 0deg, bottom (GPU) 0deg -> 180deg
  var CPU_D = "M " + (C - R) + " " + C + " A " + R + " " + R + " 0 0 1 " + (C + R) + " " + C;
  var GPU_D = "M " + (C + R) + " " + C + " A " + R + " " + R + " 0 0 1 " + (C - R) + " " + C;

  var TRACK_CPU, TRACK_GPU, FILL_CPU, FILL_GPU, cpuNum, gpuNum, cpuDegree, gpuDegree;

  var cpuC = DEFAULT_C1, gpuC = DEFAULT_C2;
  var lastKey = "";

  function el(tag, attr, parent) {
    var node = document.createElementNS(NS, tag);
    if (attr) {
      Object.keys(attr).forEach(function (k) { node.setAttribute(k, attr[k]); });
    }
    (parent || svg).appendChild(node);
    return node;
  }

  function text(x, y, size, weight, fill, anchor) {
    return el("text", {
      x: x, y: y, "text-anchor": anchor || "middle",
      fill: fill || TEXT, "font-size": size, "font-weight": weight || 300,
      "font-family": "Segoe UI, Helvetica Neue, Roboto, Arial, sans-serif"
    });
  }

  function labelTxt(x, y, txt) {
    var t = text(x, y, 30, 600, LABEL, "middle");
    t.setAttribute("letter-spacing", 10);
    t.textContent = txt;
    return t;
  }

  function build() {
    svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 640 640");
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    screenEl.appendChild(svg);

    var defs = el("defs");

    // ---- CPU gauge (top arc) ----
    TRACK_CPU = el("path", { d: CPU_D, fill: "none", stroke: TRACK, "stroke-width": STROKE, "stroke-linecap": "round" });
    FILL_CPU = el("path", {
      d: CPU_D, fill: "none",
      "stroke-width": STROKE, "stroke-linecap": "round",
      "stroke-dasharray": "0 " + ARC_LEN,
      style: "transition: stroke-dasharray 0.9s linear"
    });

    // ---- GPU gauge (bottom arc) ----
    TRACK_GPU = el("path", { d: GPU_D, fill: "none", stroke: TRACK, "stroke-width": STROKE, "stroke-linecap": "round" });
    FILL_GPU = el("path", {
      d: GPU_D, fill: "none",
      "stroke-width": STROKE, "stroke-linecap": "round",
      "stroke-dasharray": "0 " + ARC_LEN,
      style: "transition: stroke-dasharray 0.9s linear"
    });

    applyRingColours();

    // ---- orbiting sheen highlight per arc (SMIL, CSP-safe) ----
    addSheen(CPU_D, "cpuSheen");
    addSheen(GPU_D, "gpuSheen");

    // ---- CPU value + label ----
    cpuNum = text(C, 300, 128, 300, TEXT, "middle");
    cpuDegree = el("tspan", { "font-size": 48, dy: -72, fill: LABEL });
    cpuDegree.textContent = "\u00b0";
    cpuNum.textContent = "--";
    cpuNum.appendChild(cpuDegree);
    labelTxt(C, 334, "C P U");

    // ---- GPU value + label ----
    gpuNum = text(C, 436, 128, 300, TEXT, "middle");
    gpuDegree = el("tspan", { "font-size": 48, dy: -72, fill: LABEL });
    gpuDegree.textContent = "\u00b0";
    gpuNum.textContent = "--";
    gpuNum.appendChild(gpuDegree);
    labelTxt(C, 470, "G P U");
  }

  function addSheen(d, prefix) {
    var grad = document.createElementNS(NS, "linearGradient");
    grad.setAttribute("id", prefix + "Grad");
    grad.setAttribute("x1", "0%");
    grad.setAttribute("y1", "0%");
    grad.setAttribute("x2", "100%");
    grad.setAttribute("y2", "0%");
    var stops = [
      ["0%", 0.0],
      ["30%", 0.0],
      ["38%", 0.40],
      ["46%", 0.0],
      ["100%", 0.0]
    ];
    stops.forEach(function (s) {
      var st = document.createElementNS(NS, "stop");
      st.setAttribute("offset", s[0]);
      st.setAttribute("stop-color", "#FFFFFF");
      st.setAttribute("stop-opacity", String(s[1]));
      grad.appendChild(st);
    });
    var anim = document.createElementNS(NS, "animate");
    anim.setAttribute("attributeName", "x1");
    anim.setAttribute("values", "0%;120%");
    anim.setAttribute("dur", "6s");
    anim.setAttribute("repeatCount", "indefinite");
    var anim2 = document.createElementNS(NS, "animate");
    anim2.setAttribute("attributeName", "x2");
    anim2.setAttribute("values", "10%;130%");
    anim2.setAttribute("dur", "6s");
    anim2.setAttribute("repeatCount", "indefinite");
    grad.appendChild(anim);
    grad.appendChild(anim2);
    document.getElementsByTagName("defs")[0].appendChild(grad);

    var sheen = document.createElementNS(NS, "path");
    sheen.setAttribute("d", d);
    sheen.setAttribute("fill", "none");
    sheen.setAttribute("stroke", "url(#" + prefix + "Grad)");
    sheen.setAttribute("stroke-width", String(STROKE * 0.62));
    sheen.setAttribute("stroke-linecap", "round");
  }

  function setArcLen(path, frac) {
    var len = Math.max(0, Math.min(1, frac)) * ARC_LEN;
    path.setAttribute("stroke-dasharray", len + " " + ARC_LEN);
  }

  function clamp(v, lo, hi) {
    if (v == null || isNaN(v)) return 0;
    return Math.max(lo, Math.min(hi, v));
  }

  function update(gauges) {
    var cpuMax = Number(gauges.cpu_temp_max) || 100;
    var gpuMax = Number(gauges.gpu_temp_max) || 100;
    var cpuRaw = gauges.cpu_temp;
    var gpuRaw = gauges.gpu_temp;
    var cpu = Number(cpuRaw);
    var gpu = Number(gpuRaw);

    setArcLen(FILL_CPU, clamp(cpu, 0, cpuMax) / cpuMax);
    setArcLen(FILL_GPU, clamp(gpu, 0, gpuMax) / gpuMax);

    var cpuShown = (cpuRaw == null || isNaN(cpu)) ? "--" : String(Math.round(cpu));
    var gpuShown = (gpuRaw == null || isNaN(gpu)) ? "--" : String(Math.round(gpu));
    cpuNum.childNodes[0].nodeValue = cpuShown;
    gpuNum.childNodes[0].nodeValue = gpuShown;
  }

  function applyRingColours() {
    if (!FILL_CPU) return;
    FILL_CPU.setAttribute("stroke", cpuC);
    FILL_GPU.setAttribute("stroke", gpuC);
  }

  function resolve(theme) {
    var mode = (theme && theme.mode) || "iris";
    var neon = (theme && theme.neon) || "";
    var accent = (theme && theme.accent) || "";
    if (mode === "monochrome") return ["#FFFFFF", "#8a8a8a"];
    if (mode === "custom") return [neon || DEFAULT_C1, accent || DEFAULT_C2];
    return [DEFAULT_C1, DEFAULT_C2];
  }

  function luminance(hex) {
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  }

  function applyTheme(theme) {
    var a = resolve(theme);
    var cpu = a[0];
    var gpu = a[1];
    // Near-black theme colours vanish on the black LCD. Substitute the other
    // theme colour (or the iris defaults when both are near-black) so both
    // rings stay visible on the dark display.
    var cpuLum = luminance(cpu);
    var gpuLum = luminance(gpu);
    if (cpuLum < 0.10 && gpuLum >= 0.10) {
      cpu = gpu;
    } else if (gpuLum < 0.10 && cpuLum >= 0.10) {
      gpu = cpu;
    } else if (cpuLum < 0.10 && gpuLum < 0.10) {
      cpu = DEFAULT_C1;
      gpu = DEFAULT_C2;
    }
    var key = cpu + "|" + gpu;
    if (key === lastKey) return;
    lastKey = key;
    cpuC = cpu;
    gpuC = gpu;
    applyRingColours();
  }

  async function loadTheme() {
    try {
      var res = await fetch("/api/config", { headers: { "Accept": "application/json" } });
      if (res.ok) {
        var data = await res.json();
        if (data && data.theme) { applyTheme(data.theme); return; }
      }
    } catch (e) { /* app may not be running - use defaults */ }
    applyTheme(null);
  }

  async function poll() {
    var data = null;
    try {
      var res = await fetch("/api/panel/live", { headers: { "Accept": "application/json" } });
      if (res.ok) data = await res.json();
    } catch (e) { /* server not running */ }
    update(data && data.gauges || {});
  }

  function applyShape() {
    var square = !!(detected && detected.shape === "square");
    screenEl.classList.toggle("shape-circle", !square);
    screenEl.classList.toggle("shape-square", square);
  }

  async function detect() {
    try {
      var res = await fetch("/api/kraken/detect", { headers: { "Accept": "application/json" } });
      if (res.ok) {
        var data = await res.json();
        detected = data && data.found ? data : null;
      }
    } catch (e) {
      detected = null;
    }
    applyShape();
  }

  var detected = null;

  var wsConn = null;
  function connectWs() {
    try {
      if (wsConn && (wsConn.readyState === WebSocket.OPEN || wsConn.readyState === WebSocket.CONNECTING)) return;
      var loc = window.location;
      var wsProto = loc.protocol === "https:" ? "wss:" : "ws:";
      var wsHost = loc.hostname || "127.0.0.1";
      var wsPort = 15501;

      var tok = "";
      try { tok = localStorage.getItem("iris_session") || ""; } catch (_) {}
      if (!tok) {
        try {
          var m = document.cookie.match(/(?:^|;\s*)iris_session=([^;]+)/);
          if (m) tok = decodeURIComponent(m[1]);
        } catch (_) {}
      }
      var params = [];
      if (tok) params.push("session=" + encodeURIComponent(tok));
      if (typeof IRIS_TOKEN !== "undefined" && IRIS_TOKEN) params.push("token=" + encodeURIComponent(IRIS_TOKEN));
      var qs = params.length ? "?" + params.join("&") : "";

      wsConn = new WebSocket(wsProto + "//" + wsHost + ":" + wsPort + qs);
      wsConn.onopen = function () { loadTheme(); };
      wsConn.onmessage = function (e) {
        try {
          var msg = JSON.parse(e.data);
          if (msg && msg.type === "theme") applyTheme(msg.theme || null);
        } catch (_) {}
      };
      wsConn.onclose = function () { wsConn = null; setTimeout(connectWs, 2500); };
      wsConn.onerror = function () { try { wsConn.close(); } catch (_) {} };
    } catch (_) {}
  }

  build();
  applyTheme(null);
  loadTheme();
  detect();
  poll();
  setInterval(poll, 1000);
  connectWs();
})();