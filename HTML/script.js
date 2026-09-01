/* Iris v3 — HTML UI script */

(function () {
  "use strict";

  if ("serviceWorker" in navigator && !window.pywebview && !window.location.search.includes("_t=")) {
    navigator.serviceWorker.register("sw.js?v=24").catch(() => {});
  }

  const _searchParams = new URLSearchParams(window.location.search);
  const isDesktopCompanion = _searchParams.get("mode") === "desktop";
  if (isDesktopCompanion) {
    document.documentElement.classList.add("is-desktop-companion");
  }

  // ── Platform detection ──────────────────────────────────────
  const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (isIOS) {
    document.documentElement.setAttribute("data-theme", "ios");
  }
  const isAndroid = /Android/i.test(navigator.userAgent);
  const isRealMobileDevice = /Android|iPhone|iPad|iPod|Windows Phone|webOS|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent || "") || isIOS || isAndroid;
  const IS_MOBILE = isRealMobileDevice;
  let IS_APP = !!(window.pywebview && window.pywebview.api);
  if (isAndroid) {
    document.documentElement.classList.add("is-android");
    // iPhone renders at DPR 3.0; most Androids are ~2.6, so the same CSS px
    // comes out physically smaller. Scale notification fonts so Android
    // matches the iPhone's apparent size (3.0 / devicePixelRatio, clamped).
    const dpr = window.devicePixelRatio || 1;
    const s = Math.min(1.5, Math.max(1, 3 / dpr));
    const st = document.documentElement.style;
    st.setProperty("--notif-app-fs", (11 * s).toFixed(1) + "px");
    st.setProperty("--notif-title-fs", (14 * s).toFixed(1) + "px");
    st.setProperty("--notif-body-fs", (12 * s).toFixed(1) + "px");
    // Mixer frame bottom padding (rotates to the RIGHT edge in landscape):
    // same DPR scale so it matches the iPhone's physical gap, plus a small
    // Android-only extra so the frame visually clears the edge.
    st.setProperty("--pv-sliders-pad-b", (25 * s + 3).toFixed(1) + "px");
    // Slider thumbs/track: DPR scale like the fonts, but with a floor so
    // DPR-3.0 Androids (s would clamp to 1 = no visible change) still get
    // a guaranteed bump. The compact/landscape variants use the SAME scaled
    // values as portrait so landscape sliders aren't smaller than portrait.
    const sld = Math.max(s, 1.15);
    st.setProperty("--pv-sld-thumb", (30 * sld).toFixed(1) + "px");
    st.setProperty("--pv-sld-thumb-c", (30 * sld).toFixed(1) + "px");
    st.setProperty("--pv-sld-track", (12 * sld).toFixed(1) + "px");
    st.setProperty("--pv-sld-track-c", (12 * sld).toFixed(1) + "px");
    st.setProperty("--pv-sld-gap", (28 * sld).toFixed(1) + "px");
    st.setProperty("--pv-sld-gap-c", (28 * sld).toFixed(1) + "px");
  }

  function getMediaPlayerBrandIcon(nameOrPath) {
    if (!nameOrPath) return null;
    if (typeof window.getMediaPlayerBrandIcon === "function") {
      const res = window.getMediaPlayerBrandIcon(nameOrPath);
      if (res) return res;
    }
    const s = String(nameOrPath).toLowerCase();
    const clean = s.replace(/[\s\-_.]/g, "");
    const icons = window.MEDIA_PLAYER_BRAND_ICONS || {};
    for (const key in icons) {
      const cleanKey = key.replace(/[\s\-_.]/g, "");
      if (s.includes(key) || clean.includes(cleanKey)) {
        return icons[key];
      }
    }
    return null;
  }

  function getMediaPlayerAppName(pathOrName) {
    let p = pathOrName || (panelLive && panelLive.config && panelLive.config.media_player_path) || (panelDraft && panelDraft.media_player_path) || "";
    if (!p) return "Spotify";
    const s = String(p).toLowerCase();
    if (s.includes("spotify")) return "Spotify";
    if (s.includes("applemusic") || s.includes("apple music")) return "Apple Music";
    if (s.includes("itunes")) return "iTunes";
    if (s.includes("vlc")) return "VLC";
    if (s.includes("musicbee")) return "MusicBee";
    if (s.includes("foobar")) return "foobar2000";
    if (s.includes("aimp")) return "AIMP";
    if (s.includes("tidal")) return "TIDAL";
    if (s.includes("plexamp")) return "Plexamp";
    if (s.includes("wmplayer") || s.includes("windows media player")) return "WMP";
    if (s.includes("winamp")) return "Winamp";
    if (s.includes("mpc-hc") || s.includes("mpc-be")) return "MPC";

    const parts = p.split(/[\\/]/);
    let filename = parts[parts.length - 1] || "";
    if (filename.toLowerCase().endsWith(".exe")) {
      filename = filename.slice(0, -4);
    }
    if (filename) {
      return filename.charAt(0).toUpperCase() + filename.slice(1);
    }
    return "Spotify";
  }

  const API_BASE = window.location.protocol === "file:" ? "http://localhost:15502" : window.location.origin;
  const POLL_MS = 1000;

  // ── Theme Engine ─────────────────────────────────────────────
  let _lastAppliedThemeKey = "";
  window.applyTheme = function (theme) {
    theme = theme || {};
    const mode = theme.mode || "iris";
    const neon = theme.neon || "";
    const accent = theme.accent || "";
    const themeKey = `${mode}|${neon}|${accent}`;
    if (themeKey === _lastAppliedThemeKey) return;
    _lastAppliedThemeKey = themeKey;

    function hexToRgb(hex, def) {
      if (!hex || hex[0] !== "#" || (hex.length !== 7 && hex.length !== 4)) return def;
      const r = parseInt(hex.length === 7 ? hex.slice(1, 3) : hex[1] + hex[1], 16) || 0;
      const g = parseInt(hex.length === 7 ? hex.slice(3, 5) : hex[2] + hex[2], 16) || 0;
      const b = parseInt(hex.length === 7 ? hex.slice(5, 7) : hex[3] + hex[3], 16) || 0;
      return [r, g, b];
    }

    let c1 = "#48B2E9"; // Primary Neon (gradient start / active highlights)
    let c2 = "#B23AF6"; // Neon Accent (gradient end / secondary accent)

    if (mode === "monochrome") {
      c1 = "#FFFFFF"; // Primary White
      c2 = "#666666"; // Secondary Dim Grey
    } else if (mode === "custom") {
      c1 = theme.neon || "#48B2E9";
      c2 = theme.accent || "#B23AF6";
    }

    const [r1, g1, b1] = hexToRgb(c1, [72, 178, 233]);
    const [r2, g2, b2] = hexToRgb(c2, [178, 58, 246]);

    const glow = `rgba(${r1}, ${g1}, ${b1}, 0.35)`;

    // Muted Neon 1 background tint
    const bgR = Math.min(255, Math.max(0, Math.round(8 + r1 * 0.05)));
    const bgG = Math.min(255, Math.max(0, Math.round(8 + g1 * 0.05)));
    const bgB = Math.min(255, Math.max(0, Math.round(10 + b1 * 0.05)));
    const bgDarkR = Math.max(0, bgR - 4);
    const bgDarkG = Math.max(0, bgG - 4);
    const bgDarkB = Math.max(0, bgB - 4);

    const themeBg = `rgb(${bgR}, ${bgG}, ${bgB})`;
    const themeBgDark = `rgb(${bgDarkR}, ${bgDarkG}, ${bgDarkB})`;
    const themeBgGlow = `rgba(${r1}, ${g1}, ${b1}, 0.08)`;

    // Calculate perceived luminance of Neon 1 and Neon 2 (0.0 = dark, 1.0 = light)
    const lum1 = (0.299 * r1 + 0.587 * g1 + 0.114 * b1) / 255;
    const lum2 = (0.299 * r2 + 0.587 * g2 + 0.114 * b2) / 255;
    const badgeFg = lum1 > 0.52 ? "#000000" : "#ffffff";

    // Low luminance Neon 1 fallback: replace with Neon 2 if Neon 1 is dark (< 0.42) and Neon 2 is brighter
    const neonBright = (lum1 < 0.42 && lum2 > lum1) ? c2 : c1;
    const neonText = (lum1 < 0.42 && lum2 > lum1) ? c2 : c1;

    const bgCard = `linear-gradient(135deg, rgba(${Math.round(14 + r1 * 0.05)}, ${Math.round(16 + g1 * 0.05)}, ${Math.round(20 + b1 * 0.05)}, 0.9) 0%, rgba(${Math.round(10 + r1 * 0.03)}, ${Math.round(12 + g1 * 0.03)}, ${Math.round(16 + b1 * 0.03)}, 0.95) 100%)`;

    const root = document.documentElement;
    root.style.setProperty("--theme-color-1", c1);
    root.style.setProperty("--theme-color-2", c2);
    root.style.setProperty("--neon", c1);
    root.style.setProperty("--neon-text", neonText);
    root.style.setProperty("--neon-bright", neonBright);
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

    // Instantly force repaint of SVG gauge gradient arcs
    document.querySelectorAll("#pdev-ggrad, .pdev-ggrad").forEach((grad) => {
      const stops = grad.querySelectorAll("stop");
      if (stops[0]) stops[0].setAttribute("stop-color", c1);
      if (stops[1]) stops[1].setAttribute("stop-color", c2);
    });

    if (typeof _lastGaugeVals !== "undefined") _lastGaugeVals = {};
    document.querySelectorAll(".pdev-garc").forEach((arc) => {
      arc.style.stroke = "none";
      arc.style.stroke = "";
    });
    if (typeof updatePanelView === "function" && typeof panelLive !== "undefined" && panelLive) {
      try { updatePanelView(); } catch (_) {}
    }
  };

  window.addEventListener("pywebviewready", () => {
    IS_APP = true;
    try { updateNavForDevice(); } catch (_) {}
    if (document.documentElement.classList.contains("is-desktop-companion")) {
      _lastAutoFitH = 0;
      setTimeout(autoFitCompanionWindow, 50);
      setTimeout(autoFitCompanionWindow, 200);
      setTimeout(autoFitCompanionWindow, 500);
    }
  });

  function isDesktopEnvironment() {
    if (window.pywebview && window.pywebview.api) return true;
    if (IS_APP) return true;
    if (IS_MOBILE) return false;
    return true;
  }

  // ── Keep-screen-awake (phones) ──────────────────────────────
  let keepAliveEnabled = true;
  let wakeLockSentinel = null;
  let videoWakeLock = null;
  let canvasInterval = null;

  function enableMediaWakeLock() {
    if (!keepAliveEnabled) return;
    if (videoWakeLock) {
      if (videoWakeLock.paused) {
        const p = videoWakeLock.play();
        if (p && p.catch) p.catch(function () {});
      }
      return;
    }
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.fillStyle = "#000000";
        ctx.fillRect(0, 0, 1, 1);
      }

      let stream = null;
      if (canvas.captureStream) {
        stream = canvas.captureStream(1);
      } else if (canvas.mozCaptureStream) {
        stream = canvas.mozCaptureStream(1);
      }

      videoWakeLock = document.createElement("video");
      videoWakeLock.setAttribute("playsinline", "");
      videoWakeLock.setAttribute("webkit-playsinline", "");
      videoWakeLock.setAttribute("muted", "");
      videoWakeLock.muted = true;
      videoWakeLock.setAttribute("loop", "");
      videoWakeLock.loop = true;
      videoWakeLock.style.position = "fixed";
      videoWakeLock.style.top = "0px";
      videoWakeLock.style.left = "0px";
      videoWakeLock.style.width = "1px";
      videoWakeLock.style.height = "1px";
      videoWakeLock.style.opacity = "0.001";
      videoWakeLock.style.pointerEvents = "none";
      videoWakeLock.style.zIndex = "-1";

      if (stream) {
        videoWakeLock.srcObject = stream;
      }

      document.body.appendChild(videoWakeLock);

      if (canvasInterval) clearInterval(canvasInterval);
      canvasInterval = setInterval(function () {
        if (ctx) {
          ctx.fillStyle = ctx.fillStyle === "#000000" ? "#010101" : "#000000";
          ctx.fillRect(0, 0, 1, 1);
        }
      }, 1000);

      const p = videoWakeLock.play();
      if (p && p.catch) p.catch(function () {});
    } catch (_) {}
  }

  function disableMediaWakeLock() {
    if (canvasInterval) {
      clearInterval(canvasInterval);
      canvasInterval = null;
    }
    if (videoWakeLock) {
      try {
        videoWakeLock.pause();
        if (videoWakeLock.parentNode) videoWakeLock.parentNode.removeChild(videoWakeLock);
      } catch (_) {}
      videoWakeLock = null;
    }
  }

  function releaseWakeLock() {
    disableMediaWakeLock();
    const s = wakeLockSentinel;
    wakeLockSentinel = null;
    if (s && !s.released) {
      const p = s.release();
      if (p && p.catch) p.catch(function () {});
    }
  }

  function requestWakeLock() {
    if (!keepAliveEnabled) return;
    if (navigator.wakeLock && navigator.wakeLock.request) {
      if (wakeLockSentinel && !wakeLockSentinel.released) return;
      let p;
      try {
        p = navigator.wakeLock.request("screen");
      } catch (e) {
        enableMediaWakeLock();
        return;
      }
      if (p && p.then) {
        p.then(function (sentinel) {
          wakeLockSentinel = sentinel;
          sentinel.addEventListener("release", function () {
            wakeLockSentinel = null;
            if (keepAliveEnabled && document.visibilityState === "visible") {
              requestWakeLock();
            }
          });
        }).catch(function () {
          enableMediaWakeLock();
        });
      }
    } else {
      enableMediaWakeLock();
    }
  }

  function applyKeepAlive(enabled) {
    keepAliveEnabled = enabled !== false;
    if (keepAliveEnabled) {
      requestWakeLock();
      enableMediaWakeLock();
    } else {
      releaseWakeLock();
    }
  }

  (function setupKeepScreenAwake() {
    if (!IS_MOBILE || IS_APP) return;
    function onGesture() {
      requestWakeLock();
      enableMediaWakeLock();
      if (videoWakeLock && videoWakeLock.paused) {
        const p = videoWakeLock.play();
        if (p && p.catch) p.catch(function () {});
      }
    }
    document.addEventListener("touchstart", onGesture, { passive: true, capture: true });
    document.addEventListener("pointerdown", onGesture, { passive: true, capture: true });
    document.addEventListener("click", onGesture, { capture: true });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") {
        requestWakeLock();
        enableMediaWakeLock();
        if (videoWakeLock && videoWakeLock.paused) {
          const p = videoWakeLock.play();
          if (p && p.catch) p.catch(function () {});
        }
      }
    });
    requestWakeLock();
    enableMediaWakeLock();
  })();

  // ── Landscape mode ──────────────────────────────────────────
  // Applied by the `is-landscape` class on <html>, not by the media query
  // alone: iOS standalone PWAs can report a portrait viewport on cold start,
  // so (orientation: landscape) may never match. Derived from real viewport
  // dimensions + a coarse-pointer gate (touch phones only, so desktop
  // landscape windows stay unrotated). Re-evaluated on load/resize/rotate.
  function updateViewportMode() {
    const prevLand = document.documentElement.classList.contains("is-landscape");
    const isTouch = IS_MOBILE || isIOS || ("ontouchstart" in window) || (navigator.maxTouchPoints > 0) || !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
    const w = window.innerWidth;
    const h = window.innerHeight;
    const isLand = isTouch && ((w > h && Math.min(w, h) <= 768) || (typeof window.orientation !== "undefined" && Math.abs(window.orientation) === 90));
    document.documentElement.classList.toggle("is-landscape", isLand);
    // OLED vs LCD: deep blacks only look rich on a true-OLED panel. High
    // dynamic range + wide gamut is the reliable proxy (OLED phones report
    // both, LCD panels generally don't). Drives the is-oled tile styling.
    const isOled = !!(window.matchMedia &&
      window.matchMedia("(dynamic-range: high) and (color-gamut: p3)").matches);
    document.documentElement.classList.toggle("is-oled", isOled);
    const axis = isLand ? h : w;
    const gridW = Math.max(220, Math.min(Math.round(axis), 393) - 32);
    document.documentElement.style.setProperty("--pv-vw", w + "px");
    document.documentElement.style.setProperty("--pv-vh", h + "px");
    document.documentElement.style.setProperty("--pv-grid-w", gridW + "px");
    if (panelViewMode) {
      const ov = document.getElementById("panel-view");
      if (ov) {
        layoutPanelBox(ov);
        restoreBoxScroll();
      }
      // The grid button order is baked in at render time, so a landscape flip
      // must rebuild the panel (boardPagesHtml reads is-landscape live).
      if (isLand !== prevLand) {
        const pageToRestore = activeBoxPage || 1;
        pendingPanelPage = pageToRestore;
        renderPanelView();
        restoreBoxScroll(pageToRestore);
      }
    }
  }

  // Auth is carried by the loopback session or the login session cookie; the
  // access token is never embedded in the page any more.
  const IRIS_TOKEN = "";

  function apiFetch(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign({}, opts.headers || {});
    let savedTok = "";
    try { savedTok = localStorage.getItem("iris_session") || ""; } catch (_) {}
    if (savedTok) opts.headers["X-Iris-Session"] = savedTok;
    if (IRIS_TOKEN) opts.headers["X-Iris-Token"] = IRIS_TOKEN;
    return fetch(url, opts).then(function (res) {
      if (res.status === 401) {
        if (IS_MOBILE && !IS_APP && !(window.pywebview && window.pywebview.api)) {
          // Session expired or unauthenticated remote phone access -> back to login.
          window.location.href = "/login";
        }
        throw new Error("unauthorized");
      }
      return res;
    });
  }

  function copyTextNative(text) {
    if (!text) return Promise.resolve();
    return apiFetch(`${API_BASE}/api/clipboard`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text })
    }).catch(() => {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).catch(() => {});
      }
    });
  }

  let currentPage = "dashboard";
  let pluginState = {};
  let pollTimer = null;
  let lastScrollTop = 0;
  let pluginsConfig = {};
  let selectedPlugin = null;
  let deviceStatus = {};
  let alarms = [];
  let editingAlarmId = null;
  let editingAlarm = null;
  let pluginSnapshots = {};
  let alarmSaveTimer = null;
  let settingsRenderer = null;
  let panelEntities = [];
  let audioOutputDevices = [];

  let visionSensors = [];
  let visionLive = null;
  let visionTimer = null;
  let visionInWizard = false;
  let visionDraft = null;
  let wizardStep = 1;
  let wizardCapture = null;
  let testTimer = null;

  const ALARM_SOUNDS = [
    { name: "remind",  label: "Remind",  icon: "notifications_active" },
    { name: "annoy",   label: "Annoy",   icon: "alarm" },
    { name: "melody",  label: "Melody",  icon: "music_note" },
  ];

  let previewingSound = null;

  function previewSound(name) {
    if (previewingSound === name) {
      stopPreview();
      return;
    }
    stopPreview();
    previewingSound = name;
    apiFetch(`${API_BASE}/api/sounds/preview/${encodeURIComponent(name)}`).catch(() => {});
  }

  function stopPreview() {
    previewingSound = null;
    apiFetch(`${API_BASE}/api/sounds/stop`).catch(() => {});
  }

  // ── DOM refs ────────────────────────────────────────────────

  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("nav-overlay");
  const hamburger = document.getElementById("hamburger");
  const main = document.querySelector(".main");
  const content = document.getElementById("content");

  // ── Sidebar navigation (desktop) ────────────────────────────

  const navItems = document.querySelectorAll(".nav-item");

  navItems.forEach((item) => {
    item.addEventListener("click", () => {
      navItems.forEach((n) => n.classList.remove("active"));
      item.classList.add("active");
      const page = item.getAttribute("data-page");
      if (page) {
        if (page === "panel") {
          if (IS_MOBILE && !IS_APP) {
            portalAutoPanel = true;
            fetchPanel();
            openPanelView();
            closeNav();
            return;
          }
          currentPage = "panel";
          selectedPlugin = null;
          portalAutoPanel = false;
          panelViewMode = false;
          panelNav = [];
          exitPanelView();
          if (panelLiveTimer) { clearInterval(panelLiveTimer); panelLiveTimer = null; }
          renderPage();
          fetchPanel();
        } else if (page === "vision" && IS_MOBILE && !IS_APP) {
          currentPage = "dashboard";
          renderPage();
        } else {
          currentPage = page;
          selectedPlugin = null;
          exitPanelView();
          renderPage();
          if (page === "features" || page === "alarms" || page === "settings") fetchConfig();
          else if (page === "plugins") { fetchPluginsConfig(); fetchConfig(); }
          else if (page === "vision") fetchVision();
          else { visionInWizard = false; stopTestPoll(); }
        }
      }
    });
  });

  window.navigateToPage = function (pageName) {
    if (!pageName) return;
    const targetNav = document.querySelector(`.nav-item[data-page="${pageName}"]`);
    if (targetNav) {
      targetNav.click();
    } else {
      currentPage = pageName;
      selectedPlugin = null;
      exitPanelView();
      renderPage();
    }
  };

  window.irisSetPage = function (page, tab) {
    try {
      if (page === "library" && (tab === "screenshots" || tab === "notes")) {
        libraryTab = tab;
      }
      if (typeof window.navigateToPage === "function") {
        window.navigateToPage(page);
      }
      const u = new URL(window.location.href);
      u.searchParams.set("page", page);
      if (tab) u.searchParams.set("tab", tab);
      window.history.replaceState({}, "", u.toString());
    } catch (_) {}
  };

  // ── Hamburger menu (mobile) ─────────────────────────────────

  if (hamburger) {
    hamburger.addEventListener("click", toggleNav);
  }

  if (overlay) {
    overlay.addEventListener("click", closeNav);
  }

  function toggleNav() {
    sidebar.classList.toggle("open");
    overlay.classList.toggle("visible");
  }

  function closeNav() {
    sidebar.classList.remove("open");
    overlay.classList.remove("visible");
  }

  // ── Edge swipe for sidebar (mobile) ───────────────────────

  (function initSwipe() {
    const EDGE = 24;
    const THRESHOLD = 50;
    let sx = 0, sy = 0, tracking = false, gesture = null;

    document.addEventListener("touchstart", (e) => {
      if (panelViewMode) { tracking = false; return; }
      const t = e.touches[0];
      sx = t.clientX;
      sy = t.clientY;
      tracking = true;
      gesture = null;
    }, { passive: true });

    document.addEventListener("touchmove", (e) => {
      if (!tracking) return;
      const t = e.touches[0];
      const dx = t.clientX - sx;
      const dy = t.clientY - sy;
      if (!gesture && Math.abs(dx) > 10) {
        if (sx < EDGE && dx > 0) gesture = "open";
        else if (sidebar.classList.contains("open") && Math.abs(dx) > Math.abs(dy)) gesture = "close";
        else tracking = false;
      }
      if (gesture) {
        if (Math.abs(dx) > Math.abs(dy)) e.preventDefault();
      }
    }, { passive: false });

    document.addEventListener("touchend", (e) => {
      if (!tracking || !gesture) { tracking = false; return; }
      const dx = e.changedTouches[0].clientX - sx;
      if (gesture === "open" && dx > THRESHOLD) {
        sidebar.classList.add("open");
        overlay.classList.add("visible");
      } else if (gesture === "close" && Math.abs(dx) > THRESHOLD) {
        sidebar.classList.remove("open");
        overlay.classList.remove("visible");
      }
      tracking = false;
    }, { passive: true });
  })();

  // Native CSS Scroll Snapping (scroll-snap-type: x mandatory) handles page alignment
  // and smooth inertia across iOS Safari and Android Chrome without JS gesture collision.
  (function initBoxInertia() {
    // Relying on native CSS scroll snapping for silky smooth 60fps sliding
  })();

  // ── Data fetching ───────────────────────────────────────────

  let _fetchStateBusy = false;
  async function fetchState() {
    if (_fetchStateBusy) return;
    _fetchStateBusy = true;
    try {
      const res = await apiFetch(`${API_BASE}/api/plugins/state`);
      if (res.ok) {
        const next = await res.json();
        const prev = pluginState;
        pluginState = next;
        // In-place live updates only — never rebuild the whole page from poll.
        if (currentPage === "plugins" && selectedPlugin && settingsRenderer) {
          var dataEl = main.querySelector(".plugin-data-container");
          if (dataEl && next[selectedPlugin]) {
            var snap = pluginSnapshots[selectedPlugin] || next[selectedPlugin];
            var newHtml = '<span class="plugin-edit-label">DATA</span>' +
              settingsRenderer._renderPluginData(selectedPlugin, snap, next[selectedPlugin]);
            if (dataEl.innerHTML !== newHtml) {
              dataEl.innerHTML = newHtml;
            }
          }
        } else if (currentPage === "dashboard") {
          // Only rebuild dashboard when plugin availability/status cards would change.
          var statusChanged = false;
          var names = Object.keys(next).filter(function(n) { return n !== "vision"; });
          var prevNames = Object.keys(prev).filter(function(n) { return n !== "vision"; });
          for (var i = 0; i < names.length; i++) {
            var n = names[i];
            var a = (prev[n] && prev[n].available) || false;
            var b = (next[n] && next[n].available) || false;
            if (a !== b) { statusChanged = true; break; }
          }
          if (statusChanged || prevNames.length !== names.length) {
            renderDashboard();
          }
        }
      }
    } catch (_) {
      // server not running yet — silent fail
    }
    _fetchStateBusy = false;
    pollTimer = setTimeout(fetchState, POLL_MS);
  }

  function renderInitialView() {
    const params = new URLSearchParams(window.location.search);
    const isViewerParam = params.get("view") === "viewer";
    const viewerFile = params.get("file");
    if (isViewerParam && viewerFile) {
      document.body.classList.add("standalone-viewer-mode");
      openLibraryViewer(viewerFile);
      return;
    }

    const isNotepadParam = params.get("view") === "notepad";
    if (isNotepadParam) {
      document.body.classList.add("standalone-notepad-mode");
      const noteFile = params.get("file");
      const noteApp = params.get("app") || "general";
      const noteTitle = params.get("title") || "";
      const noteBody = params.get("body") || "";
      openNotepad(noteFile, noteApp, true, noteTitle, noteBody);
      return;
    }

    const isLibParam = params.get("view") === "library" || params.get("page") === "library";
    if (isLibParam) {
      currentPage = "library";
      const tab = params.get("tab");
      if (tab === "notes" || tab === "screenshots") {
        libraryTab = tab;
      }
      navItems.forEach((n) => n.classList.toggle("active", n.dataset.page === "library"));
      renderPage();
      if (viewerFile) {
        setTimeout(() => openLibraryViewer(viewerFile), 300);
      }
      if (params.get("action") === "new_note" || params.get("action") === "note") {
        setTimeout(() => openNotepad(null, params.get("app") || "general"), 150);
      }
      return;
    }

    const isPanelParam = params.get("view") === "panel" || params.get("panel") === "1";
    if (isPanelParam) {
      currentPage = "panel";
      portalAutoPanel = false;
      openPanelView();
      fetchPanel();
      return;
    } else if (IS_APP || !IS_MOBILE) {
      renderPage();
    } else {
      // Phone portal: land directly on the live panel instead of the dashboard.
      currentPage = "panel";
      navItems.forEach((n) => n.classList.remove("active"));
      const panelNavItem = document.querySelector('.nav-item[data-page="panel"]');
      if (panelNavItem) panelNavItem.classList.add("active");
      portalAutoPanel = true;
      fetchPanel();
    }
  }

  function updateNavForDevice() {
    const isMobile = (window.matchMedia && window.matchMedia("(max-width: 768px)").matches) || isIOS || isAndroid;
    const panelLabel = document.getElementById("panel-nav-label") || document.querySelector('.nav-item[data-page="panel"] .label');
    const visionNav = document.querySelector('.nav-item[data-page="vision"]');

    if (isMobile && !IS_APP) {
      if (panelLabel) panelLabel.textContent = "Panel";
      if (visionNav) visionNav.style.display = "none";
    } else {
      if (panelLabel) panelLabel.textContent = "Panel Editor";
      if (visionNav) visionNav.style.display = "";
    }
  }

  function startPolling() {
    const urlParams = new URLSearchParams(window.location.search);
    const isStandaloneViewer = urlParams.get("view") === "viewer";
    const isStandaloneNotepad = urlParams.get("view") === "notepad";

    if (isStandaloneViewer || isStandaloneNotepad) {
      renderInitialView();
      connectWs();
      return;
    }

    const isMobilePanel = (IS_MOBILE && !IS_APP) || urlParams.get("view") === "panel" || urlParams.get("panel") === "1";

    if (isMobilePanel) {
      currentPage = "panel";
      portalAutoPanel = true;
      openPanelView();
      fetchConfig();
      fetchPanel();
      fetchPanelLive();
      if (!panelLiveTimer) panelLiveTimer = setInterval(fetchPanelLive, 1000);
      connectWs();
      return;
    }

    settingsRenderer = new SettingsRenderer(API_BASE);
    updateNavForDevice();
    window.addEventListener("resize", updateNavForDevice);
    
    // Render initial page immediately to avoid any black window / unpainted frame
    renderInitialView();

    fetchConfig();
    fetchPanel();
    fetchEntities();
    fetchAudioDevices();

    settingsRenderer.loadPages().then(function (pages) {
      if (pages && pages.length && currentPage === "settings") {
        renderPage();
      }
    }).catch(function () {});

    fetchState();
    fetchPluginsConfig();
    fetchDeviceStatus();
    fetchPanelLive();
    if (!panelLiveTimer) panelLiveTimer = setInterval(fetchPanelLive, 1000);
    connectWs();
  }

  // ── Page rendering ──────────────────────────────────────────

  function renderPage() {
    try {
      if ((IS_MOBILE && !IS_APP) && (currentPage === "vision" || (currentPage === "panel" && !panelViewMode))) {
        portalAutoPanel = true;
        fetchPanel();
        openPanelView();
        return;
      }
      const sc = main.querySelector('.settings-content') || main.querySelector('.content') || main;
      const prevScroll = sc ? sc.scrollTop : 0;
      if (currentPage === "dashboard") {
        renderDashboard();
      } else if (currentPage === "alarms") {
        alarms = featureConfig.alarms || [];
        renderAlarms();
      } else if (currentPage === "notifications") {
        renderNotifications();
      } else if (currentPage === "library") {
        renderLibrary();
      } else if (currentPage === "plugins") {
        if (selectedPlugin) {
          renderPluginSettings(selectedPlugin);
        } else {
          renderPlugins();
        }
      } else if (settingsRenderer && settingsRenderer.getPage(currentPage)) {
        renderDeclarativePage(currentPage);
      } else if (currentPage === "features") {
        renderFeatures();
      } else if (currentPage === "vision") {
        renderVision();
      } else if (currentPage === "automations") {
        renderAutomations();
      } else if (currentPage === "panel") {
        renderPanel();
      } else {
        renderPlaceholder();
      }
      const newSc = main.querySelector('.settings-content') || main.querySelector('.content') || main;
      if (newSc && prevScroll) newSc.scrollTop = prevScroll;
    } catch (err) {
      console.error("[Iris] renderPage error:", err);
      try { renderPlaceholder(); } catch (_) {}
    }
  }

  // ── Declarative page rendering ────────────────────────────────

  function renderDeclarativePage(pageId) {
    try {
      var page = settingsRenderer ? settingsRenderer.getPage(pageId) : null;
      if (!page) { renderPlaceholder(); return; }

      var contentHtml = settingsRenderer.renderBuiltInPage(
        pageId, featureConfig, pluginsConfig, pluginState, deviceStatus
      );

      main.innerHTML =
        '<header>' +
          '<div class="header-left">' +
            '<button class="hamburger" id="hamburger" aria-label="Menu">' +
              '<span class="material-icons-outlined">menu</span>' +
            '</button>' +
            '<div>' +
              '<h1>' + esc(page.title) + '</h1>' +
            '</div>' +
          '</div>' +
          '<button class="done-btn" id="done-btn">Done</button>' +
        '</header>' +
        (contentHtml || '');

      rebindHamburger();

      if (page.sections && page.sections.length > 0) {
        var container = main.querySelector('.settings-content');
        if (container && settingsRenderer) {
          settingsRenderer.bindBuiltInPage(container, pageId, featureConfig, function (patch) {
            saveFeature(patch);
          });
        }
      }
    } catch (ex) {
      console.error("renderDeclarativePage error:", ex);
      renderPlaceholder();
    }
  }

  // ── Features page ──────────────────────────────────────────

  let featureConfig = {};
  let featureSaveTimer = null;

  const CLOCK_MODES = ["Small Clock", "Large Clock", "Day and time"];
  const CLOCK_KEYS = { "Small Clock": {}, "Large Clock": { feature_large_clock: true }, "Day and time": { feature_day_clock: true } };

  const CLOCK_DISPLAY_TOGGLES = [
    ["feature_greeting", "Greeting message", "Show greeting message on startup"],
    ["feature_time", "Time display", "Show/hide the current time on the display"],
    ["feature_date", "Date reminder", "Alternate time display with the current date"],
    ["feature_minute_bar", "Minute bar", "Visual minute progress bar on the display"],
  ];

  const EXTRAS_TOGGLES = [
    ["feature_eyes", "Animated eyes", "Animated eyes that follow motion"],
    ["feature_notifications", "Notifications", "Show phone/PC notifications on the display"],
    ["night_mode_enabled", "Night mode", "Dim display during nighttime hours"],
    ["pc_stats_enabled", "PC Stats", "Show PC hardware stats on the display"],
  ];

  let _fetchConfigBusy = false;
  async function fetchConfig() {
    if (_fetchConfigBusy) return;
    _fetchConfigBusy = true;
    try {
      const res = await apiFetch(`${API_BASE}/api/config`);
      if (res.ok) {
        featureConfig = await res.json();
        if (featureConfig.theme && typeof window.applyTheme === "function") {
          window.applyTheme(featureConfig.theme);
        }
        if (currentPage === "features" || currentPage === "alarms" || currentPage === "settings" || (currentPage === "plugins" && selectedPlugin)) renderPage();
        setTimeout(checkLightingWizard, 1200);
      }
    } catch (_) {}
    _fetchConfigBusy = false;
  }

  async function fetchEntities() {
    try {
      const res = await apiFetch(`${API_BASE}/api/panel/entities`);
      if (res.ok) {
        const data = await res.json();
        panelEntities = data.entities || [];
      }
    } catch (_) {}
  }

  async function fetchAudioDevices() {
    try {
      const res = await apiFetch(`${API_BASE}/api/audio/devices`);
      if (res.ok) {
        const data = await res.json();
        audioOutputDevices = data.devices || [];
      }
    } catch (_) {}
  }

  async function fetchDeviceStatus() {
    if (currentPage === "dashboard" || currentPage === "features") {
      try {
        const res = await apiFetch(`${API_BASE}/api/status`);
        if (res.ok) {
          const next = await res.json();
          const prev = deviceStatus;
          deviceStatus = next;
          var changed = !prev
            || prev.connected !== next.connected
            || prev.port !== next.port
            || prev.last_notification !== next.last_notification;
          if (currentPage === "dashboard") {
            if (changed) renderDashboard();
          } else if (currentPage === "features") {
            var prevConnected = prev ? prev.connected : undefined;
            if (prevConnected !== next.connected) renderPage();
          }
        }
      } catch (_) {}
      setTimeout(fetchDeviceStatus, 5000);
    }
  }

  function getClockMode() {
    if (featureConfig.feature_large_clock) return "Large Clock";
    if (featureConfig.feature_day_clock) return "Day and time";
    return "Small Clock";
  }

  function saveFeature(patch) {
    Object.assign(featureConfig, patch);
    clearTimeout(featureSaveTimer);
    featureSaveTimer = setTimeout(() => {
      apiFetch(`${API_BASE}/api/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(featureConfig),
      }).catch(() => {});
    }, 400);
  }

  function renderFeatures() {
    const clockMode = getClockMode();
    const userName = featureConfig.user_name || "";

    main.innerHTML = `
      <header>
        <div class="header-left">
          <button class="hamburger" id="hamburger" aria-label="Menu">
            <span class="material-icons-outlined">menu</span>
          </button>
          <div>
            <h1>Pixel Clock</h1>
          </div>
        </div>
        <button class="done-btn" id="done-btn">Done</button>
      </header>
      <section class="content feat-content">
        <div class="feat-section">
          <h2 class="feat-heading">Clock Display</h2>
          <div class="feat-card">
            <input type="text" id="user-name" class="feat-input" placeholder="Your Name" value="${esc(userName)}">
            <select id="clock-mode" class="feat-select">
              ${CLOCK_MODES.map((m) => `<option value="${m}" ${m === clockMode ? "selected" : ""}>${m}</option>`).join("")}
            </select>
            ${CLOCK_DISPLAY_TOGGLES.map(([key, label, tip]) => featToggle(key, label, tip)).join("")}
          </div>
        </div>

        <div class="feat-section">
          <h2 class="feat-heading">Extras</h2>
          <div class="feat-card">
            ${EXTRAS_TOGGLES.map(([key, label, tip]) => featToggle(key, label, tip)).join("")}
          </div>
        </div>
      </section>`;

    // Wire up clock mode
    document.getElementById("clock-mode").addEventListener("change", (e) => {
      const patch = { feature_large_clock: false, feature_day_clock: false };
      Object.assign(patch, CLOCK_KEYS[e.target.value]);
      saveFeature(patch);
    });

    // Wire up user name
    const nameInput = document.getElementById("user-name");
    let nameTimer = null;
    nameInput.addEventListener("input", () => {
      clearTimeout(nameTimer);
      nameTimer = setTimeout(() => {
        saveFeature({ user_name: nameInput.value.trim() });
      }, 300);
    });

    // Wire up toggles
    document.querySelectorAll(".feat-toggle").forEach((el) => {
      el.addEventListener("click", () => {
        const key = el.dataset.key;
        const on = el.classList.toggle("on");
        saveFeature({ [key]: on });
      });
    });

    rebindHamburger();
  }

  function featToggle(key, label, tip) {
    const on = featureConfig[key] ? "on" : "";
    return `<div class="feat-toggle-row" ${tip ? `title="${esc(tip)}"` : ""}>
      <span class="feat-toggle-label">${esc(label)}</span>
      <div class="feat-toggle ${on}" data-key="${esc(key)}">
        <div class="feat-toggle-thumb"></div>
      </div>
    </div>`;
  }

  // ── Alarms page ───────────────────────────────────────────

  const DAY_LABELS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
  const DAY_BITS = [1, 2, 3, 4, 5, 6, 0];

  function alarmTimeStr(a) {
    return String(a.hour).padStart(2, "0") + ":" + String(a.minute).padStart(2, "0");
  }

  function alarmDaysStr(days) {
    return DAY_LABELS.filter((_, i) => (days >> DAY_BITS[i]) & 1).join(", ");
  }

  function alarmEditDaysStr(days) {
    return DAY_LABELS.map((lbl, i) => (days >> DAY_BITS[i]) & 1 ? lbl.substring(0, 2) : "--").join("  ");
  }

  function saveAlarmDebounced() {
    clearTimeout(alarmSaveTimer);
    alarmSaveTimer = setTimeout(() => {
      featureConfig.alarms = alarms;
      apiFetch(`${API_BASE}/api/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(featureConfig),
      }).catch(() => {});
    }, 400);
  }

  function renderAlarms() {
    if (editingAlarmId === "new" && !editingAlarm) {
      editingAlarm = { hour: 8, minute: 0, days: 62, enabled: true, message: "", show_eyes: true, sound: "remind" };
    }
    if (editingAlarmId && editingAlarm) {
      renderAlarmEdit();
      return;
    }

    const cards = alarms.map(a => renderAlarmCard(a)).join("");
    const empty = !cards
      ? '<div class="alarm-empty"><p>No alarms yet</p><p class="alarm-empty-sub">Add an alarm to get started.</p></div>'
      : "";

    main.innerHTML = `
      <header>
        <div class="header-left">
          <button class="hamburger" id="hamburger" aria-label="Menu">
            <span class="material-icons-outlined">menu</span>
          </button>
          <div>
            <h1>Alarms</h1>
          </div>
        </div>
        <button class="done-btn" id="done-btn">Done</button>
      </header>
      <section class="content alarm-content">
        ${cards}${empty}
        <button class="alarm-add-btn" id="alarm-add-btn">
          <span class="material-icons-outlined">add</span>
          Add Alarm
        </button>
      </section>`;

    document.getElementById("alarm-add-btn").addEventListener("click", () => {
      editingAlarmId = "new";
      editingAlarm = { hour: 8, minute: 0, days: 62, enabled: true, message: "", show_eyes: true, sound: "remind" };
      renderAlarms();
    });

    alarms.forEach(a => {
      const card = document.getElementById("alarm-" + a.id);
      if (!card) return;

      card.querySelector(".alarm-toggle").addEventListener("click", (e) => {
        e.stopPropagation();
        a.enabled = !a.enabled;
        saveAlarmDebounced();
        renderAlarms();
      });

      card.querySelector(".alarm-delete-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        alarms = alarms.filter(x => x.id !== a.id);
        saveAlarmDebounced();
        renderAlarms();
      });

      card.addEventListener("click", () => {
        editingAlarmId = a.id;
        editingAlarm = Object.assign({}, a);
        renderAlarms();
      });
    });

    rebindHamburger();
  }

  function renderAlarmCard(a) {
    const time = alarmTimeStr(a);
    const days = alarmDaysStr(a.days);
    const msg = a.message ? esc(a.message) : "";
    return `
      <div class="alarm-card" id="alarm-${a.id}">
        <div class="alarm-card-top">
          <div class="alarm-time">${esc(time)}</div>
          <div class="alarm-card-actions">
            <button class="alarm-delete-btn" title="Delete">
              <span class="material-icons-outlined">close</span>
            </button>
            <div class="alarm-toggle ${a.enabled ? "on" : ""}">
              <div class="alarm-toggle-thumb"></div>
            </div>
          </div>
        </div>
        <div class="alarm-card-days">${esc(days)}</div>
        ${msg ? `<div class="alarm-card-msg">${msg}</div>` : ""}
      </div>`;
  }

  function renderAlarmEdit() {
    const data = editingAlarm;
    const isNew = editingAlarmId === "new";
    const days = data.days;

    main.innerHTML = `
      <header>
        <div class="header-left">
          <button class="hamburger" id="hamburger" aria-label="Menu">
            <span class="material-icons-outlined">menu</span>
          </button>
          <button class="back-btn" id="back-btn">
            <span class="material-icons-outlined">arrow_back</span>
          </button>
          <div>
            <h1>${isNew ? "New Alarm" : "Edit Alarm"}</h1>
          </div>
        </div>
        <button class="done-btn" id="done-btn">Done</button>
      </header>
      <section class="content alarm-content alarm-edit-content">
        <div class="alarm-edit-card">
          <div class="alarm-edit-header">
            <span class="alarm-edit-label">${isNew ? "NEW ALARM" : "EDIT ALARM"}</span>
            <div class="alarm-edit-enabled-row">
              <span class="alarm-edit-enabled-label">ENABLED</span>
              <div class="alarm-toggle ${data.enabled ? "on" : ""}" id="alarm-edit-toggle">
                <div class="alarm-toggle-thumb"></div>
              </div>
            </div>
          </div>

          <div class="alarm-time-picker" id="alarm-time-picker">
            <div class="alarm-spinner">
              <button class="alarm-spinner-btn" id="hour-up">&#9650;</button>
              <div class="alarm-spinner-val" id="hour-val">${String(data.hour).padStart(2, "0")}</div>
              <button class="alarm-spinner-btn" id="hour-dn">&#9660;</button>
            </div>
            <span class="alarm-colon">:</span>
            <div class="alarm-spinner">
              <button class="alarm-spinner-btn" id="min-up">&#9650;</button>
              <div class="alarm-spinner-val" id="min-val">${String(data.minute).padStart(2, "0")}</div>
              <button class="alarm-spinner-btn" id="min-dn">&#9660;</button>
            </div>
          </div>

          <div class="alarm-edit-section">
            <span class="alarm-edit-section-label">ACTIVE DAYS</span>
            <div class="alarm-day-picker" id="alarm-day-picker">
              ${DAY_LABELS.map((lbl, i) => {
                const active = (days >> DAY_BITS[i]) & 1;
                return `<div class="alarm-day ${active ? "on" : ""}" data-idx="${i}">${lbl}</div>`;
              }).join("")}
            </div>
          </div>

          <div class="alarm-edit-section">
            <span class="alarm-edit-section-label">Message</span>
            <input type="text" class="feat-input alarm-msg-input" id="alarm-msg-input"
                   placeholder="Optional message" value="${esc(data.message)}">
          </div>

          <div class="alarm-edit-section">
            <span class="alarm-edit-section-label">Alarm Sound</span>
            <div class="alarm-sound-picker" id="alarm-sound-picker">
              ${ALARM_SOUNDS.map(s => {
                const active = (data.sound || "remind") === s.name;
                return `<div class="alarm-sound-btn ${active ? "active" : ""}" data-sound="${s.name}">
                  <span class="material-icons-outlined">${s.icon}</span>
                  <span class="alarm-sound-label">${s.label}</span>
                </div>`;
              }).join("")}
            </div>
          </div>

          <div class="alarm-edit-buttons">
            ${!isNew ? '<button class="alarm-btn alarm-btn-delete" id="alarm-delete">Delete</button>' : ""}
            <div class="alarm-edit-buttons-right">
              <button class="alarm-btn alarm-btn-cancel" id="alarm-cancel">Cancel</button>
              <button class="alarm-btn alarm-btn-save" id="alarm-save">Save</button>
            </div>
          </div>
        </div>
      </section>`;

    document.getElementById("back-btn").addEventListener("click", () => {
      stopPreview();
      editingAlarmId = null;
      editingAlarm = null;
      renderAlarms();
    });

    document.getElementById("alarm-edit-toggle").addEventListener("click", function () {
      data.enabled = this.classList.toggle("on");
    });

    const spin = (field, delta) => {
      const lo = field === "hour" ? 0 : 0;
      const hi = field === "hour" ? 23 : 59;
      data[field] = (data[field] + delta + hi + 1) % (hi + 1);
      document.getElementById(field === "hour" ? "hour-val" : "min-val")
        .textContent = String(data[field]).padStart(2, "0");
    };
    document.getElementById("hour-up").addEventListener("click", () => spin("hour", 1));
    document.getElementById("hour-dn").addEventListener("click", () => spin("hour", -1));
    document.getElementById("min-up").addEventListener("click", () => spin("minute", 1));
    document.getElementById("min-dn").addEventListener("click", () => spin("minute", -1));

    document.getElementById("hour-val").addEventListener("wheel", (e) => {
      e.preventDefault();
      spin("hour", e.deltaY < 0 ? 1 : -1);
    }, { passive: false });
    document.getElementById("min-val").addEventListener("wheel", (e) => {
      e.preventDefault();
      spin("minute", e.deltaY < 0 ? 1 : -1);
    }, { passive: false });

    document.getElementById("alarm-day-picker").addEventListener("click", (e) => {
      const el = e.target.closest(".alarm-day");
      if (!el) return;
      const idx = parseInt(el.dataset.idx);
      data.days ^= (1 << DAY_BITS[idx]);
      el.classList.toggle("on");
    });

    const msgInput = document.getElementById("alarm-msg-input");
    msgInput.addEventListener("input", () => { data.message = msgInput.value; });

    document.getElementById("alarm-sound-picker").addEventListener("click", (e) => {
      const btn = e.target.closest(".alarm-sound-btn");
      if (!btn) return;
      const name = btn.dataset.sound;
      data.sound = name;
      document.querySelectorAll(".alarm-sound-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      previewSound(name);
    });

    document.querySelector(".alarm-edit-card").addEventListener("click", (e) => {
      if (!e.target.closest(".alarm-sound-picker")) {
        stopPreview();
      }
    });

    document.getElementById("alarm-cancel").addEventListener("click", () => {
      stopPreview();
      editingAlarmId = null;
      editingAlarm = null;
      renderAlarms();
    });

    const saveBtn = document.getElementById("alarm-save");
    if (saveBtn) {
      saveBtn.addEventListener("click", () => {
        stopPreview();
        data.hour = Math.max(0, Math.min(23, parseInt(data.hour) || 0));
        data.minute = Math.max(0, Math.min(59, parseInt(data.minute) || 0));

        if (isNew) {
          data.id = alarms.length ? Math.max(...alarms.map(a => a.id)) + 1 : 1;
          alarms.push(data);
        } else {
          const existing = alarms.find(a => a.id === data.id);
          if (existing) Object.assign(existing, data);
        }

        editingAlarmId = null;
        editingAlarm = null;
        saveAlarmDebounced();
        renderAlarms();
      });
    }

    rebindHamburger();
  }

  // ── Plugins page ──────────────────────────────────────────

  const STATUS_COLORS = {
    running: "var(--neon-grn)",
    connected: "var(--neon-grn)",
    waiting: "var(--fg-dim)",
    disconnected: "var(--neon-red)",
    inactive: "var(--fg-dim)",
    missing: "var(--neon-red)",
    disabled: "var(--neon-red)",
    unknown: "var(--fg-dim)",
  };

  let _fetchPluginsConfigBusy = false;
  async function fetchPluginsConfig() {
    if (_fetchPluginsConfigBusy) return;
    _fetchPluginsConfigBusy = true;
    try {
      const res = await apiFetch(`${API_BASE}/api/plugins/config`);
      if (res.ok) {
        const next = await res.json();
        const prevJson = JSON.stringify(pluginsConfig);
        const nextJson = JSON.stringify(next);
        pluginsConfig = next;
        if (prevJson !== nextJson) {
          if (currentPage === "plugins") renderPage();
          else if (currentPage === "dashboard") renderDashboard();
        }
      }
    } catch (_) {}
    _fetchPluginsConfigBusy = false;
    setTimeout(fetchPluginsConfig, 30000);
  }

  function renderPlugins() {
    const names = Object.keys(pluginsConfig);

    const tiles = names.map((name) => {
      const p = pluginsConfig[name];
      const icon = (pluginsConfig[name] || {}).icon || "extension";
      const color = STATUS_COLORS[p.status_code] || "var(--fg-dim)";
      return `
        <div class="plugin-tile" data-name="${esc(name)}">
          <div class="plugin-tile-icon">
            <span class="material-icons-outlined">${icon}</span>
          </div>
          <div class="plugin-tile-info">
            <span class="plugin-tile-name">${esc(p.display_name)}</span>
            <span class="plugin-tile-status" style="color:${color}">${esc(p.status_label)}</span>
          </div>
          <span class="material-icons-outlined plugin-tile-arrow">chevron_right</span>
        </div>`;
    }).join("");

    main.innerHTML = `
      <header>
        <div class="header-left">
          <button class="hamburger" id="hamburger" aria-label="Menu">
            <span class="material-icons-outlined">menu</span>
          </button>
          <div>
            <h1>Plugins</h1>
          </div>
        </div>
        <button class="done-btn" id="done-btn">Done</button>
      </header>
      <section class="content plugin-content">
        ${tiles || '<div class="card"><h2>No plugins</h2><p>Install plugins to get started.</p></div>'}
      </section>`;

    document.querySelectorAll(".plugin-tile").forEach((el) => {
      el.addEventListener("click", () => {
        selectedPlugin = el.dataset.name;
        fetchConfig();
        renderPage();
      });
    });

    rebindHamburger();
  }

  function renderPluginSettings(name) {
    var p = pluginsConfig[name] || {};

    var contentHtml = "";
    if (settingsRenderer) {
      contentHtml = settingsRenderer.renderPluginPage(name, p, pluginSnapshots[name], pluginState[name], (panelDraft && panelDraft.panel_profiles) ? panelDraft : featureConfig);
    }

    main.innerHTML =
      '<header>' +
        '<div class="header-left">' +
          '<button class="hamburger" id="hamburger" aria-label="Menu">' +
            '<span class="material-icons-outlined">menu</span>' +
          '</button>' +
          '<div>' +
            '<h1>' + esc(p.display_name || name) + '</h1>' +
          '</div>' +
        '</div>' +
        '<div style="display:flex;align-items:center;gap:8px">' +
          '<button class="done-btn" id="back-btn">Back</button>' +
          '<button class="done-btn" id="done-btn">Done</button>' +
        '</div>' +
      '</header>' +
      contentHtml;

    function returnToDashboard() {
      selectedPlugin = null;
      currentPage = "dashboard";
      navItems.forEach((n) => n.classList.toggle("active", n.dataset.page === "dashboard"));
      renderPage();
    }

    var backBtn = document.getElementById("back-btn");
    if (backBtn) backBtn.addEventListener("click", returnToDashboard);

    var doneBtn = document.getElementById("done-btn");
    if (doneBtn) doneBtn.addEventListener("click", returnToDashboard);

    rebindHamburger();

    if (settingsRenderer) {
      var container = main.querySelector('.settings-content');
      if (container) {
        settingsRenderer.bindPluginPage(container, name, p, function (pluginName, field, value) {
          var saved = savePluginField(pluginName, field, value);
          if (field === "use_fahrenheit") {
            (saved || Promise.resolve()).then(function () {
              return apiFetch(API_BASE + "/api/plugins/config");
            }).then(function (r) { return r.json(); })
              .then(function (next) {
                pluginsConfig = next;
                if (selectedPlugin === pluginName && currentPage === "plugins") renderPage();
              })
              .catch(function () {});
          }
        }, function (pluginName, outputId, on) {
          if (!pluginsConfig[pluginName]) pluginsConfig[pluginName] = {};
          var outputs = pluginsConfig[pluginName].outputs || {};
          outputs[outputId] = on;
          pluginsConfig[pluginName].outputs = outputs;
          apiFetch(API_BASE + "/api/plugins/" + encodeURIComponent(pluginName) + "/outputs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(outputs),
          }).catch(function () {});
        }, function (pluginName, actionId) {
          apiFetch(API_BASE + "/api/plugins/" + encodeURIComponent(pluginName) + "/action/" + encodeURIComponent(actionId), {
            method: "POST",
          }).then(function(r) { return r.json(); })
            .then(function(res) {
              if (res && res.ok) {
                var msg = (res.result && res.result.message) || "Action completed";
                alert(msg);
                if (typeof fetchConfig === "function") fetchConfig();
                if (typeof fetchPanel === "function") fetchPanel();
                apiFetch(API_BASE + "/api/plugins/config").then(function(r) { return r.json(); }).then(function(next) {
                  pluginsConfig = next;
                  if (selectedPlugin === pluginName && currentPage === "plugins") renderPage();
                }).catch(function(){});
              } else {
                alert((res && res.error) || "Action failed");
              }
            })
            .catch(function (e) { alert("Action error: " + e); });
        });
      }
    }

    // Snapshot once for layout/debug fields; live poll stays lightweight.
    if (!pluginSnapshots[name]) {
      apiFetch(API_BASE + "/api/plugins/" + encodeURIComponent(name) + "/snapshot")
        .then(function (r) { return r.json(); })
        .then(function (snap) {
          pluginSnapshots[name] = snap;
          var dataEl = main.querySelector(".plugin-data-container");
          if (dataEl && settingsRenderer) {
            dataEl.innerHTML = '<span class="plugin-edit-label">DATA</span>' +
              settingsRenderer._renderPluginData(name, snap, pluginState[name]);
          }
        })
        .catch(function () {});
    }
  }

  function renderRequirements(reqs) {
    const items = reqs.map((r) => {
      const icon = r.met ? "check_circle" : "cancel";
      const color = r.met ? "var(--neon-grn)" : "var(--neon-red)";
      return `<div class="plugin-req-row">
        <span class="material-icons-outlined" style="color:${color};font-size:18px">${icon}</span>
        <span class="plugin-req-name">${esc(r.name)}</span>
        <span class="plugin-req-desc">${esc(r.description)}</span>
      </div>`;
    }).join("");
    return `<div class="plugin-reqs">${items}</div>`;
  }

  function savePluginField(name, field, value) {
    if (!pluginsConfig[name]) pluginsConfig[name] = {};
    pluginsConfig[name][field] = value;
    return apiFetch(`${API_BASE}/api/plugins/config/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pluginsConfig[name]),
    }).catch(() => {});
  }

  // ── Automations Section ──────────────────────────────────────

  let automationsList = [];
  let automationsDisclaimerAck = false;
  let autoModalOpen = false;

  async function fetchAutomations() {
    try {
      const res = await apiFetch(`${API_BASE}/api/automations`);
      if (res.ok) {
        const data = await res.json();
        automationsList = data.rules || [];
        automationsDisclaimerAck = !!data.disclaimer_acknowledged;
      }
    } catch (_) {}
  }

  function renderAutomations() {
    Promise.all([fetchAutomations(), fetchEntities()]).then(() => {
      main.innerHTML = `
        <header>
          <div class="header-left">
            <button class="hamburger" id="hamburger" aria-label="Menu">
              <span class="material-icons-outlined">menu</span>
            </button>
            <div>
              <h1>Automations</h1>
              <span class="header-sub">Entity triggers, background macros, and button box actions</span>
            </div>
          </div>
          <button class="done-btn" id="done-btn">Done</button>
        </header>

        <section class="content vision-content">
          <div class="vision-toolbar">
            <span class="vision-toolbar-title">Active Rules</span>
            <button class="settings-btn settings-btn-primary" id="auto-new-btn">
              <span class="material-icons-outlined">add</span>
              New Automation
            </button>
          </div>

          ${!automationsDisclaimerAck ? `
            <div class="auto-disclaimer-card">
              <span class="material-icons-outlined auto-disclaimer-icon">warning_amber</span>
              <div class="auto-disclaimer-text">
                <strong>Fair-Play & Anti-Cheat Notice (Input Automation Caution)</strong><br>
                Automating hardware keystrokes in online games or third-party applications may violate terms of service or trigger automated anti-cheat systems. You assume all responsibility when enabling hotkey macros. Non-intrusive actions (lighting, audio, display) carry zero risk.
                <br>
                <button class="auto-ack-btn" id="auto-ack-disclaimer-btn">I Understand & Acknowledge Risk</button>
              </div>
            </div>
          ` : ""}

          <div class="vision-grid">
            ${automationsList.length === 0 ? `
              <div class="vision-empty">
                <span class="material-icons-outlined">auto_mode</span>
                <div>No automations configured</div>
                <div class="vision-empty-sub">Click "New Automation" to create an entity trigger pipeline.</div>
              </div>
            ` : automationsList.map(rule => `
              <div class="vision-card" data-id="${esc(rule.id)}">
                <div class="vision-card-head">
                  <div class="vision-card-title-group">
                    <span class="vision-status-dot ${rule.enabled !== false ? 'online' : 'offline'}" style="background:${rule.enabled !== false ? 'var(--neon-grn)' : 'var(--fg-dim)'}"></span>
                    <span class="vision-card-name" title="${esc(rule.name || 'Untitled')}">${esc(rule.name || "Untitled")}</span>
                  </div>
                  <div class="settings-toggle ${rule.enabled !== false ? 'on' : ''} auto-rule-toggle" data-id="${esc(rule.id)}" title="Toggle automation rule">
                    <div class="settings-toggle-thumb"></div>
                  </div>
                </div>

                <div style="font-size:11px;color:var(--fg-dim);margin-top:-2px">
                  ${esc(rule.profile_id ? ("PROFILE: " + rule.profile_id) : (rule.exe ? rule.exe : "GLOBAL AUTOMATION"))}
                </div>

                <div class="auto-card-pipeline">
                  <div class="auto-pipe-row">
                    <span class="auto-badge auto-badge-trigger">IF</span>
                    <span>${esc(rule.trigger_key)} ${esc(rule.operator)} ${esc(String(rule.target_value))}</span>
                  </div>
                  <div class="auto-pipe-row">
                    <span class="auto-badge auto-badge-action">THEN</span>
                    <span>${(rule.actions || []).map(a => a.type === "hotkey" ? `Key '${a.hotkey}'` : a.type === "sound" ? `Sound '${a.sound}'` : a.type === "openrgb" ? `OpenRGB '${a.profile}'` : a.type === "notification" ? `Toast '${a.message}'` : a.type).join(" + ") || "No Action"}</span>
                  </div>
                </div>

                <div class="vision-card-actions" style="margin-top:6px">
                  <button class="settings-btn auto-btn-box-export" data-id="${esc(rule.id)}" title="Add interactive button to active Button Box">
                    <span class="material-icons-outlined" style="font-size:16px">add_to_photos</span>
                    Add to Button Box
                  </button>
                  <div class="vision-card-btns">
                    <button class="settings-btn auto-test-btn" data-id="${esc(rule.id)}" title="Test trigger actions">Test</button>
                    <button class="settings-btn auto-edit-btn" data-id="${esc(rule.id)}" title="Edit">Edit</button>
                    <button class="settings-btn settings-btn-danger auto-del-btn" data-id="${esc(rule.id)}" title="Delete">✕</button>
                  </div>
                </div>
              </div>
            `).join("")}
          </div>
        </section>
      `;

      wireAutomations();
    });
  }

  function wireAutomations() {
    const doneBtn = document.getElementById("done-btn");
    if (doneBtn) doneBtn.onclick = () => { currentPage = "dashboard"; renderPage(); };

    const newBtn = document.getElementById("auto-new-btn");
    if (newBtn) newBtn.onclick = () => openAutomationModal();

    const ackBtn = document.getElementById("auto-ack-disclaimer-btn");
    if (ackBtn) {
      ackBtn.onclick = async () => {
        await apiFetch(`${API_BASE}/api/automations/disclaimer_ack`, { method: "POST" });
        automationsDisclaimerAck = true;
        renderAutomations();
      };
    }

    document.querySelectorAll(".auto-rule-toggle").forEach(tog => {
      tog.onclick = async (e) => {
        e.stopPropagation();
        const id = tog.getAttribute("data-id");
        const rule = automationsList.find(r => r.id === id);
        if (rule) {
          rule.enabled = !tog.classList.contains("on");
          tog.classList.toggle("on", rule.enabled);
          await apiFetch(`${API_BASE}/api/automations`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(rule),
          });
          renderAutomations();
        }
      };
    });

    document.querySelectorAll(".auto-del-btn").forEach(btn => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-id");
        if (confirm("Delete this automation rule?")) {
          await apiFetch(`${API_BASE}/api/automations/${encodeURIComponent(id)}/delete`, { method: "POST" });
          renderAutomations();
        }
      };
    });

    document.querySelectorAll(".auto-edit-btn").forEach(btn => {
      btn.onclick = () => {
        const id = btn.getAttribute("data-id");
        const rule = automationsList.find(r => r.id === id);
        if (rule) openAutomationModal(rule);
      };
    });

    document.querySelectorAll(".auto-test-btn").forEach(btn => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-id");
        const rule = automationsList.find(r => r.id === id);
        if (rule) {
          await apiFetch(`${API_BASE}/api/automations/test`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(rule),
          });
        }
      };
    });

    document.querySelectorAll(".auto-btn-box-export").forEach(btn => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-id");
        const res = await apiFetch(`${API_BASE}/api/automations/${encodeURIComponent(id)}/export_button`, { method: "POST" });
        if (res.ok) {
          btn.innerHTML = `<span class="material-icons-outlined" style="font-size:16px">check</span> Added!`;
          setTimeout(() => renderAutomations(), 1200);
        }
      };
    });
  }

  function openAutomationModal(existing) {
    const profiles = ((panelDraft && panelDraft.panel_profiles) || (featureConfig && featureConfig.panel_profiles) || []).map(p => ({
      id: p.id,
      name: p.name || p.id,
      exe: p.exe || "",
    }));

    const draft = existing ? JSON.parse(JSON.stringify(existing)) : {
      id: "",
      name: "",
      enabled: true,
      profile_id: "",
      exe: "",
      trigger_key: "",
      operator: "==",
      target_value: "",
      require_foreground: true,
      cooldown_s: 10.0,
      actions: [
        { type: "sound", sound: "chime" }
      ]
    };

    if (!Array.isArray(draft.actions)) draft.actions = [];

    // Group entities by plugin / domain for 2-step plugin + searchable entity picker
    const pluginGroups = { "all": "All Plugins & Core" };
    (panelEntities || []).forEach(ent => {
      const plg = ent.plugin || (ent.id && ent.id.includes(".") ? ent.id.split(".")[0] : "core");
      const dName = ent.domain || plg.toUpperCase();
      if (!pluginGroups[plg]) pluginGroups[plg] = dName;
    });

    let autoPluginOptionsHtml = Object.keys(pluginGroups).map(k => `<option value="${esc(k)}">${esc(pluginGroups[k])}</option>`).join("");

    // Prepare sources/categories for Action Pipeline
    const actionCategories = [
      { id: "core_hotkey", label: "Hardware Hotkey / Macro" },
      { id: "core_sound", label: "Audio Alert / Sound" },
      { id: "core_notif", label: "Toast Notification" },
      { id: "core_media", label: "Core: Media Controls" },
      { id: "core_system", label: "Core: System Actions" },
    ];

    // Add installed plugins dynamically
    Object.keys(pluginsConfig || {}).forEach(k => {
      const p = pluginsConfig[k] || {};
      actionCategories.push({
        id: `plugin_${k}`,
        plugin_id: k,
        label: `Plugin: ${p.display_name || k}`
      });
    });

    const backdrop = document.createElement("div");
    backdrop.className = "panel-modal-backdrop";
    backdrop.id = "auto-modal-backdrop";
    backdrop.innerHTML = `
      <div class="panel-modal panel-modal-wide" id="auto-modal" style="max-width:920px">
        <div class="panel-modal-header">
          <h3>${existing ? "Edit Automation" : "New Automation"}</h3>
          <span class="panel-modal-subtitle">Configure trigger entity, linked process, and conditional inline action pipeline</span>
        </div>

        <div class="panel-modal-body-grid">
          <div class="panel-modal-col">
            <div class="settings-control">
              <label class="settings-label">Automation Name</label>
              <input type="text" class="settings-input" id="m-name" value="${esc(draft.name || "")}" placeholder="e.g. Shields State Monitor">
            </div>

            <div class="settings-control">
              <label class="settings-label">Trigger Entity / State Source</label>
              <div class="settings-picker-row" style="gap:6px;margin-bottom:6px">
                <select class="settings-select" id="m-trig-plugin" style="width:140px;flex:0 0 auto">
                  ${autoPluginOptionsHtml}
                </select>
                <input type="text" class="settings-input" id="m-trig-search" placeholder="Search trigger entities..." style="flex:1">
              </div>
              <select class="settings-select" id="m-key" style="width:100%"></select>
            </div>
          </div>

          <div class="panel-modal-col">
            <div class="settings-control">
              <label class="settings-label">Linked Button Profile</label>
              <select class="settings-select" id="m-profile">
                <option value="">(None / Global Automation)</option>
                ${profiles.map(p => `<option value="${esc(p.id)}" data-exe="${esc(p.exe)}" ${draft.profile_id === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
              </select>
            </div>

            <div class="settings-control">
              <label class="settings-label">Target Process (Exe)</label>
              <div class="settings-picker-row">
                <input type="text" class="settings-input" id="m-exe" value="${esc(draft.exe || "")}" placeholder="Auto-filled from profile or custom">
                <button type="button" class="settings-btn" id="m-browse-exe" title="Browse executable on PC">
                  <span class="material-icons-outlined" style="font-size:16px">folder_open</span>
                  Browse
                </button>
              </div>
            </div>

            <div class="settings-control">
              <label class="settings-label">Cooldown between state changes (s)</label>
              <input type="number" class="settings-input" id="m-cooldown" value="${draft.cooldown_s || 2}" min="1" max="3600">
            </div>
          </div>
        </div>

        <div style="display:flex;align-items:center;justify-content:space-between;margin-top:12px;border-top:1px solid rgba(255,255,255,0.06);padding-top:12px">
          <div>
            <span class="settings-label" style="color:var(--neon-text);font-size:13px;font-weight:600">Action Pipeline</span>
            <span style="font-size:11px;color:var(--fg-dim);display:block">Define conditions, actions, and optional pulse durations per row</span>
          </div>
          <button type="button" class="settings-btn" id="m-add-action-btn">
            <span class="material-icons-outlined" style="font-size:16px">add</span> Add Action
          </button>
        </div>

        <!-- Table Header Row -->
        <div style="display:grid;grid-template-columns: 220px 170px 200px 70px 32px;gap:8px;padding:6px 10px;font-size:11px;font-weight:600;color:var(--fg-dim);text-transform:uppercase;letter-spacing:0.5px;margin-top:8px">
          <div>When State is</div>
          <div>Action Type</div>
          <div>Target / Value</div>
          <div style="text-align:center">Duration</div>
          <div></div>
        </div>

        <div id="m-actions-table" style="display:flex;flex-direction:column;gap:6px">
        </div>

        <div class="panel-modal-actions">
          <button class="settings-btn settings-btn-secondary" id="modal-cancel">Cancel</button>
          <button class="settings-btn settings-btn-primary" id="modal-save">Save Automation</button>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);

    // Flatten actions from draft or default
    let currentActions = [];
    if (draft.actions && Array.isArray(draft.actions) && draft.actions.length > 0) {
      currentActions = JSON.parse(JSON.stringify(draft.actions));
    } else if (draft.branches && Array.isArray(draft.branches) && draft.branches.length > 0) {
      draft.branches.forEach(b => {
        const cond = b.condition || {};
        (b.actions || []).forEach(a => {
          const actCopy = JSON.parse(JSON.stringify(a));
          actCopy.operator = cond.operator || "==";
          actCopy.target_value = cond.target_value;
          actCopy.duration_s = b.duration_s || 0;
          currentActions.push(actCopy);
        });
      });
    } else {
      currentActions = [
        { operator: "==", target_value: false, duration_s: 0, type: "openrgb", profile: "Red" }
      ];
    }

    const actionsTable = backdrop.querySelector("#m-actions-table");
    const trigPluginSel = backdrop.querySelector("#m-trig-plugin");
    const trigSearchInput = backdrop.querySelector("#m-trig-search");
    const triggerKeySel = backdrop.querySelector("#m-key");

    function getSourceForAction(act) {
      if (act.type === "hotkey") return "core_hotkey";
      if (act.type === "sound") return "core_sound";
      if (act.type === "notification") return "core_notif";
      if (act.type === "openrgb" || (act.slot && (act.slot.plugin === "openrgb" || act.slot.openrgb_profile))) return "plugin_openrgb";
      if (act.type === "home_assistant" || act.type === "ha" || (act.slot && act.slot.plugin === "ha")) return "plugin_ha";
      if (act.slot) {
        if (act.slot.plugin) return `plugin_${act.slot.plugin}`;
        if (act.slot.entity && act.slot.entity.startsWith("media.")) return "core_media";
        if (act.slot.entity && act.slot.entity.startsWith("system.")) return "core_system";
      }
      return "core_hotkey";
    }

    function renderActionsTable() {
      const trigKey = triggerKeySel.value || draft.trigger_key;
      const ent = (panelEntities || []).find(e => (e.id === trigKey || e.state_key === trigKey));
      const hasLabels = ent && ent.labels && (ent.labels.on || ent.labels.off);
      const onLabel = hasLabels ? (ent.labels.on || "ON") : "Active / True";
      const offLabel = hasLabels ? (ent.labels.off || "OFF") : "Inactive / False";

      if (currentActions.length === 0) {
        actionsTable.innerHTML = `<div style="font-size:12px;color:var(--fg-dim);padding:14px;text-align:center;background:var(--bg-card);border:1px dashed var(--border);border-radius:var(--radius-small)">No actions in pipeline. Click "+ Add Action" above.</div>`;
        return;
      }

      actionsTable.innerHTML = currentActions.map((act, aIdx) => {
        const curOp = act.operator || (act.condition && act.condition.operator) || "==";
        const curVal = (act.target_value !== undefined) ? act.target_value : (act.condition ? act.condition.target_value : false);
        const dur = act.duration_s || 0;
        const currentSrc = getSourceForAction(act);

        // 1. Condition controls
        let valInputHtml = "";
        if (hasLabels || ent?.type === "status" || typeof curVal === "boolean") {
          const isOff = (curVal === false || String(curVal).toLowerCase() === "false" || String(curVal).toUpperCase() === offLabel.toUpperCase());
          valInputHtml = `
            <select class="settings-select row-val-sel" data-aidx="${aIdx}" style="flex:1;min-width:0">
              <option value="false" ${isOff ? "selected" : ""}>${esc(offLabel)} (Down)</option>
              <option value="true" ${!isOff ? "selected" : ""}>${esc(onLabel)} (Online)</option>
            </select>
          `;
        } else {
          valInputHtml = `
            <input type="text" class="settings-input row-val-input" data-aidx="${aIdx}" value="${esc(String(curVal !== undefined ? curVal : ""))}" placeholder="Target value" style="flex:1;min-width:0">
          `;
        }

        // 2. Action value controls (Fixed 200px width with ellipsis)
        let detailHtml = "";
        if (currentSrc === "core_hotkey") {
          detailHtml = `<input type="text" class="settings-input row-act-val" data-aidx="${aIdx}" value="${esc(act.hotkey || "")}" placeholder="Key (e.g. 7, F13)" style="width:200px">`;
        } else if (currentSrc === "core_sound") {
          detailHtml = `
            <select class="settings-select row-act-val" data-aidx="${aIdx}" style="width:200px">
              <option value="chime" ${act.sound === "chime" ? "selected" : ""}>Chime</option>
              <option value="alarm_fast" ${act.sound === "alarm_fast" ? "selected" : ""}>Fast Alarm</option>
              <option value="remind" ${act.sound === "remind" ? "selected" : ""}>Remind</option>
            </select>
          `;
        } else if (currentSrc === "core_notif") {
          detailHtml = `<input type="text" class="settings-input row-act-val" data-aidx="${aIdx}" value="${esc(act.message || "")}" placeholder="Toast message on screen" style="width:200px">`;
        } else if (currentSrc === "plugin_openrgb") {
          const openrgbEntities = (panelEntities || []).filter(e => e.plugin === "openrgb" || (e.id && e.id.startsWith("openrgb.")));
          const curProf = act.profile || (act.slot && act.slot.openrgb_profile) || "inherit";
          detailHtml = `
            <select class="settings-select row-act-val" data-aidx="${aIdx}" style="width:200px" title="${esc(curProf)}">
              <option value="inherit" ${curProf === "inherit" ? "selected" : ""}>⟲ Revert to Profile</option>
              ${openrgbEntities.filter(e => e.openrgb_profile || e.name).map(e => {
                const pName = e.openrgb_profile || e.name;
                return `<option value="${esc(pName)}" title="${esc(pName)}" ${curProf === pName ? "selected" : ""}>Profile: ${esc(pName)}</option>`;
              }).join("")}
            </select>
          `;
        } else if (currentSrc === "plugin_ha") {
          const haEntities = (panelEntities || []).filter(e => e.plugin === "ha" || (e.id && e.id.startsWith("ha.")));
          const curScript = act.entity || act.script || (act.slot && (act.slot.entity || act.slot.button_id)) || "inherit";
          detailHtml = `
            <select class="settings-select row-act-val" data-aidx="${aIdx}" style="width:200px" title="${esc(curScript)}">
              <option value="inherit" ${curScript === "inherit" ? "selected" : ""}>⟲ Revert to Profile</option>
              ${haEntities.map(e => {
                const label = e.name || e.id;
                return `<option value="${esc(e.id)}" title="${esc(label)} (${esc(e.id)})" ${curScript === e.id ? "selected" : ""}>${esc(label)}</option>`;
              }).join("")}
            </select>
          `;
        } else {
          const pName = currentSrc.replace("plugin_", "");
          const pEntities = (panelEntities || []).filter(e => e.plugin === pName || (e.id && e.id.startsWith(pName + ".")));
          const curEnt = (act.slot && (act.slot.entity || act.slot.button_id)) || (pEntities[0] ? pEntities[0].id : "");
          detailHtml = `
            <select class="settings-select row-act-val" data-aidx="${aIdx}" style="width:200px" title="${esc(curEnt)}">
              ${pEntities.map(e => {
                const label = e.name || e.id;
                return `<option value="${esc(e.id)}" title="${esc(label)} (${esc(e.id)})" ${curEnt === e.id ? "selected" : ""}>${esc(label)}</option>`;
              }).join("")}
            </select>
          `;
        }

        return `
          <div style="display:grid;grid-template-columns: 220px 170px 200px 70px 32px;gap:8px;align-items:center;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-small);padding:6px 10px">
            <!-- 1. Condition Column -->
            <div style="display:flex;align-items:center;gap:6px;min-width:0">
              <select class="settings-select row-op-sel" data-aidx="${aIdx}" style="width:65px;flex:0 0 auto">
                <option value="==" ${curOp === "==" ? "selected" : ""}>==</option>
                <option value="!=" ${curOp === "!=" ? "selected" : ""}>!=</option>
                <option value="<" ${curOp === "<" ? "selected" : ""}>&lt;</option>
                <option value=">" ${curOp === ">" ? "selected" : ""}>&gt;</option>
              </select>
              ${valInputHtml}
            </div>

            <!-- 2. Action Category Column -->
            <div style="min-width:0">
              <select class="settings-select row-src-sel" data-aidx="${aIdx}" style="width:100%">
                ${actionCategories.map(c => `<option value="${esc(c.id)}" ${currentSrc === c.id ? "selected" : ""}>${esc(c.label)}</option>`).join("")}
              </select>
            </div>

            <!-- 3. Target / Value Column -->
            <div style="display:flex;align-items:center;width:200px;overflow:hidden">
              ${detailHtml}
            </div>

            <!-- 4. Duration Column -->
            <div style="display:flex;align-items:center;justify-content:center" title="Duration in seconds (0 = Stay until state changes)">
              <input type="number" class="settings-input row-dur-input" data-aidx="${aIdx}" value="${dur}" min="0" max="3600" style="width:100%;padding:4px 6px;text-align:center" placeholder="0">
            </div>

            <!-- 5. Delete Column -->
            <div style="display:flex;justify-content:center">
              <button type="button" class="settings-btn settings-btn-danger settings-btn-mini row-del-btn" data-aidx="${aIdx}" title="Remove action" style="padding:4px 8px">✕</button>
            </div>
          </div>
        `;
      }).join("");

      // Wire row inputs
      actionsTable.querySelectorAll(".row-op-sel").forEach(sel => {
        sel.onchange = (e) => {
          const aIdx = parseInt(e.target.getAttribute("data-aidx"), 10);
          currentActions[aIdx].operator = e.target.value;
        };
      });

      actionsTable.querySelectorAll(".row-val-sel, .row-val-input").forEach(inp => {
        inp.onchange = (e) => {
          const aIdx = parseInt(e.target.getAttribute("data-aidx"), 10);
          const v = e.target.value;
          currentActions[aIdx].target_value = (v === "true") ? true : (v === "false" ? false : (!isNaN(Number(v)) && v !== "" ? Number(v) : v));
        };
      });

      actionsTable.querySelectorAll(".row-dur-input").forEach(inp => {
        inp.oninput = (e) => {
          const aIdx = parseInt(e.target.getAttribute("data-aidx"), 10);
          currentActions[aIdx].duration_s = Number(e.target.value) || 0;
        };
      });

      actionsTable.querySelectorAll(".row-del-btn").forEach(btn => {
        btn.onclick = () => {
          const aIdx = parseInt(btn.getAttribute("data-aidx"), 10);
          currentActions.splice(aIdx, 1);
          renderActionsTable();
        };
      });

      actionsTable.querySelectorAll(".row-src-sel").forEach(sel => {
        sel.onchange = (e) => {
          const aIdx = parseInt(e.target.getAttribute("data-aidx"), 10);
          const src = e.target.value;
          const oldOp = currentActions[aIdx].operator || "==";
          const oldVal = currentActions[aIdx].target_value;
          const oldDur = currentActions[aIdx].duration_s || 0;

          if (src === "core_hotkey") currentActions[aIdx] = { operator: oldOp, target_value: oldVal, duration_s: oldDur, type: "hotkey", hotkey: "7" };
          else if (src === "core_sound") currentActions[aIdx] = { operator: oldOp, target_value: oldVal, duration_s: oldDur, type: "sound", sound: "alarm_fast" };
          else if (src === "core_notif") currentActions[aIdx] = { operator: oldOp, target_value: oldVal, duration_s: oldDur, type: "notification", message: "Triggered" };
          else if (src === "plugin_openrgb") currentActions[aIdx] = { operator: oldOp, target_value: oldVal, duration_s: oldDur, type: "openrgb", profile: "inherit" };
          else if (src === "plugin_ha") currentActions[aIdx] = { operator: oldOp, target_value: oldVal, duration_s: oldDur, type: "home_assistant", entity: "inherit" };
          else if (src.startsWith("plugin_")) {
            const pName = src.replace("plugin_", "");
            const pEntities = (panelEntities || []).filter(x => x.plugin === pName || (x.id && x.id.startsWith(pName + ".")));
            const firstEnt = pEntities[0];
            currentActions[aIdx] = {
              operator: oldOp, target_value: oldVal, duration_s: oldDur,
              type: "slot",
              slot: { type: "action", entity: firstEnt ? firstEnt.id : pName, plugin: pName, button_id: firstEnt ? (firstEnt.button_id || firstEnt.id.split(".")[1] || "") : "" }
            };
          }
          renderActionsTable();
        };
      });

      actionsTable.querySelectorAll(".row-act-val").forEach(inp => {
        inp.onchange = (e) => {
          const aIdx = parseInt(inp.getAttribute("data-aidx"), 10);
          const act = currentActions[aIdx];
          const val = inp.value;
          if (act.type === "hotkey") act.hotkey = val;
          else if (act.type === "sound") act.sound = val;
          else if (act.type === "notification") act.message = val;
          else if (act.type === "openrgb") act.profile = val;
          else if (act.type === "home_assistant" || act.type === "ha") act.entity = val;
          else if (act.type === "slot" || act.slot) {
            const entObj = (panelEntities || []).find(x => x.id === val);
            currentActions[aIdx] = {
              operator: act.operator, target_value: act.target_value, duration_s: act.duration_s,
              type: "slot",
              slot: { type: entObj ? (entObj.type || "action") : "action", entity: val, plugin: entObj ? entObj.plugin : (val.split(".")[0] || ""), button_id: entObj ? (entObj.button_id || val.split(".")[1] || "") : "" }
            };
          }
        };
      });
    }

    backdrop.querySelector("#m-add-action-btn").onclick = () => {
      currentActions.push({
        operator: "==",
        target_value: false,
        duration_s: 0,
        type: "openrgb",
        profile: "Red"
      });
      renderActionsTable();
    };

    function renderTriggerEntityOptions(targetKey) {
      const curPlg = trigPluginSel.value || "all";
      const q = (trigSearchInput.value || "").trim().toLowerCase();

      let filtered = (panelEntities || []).filter(e => {
        const plg = e.plugin || (e.id && e.id.includes(".") ? e.id.split(".")[0] : "core");
        if (curPlg !== "all" && plg !== curPlg) return false;
        if (q) {
          const matchName = (e.name || "").toLowerCase().includes(q);
          const matchId = (e.id || "").toLowerCase().includes(q);
          const matchDomain = (e.domain || "").toLowerCase().includes(q);
          if (!matchName && !matchId && !matchDomain) return false;
        }
        return true;
      });

      let h = `<option value="">(Select Trigger Entity...)</option>`;
      filtered.forEach(ent => {
        const val = ent.id || ent.state_key || "";
        const sel = (targetKey && (targetKey === val || targetKey === ent.id)) ? "selected" : "";
        const rawDType = ent.raw_data_type || ent.type || "state";
        h += `<option value="${esc(val)}" ${sel}>${esc(ent.name || val)} (${esc(rawDType)})</option>`;
      });

      triggerKeySel.innerHTML = h;
      renderActionsTable();
    }

    trigPluginSel.onchange = () => renderTriggerEntityOptions();
    trigSearchInput.oninput = () => renderTriggerEntityOptions();
    triggerKeySel.onchange = () => renderActionsTable();

    if (draft.trigger_key) {
      const matchEnt = (panelEntities || []).find(e => (e.id === draft.trigger_key || e.state_key === draft.trigger_key));
      if (matchEnt && matchEnt.plugin) {
        trigPluginSel.value = matchEnt.plugin;
      }
    }
    renderTriggerEntityOptions(draft.trigger_key);

    const profileSel = backdrop.querySelector("#m-profile");
    const exeInput = backdrop.querySelector("#m-exe");
    profileSel.onchange = () => {
      const opt = profileSel.options[profileSel.selectedIndex];
      const pExe = opt ? opt.getAttribute("data-exe") : "";
      if (pExe) exeInput.value = pExe;
    };

    backdrop.querySelector("#m-browse-exe").onclick = async () => {
      try {
        const res = await apiFetch(`${API_BASE}/api/dialog/browse?type=exe`);
        if (res.ok) {
          const data = await res.json();
          if (data && data.path) exeInput.value = data.path;
        }
      } catch (_) {}
    };

    const closeModal = () => { try { backdrop.remove(); } catch (_) {} };
    backdrop.onclick = (e) => { if (e.target === backdrop) closeModal(); };
    backdrop.querySelector("#modal-cancel").onclick = closeModal;

    backdrop.querySelector("#modal-save").onclick = async () => {
      const name = backdrop.querySelector("#m-name").value.trim() || "Automation";
      const profId = backdrop.querySelector("#m-profile").value.trim();
      const exe = exeInput.value.trim();
      const trigKey = triggerKeySel.value.trim();
      const cooldown = Number(backdrop.querySelector("#m-cooldown").value) || 2;

      const payload = {
        id: draft.id || undefined,
        name: name,
        enabled: draft.enabled !== false,
        profile_id: profId,
        exe: exe,
        trigger_key: trigKey,
        require_foreground: !!exe,
        cooldown_s: cooldown,
        actions: currentActions,
      };

      await apiFetch(`${API_BASE}/api/automations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      closeModal();
      renderAutomations();
    };
  }

  // ── Vision page ──────────────────────────────────────────────

  const VISION_MODES = {
    color_percentage: "Colour Percentage",
    pixel_match: "Pixel Match",
    average_brightness: "Average Brightness",
    ocr_text: "Text Match (OCR)",
    ocr_number: "Number Value (OCR)",
  };

  const VISION_WIZARD_STEPS = [
    "Capture Region", "Detection Mode", "App", "Configure", "Test",
  ];

  function defaultDraft() {
    return {
      name: "",
      enabled: true,
      mode: "color_percentage",
      exe: "",
      anchor: null,
      region: null,
      color: "#ff0000",
      pixel: { x_pct: 50, y_pct: 50 },
      tolerance: 40,
      threshold: 30,
      direction: "below",
      poll_rate: 1.0,
      cooldown_s: 10,
      event_name: "",
      event_message: "",
      output_display: true,
      flash_name: false,
      play_sound: false,
      require_foreground: false,
      ocr_pattern: "",
      ocr_match_type: "contains",
      ocr_case_sensitive: false,
    };
  }

  async function fetchVision() {
    try {
      const res = await apiFetch(`${API_BASE}/api/vision/sensors`);
      if (res.ok) {
        const data = await res.json();
        const nextSensors = data.sensors || [];
        const live = data.live || null;
        if (currentPage === "vision" && !visionInWizard) {
          if (sensorListChanged(visionSensors, nextSensors)) {
            visionSensors = nextSensors;
            visionLive = live;
            renderVision();
          } else {
            visionSensors = nextSensors;
            visionLive = live;
            applyVisionLive();
          }
        } else {
          visionSensors = nextSensors;
          visionLive = live;
        }
      }
    } catch (_) {}
    clearTimeout(visionTimer);
    if (currentPage === "vision" && !visionInWizard) {
      visionTimer = setTimeout(fetchVision, 2000);
    }
  }

  function sensorListChanged(a, b) {
    if (!a || !b || a.length !== b.length) return true;
    const sig = (arr) => arr.map((s) => s.id + ":" + (s.enabled ? "1" : "0")).join(",");
    return sig(a) !== sig(b);
  }

  function applyVisionLive() {
    if (!visionLive || !visionLive.sensors) return;
    visionLive.sensors.forEach((live) => {
      const card = document.querySelector(`.vision-card[data-id="${live.id}"]`);
      if (!card) return;
      const cfg = visionSensors.find((s) => s.id === live.id);
      const disabled = cfg && !cfg.enabled;
      const running = live.running;
      const active = live.active;
      const dotColor = disabled ? "var(--fg-dim)"
        : (active ? "var(--neon-grn)" : "var(--neon-red)");
      const statusColor = disabled ? "var(--fg-dim)"
        : (active ? "var(--neon-grn)" : (running ? "var(--fg-dim)" : "var(--neon-red)"));

      const valEl = card.querySelector(".vision-card-value");
      if (valEl) {
        let valueDisplay = "";
        if (live.value !== null && live.value !== undefined && live.value !== "") {
          valueDisplay = typeof live.value === "number" ? String(live.value) : `"${String(live.value)}"`;
        }
        valEl.textContent = valueDisplay;
        valEl.title = valueDisplay;
        valEl.style.color = active ? "#ffffff" : "var(--fg-dim)";
      }
      const statusEl = card.querySelector(".vision-card-status");
      if (statusEl) {
        statusEl.textContent = disabled ? "Disabled"
          : (!running ? "App not running"
            : (active ? "Triggered" : "Watching"));
        statusEl.style.color = statusColor;
        if (active) statusEl.classList.add("triggered");
        else statusEl.classList.remove("triggered");
      }
      const dotEl = card.querySelector(".vision-status-dot");
      if (dotEl) dotEl.style.background = dotColor;
    });
  }

  function renderVision() {
    if (visionInWizard) { renderVisionWizard(); return; }
    main.innerHTML = `
      <header>
        <div class="header-left">
          <button class="hamburger" id="hamburger" aria-label="Menu">
            <span class="material-icons-outlined">menu</span>
          </button>
          <div>
            <h1>Vision</h1>
          </div>
        </div>
        <button class="done-btn" id="done-btn">Done</button>
      </header>
      <section class="content vision-content">
        <div class="vision-toolbar">
          <span class="vision-toolbar-title">Monitor screen regions and trigger events</span>
          <button class="settings-btn vision-add-btn" id="vision-add-btn">
            <span class="material-icons-outlined">add</span> Add Sensor
          </button>
        </div>
        <div class="vision-grid">
          ${visionSensors.length ? visionSensors.map(renderVisionCard).join("") : renderVisionEmpty()}
        </div>
      </section>`;
    rebindHamburger();
    const addBtn = document.getElementById("vision-add-btn");
    if (addBtn) {
      addBtn.addEventListener("click", () => {
        visionDraft = defaultDraft();
        wizardStep = 1;
        wizardCapture = null;
        visionInWizard = true;
        renderVisionWizard();
      });
    }
    document.querySelectorAll(".vision-card-toggle").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.dataset.id;
        const on = el.classList.toggle("on");
        const sensor = visionSensors.find((s) => s.id === id);
        if (sensor) updateSensor(id, Object.assign({}, sensor, { enabled: on }), true);
      });
    });
    document.querySelectorAll(".vision-card-test").forEach((el) => {
      el.addEventListener("click", () => {
        const sensor = visionSensors.find((s) => s.id === el.dataset.id);
        if (!sensor) return;
        testSensorNow(sensor);
      });
    });
    document.querySelectorAll(".vision-card-edit").forEach((el) => {
      el.addEventListener("click", () => {
        const sensor = visionSensors.find((s) => s.id === el.dataset.id);
        if (!sensor) return;
        visionDraft = Object.assign(defaultDraft(), JSON.parse(JSON.stringify(sensor)));
        wizardCapture = {
          exe: sensor.exe || "",
          anchor: sensor.anchor || null,
          region: sensor.region || null,
        };
        wizardStep = 5;
        visionInWizard = true;
        renderVisionWizard();
      });
    });
    document.querySelectorAll(".vision-card-del").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.dataset.id;
        if (!confirm("Delete this sensor?")) return;
        apiFetch(`${API_BASE}/api/vision/sensors/${encodeURIComponent(id)}/delete`, { method: "POST" })
          .then((r) => r.json())
          .then(() => fetchVision())
          .catch(() => {});
      });
    });
  }

  function renderVisionEmpty() {
    return `
      <div class="vision-empty">
        <span class="material-icons-outlined">visibility</span>
        <p>No vision sensors yet.</p>
        <p class="vision-empty-sub">Add a sensor to monitor a region of your screen.</p>
      </div>`;
  }

  function renderVisionCard(s) {
    const live = visionLive && visionLive.sensors
      ? visionLive.sensors.find((x) => x.id === s.id) : null;
    const running = live ? live.running : false;
    const active = live ? live.active : false;
    const value = live ? live.value : null;
    const dotColor = !s.enabled ? "var(--fg-dim)"
      : (active ? "var(--neon-grn)" : "var(--neon-red)");
    const statusColor = !s.enabled ? "var(--fg-dim)"
      : (active ? "var(--neon-grn)" : (running ? "var(--fg-dim)" : "var(--neon-red)"));
    const statusLabel = !s.enabled ? "Disabled"
      : (running ? (active ? "Triggered" : "Watching") : "App not running");
    
    let valueDisplay = "";
    if (value !== null && value !== undefined && value !== "") {
      valueDisplay = typeof value === "number" ? String(value) : `"${String(value)}"`;
    }

    const isOcrText = s.mode === "ocr_text";
    const isOcrNum = s.mode === "ocr_number";
    let targetSummary = "";
    if (isOcrText) {
      targetSummary = s.ocr_pattern ? ` · "${s.ocr_pattern}"` : "";
    } else if (isOcrNum) {
      const op = s.direction === "above" ? ">" : (s.direction === "equal" ? "==" : "<");
      targetSummary = ` · ${op} ${s.threshold}`;
    }

    const modeSummary = `${VISION_MODES[s.mode] || s.mode}${targetSummary}${s.require_foreground ? " · Focused" : ""}`;

    return `
      <div class="vision-card" data-id="${esc(s.id)}">
        <div class="vision-card-head">
          <div class="vision-card-title-group">
            <span class="vision-status-dot" style="background:${dotColor}"></span>
            <span class="vision-card-name" title="${esc(s.name || s.id)}">${esc(s.name || s.id)}</span>
          </div>
          <div class="vision-card-status-group">
            <span class="vision-card-status ${active ? "triggered" : ""}" style="color:${statusColor}">${statusLabel}</span>
            ${valueDisplay ? `<span class="vision-card-value" style="color:${active ? "#ffffff" : "var(--fg-dim)"}" title="${esc(valueDisplay)}">${esc(valueDisplay)}</span>` : ""}
          </div>
        </div>
        <div class="vision-card-meta">
          <span class="vision-card-app" title="${esc(s.exe || "—")}">
            <span class="material-icons-outlined">apps</span> ${esc(s.exe || "—")}
          </span>
          <span class="vision-meta-sep">•</span>
          <span class="vision-card-mode" title="${esc(modeSummary)}">${esc(modeSummary)}</span>
        </div>
        <div class="vision-card-actions">
          <span class="vision-toggle-label">Enabled
            <div class="settings-toggle ${s.enabled ? "on" : ""} vision-card-toggle" data-id="${esc(s.id)}">
              <div class="settings-toggle-thumb"></div>
            </div>
          </span>
          <div class="vision-card-btns">
            <button class="settings-btn vision-card-test" data-id="${esc(s.id)}">Test</button>
            <button class="settings-btn vision-card-edit" data-id="${esc(s.id)}">Edit</button>
            <button class="settings-btn vision-card-del danger" data-id="${esc(s.id)}">Delete</button>
          </div>
        </div>
      </div>`;
  }

  function testSensorNow(sensor) {
    const body = Object.assign({}, sensor);
    if (!body.anchor) body.anchor = null;
    apiFetch(`${API_BASE}/api/vision/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((d) => {
        alert(`Value: ${d.value}  —  ${d.active ? "Triggered" : "Not triggered"}`);
      })
      .catch(() => alert("Test failed"));
  }

  function updateSensor(id, sensor, silent) {
    apiFetch(`${API_BASE}/api/vision/sensors/${encodeURIComponent(id)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sensor),
    })
      .then((r) => r.json())
      .then(() => { if (!silent) fetchVision(); })
      .catch(() => { if (!silent) alert("Save failed"); });
  }

  // ── Notifications Tab (Web Portal) ───────────────────────────

  let notifData = { notifications: [], archived: [], max_stored: 50, rules: {}, sources: [] };
  let notifTab = "inbox";
  let notifTimer = null;

  async function fetchNotifications() {
    clearTimeout(notifTimer);
    if (currentPage !== "notifications") return;
    try {
      const res = await apiFetch(`${API_BASE}/api/notifications`);
      if (res.ok) {
        notifData = await res.json();
        if (currentPage === "notifications") {
          renderNotificationsList();
        }
      }
    } catch (_) {}
    if (currentPage === "notifications") {
      notifTimer = setTimeout(fetchNotifications, 2500);
    }
  }

  function formatRelativeTime(ts) {
    if (!ts) return "";
    const diff = Math.floor(Date.now() / 1000 - ts);
    if (diff < 10) return "Just now";
    if (diff < 60) return `${diff}s ago`;
    const m = Math.floor(diff / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d < 7) return `${d}d ago`;
    const dt = new Date(ts * 1000);
    return dt.toLocaleDateString();
  }

  // ── Library ───────────────────────────────────────────────────────────────

  var libraryTab = "screenshots";   // "screenshots" | "notes"
  var libraryFilter = "all";        // app name or "all"
  var libraryItems = [];            // cached from last fetch

  function renderLibrary() {
    main.innerHTML = `
      <header>
        <div class="header-left">
          <button class="hamburger" id="hamburger" aria-label="Menu">
            <span class="material-icons-outlined">menu</span>
          </button>
          <div>
            <h1>Library</h1>
          </div>
        </div>
        <button class="done-btn" id="done-btn">Done</button>
      </header>
      <section class="content lib-content">
        <div class="lib-toolbar">
          <div class="lib-tab-group">
            <button class="lib-tab-btn ${libraryTab === 'screenshots' ? 'active' : ''}" id="lib-tab-screenshots">
              <span class="material-icons-outlined" style="font-size:17px;">photo_library</span>
              Screenshots
            </button>
            <button class="lib-tab-btn ${libraryTab === 'notes' ? 'active' : ''}" id="lib-tab-notes">
              <span class="material-icons-outlined" style="font-size:17px;">sticky_note_2</span>
              Notes
            </button>
          </div>
          <div class="lib-filter-wrap">
            <span class="material-icons-outlined" style="font-size:16px;color:var(--fg-dim);">filter_list</span>
            <select id="lib-filter-select" class="lib-filter-select">
              <option value="all">All Apps</option>
            </select>
          </div>
          ${libraryTab === 'notes' ? `<button class="lib-new-note-btn" id="lib-new-note-btn">
            <span class="material-icons-outlined" style="font-size:16px;">add</span> New Note
          </button>` : ''}
        </div>
        <div id="lib-items-container" class="lib-items-container"></div>
      </section>`;

    rebindHamburger();
    wireLibraryEvents();
    fetchLibraryItems();
  }

  function wireLibraryEvents() {
    const tabScreenshots = document.getElementById("lib-tab-screenshots");
    const tabNotes = document.getElementById("lib-tab-notes");
    if (tabScreenshots) {
      tabScreenshots.addEventListener("click", () => {
        libraryTab = "screenshots";
        renderLibrary();
      });
    }
    if (tabNotes) {
      tabNotes.addEventListener("click", () => {
        libraryTab = "notes";
        renderLibrary();
      });
    }
    const filterSel = document.getElementById("lib-filter-select");
    if (filterSel) {
      filterSel.addEventListener("change", () => {
        libraryFilter = filterSel.value;
        renderLibraryItems();
      });
    }
    const newNoteBtn = document.getElementById("lib-new-note-btn");
    if (newNoteBtn) {
      newNoteBtn.addEventListener("click", () => openNotepad(null));
    }
  }

  async function fetchLibraryItems() {
    try {
      const r = await apiFetch(`${API_BASE}/api/library/items`);
      const data = await r.json();
      libraryItems = data.items || [];
      populateLibraryFilter();
      renderLibraryItems();
    } catch (e) {
      const c = document.getElementById("lib-items-container");
      if (c) c.innerHTML = `<p class="lib-empty">Could not load library.</p>`;
    }
  }

  function populateLibraryFilter() {
    const sel = document.getElementById("lib-filter-select");
    if (!sel) return;
    const apps = [...new Set(libraryItems.map(i => i.app))].sort();
    const counts = {};
    libraryItems.forEach(i => { counts[i.app] = (counts[i.app] || 0) + 1; });
    sel.innerHTML = `<option value="all">All Apps</option>` +
      apps.map(a => `<option value="${a}" ${libraryFilter === a ? 'selected' : ''}>${a} (${counts[a]})</option>`).join('');
    if (libraryFilter !== 'all' && !apps.includes(libraryFilter)) libraryFilter = 'all';
    sel.value = libraryFilter;
  }

  function renderLibraryItems() {
    const container = document.getElementById("lib-items-container");
    if (!container) return;

    const filtered = libraryItems.filter(item => {
      if (libraryTab === "screenshots" && item.type !== "screenshot") return false;
      if (libraryTab === "notes" && item.type !== "note") return false;
      if (libraryFilter !== "all" && item.app !== libraryFilter) return false;
      return true;
    });

    if (!filtered.length) {
      container.innerHTML = `<p class="lib-empty">No ${libraryTab} yet${libraryFilter !== 'all' ? ' for "' + libraryFilter + '"' : ''}.</p>`;
      return;
    }

    if (libraryTab === "screenshots") {
      container.innerHTML = `<div class="lib-grid">${filtered.map(item => libScreenshotCardHtml(item)).join('')}</div>`;
      container.querySelectorAll(".lib-card-screenshot").forEach(card => {
        const filename = card.dataset.filename;
        card.querySelector(".lib-card-img-wrap").addEventListener("click", () => openLibraryViewer(filename));
        const titleEl = card.querySelector(".lib-card-title");
        if (titleEl) {
          titleEl.addEventListener("click", (e) => { e.stopPropagation(); titleEl.focus(); });
          titleEl.addEventListener("blur", () => saveLibrarySidecar(filename, titleEl.textContent.trim()));
          titleEl.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); titleEl.blur(); } });
        }
        card.querySelector(".lib-card-delete").addEventListener("click", (e) => {
          e.stopPropagation();
          confirmLibraryDelete(filename, "screenshot and its annotations");
        });
      });
    } else {
      container.innerHTML = `<div class="lib-notes-list">${filtered.map(item => libNoteCardHtml(item)).join('')}</div>`;
      container.querySelectorAll(".lib-card-note").forEach(card => {
        const filename = card.dataset.filename;
        card.querySelector(".lib-note-body").addEventListener("click", () => openNotepad(filename));
        card.querySelector(".lib-card-delete").addEventListener("click", (e) => {
          e.stopPropagation();
          confirmLibraryDelete(filename, "note");
        });
      });
    }
  }

  function libScreenshotCardHtml(item) {
    const ts = new Date(item.ts * 1000).toLocaleString([], {dateStyle:"short", timeStyle:"short"});
    const title = item.title || "";
    return `<div class="lib-card-screenshot" data-filename="${item.filename}">
      <div class="lib-card-img-wrap">
        <img class="lib-card-img" src="${API_BASE}/api/library/image/${encodeURIComponent(item.filename)}" alt="${item.filename}" loading="lazy">
      </div>
      <div class="lib-card-meta">
        <span class="lib-card-app">${item.app}</span>
        <span class="lib-card-ts">${ts}</span>
      </div>
      <div class="lib-card-title-row">
        <span class="lib-card-title" contenteditable="true" spellcheck="false" placeholder="Add title…">${escapeHtml(title)}</span>
        <button class="lib-card-delete" title="Delete screenshot">
          <span class="material-icons-outlined" style="font-size:16px;">delete</span>
        </button>
      </div>
    </div>`;
  }

  function libNoteCardHtml(item) {
    const ts = new Date(item.ts * 1000).toLocaleString([], {dateStyle:"short", timeStyle:"short"});
    const title = item.title || "";
    const preview = item.preview || "";
    return `<div class="lib-card-note" data-filename="${item.filename}">
      <div class="lib-note-body">
        <div class="lib-note-header">
          <span class="lib-card-app">${item.app}</span>
          <span class="lib-card-ts">${ts}</span>
        </div>
        ${title ? `<div class="lib-note-title">${escapeHtml(title)}</div>` : ''}
        <p class="lib-note-preview">${escapeHtml(preview) || (!title ? '<em style="opacity:0.4">Empty note</em>' : '')}</p>
      </div>
      <button class="lib-card-delete" title="Delete note">
        <span class="material-icons-outlined" style="font-size:16px;">delete</span>
      </button>
    </div>`;
  }

  function escapeHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  async function saveLibrarySidecar(filename, title) {
    try {
      await apiFetch(`${API_BASE}/api/library/sidecar/${encodeURIComponent(filename)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title })
      });
      // Update cached item
      const item = libraryItems.find(i => i.filename === filename);
      if (item) item.title = title;
    } catch (e) { /* silent */ }
  }

  async function openLibraryViewer(filename) {
    const existing = document.getElementById("iris-screenshot-viewer");
    if (existing) existing.remove();
    const item = libraryItems.find(i => i.filename === filename);
    const title = item ? (item.title || item.app) : filename;

    // Fetch existing annotations from sidecar
    let sidecarData = { title: "", annotations: [] };
    try {
      const res = await apiFetch(`${API_BASE}/api/library/sidecar/${encodeURIComponent(filename)}`);
      if (res.ok) {
        sidecarData = await res.json();
        if (!Array.isArray(sidecarData.annotations)) sidecarData.annotations = [];
      }
    } catch (_) {}

    const el = document.createElement("div");
    el.id = "iris-screenshot-viewer";
    el.innerHTML = `
      <div class="ssv-bar">
        <div class="ssv-title-wrap">
          <span class="ssv-ts">${escapeHtml(title)}</span>
        </div>
        <div class="ssv-actions">
          <div class="ssv-tool-group">
            <button type="button" class="ssv-tool active" data-tool="arrow" title="Arrow & Label Annotation (A)">
              <span class="material-icons-outlined" style="font-size:18px;">north_east</span>
            </button>
            <button type="button" class="ssv-tool" data-tool="pen" title="Freehand Drawing Pen (P)">
              <span class="material-icons-outlined" style="font-size:18px;">draw</span>
            </button>
            <button type="button" class="ssv-tool" data-tool="hand" title="Pan View (H / Space+Drag)">
              <span class="material-icons-outlined" style="font-size:18px;">pan_tool</span>
            </button>
            <button type="button" class="ssv-tool" data-tool="zoom" title="Zoom In/Out (Z)">
              <span class="material-icons-outlined" style="font-size:18px;">zoom_in</span>
            </button>
          </div>
          <button type="button" class="ssv-btn-icon" id="ssv-reset-btn" title="Reset View (0)">
            <span class="material-icons-outlined" style="font-size:18px;">fit_screen</span>
          </button>
          <span class="ssv-zoom-label" id="ssv-zoom-label" style="display:none">100%</span>
          <button type="button" class="ssv-btn-icon" id="ssv-toggle-ann-btn" title="Show/Hide Annotations">
            <span class="material-icons-outlined" style="font-size:18px;">visibility</span>
          </button>
          <button type="button" class="ssv-btn-icon" id="ssv-copy-btn" title="Copy image with annotations to clipboard">
            <span class="material-icons-outlined" style="font-size:18px;">content_copy</span>
          </button>
          <button type="button" class="ssv-btn-icon" id="ssv-delete-btn" title="Delete screenshot">
            <span class="material-icons-outlined" style="font-size:18px;">delete</span>
          </button>
          <button type="button" class="ssv-btn-icon" id="ssv-fullscreen-btn" title="Toggle Fullscreen">
            <span class="material-icons-outlined" style="font-size:18px;">fullscreen</span>
          </button>
          <button type="button" class="ssv-close" aria-label="Close">&#x2715;</button>
        </div>
      </div>
      <div class="ssv-canvas-stage" id="ssv-stage">
        <div class="ssv-world" id="ssv-world">
          <img id="ssv-img" class="ssv-img" src="${API_BASE}/api/library/image/${encodeURIComponent(filename)}" alt="Screenshot" draggable="false">
        </div>
        <canvas id="ssv-ink" class="ssv-ink-canvas"></canvas>
        <canvas id="ssv-canvas" class="ssv-annotation-canvas"></canvas>
      </div>`;
    document.body.appendChild(el);

    const img = el.querySelector("#ssv-img");
    const world = el.querySelector("#ssv-world");
    const canvas = el.querySelector("#ssv-canvas");
    const inkCanvas = el.querySelector("#ssv-ink");
    const stage = el.querySelector("#ssv-stage");
    const ctx = canvas.getContext("2d");
    const inkCtx = inkCanvas.getContext("2d");
    const annotations = sidecarData.annotations || [];

    let viewScale = 1.0;
    let viewTx = 0, viewTy = 0;
    let toolMode = "arrow"; // "arrow" | "pen" | "hand" | "zoom"
    let fitW = 0, fitH = 0;
    let stageW = 0, stageH = 0;
    let dpr = window.devicePixelRatio || 1;

    let isDrawing = false;
    let startX = 0, startY = 0;
    let currX = 0, currY = 0;
    let activeStroke = null;
    let activeTextBox = null;
    let draggingTailIdx = null;
    let draggingHeadIdx = null;
    let resizingLabel = null;

    let isPanning = false;
    let panStartX = 0, panStartY = 0;
    let panInitTx = 0, panInitTy = 0;
    let isZoomDragging = false;
    let zoomStartY = 0, zoomInitScale = 1.0;
    let isSpacePanning = false;
    let currentColor = "#48B2E9";
    let annotationsVisible = true;
    let rafPending = false;
    let retryCount = 0;

    function handleImageError() {
      if (retryCount < 3) {
        retryCount++;
        setTimeout(function () {
          if (img) {
            img.src = `${API_BASE}/api/library/image/${encodeURIComponent(filename)}?retry=${retryCount}&t=${Date.now()}`;
          }
        }, 400 * retryCount);
      } else {
        console.error("Screenshot image failed to load after retries:", filename);
      }
    }

    img.addEventListener("error", handleImageError);

    function screenToWorld(sx, sy) {
      const fw = fitW || 1;
      const fh = fitH || 1;
      return {
        nx: Math.max(0, Math.min(1, ((sx - viewTx) / viewScale) / fw)),
        ny: Math.max(0, Math.min(1, ((sy - viewTy) / viewScale) / fh))
      };
    }

    function worldToScreen(nx, ny) {
      return {
        sx: nx * (fitW || 1) * viewScale + viewTx,
        sy: ny * (fitH || 1) * viewScale + viewTy
      };
    }

    function updateZoomLabel() {
      const label = el.querySelector("#ssv-zoom-label");
      if (!label) return;
      const pct = Math.round(viewScale * 100);
      label.textContent = pct + "%";
      if (Math.abs(viewScale - 1.0) < 0.01) {
        label.style.display = "none";
      } else {
        label.style.display = "inline-flex";
      }
    }

    function applyViewTransform() {
      if (world) {
        world.style.transform = `translate(${viewTx}px, ${viewTy}px) scale(${viewScale})`;
      }
      updateZoomLabel();
      scheduleRedraw();
    }

    function resizeCanvas() {
      if (!img.complete || img.naturalWidth === 0) return;
      stageW = stage.clientWidth;
      stageH = stage.clientHeight;
      if (stageW <= 0 || stageH <= 0) return;

      dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(stageW * dpr);
      canvas.height = Math.round(stageH * dpr);
      canvas.style.width = stageW + "px";
      canvas.style.height = stageH + "px";

      if (inkCanvas) {
        inkCanvas.width = Math.round(stageW * dpr);
        inkCanvas.height = Math.round(stageH * dpr);
        inkCanvas.style.width = stageW + "px";
        inkCanvas.style.height = stageH + "px";
      }

      const maxW = stageW - 32;
      const maxH = stageH - 32;
      const imgAspect = img.naturalWidth / img.naturalHeight;
      let w = maxW;
      let h = maxW / imgAspect;
      if (h > maxH) {
        h = maxH;
        w = maxH * imgAspect;
      }
      fitW = Math.round(w);
      fitH = Math.round(h);

      if (world) {
        world.style.width = fitW + "px";
        world.style.height = fitH + "px";
      }

      if (Math.abs(viewScale - 1.0) < 0.01) {
        viewTx = (stageW - fitW) / 2;
        viewTy = (stageH - fitH) / 2;
      }

      applyViewTransform();
    }

    img.addEventListener("load", resizeCanvas);
    window.addEventListener("resize", resizeCanvas);
    setTimeout(resizeCanvas, 50);

    function wrapText(context, text, maxWidth) {
      if (!maxWidth) return [text];
      const words = text.split(" ");
      const lines = [];
      let currentLine = words[0] || "";

      for (let i = 1; i < words.length; i++) {
        const word = words[i];
        const width = context.measureText(currentLine + " " + word).width;
        if (width < maxWidth) {
          currentLine += " " + word;
        } else {
          lines.push(currentLine);
          currentLine = word;
        }
      }
      lines.push(currentLine);
      return lines;
    }

    function getAnnotationLayout(ann) {
      const w = fitW || 1;
      const h = fitH || 1;
      const x1 = ann.x1 * w;
      const y1 = ann.y1 * h;
      const x2 = ann.x2 * w;
      const y2 = ann.y2 * h;

      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.font = "600 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
      const padH = 12, padV = 6;
      const text = ann.text || "";
      
      let lines = [text];
      let boxW = 36;
      let boxH = 26;
      const lineHeight = 18;

      if (ann.box_width) {
        boxW = Math.max(ann.box_width * w, 50);
        const maxTextW = boxW - padH * 2;
        lines = wrapText(ctx, text, maxTextW);
        boxH = Math.max(lines.length * lineHeight + padV * 2, 26);
      } else {
        const metrics = ctx.measureText(text);
        boxW = Math.max(metrics.width + padH * 2, 36);
        boxH = 26;
      }

      let boxX = x2 + 10;
      let boxY = y2 - boxH / 2;
      if (boxX + boxW > w) boxX = x2 - boxW - 10;
      if (boxY + boxH > h) boxY = h - boxH - 6;
      if (boxY < 6) boxY = 6;
      ctx.restore();

      return { x1, y1, x2, y2, boxX, boxY, boxW, boxH, lines, lineHeight, padH, padV };
    }

    function distToSegment(px, py, x1, y1, x2, y2) {
      const dx = x2 - x1;
      const dy = y2 - y1;
      const lenSq = dx * dx + dy * dy;
      if (lenSq === 0) return Math.hypot(px - x1, py - y1);
      const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq));
      return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
    }

    function hitTestAnnotation(sx, sy) {
      if (!annotationsVisible) return null;
      const edgeThreshold = 8;

      // 1. Check label badges & resize edges (in screen coordinates)
      for (let i = annotations.length - 1; i >= 0; i--) {
        const ann = annotations[i];
        if (ann.type === "path") continue;
        let ownerIdx = i;
        let ownerAnn = ann;
        if (!ann.text) {
          const rootIdx = annotations.findIndex(a => a.type !== "path" && !!a.text && Math.hypot(a.x2 - ann.x2, a.y2 - ann.y2) < 0.02);
          if (rootIdx !== -1) {
            ownerIdx = rootIdx;
            ownerAnn = annotations[rootIdx];
          }
        }

        const layout = getAnnotationLayout(ownerAnn);
        const sBoxTopLeft = worldToScreen(layout.boxX / (fitW || 1), layout.boxY / (fitH || 1));
        const sBoxW = layout.boxW * viewScale;
        const sBoxH = layout.boxH * viewScale;

        if (sy >= sBoxTopLeft.sy && sy <= sBoxTopLeft.sy + sBoxH) {
          if (Math.abs(sx - (sBoxTopLeft.sx + sBoxW)) <= edgeThreshold) {
            return { index: ownerIdx, target: "resize_right", annotation: ownerAnn, layout };
          }
          if (Math.abs(sx - sBoxTopLeft.sx) <= edgeThreshold) {
            return { index: ownerIdx, target: "resize_left", annotation: ownerAnn, layout };
          }
          if (sx > sBoxTopLeft.sx && sx < sBoxTopLeft.sx + sBoxW) {
            return { index: ownerIdx, target: "label", annotation: ownerAnn, layout };
          }
        }
      }

      // 2. Check arrow heads and tail anchors (in screen coordinates)
      for (let i = annotations.length - 1; i >= 0; i--) {
        const ann = annotations[i];
        if (ann.type === "path") continue;
        const layout = getAnnotationLayout(ann);
        const sHead = worldToScreen(layout.x1 / (fitW || 1), layout.y1 / (fitH || 1));
        const sTail = worldToScreen(layout.x2 / (fitW || 1), layout.y2 / (fitH || 1));

        if (Math.hypot(sx - sHead.sx, sy - sHead.sy) <= 14) {
          return { index: i, target: "head", annotation: ann, layout };
        }

        if (Math.hypot(sx - sTail.sx, sy - sTail.sy) <= 12) {
          let ownerIdx = i;
          let ownerAnn = ann;
          if (!ann.text) {
            const rootIdx = annotations.findIndex(a => a.type !== "path" && !!a.text && Math.hypot(a.x2 - ann.x2, a.y2 - ann.y2) < 0.02);
            if (rootIdx !== -1) {
              ownerIdx = rootIdx;
              ownerAnn = annotations[rootIdx];
            }
          }
          return { index: ownerIdx, target: "tail", annotation: ownerAnn, layout };
        }
      }

      // 3. Check freehand path strokes proximity (within 8 screen pixels)
      for (let i = annotations.length - 1; i >= 0; i--) {
        const ann = annotations[i];
        if (ann.type !== "path" || !ann.points || ann.points.length < 2) continue;
        for (let j = 0; j < ann.points.length - 1; j++) {
          const p1 = worldToScreen(ann.points[j][0], ann.points[j][1]);
          const p2 = worldToScreen(ann.points[j + 1][0], ann.points[j + 1][1]);
          const dist = distToSegment(sx, sy, p1.sx, p1.sy, p2.sx, p2.sy);
          if (dist <= 8) {
            return { index: i, target: "path", annotation: ann };
          }
        }
      }

      return null;
    }

    function drawArrow(context, fromX, fromY, toX, toY, color, isMovingTail) {
      const headlen = 15;
      const dx = toX - fromX;
      const dy = toY - fromY;
      const angle = Math.atan2(dy, dx);

      context.save();
      context.strokeStyle = color;
      context.fillStyle = color;
      context.lineWidth = 3.5;
      context.lineCap = "round";
      context.lineJoin = "round";
      context.shadowColor = "rgba(0,0,0,0.85)";
      context.shadowBlur = 6;

      // Line from head to tail
      context.beginPath();
      context.moveTo(fromX, fromY);
      context.lineTo(toX, toY);
      context.stroke();

      // Arrow head pointing towards the point of interest
      context.beginPath();
      context.moveTo(fromX, fromY);
      context.lineTo(fromX + headlen * Math.cos(angle - Math.PI / 6), fromY + headlen * Math.sin(angle - Math.PI / 6));
      context.lineTo(fromX + headlen * Math.cos(angle + Math.PI / 6), fromY + headlen * Math.sin(angle + Math.PI / 6));
      context.closePath();
      context.fill();

      // Tail handle circle
      context.beginPath();
      context.arc(toX, toY, isMovingTail ? 6.5 : 5, 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = "#ffffff";
      context.lineWidth = 2;
      context.stroke();
      context.restore();
    }

    function drawPath(context, ann) {
      const pts = ann.points;
      if (!pts || pts.length < 2) return;
      const w = fitW || 1, h = fitH || 1;
      context.save();
      context.strokeStyle = ann.color || "#48B2E9";
      context.lineWidth = ann.lineWidth || 3.5;
      context.lineCap = "round";
      context.lineJoin = "round";
      context.shadowColor = "rgba(0,0,0,0.75)";
      context.shadowBlur = 4;

      context.beginPath();
      context.moveTo(pts[0][0] * w, pts[0][1] * h);
      for (let i = 1; i < pts.length; i++) {
        context.lineTo(pts[i][0] * w, pts[i][1] * h);
      }
      context.stroke();
      context.restore();
    }

    function drawAnnotationLabel(context, layout, text, color) {
      context.save();
      context.font = "600 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
      const { boxX, boxY, boxW, boxH, lines, lineHeight, padH, padV } = layout;

      // Background badge plate
      context.fillStyle = "rgba(12, 14, 18, 0.95)";
      context.strokeStyle = color;
      context.lineWidth = 2;
      context.shadowColor = "rgba(0,0,0,0.85)";
      context.shadowBlur = 8;

      context.beginPath();
      if (context.roundRect) {
        context.roundRect(boxX, boxY, boxW, boxH, 6);
      } else {
        context.rect(boxX, boxY, boxW, boxH);
      }
      context.fill();
      context.stroke();

      // Sharp text
      context.fillStyle = "#ffffff";
      context.shadowBlur = 0;
      context.textBaseline = "top";

      const startTextY = boxY + Math.max((boxH - (lines.length * lineHeight)) / 2, padV);
      lines.forEach((line, idx) => {
        context.fillText(line, boxX + padH, startTextY + idx * lineHeight);
      });

      context.restore();
    }

    function scheduleRedraw(dragArrow) {
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(() => {
        rafPending = false;
        redraw(dragArrow);
      });
    }

    function redraw(dragArrow) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (fitW === 0 || fitH === 0) return;

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.translate(viewTx, viewTy);
      ctx.scale(viewScale, viewScale);

      if (annotationsVisible) {
        // 1. Draw all saved freehand paths
        annotations.forEach((ann) => {
          if (ann.type === "path") {
            drawPath(ctx, ann);
          }
        });

        // 2. Draw all arrow lines and heads
        annotations.forEach((ann, idx) => {
          if (ann.type !== "path") {
            const layout = getAnnotationLayout(ann);
            const isMoving = draggingTailIdx === idx;
            drawArrow(ctx, layout.x1, layout.y1, layout.x2, layout.y2, ann.color || "#48B2E9", isMoving);
          }
        });
      }

      // 3. Draw in-progress new arrow
      if (dragArrow) {
        drawArrow(ctx, dragArrow.x1 * fitW, dragArrow.y1 * fitH, dragArrow.x2 * fitW, dragArrow.y2 * fitH, currentColor || "#48B2E9", true);
      }

      if (annotationsVisible) {
        // 4. Draw label badges topmost
        annotations.forEach((ann) => {
          if (ann.type !== "path" && ann.text) {
            const layout = getAnnotationLayout(ann);
            drawAnnotationLabel(ctx, layout, ann.text, ann.color || "#48B2E9");
          }
        });
      }

      ctx.restore();
    }

    function drawInkStroke(pts) {
      if (!inkCtx || !pts || pts.length < 2) return;
      inkCtx.clearRect(0, 0, inkCanvas.width, inkCanvas.height);
      inkCtx.save();
      inkCtx.scale(dpr, dpr);
      inkCtx.strokeStyle = currentColor || "#48B2E9";
      inkCtx.lineWidth = (3.5 * viewScale);
      inkCtx.lineCap = "round";
      inkCtx.lineJoin = "round";
      inkCtx.shadowColor = "rgba(0,0,0,0.6)";
      inkCtx.shadowBlur = 4;

      inkCtx.beginPath();
      const p0 = worldToScreen(pts[0].nx, pts[0].ny);
      inkCtx.moveTo(p0.sx, p0.sy);
      for (let i = 1; i < pts.length; i++) {
        const p = worldToScreen(pts[i].nx, pts[i].ny);
        inkCtx.lineTo(p.sx, p.sy);
      }
      inkCtx.stroke();
      inkCtx.restore();
    }

    async function saveAnnotations() {
      try {
        await apiFetch(`${API_BASE}/api/library/sidecar/${encodeURIComponent(filename)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ annotations })
        });
      } catch (_) {}
    }

    function promptAnnotationText(nx1, ny1, nx2, ny2, existingIdx) {
      if (activeTextBox) activeTextBox.remove();

      const isEdit = typeof existingIdx === "number";
      const initialText = isEdit ? (annotations[existingIdx].text || "") : "";
      let selectedColor = isEdit ? (annotations[existingIdx].color || currentColor || "#48B2E9") : (currentColor || "#48B2E9");

      const NEON_COLORS = [
        { name: "blue", hex: "#48B2E9" },
        { name: "green", hex: "#00ff88" },
        { name: "red", hex: "#ff3355" },
        { name: "purple", hex: "#B23AF6" }
      ];

      const box = document.createElement("div");
      box.className = "ssv-text-box";
      const sTail = worldToScreen(nx2, ny2);
      const left = Math.min(Math.max(sTail.sx + 10, 10), (stageW || canvas.width) - 220);
      const top = Math.min(Math.max(sTail.sy - 30, 10), (stageH || canvas.height) - 90);
      box.style.left = left + "px";
      box.style.top = top + "px";
      box.style.borderColor = selectedColor;

      const swatchesHtml = NEON_COLORS.map(c => `
        <button type="button" class="ssv-swatch ${c.hex.toLowerCase() === selectedColor.toLowerCase() ? "active" : ""}" data-color="${c.hex}" style="background-color:${c.hex}; color:${c.hex};" title="${c.name}"></button>
      `).join("");

      box.innerHTML = `
        <input type="text" class="ssv-text-input" placeholder="Type label…" value="${escapeHtml(initialText)}" autocomplete="off">
        <div class="ssv-text-actions">
          <div class="ssv-swatches">
            ${swatchesHtml}
          </div>
          <div class="ssv-action-btns">
            <button type="button" class="ssv-btn-sm ssv-btn-del" id="ssv-cancel">Cancel</button>
            <button type="button" class="ssv-btn-sm ssv-btn-ok" id="ssv-ok">Done</button>
          </div>
        </div>`;

      stage.appendChild(box);
      activeTextBox = box;
      const inp = box.querySelector(".ssv-text-input");
      inp.focus();
      inp.select();

      box.querySelectorAll(".ssv-swatch").forEach(swatch => {
        swatch.addEventListener("click", () => {
          box.querySelectorAll(".ssv-swatch").forEach(s => s.classList.remove("active"));
          swatch.classList.add("active");
          selectedColor = swatch.dataset.color;
          currentColor = selectedColor;
          box.style.borderColor = selectedColor;
        });
      });

      const commit = () => {
        const val = inp.value.trim();
        if (val) {
          if (isEdit) {
            const targetAnn = annotations[existingIdx];
            targetAnn.text = val;
            targetAnn.color = selectedColor;
            annotations.forEach(a => {
              if (a.type !== "path" && Math.hypot(a.x2 - targetAnn.x2, a.y2 - targetAnn.y2) < 0.02) {
                a.color = selectedColor;
              }
            });
          } else {
            annotations.push({
              type: "arrow_text",
              x1: nx1,
              y1: ny1,
              x2: nx2,
              y2: ny2,
              text: val,
              color: selectedColor
            });
          }
          saveAnnotations();
          redraw();
        } else if (isEdit) {
          annotations.splice(existingIdx, 1);
          saveAnnotations();
          redraw();
        } else {
          redraw();
        }
        box.remove();
        activeTextBox = null;
      };

      box.querySelector("#ssv-ok").addEventListener("click", commit);
      box.querySelector("#ssv-cancel").addEventListener("click", () => {
        box.remove();
        activeTextBox = null;
        redraw();
      });
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); commit(); }
        if (e.key === "Escape") { box.remove(); activeTextBox = null; redraw(); }
      });
    }

    function setToolMode(mode) {
      toolMode = mode;
      el.querySelectorAll(".ssv-tool").forEach(btn => {
        btn.classList.toggle("active", btn.getAttribute("data-tool") === mode);
      });
      updateCursor();
    }

    function updateCursor(targetCursor) {
      if (targetCursor) {
        canvas.style.cursor = targetCursor;
        return;
      }
      if (isSpacePanning || toolMode === "hand") {
        canvas.style.cursor = isPanning ? "grabbing" : "grab";
      } else if (toolMode === "zoom") {
        canvas.style.cursor = "zoom-in";
      } else if (toolMode === "pen") {
        canvas.style.cursor = "crosshair";
      } else {
        canvas.style.cursor = "crosshair";
      }
    }

    el.querySelectorAll(".ssv-tool").forEach(btn => {
      btn.addEventListener("click", () => {
        setToolMode(btn.getAttribute("data-tool"));
      });
    });

    const resetBtn = el.querySelector("#ssv-reset-btn");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        viewScale = 1.0;
        viewTx = (stageW - fitW) / 2;
        viewTy = (stageH - fitH) / 2;
        applyViewTransform();
      });
    }

    // Context menu right-click deletion
    canvas.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const rect = stage.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const hit = hitTestAnnotation(sx, sy);
      if (hit) {
        if (hit.target === "path") {
          if (confirm("Delete this drawing stroke? This cannot be undone.")) {
            annotations.splice(hit.index, 1);
            saveAnnotations();
            redraw();
          }
          return;
        }

        if (hit.target === "head") {
          if (confirm("Delete this arrow? This cannot be undone.")) {
            annotations.splice(hit.index, 1);
            saveAnnotations();
            redraw();
          }
          return;
        }

        const targetAnn = annotations[hit.index];
        const shared = annotations.filter(a => a.type !== "path" && Math.hypot(a.x2 - targetAnn.x2, a.y2 - targetAnn.y2) < 0.02);
        const countMsg = shared.length > 1 ? ` (${shared.length} arrows)` : "";
        const labelName = targetAnn.text || "this annotation";

        if (confirm(`Delete label "${labelName}"${countMsg}? This cannot be undone.`)) {
          for (let i = annotations.length - 1; i >= 0; i--) {
            if (annotations[i].type !== "path" && Math.hypot(annotations[i].x2 - targetAnn.x2, annotations[i].y2 - targetAnn.y2) < 0.02) {
              annotations.splice(i, 1);
            }
          }
          saveAnnotations();
          redraw();
        }
      }
    });

    // Mouse wheel zoom centered on cursor
    stage.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = stage.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      const newScale = Math.max(0.2, Math.min(10.0, viewScale * factor));
      viewTx = mouseX - (mouseX - viewTx) * (newScale / viewScale);
      viewTy = mouseY - (mouseY - viewTy) * (newScale / viewScale);
      viewScale = newScale;
      applyViewTransform();
    }, { passive: false });

    // Double click to toggle 2x zoom centered on click
    canvas.addEventListener("dblclick", (e) => {
      const rect = stage.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;
      if (Math.abs(viewScale - 1.0) < 0.05) {
        const newScale = 2.2;
        viewTx = clickX - (clickX - viewTx) * (newScale / viewScale);
        viewTy = clickY - (clickY - viewTy) * (newScale / viewScale);
        viewScale = newScale;
      } else {
        viewScale = 1.0;
        viewTx = (stageW - fitW) / 2;
        viewTy = (stageH - fitH) / 2;
      }
      applyViewTransform();
    });

    // Pointer Events on canvas
    canvas.addEventListener("pointerdown", (e) => {
      if (e.button === 2) return; // Handled by contextmenu
      if (activeTextBox) { activeTextBox.remove(); activeTextBox = null; }
      const rect = stage.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const worldPt = screenToWorld(sx, sy);

      // Hand tool or Spacebar pan
      if (isSpacePanning || toolMode === "hand" || e.button === 1) {
        isPanning = true;
        panStartX = e.clientX;
        panStartY = e.clientY;
        panInitTx = viewTx;
        panInitTy = viewTy;
        canvas.setPointerCapture(e.pointerId);
        updateCursor("grabbing");
        return;
      }

      // Zoom drag tool
      if (toolMode === "zoom") {
        isZoomDragging = true;
        zoomStartY = e.clientY;
        zoomInitScale = viewScale;
        canvas.setPointerCapture(e.pointerId);
        return;
      }

      // Freehand drawing pen tool
      if (toolMode === "pen") {
        isDrawing = true;
        activeStroke = [worldPt];
        canvas.setPointerCapture(e.pointerId);
        drawInkStroke(activeStroke);
        return;
      }

      // Arrow mode
      const hit = hitTestAnnotation(sx, sy);

      // 1. Arrow head drag
      if (hit && hit.target === "head") {
        draggingHeadIdx = hit.index;
        canvas.setPointerCapture(e.pointerId);
        redraw();
        return;
      }

      // 2. Label resize drag
      if (hit && (hit.target === "resize_right" || hit.target === "resize_left")) {
        resizingLabel = {
          index: hit.index,
          side: hit.target,
          initialBoxW: hit.layout.boxW,
          startSx: sx,
          ann: hit.annotation
        };
        canvas.setPointerCapture(e.pointerId);
        return;
      }

      // 3. Arrow tail anchor drag
      if (hit && hit.target === "tail") {
        draggingTailIdx = hit.index;
        canvas.setPointerCapture(e.pointerId);
        redraw();
        return;
      }

      // 4. Click inside label badge -> edit text
      if (hit && hit.target === "label") {
        promptAnnotationText(hit.annotation.x1, hit.annotation.y1, hit.annotation.x2, hit.annotation.y2, hit.index);
        return;
      }

      // 5. Start new arrow
      isDrawing = true;
      startX = worldPt.nx;
      startY = worldPt.ny;
      currX = worldPt.nx;
      currY = worldPt.ny;
      canvas.setPointerCapture(e.pointerId);
    });

    canvas.addEventListener("pointermove", (e) => {
      const rect = stage.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const worldPt = screenToWorld(sx, sy);

      if (isPanning) {
        viewTx = panInitTx + (e.clientX - panStartX);
        viewTy = panInitTy + (e.clientY - panStartY);
        applyViewTransform();
        return;
      }

      if (isZoomDragging) {
        const dy = zoomStartY - e.clientY;
        const zoomFactor = Math.pow(2, dy / 150);
        const newScale = Math.max(0.2, Math.min(10.0, zoomInitScale * zoomFactor));
        const centerX = stageW / 2;
        const centerY = stageH / 2;
        viewTx = centerX - (centerX - viewTx) * (newScale / viewScale);
        viewTy = centerY - (centerY - viewTy) * (newScale / viewScale);
        viewScale = newScale;
        applyViewTransform();
        return;
      }

      if (toolMode === "pen" && isDrawing && activeStroke) {
        const events = (e.getCoalescedEvents && e.getCoalescedEvents().length) ? e.getCoalescedEvents() : [e];
        events.forEach(ev => {
          const evSx = ev.clientX - rect.left;
          const evSy = ev.clientY - rect.top;
          activeStroke.push(screenToWorld(evSx, evSy));
        });
        drawInkStroke(activeStroke);
        return;
      }

      // Arrow head repositioning
      if (draggingHeadIdx !== null) {
        const ann = annotations[draggingHeadIdx];
        ann.x1 = worldPt.nx;
        ann.y1 = worldPt.ny;
        scheduleRedraw();
        return;
      }

      // Label width resizing
      if (resizingLabel) {
        const dsx = (sx - resizingLabel.startSx) / viewScale;
        let newWidthPx = resizingLabel.initialBoxW;
        if (resizingLabel.side === "resize_right") {
          newWidthPx += dsx;
        } else {
          newWidthPx -= dsx;
        }
        newWidthPx = Math.max(50, Math.min(newWidthPx, (fitW || 500) * 0.8));
        resizingLabel.ann.box_width = newWidthPx / (fitW || 1);
        scheduleRedraw();
        return;
      }

      // Tail anchor repositioning
      if (draggingTailIdx !== null) {
        const primaryAnn = annotations[draggingTailIdx];
        const oldX2 = primaryAnn.x2;
        const oldY2 = primaryAnn.y2;
        const newX2 = worldPt.nx;
        const newY2 = worldPt.ny;

        annotations.forEach(ann => {
          if (ann.type !== "path" && Math.hypot(ann.x2 - oldX2, ann.y2 - oldY2) < 0.02) {
            ann.x2 = newX2;
            ann.y2 = newY2;
          }
        });
        scheduleRedraw();
        return;
      }

      // In-progress new arrow drag preview
      if (isDrawing && toolMode === "arrow") {
        currX = worldPt.nx;
        currY = worldPt.ny;
        const hit = hitTestAnnotation(sx, sy);
        if (hit && hit.target !== "path" && hit.annotation) {
          scheduleRedraw({ x1: startX, y1: startY, x2: hit.annotation.x2, y2: hit.annotation.y2 });
        } else {
          scheduleRedraw({ x1: startX, y1: startY, x2: currX, y2: currY });
        }
        return;
      }

      // Hover cursor management
      if (isSpacePanning || toolMode === "hand") {
        updateCursor("grab");
        return;
      }
      if (toolMode === "zoom") {
        updateCursor("zoom-in");
        return;
      }
      if (toolMode === "pen") {
        updateCursor("crosshair");
        return;
      }

      const hit = hitTestAnnotation(sx, sy);
      if (hit) {
        if (hit.target === "resize_right" || hit.target === "resize_left") {
          updateCursor("ew-resize");
        } else if (hit.target === "head" || hit.target === "tail") {
          updateCursor("move");
        } else if (hit.target === "path") {
          updateCursor("pointer");
        } else {
          updateCursor("pointer");
        }
      } else {
        updateCursor("crosshair");
      }
    });

    canvas.addEventListener("pointerup", (e) => {
      if (isPanning) {
        isPanning = false;
        updateCursor();
        return;
      }

      if (isZoomDragging) {
        isZoomDragging = false;
        return;
      }

      if (draggingHeadIdx !== null) {
        draggingHeadIdx = null;
        saveAnnotations();
        redraw();
        return;
      }

      if (resizingLabel) {
        resizingLabel = null;
        saveAnnotations();
        redraw();
        return;
      }

      if (draggingTailIdx !== null) {
        draggingTailIdx = null;
        saveAnnotations();
        redraw();
        return;
      }

      if (toolMode === "pen" && isDrawing && activeStroke) {
        isDrawing = false;
        if (inkCtx) inkCtx.clearRect(0, 0, inkCanvas.width, inkCanvas.height);
        if (activeStroke.length >= 2) {
          annotations.push({
            type: "path",
            points: activeStroke.map(p => [p.nx, p.ny]),
            color: currentColor || "#48B2E9",
            lineWidth: 3.5
          });
          saveAnnotations();
        }
        activeStroke = null;
        redraw();
        return;
      }

      if (isDrawing && toolMode === "arrow") {
        isDrawing = false;
        const rect = stage.getBoundingClientRect();
        const endSx = e.clientX - rect.left;
        const endSy = e.clientY - rect.top;
        const worldEnd = screenToWorld(endSx, endSy);
        const distPx = Math.hypot(endSx - (worldToScreen(startX, startY).sx), endSy - (worldToScreen(startX, startY).sy));

        if (distPx > 15) {
          const hit = hitTestAnnotation(endSx, endSy);
          if (hit && hit.target !== "path" && hit.annotation) {
            const existingAnn = hit.annotation;
            annotations.push({
              type: "arrow_text",
              x1: startX,
              y1: startY,
              x2: existingAnn.x2,
              y2: existingAnn.y2,
              text: "",
              color: existingAnn.color || currentColor || "#48B2E9"
            });
            saveAnnotations();
            redraw();
          } else {
            promptAnnotationText(startX, startY, worldEnd.nx, worldEnd.ny);
          }
        } else {
          redraw();
        }
      }
    });

    const toggleAnnBtn = el.querySelector("#ssv-toggle-ann-btn");
    if (toggleAnnBtn) {
      toggleAnnBtn.addEventListener("click", () => {
        annotationsVisible = !annotationsVisible;
        const icon = toggleAnnBtn.querySelector(".material-icons-outlined");
        if (icon) icon.textContent = annotationsVisible ? "visibility" : "visibility_off";
        toggleAnnBtn.style.color = annotationsVisible ? "var(--fg, #e8eaed)" : "var(--neon-dim, #666)";
        redraw();
      });
    }

    const delBtn = el.querySelector("#ssv-delete-btn");
    if (delBtn) {
      delBtn.addEventListener("click", () => {
        if (!confirm(`Delete screenshot "${title || filename}"? This cannot be undone.`)) return;
        apiFetch(`${API_BASE}/api/library/delete/${encodeURIComponent(filename)}`, { method: "POST" })
          .then(() => {
            libraryItems = libraryItems.filter(i => i.filename !== filename);
            populateLibraryFilter();
            renderLibraryItems();
            closeViewerAction();
          })
          .catch(() => alert("Delete failed."));
      });
    }

    const copyBtn = el.querySelector("#ssv-copy-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", async () => {
        if (!img.complete || img.naturalWidth === 0) return;
        try {
          const expCanvas = document.createElement("canvas");
          expCanvas.width = img.naturalWidth;
          expCanvas.height = img.naturalHeight;
          const expCtx = expCanvas.getContext("2d");

          expCtx.drawImage(img, 0, 0);

          if (annotationsVisible) {
            const scale = img.naturalWidth / (fitW || 1);
            expCtx.save();
            expCtx.scale(scale, scale);

            // 1. Draw all freehand paths
            annotations.forEach((ann) => {
              if (ann.type === "path") {
                drawPath(expCtx, ann);
              }
            });

            // 2. Draw all arrow lines and heads
            annotations.forEach((ann) => {
              if (ann.type !== "path") {
                const layout = getAnnotationLayout(ann);
                drawArrow(expCtx, layout.x1, layout.y1, layout.x2, layout.y2, ann.color || "#48B2E9", false);
              }
            });

            // 3. Draw label badges topmost
            annotations.forEach((ann) => {
              if (ann.type !== "path" && ann.text) {
                const layout = getAnnotationLayout(ann);
                drawAnnotationLabel(expCtx, layout, ann.text, ann.color || "#48B2E9");
              }
            });

            expCtx.restore();
          }

          expCanvas.toBlob(async (blob) => {
            if (!blob) return;
            try {
              if (navigator.clipboard && navigator.clipboard.write) {
                await navigator.clipboard.write([
                  new ClipboardItem({ "image/png": blob })
                ]);
              } else {
                throw new Error("Clipboard API not available");
              }

              copyBtn.classList.add("copied");
              const icon = copyBtn.querySelector(".material-icons-outlined");
              if (icon) icon.textContent = "check";
              setTimeout(() => {
                copyBtn.classList.remove("copied");
                if (icon) icon.textContent = "content_copy";
              }, 2000);
            } catch (err) {
              console.warn("Clipboard copy fallback downloading:", err);
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = `annotated_${filename}`;
              a.click();
              URL.revokeObjectURL(a.href);
            }
          }, "image/png");
        } catch (e) {
          console.error("Failed to copy image:", e);
        }
      });
    }

    const isStandaloneWindow = document.body.classList.contains("standalone-viewer-mode");
    const fsBtn = el.querySelector("#ssv-fullscreen-btn");
    if (fsBtn) {
      if (isStandaloneWindow) {
        fsBtn.title = "Reduce to Small Preview";
        const icon = fsBtn.querySelector(".material-icons-outlined");
        if (icon) icon.textContent = "fullscreen_exit";
        fsBtn.addEventListener("click", () => {
          closeViewerAction();
        });
      } else {
        fsBtn.addEventListener("click", () => {
          if (window.pywebview && window.pywebview.api && window.pywebview.api.open_fullscreen_viewer) {
            window.pywebview.api.open_fullscreen_viewer(filename);
            el.remove();
          } else {
            if (!document.fullscreenElement) {
              if (el.requestFullscreen) el.requestFullscreen();
              else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
            } else {
              if (document.exitFullscreen) document.exitFullscreen();
              else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
            }
          }
        });
      }
    }

    const onFsChange = () => {
      setTimeout(resizeCanvas, 100);
      if (fsBtn && !isStandaloneWindow) {
        const isFs = !!document.fullscreenElement;
        fsBtn.querySelector(".material-icons-outlined").textContent = isFs ? "fullscreen_exit" : "fullscreen";
      }
    };
    document.addEventListener("fullscreenchange", onFsChange);
    document.addEventListener("webkitfullscreenchange", onFsChange);

    const onKeyDown = (e) => {
      if (activeTextBox) return; // Don't intercept while typing in label input
      if (e.key === "Escape") {
        closeViewerAction();
      } else if (e.key === " " && !isSpacePanning) {
        isSpacePanning = true;
        updateCursor();
      } else if (e.key === "a" || e.key === "A") {
        setToolMode("arrow");
      } else if (e.key === "p" || e.key === "P") {
        setToolMode("pen");
      } else if (e.key === "h" || e.key === "H") {
        setToolMode("hand");
      } else if (e.key === "z" || e.key === "Z") {
        setToolMode("zoom");
      } else if (e.key === "0") {
        viewScale = 1.0;
        viewTx = (stageW - fitW) / 2;
        viewTy = (stageH - fitH) / 2;
        applyViewTransform();
      } else if (e.key === "=" || e.key === "+") {
        const newScale = Math.min(10.0, viewScale * 1.25);
        const centerX = stageW / 2;
        const centerY = stageH / 2;
        viewTx = centerX - (centerX - viewTx) * (newScale / viewScale);
        viewTy = centerY - (centerY - viewTy) * (newScale / viewScale);
        viewScale = newScale;
        applyViewTransform();
      } else if (e.key === "-" || e.key === "_") {
        const newScale = Math.max(0.2, viewScale / 1.25);
        const centerX = stageW / 2;
        const centerY = stageH / 2;
        viewTx = centerX - (centerX - viewTx) * (newScale / viewScale);
        viewTy = centerY - (centerY - viewTy) * (newScale / viewScale);
        viewScale = newScale;
        applyViewTransform();
      }
    };

    const onKeyUp = (e) => {
      if (e.key === " ") {
        isSpacePanning = false;
        updateCursor();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);

    const closeViewerAction = () => {
      if (isStandaloneWindow) {
        if (window.pywebview && window.pywebview.api) {
          if (window.pywebview.api.close_viewer) {
            window.pywebview.api.close_viewer();
            return;
          }
          if (window.pywebview.api.close_panel) {
            window.pywebview.api.close_panel();
            return;
          }
        }
        window.close();
        return;
      }
      if (document.fullscreenElement) {
        if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
      }
      document.removeEventListener("fullscreenchange", onFsChange);
      document.removeEventListener("webkitfullscreenchange", onFsChange);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("resize", resizeCanvas);
      el.remove();
    };

    el.querySelector(".ssv-close").addEventListener("click", closeViewerAction);

    if (typeof screensaverWakeOnEvent === "function") screensaverWakeOnEvent();
  }

  function confirmLibraryDelete(filename, label) {
    if (!confirm(`Delete this ${label}? This cannot be undone.`)) return;
    apiFetch(`${API_BASE}/api/library/delete/${encodeURIComponent(filename)}`, { method: "POST" })
      .then(() => {
        libraryItems = libraryItems.filter(i => i.filename !== filename);
        populateLibraryFilter();
        renderLibraryItems();
      })
      .catch(() => alert("Delete failed."));
  }

  // ── Notepad Modal (Fixed 400x500, exact Edit Action Modal styling) ────────

  function openNotepad(filename, defaultApp, forceLocal = false, initialTitle = "", initialBody = "") {
    if (!forceLocal && !document.body.classList.contains("standalone-notepad-mode") && (IS_APP || !IS_MOBILE)) {
      apiFetch(`${API_BASE}/api/notepad/open?file=${encodeURIComponent(filename || "")}&app=${encodeURIComponent(defaultApp || "")}&title=${encodeURIComponent(initialTitle || "")}&body=${encodeURIComponent(initialBody || "")}`)
        .catch(() => openNotepad(filename, defaultApp, true, initialTitle, initialBody));
      return;
    }

    const existing = document.getElementById("iris-notepad");
    if (existing) existing.remove();

    const noteApp = (defaultApp || (libraryFilter !== "all" ? libraryFilter : "general")).trim() || "general";

    const el = document.createElement("div");
    el.id = "iris-notepad";
    el.innerHTML = `
      <div class="panel-modal panel-notepad-modal">
        <div class="notepad-modal-header">
          <div>
            <h3>${filename ? 'Edit Note' : 'New Note'}</h3>
            <span class="notepad-modal-subtitle">${filename ? esc(filename) : 'Iris Desktop Note'}</span>
          </div>
          <button type="button" class="notepad-modal-close" id="notepad-close-btn" aria-label="Close">✕</button>
        </div>
        <div class="notepad-modal-body">
          <div class="settings-control" style="padding:0;">
            <label class="settings-label">Title</label>
            <input type="text" class="settings-input" id="notepad-title" placeholder="Note title…" autocomplete="off">
          </div>
          <div class="settings-control" style="padding:0; flex:1 1 auto; display:flex; flex-direction:column; min-height:0;">
            <label class="settings-label">Note</label>
            <textarea class="settings-input panel-notepad-textarea" id="notepad-body" placeholder="Write your note here…" spellcheck="true"></textarea>
          </div>
        </div>
        <div class="notepad-modal-actions">
          <span id="notepad-status-msg" style="font-size:11px; color:var(--fg-dim);"></span>
          <div style="display:flex; gap:8px;">
            <button type="button" class="settings-btn" id="notepad-cancel">Cancel</button>
            <button type="button" class="settings-btn settings-btn-primary" id="notepad-save">Save</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(el);

    const titleEl = document.getElementById("notepad-title");
    const bodyEl = document.getElementById("notepad-body");
    const statusEl = document.getElementById("notepad-status-msg");
    const closeBtn = document.getElementById("notepad-close-btn");
    const cancelBtn = document.getElementById("notepad-cancel");
    const saveBtn = document.getElementById("notepad-save");

    let currentApp = noteApp;

    if (filename) {
      apiFetch(`${API_BASE}/api/library/note/${encodeURIComponent(filename)}`)
        .then(r => r.json())
        .then(data => {
          titleEl.value = data.title || "";
          currentApp = data.app || noteApp;
          bodyEl.value = data.content || "";
          bodyEl.focus();
        }).catch(() => {});
    } else {
      if (initialTitle) titleEl.value = initialTitle;
      if (initialBody) {
        bodyEl.value = initialBody;
      }
      setTimeout(() => {
        if (bodyEl && initialBody) {
          bodyEl.focus();
          bodyEl.setSelectionRange(bodyEl.value.length, bodyEl.value.length);
        } else if (titleEl) {
          titleEl.focus();
        }
      }, 50);
    }

    function closeNotepad() {
      if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.close_window === "function") {
        window.pywebview.api.close_window();
        return;
      }
      if (document.body.classList.contains("standalone-notepad-mode")) {
        window.close();
        return;
      }
      if (el && el.parentNode) el.remove();
    }

    if (closeBtn) closeBtn.addEventListener("click", closeNotepad);
    if (cancelBtn) cancelBtn.addEventListener("click", closeNotepad);

    el.addEventListener("click", (e) => {
      if (e.target === el) closeNotepad();
    });

    el.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeNotepad();
      } else if (e.key === "s" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        saveNote(false);
      }
    });

    async function saveNote(closeOnSave = true) {
      const payload = {
        title: titleEl.value.trim(),
        app: currentApp || "general",
        content: bodyEl.value,
        filename: filename || ""
      };
      try {
        const r = await apiFetch(`${API_BASE}/api/library/note`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await r.json();
        if (data.ok) {
          if (statusEl) {
            statusEl.textContent = "✓ Saved to Library";
            statusEl.style.color = "var(--neon-text, #48B2E9)";
          }
          if (closeOnSave) {
            setTimeout(closeNotepad, 150);
          }
          if (currentPage === "library") {
            fetchLibraryItems();
          }
        }
      } catch (e) {
        if (statusEl) {
          statusEl.textContent = "Save failed";
          statusEl.style.color = "#ff5555";
        }
      }
    }

    if (saveBtn) {
      saveBtn.addEventListener("click", () => saveNote(true));
    }
  }

  function renderNotifications() {
    main.innerHTML = `
      <header>
        <div class="header-left">
          <button class="hamburger" id="hamburger" aria-label="Menu">
            <span class="material-icons-outlined">menu</span>
          </button>
          <div>
            <h1>Notifications</h1>
          </div>
        </div>
        <button class="done-btn" id="done-btn">Done</button>
      </header>
      <section class="content notif-content">
        <div class="notif-page-wrap">
          <div class="notif-top-bar">
            <div class="notif-tab-group">
              <button class="notif-tab-btn ${notifTab === 'inbox' ? 'active' : ''}" id="notif-tab-inbox">
                <span class="material-icons-outlined" style="font-size:18px;">inbox</span>
                Inbox
                <span class="notif-count-pill" id="notif-inbox-count">${(notifData.notifications || []).length}</span>
              </button>
              <button class="notif-tab-btn ${notifTab === 'archived' ? 'active' : ''}" id="notif-tab-archived">
                <span class="material-icons-outlined" style="font-size:18px;">archive</span>
                Archive
                <span class="notif-count-pill" id="notif-archived-count">${(notifData.archived || []).length}</span>
              </button>
            </div>
            <div class="notif-actions-group">
              <button class="notif-tool-btn" id="notif-archive-all-btn" title="Archive all inbox notifications">
                <span class="material-icons-outlined" style="font-size:16px;">archive</span> Archive All
              </button>
              <button class="notif-tool-btn danger" id="notif-clear-all-btn" title="Clear notifications">
                <span class="material-icons-outlined" style="font-size:16px;">delete_sweep</span> Clear
              </button>
              <button class="notif-tool-btn" id="notif-settings-btn" title="Anti-spam & storage settings">
                <span class="material-icons-outlined" style="font-size:16px;">tune</span> Rules &amp; Storage
              </button>
            </div>
          </div>
          <div class="notif-cards-list" id="notif-cards-container"></div>
        </div>
      </section>`;

    rebindHamburger();
    wireNotificationsEvents();
    renderNotificationsList();
    fetchNotifications();
  }

  function wireNotificationsEvents() {
    const inboxTab = document.getElementById("notif-tab-inbox");
    const archTab = document.getElementById("notif-tab-archived");
    if (inboxTab) {
      inboxTab.addEventListener("click", () => {
        notifTab = "inbox";
        inboxTab.classList.add("active");
        if (archTab) archTab.classList.remove("active");
        renderNotificationsList();
      });
    }
    if (archTab) {
      archTab.addEventListener("click", () => {
        notifTab = "archived";
        archTab.classList.add("active");
        if (inboxTab) inboxTab.classList.remove("active");
        renderNotificationsList();
      });
    }

    const archAllBtn = document.getElementById("notif-archive-all-btn");
    if (archAllBtn) {
      archAllBtn.addEventListener("click", async () => {
        await apiFetch(`${API_BASE}/api/notifications/archive-all`, { method: "POST" });
        fetchNotifications();
      });
    }

    const clearAllBtn = document.getElementById("notif-clear-all-btn");
    if (clearAllBtn) {
      clearAllBtn.addEventListener("click", async () => {
        const isArch = notifTab === "archived";
        if (confirm(`Clear all ${isArch ? "archived" : "inbox"} notifications?`)) {
          await apiFetch(`${API_BASE}/api/notifications/clear`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ include_archived: isArch })
          });
          fetchNotifications();
        }
      });
    }

    const settingsBtn = document.getElementById("notif-settings-btn");
    if (settingsBtn) {
      settingsBtn.addEventListener("click", () => {
        showNotificationSettingsModal();
      });
    }
  }

  function renderNotificationsList() {
    const container = document.getElementById("notif-cards-container");
    if (!container) return;

    const inboxCountEl = document.getElementById("notif-inbox-count");
    const archCountEl = document.getElementById("notif-archived-count");
    if (inboxCountEl) inboxCountEl.textContent = (notifData.notifications || []).length;
    if (archCountEl) archCountEl.textContent = (notifData.archived || []).length;

    const items = notifTab === "archived" ? (notifData.archived || []) : (notifData.notifications || []);
    const notifSig = notifTab + ":" + items.map((n) => (n.id || "") + ":" + (n.timestamp || 0) + ":" + (n.archived ? 1 : 0)).join(";");

    if (container.getAttribute("data-sig") === notifSig) {
      // Just update relative timestamps without touching DOM structure or listeners
      const timeEls = container.querySelectorAll(".notif-card-time");
      timeEls.forEach((el, i) => {
        if (items[i]) el.textContent = formatRelativeTime(items[i].timestamp);
      });
      return;
    }
    container.setAttribute("data-sig", notifSig);

    if (!items.length) {
      container.innerHTML = `
        <div class="notif-empty-state">
          <span class="material-icons-outlined">${notifTab === 'archived' ? 'inventory_2' : 'notifications_none'}</span>
          <div style="font-size:14px; font-weight:600; color:#fff;">
            No ${notifTab === 'archived' ? 'archived' : 'inbox'} notifications
          </div>
          <div style="font-size:12px;">Incoming persistent alerts and toasts will appear here.</div>
        </div>`;
      return;
    }

    const rules = notifData.rules || {};
    container.innerHTML = items.map((n) => {
      const appName = esc(n.app || "System");
      const rule = rules[n.app] || "normal";
      let ruleBadge = "";
      if (rule === "demote_to_events") {
        ruleBadge = `<span class="notif-card-rule-badge">Events Only</span>`;
      } else if (rule === "muted") {
        ruleBadge = `<span class="notif-card-rule-badge" style="color:#f87171; border-color:rgba(239,68,68,0.3);">Muted</span>`;
      }
      return `
        <div class="notif-item-card ${n.archived ? 'is-archived' : ''}" data-id="${esc(n.id)}">
          <div class="notif-card-top">
            <div class="notif-card-source-wrap">
              <span class="notif-card-app">${appName}</span>
              ${ruleBadge}
              <span class="notif-card-time">${formatRelativeTime(n.timestamp)}</span>
            </div>
            <div class="notif-card-ctrls">
              <button class="notif-icon-btn notif-toggle-archive" data-id="${esc(n.id)}" data-archived="${n.archived ? '1' : '0'}" title="${n.archived ? 'Restore to inbox' : 'Archive'}">
                <span class="material-icons-outlined" style="font-size:17px;">${n.archived ? 'unarchive' : 'archive'}</span>
              </button>
              <button class="notif-icon-btn delete notif-delete-btn" data-id="${esc(n.id)}" title="Delete">
                <span class="material-icons-outlined" style="font-size:17px;">delete_outline</span>
              </button>
            </div>
          </div>
          ${n.title ? `<div class="notif-card-title">${linkifyText(n.title)}</div>` : ''}
          ${n.body ? `<div class="notif-card-body">${linkifyText(n.body)}</div>` : ''}
        </div>`;
    }).join("");

    container.querySelectorAll(".notif-toggle-archive").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        const wasArch = btn.getAttribute("data-archived") === "1";
        await apiFetch(`${API_BASE}/api/notifications/archive`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: id, archived: !wasArch })
        });
        fetchNotifications();
      });
    });

    container.querySelectorAll(".notif-delete-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        await apiFetch(`${API_BASE}/api/notifications/delete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: id })
        });
        fetchNotifications();
      });
    });
  }

  function showNotificationSettingsModal() {
    let existingModal = document.getElementById("notif-settings-modal");
    if (existingModal) existingModal.remove();

    const maxLimit = notifData.max_stored || 50;
    const rules = notifData.rules || {};
    const sources = notifData.sources || [];

    const sourcesHtml = sources.length ? sources.map((src) => {
      const curRule = rules[src] || "normal";
      return `
        <tr>
          <td><strong style="color:#ffffff;">${esc(src)}</strong></td>
          <td>
            <select class="notif-rule-select" data-source="${esc(src)}">
              <option value="normal" ${curRule === 'normal' ? 'selected' : ''}>Normal (Stored &amp; Persist)</option>
              <option value="demote_to_events" ${curRule === 'demote_to_events' ? 'selected' : ''}>Demote to Events (5s Transient)</option>
              <option value="muted" ${curRule === 'muted' ? 'selected' : ''}>Muted (Suppress All)</option>
            </select>
          </td>
        </tr>`;
    }).join("") : `<tr><td colspan="2" style="color:var(--fg-dim); text-align:center; padding:12px;">No notification sources recorded yet</td></tr>`;

    const backdrop = document.createElement("div");
    backdrop.id = "notif-settings-modal";
    backdrop.className = "panel-modal-backdrop";
    backdrop.innerHTML = `
      <div class="panel-modal panel-modal-wide" style="max-width:580px;" onclick="event.stopPropagation();">
        <div class="panel-modal-header" style="display:flex; flex-direction:row; align-items:center; justify-content:space-between;">
          <div>
            <h3>Notification Storage &amp; Anti-Spam Rules</h3>
            <div class="panel-modal-subtitle">Configure message storage limits and filter noisy plugins</div>
          </div>
          <button class="settings-btn secondary" id="notif-modal-close" style="padding:4px 8px; font-size:16px;">&times;</button>
        </div>
        <div style="display:flex; flex-direction:column; gap:16px; padding:10px 0;">
          <div>
            <label class="settings-label" style="font-weight:700; margin-bottom:6px; display:block;">Max Stored Notifications</label>
            <div style="display:flex; align-items:center; gap:12px;">
              <input type="range" id="notif-limit-slider" min="10" max="200" step="5" value="${maxLimit}" style="flex:1; accent-color:var(--neon);">
              <span id="notif-limit-val" style="font-weight:700; width:45px; text-align:right; color:var(--neon);">${maxLimit}</span>
            </div>
            <div class="settings-hint" style="font-size:11px; color:var(--fg-dim); margin-top:4px;">Older notifications in inbox will be automatically trimmed when limit is exceeded.</div>
          </div>
          <div>
            <label class="settings-label" style="font-weight:700; margin-bottom:6px; display:block;">Anti-Spam Source Rules</label>
            <div class="settings-hint" style="font-size:11px; color:var(--fg-dim); margin-bottom:8px;">If an app or plugin produces excessive notifications, you can demote it to 5-second transient events or mute it entirely.</div>
            <table class="notif-rules-table">
              <thead>
                <tr><th>Source Application / Plugin</th><th>Behavior Rule</th></tr>
              </thead>
              <tbody>${sourcesHtml}</tbody>
            </table>
          </div>
        </div>
        <div class="panel-modal-actions">
          <button class="settings-btn secondary" id="notif-modal-cancel">Cancel</button>
          <button class="settings-btn primary" id="notif-modal-save">Save Settings</button>
        </div>
      </div>`;

    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) {
        backdrop.remove();
      }
    });
    const dialogCard = backdrop.querySelector(".panel-modal");
    if (dialogCard) {
      dialogCard.addEventListener("click", (e) => e.stopPropagation());
    }
    document.body.appendChild(backdrop);

    const slider = document.getElementById("notif-limit-slider");
    const valLabel = document.getElementById("notif-limit-val");
    if (slider && valLabel) {
      slider.addEventListener("input", () => {
        valLabel.textContent = slider.value;
      });
    }

    const closeModal = () => backdrop.remove();
    document.getElementById("notif-modal-close").addEventListener("click", closeModal);
    document.getElementById("notif-modal-cancel").addEventListener("click", closeModal);

    document.getElementById("notif-modal-save").addEventListener("click", async () => {
      const newLimit = parseInt(slider.value, 10);
      await apiFetch(`${API_BASE}/api/notifications/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_stored: newLimit })
      });

      const selectEls = backdrop.querySelectorAll(".notif-rule-select");
      for (const sel of selectEls) {
        const src = sel.getAttribute("data-source");
        const rule = sel.value;
        await apiFetch(`${API_BASE}/api/notifications/rule`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source: src, rule: rule })
        });
      }

      closeModal();
      fetchNotifications();
    });
  }

  // ── Vision wizard ────────────────────────────────────────────

  function renderVisionWizard() {
    const d = visionDraft || defaultDraft();
    const editing = !!d.id;
    main.innerHTML = `
      <header>
        <div class="header-left">
          <button class="hamburger" id="hamburger" aria-label="Menu">
            <span class="material-icons-outlined">menu</span>
          </button>
          <div>
            <h1>${editing ? "Edit Sensor" : "New Sensor"}</h1>
          </div>
        </div>
        <div class="header-actions">
          ${editing ? '<button class="settings-btn" id="wizard-save-btn">Save Sensor</button>' : ""}
          <button class="done-btn" id="wizard-cancel-btn">Cancel</button>
        </div>
      </header>
      <section class="content vision-content vision-wizard-content">
        ${editing ? renderVisionEditPane() : `
        <div class="vision-stepper">
          ${VISION_WIZARD_STEPS.map((label, i) => `
            <div class="vision-step ${i + 1 <= wizardStep ? "done" : ""} ${i + 1 === wizardStep ? "active" : ""}"
                 data-step="${i + 1}" ${i + 1 < wizardStep ? 'style="cursor:pointer"' : ""}>
              <span class="vision-step-num">${i + 1}</span>
              <span class="vision-step-label">${label}</span>
            </div>`).join("")}
        </div>
        <div class="vision-wizard-body">
          ${renderWizardStep1()}
          ${renderWizardStep2()}
          ${renderWizardStep3()}
          ${renderWizardStep4()}
          ${renderWizardStep5()}
        </div>`}
      </section>`;
    rebindHamburger();
    wireWizard();
  }

  function renderVisionEditPane() {
    const d = visionDraft || defaultDraft();
    return `
      <div class="vision-wizard-body">
        <div class="vision-wizard-pane" id="pane-5">
          <h3>Test &amp; Configure</h3>
          <p>Live reading — ${esc(d.exe || "any app")} must be running to sample.</p>
          <div class="vision-test-readout" id="vision-test-readout">—</div>
          <div class="vision-test-sub" id="vision-test-sub"></div>
          <div class="vision-test-status" id="vision-test-status">Waiting…</div>
          ${renderVisionConfigForm()}
        </div>
      </div>`;
  }

  function renderVisionConfigForm() {
    const d = visionDraft || defaultDraft();
    const isOcrText = d.mode === "ocr_text";
    const isOcrNum = d.mode === "ocr_number";
    const isOcr = isOcrText || isOcrNum;

    return `
      <div class="vision-wizard-form">
        <div class="settings-control">
          <label class="settings-label">Sensor Name</label>
          <input type="text" class="settings-input" id="wz-name" value="${esc(d.name || "")}">
        </div>
        <div class="settings-control">
          <label class="settings-label">Event Message</label>
          <input type="text" class="settings-input" id="wz-event-msg" value="${esc(d.event_message || "")}" placeholder="Optional: {value} replaces with reading">
        </div>
        <div class="settings-control" style="grid-column:1 / -1">
          <label class="settings-label">Detection Mode</label>
          <select class="settings-select" id="wz-mode">
            ${Object.keys(VISION_MODES).map((m) =>
              `<option value="${m}" ${m === d.mode ? "selected" : ""}>${VISION_MODES[m]}</option>`).join("")}
          </select>
        </div>

        ${isOcrText ? `
        <div class="settings-control" style="grid-column:1 / -1">
          <label class="settings-label">Target Text / Pattern</label>
          <input type="text" class="settings-input" id="wz-ocr-pattern" value="${esc(d.ocr_pattern || "")}" placeholder="e.g. WARNING, LOW OXYGEN, or Regex">
        </div>
        <div class="settings-control">
          <label class="settings-label">Match Type</label>
          <select class="settings-select" id="wz-ocr-match-type">
            <option value="contains" ${d.ocr_match_type !== "exact" && d.ocr_match_type !== "regex" ? "selected" : ""}>Contains Text</option>
            <option value="exact" ${d.ocr_match_type === "exact" ? "selected" : ""}>Exact Match</option>
            <option value="regex" ${d.ocr_match_type === "regex" ? "selected" : ""}>Regular Expression</option>
          </select>
        </div>
        <div class="settings-toggle-row">
          <span class="settings-toggle-label">Case Sensitive</span>
          <div class="settings-toggle ${d.ocr_case_sensitive ? "on" : ""}" id="wz-ocr-case"><div class="settings-toggle-thumb"></div></div>
        </div>
        ` : ""}

        ${isOcrNum ? `
        <div class="settings-control">
          <label class="settings-label">Condition</label>
          <select class="settings-select" id="wz-direction">
            <option value="below" ${d.direction === "below" ? "selected" : ""}>Below Threshold (&lt;)</option>
            <option value="above" ${d.direction === "above" ? "selected" : ""}>Above Threshold (&gt;)</option>
            <option value="equal" ${d.direction === "equal" ? "selected" : ""}>Equal to (==)</option>
          </select>
        </div>
        <div class="settings-control">
          <label class="settings-label">Threshold Value</label>
          <input type="number" class="settings-input" id="wz-threshold" value="${esc(String(d.threshold))}" step="0.1">
        </div>
        ` : ""}

        ${!isOcr ? `
        <div class="settings-control">
          <label class="settings-label">Colour</label>
          <div class="vision-color-row">
            <button type="button" class="settings-btn vision-recapture-btn" id="wz-recapture" title="Recapture screen region">
              <span class="material-icons-outlined">center_focus_strong</span>
            </button>
            <input type="color" class="settings-color" id="wz-color" value="${esc(d.color || "#ff0000")}">
            <input type="text" class="settings-input" id="wz-color-hex" value="${esc(d.color || "#ff0000")}" spellcheck="false">
          </div>
        </div>
        <div class="settings-control">
          <label class="settings-label">Tolerance (0-255)</label>
          <input type="number" class="settings-input" id="wz-tolerance" value="${esc(String(d.tolerance))}" min="0" max="255">
        </div>
        <div class="settings-control">
          <label class="settings-label">Threshold ${d.mode === "average_brightness" ? "(0-255)" : "(%)"}</label>
          <input type="number" class="settings-input" id="wz-threshold" value="${esc(String(d.threshold))}" step="0.1">
        </div>
        <div class="settings-control">
          <label class="settings-label">Direction</label>
          <select class="settings-select" id="wz-direction">
            <option value="below" ${d.direction !== "above" ? "selected" : ""}>Below threshold</option>
            <option value="above" ${d.direction === "above" ? "selected" : ""}>Above threshold</option>
          </select>
        </div>
        ` : ""}

        <div class="settings-control">
          <label class="settings-label">Poll Rate (Hz)</label>
          <input type="number" class="settings-input" id="wz-poll-rate" value="${esc(String(d.poll_rate))}" min="0.1" max="10" step="0.1">
        </div>
        <div class="settings-control">
          <label class="settings-label">Cooldown (seconds)</label>
          <input type="number" class="settings-input" id="wz-cooldown" value="${esc(String(d.cooldown_s))}" min="0" step="1">
        </div>
        <div class="settings-toggle-row">
          <span class="settings-toggle-label">Hardware Display</span>
          <div class="settings-toggle ${d.output_display ? "on" : ""}" id="wz-output"><div class="settings-toggle-thumb"></div></div>
        </div>
        <div class="settings-toggle-row">
          <span class="settings-toggle-label">Flash name</span>
          <div class="settings-toggle ${d.flash_name ? "on" : ""}" id="wz-flash-name" title="Persistently flash the first 4 letters of the sensor name while the threshold is met"><div class="settings-toggle-thumb"></div></div>
        </div>
        <div class="settings-toggle-row">
          <span class="settings-toggle-label">Play Sound</span>
          <div class="settings-toggle ${d.play_sound ? "on" : ""}" id="wz-play-sound" title="Play notification sound once when triggered"><div class="settings-toggle-thumb"></div></div>
        </div>
        <div class="settings-toggle-row">
          <span class="settings-toggle-label">Only when focused</span>
          <div class="settings-toggle ${d.require_foreground ? "on" : ""}" id="wz-require-fg" title="Only measure while the target app is the foreground window. Ignores background/menu windows."><div class="settings-toggle-thumb"></div></div>
        </div>
      </div>`;
  }

  function renderWizardStep1() {
    if (wizardStep !== 1) return "";
    return `
      <div class="vision-wizard-pane" id="pane-1">
        <h3>1. Capture Region</h3>
        <p>Press capture, then drag a rectangle over the area of your screen to monitor.
        The panel hides while you drag.</p>
        <button class="settings-btn vision-capture-btn" id="capture-btn">
          <span class="material-icons-outlined">center_focus_strong</span> Capture Region
        </button>
        <div class="vision-capture-status" id="capture-status"></div>
      </div>`;
  }

  function renderWizardStep2() {
    if (wizardStep !== 2 || !wizardCapture || !wizardCapture.screenshot_b64) return "";
    const d = visionDraft || defaultDraft();
    const isOcr = d.mode === "ocr_text" || d.mode === "ocr_number";
    const detectedText = wizardCapture.detected_text || "";
    const words = wizardCapture.words || [];

    return `
      <div class="vision-wizard-pane" id="pane-2">
        <h3>2. Detection Mode &amp; Sampling</h3>
        <p>Choose what to watch for in this captured region.</p>
        
        <div class="vision-mode-tabs">
          <button type="button" class="vision-mode-tab ${!isOcr ? "active" : ""}" data-mode-cat="pixel">
            <span class="material-icons-outlined">palette</span> Colour / Pixel
          </button>
          <button type="button" class="vision-mode-tab ${d.mode === "ocr_text" ? "active" : ""}" data-mode-cat="ocr_text">
            <span class="material-icons-outlined">text_fields</span> Text Match (OCR)
          </button>
          <button type="button" class="vision-mode-tab ${d.mode === "ocr_number" ? "active" : ""}" data-mode-cat="ocr_number">
            <span class="material-icons-outlined">pin</span> Number (OCR)
          </button>
        </div>

        ${!isOcr ? `
        <p>Click on the preview to sample the colour to watch for.
        <span class="vision-swatch" id="vision-swatch" style="background:${esc(visionDraft.color)}"></span>
        <span id="vision-color-hex">${esc(visionDraft.color)}</span></p>
        <canvas id="vision-preview-canvas" class="vision-preview-canvas"></canvas>
        ` : `
        <div class="ocr-detected-box">
          <div class="ocr-detected-label">Recognized Text</div>
          <div class="ocr-detected-row">
            <div class="ocr-detected-text" id="ocr-detected-text" title="${esc(detectedText)}">${esc(detectedText || "No text detected in this crop")}</div>
            <button type="button" class="settings-btn ocr-copy-btn" id="ocr-copy-btn" title="Copy recognized text">
              <span class="material-icons-outlined">content_copy</span>
            </button>
          </div>
          ${words.length ? `
          <div class="ocr-detected-label">Click a word to set target pattern:</div>
          <div class="ocr-words-list" style="margin-bottom:12px;">
            ${words.map(w => `<button type="button" class="ocr-word-chip ${visionDraft.ocr_pattern === w.text ? "selected" : ""}" data-word="${esc(w.text)}">${esc(w.text)}</button>`).join("")}
          </div>
          ` : ""}
          <div class="settings-control" style="margin-top:8px;">
            <label class="settings-label">${d.mode === "ocr_text" ? "Target Text / Keyword" : "Target Number / Filter"}</label>
            <input type="text" class="settings-input" id="wz-step2-pattern" value="${esc(visionDraft.ocr_pattern || (d.mode === 'ocr_text' ? detectedText : ''))}" placeholder="e.g. WARNING, LOW OXYGEN, or number">
          </div>
        </div>
        <img src="data:image/png;base64,${wizardCapture.screenshot_b64}" class="vision-preview-canvas" style="object-fit:contain;" alt="Crop Preview">
        `}

        <div class="vision-wizard-nav">
          <button class="settings-btn" id="wizard-back-btn">Back</button>
          <button class="settings-btn" id="wizard-next-btn">Continue</button>
        </div>
      </div>`;
  }

  function renderWizardStep3() {
    if (wizardStep !== 3) return "";
    return `
      <div class="vision-wizard-pane" id="pane-3">
        <h3>3. Target App</h3>
        <p>Sensor only runs while this app is open. Detected automatically from the region.</p>
        <div class="settings-control">
          <label class="settings-label">Executable</label>
          <input type="text" class="settings-input" id="wizard-exe" value="${esc(visionDraft.exe || "")}" placeholder="AppName.exe">
        </div>
        <div class="vision-wizard-nav">
          <button class="settings-btn" id="wizard-back-btn">Back</button>
          <button class="settings-btn" id="wizard-next-btn">Continue</button>
        </div>
      </div>`;
  }

  function renderWizardStep4() {
    if (wizardStep !== 4) return "";
    return `
      <div class="vision-wizard-pane" id="pane-4">
        <h3>4. Configure</h3>
        ${renderVisionConfigForm()}
        <div class="vision-wizard-nav">
          <button class="settings-btn" id="wizard-back-btn">Back</button>
          <button class="settings-btn" id="wizard-next-btn">Continue</button>
        </div>
      </div>`;
  }

  function renderWizardStep5() {
    if (wizardStep !== 5) return "";
    return `
      <div class="vision-wizard-pane" id="pane-5">
        <h3>5. Test</h3>
        <p>Live reading — ${esc(visionDraft.exe || "any app")} must be running to sample.</p>
        <div class="vision-test-readout" id="vision-test-readout">—</div>
        <div class="vision-test-sub" id="vision-test-sub"></div>
        <div class="vision-test-status" id="vision-test-status">Waiting…</div>
        <div class="vision-wizard-nav">
          <button class="settings-btn" id="wizard-back-btn">Back</button>
          <button class="settings-btn" id="wizard-save-btn">Save Sensor</button>
        </div>
      </div>`;
  }

  function testDraftBody() {
    const d = visionDraft;
    const body = Object.assign({}, d);
    if (!body.anchor || !body.region) {
      delete body.anchor;
      delete body.region;
    }
    return body;
  }

  function startTestPoll() {
    stopTestPoll();
    testTimer = setInterval(() => {
      apiFetch(`${API_BASE}/api/vision/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(testDraftBody()),
      })
        .then((r) => r.json())
        .then((data) => {
          const el = document.getElementById("vision-test-readout");
          const sub = document.getElementById("vision-test-sub");
          const st = document.getElementById("vision-test-status");
          if (el) {
            const isOcr = data.mode === "ocr_text" || data.mode === "ocr_number";
            if (isOcr) el.classList.remove("is-num");
            else el.classList.add("is-num");

            const valStr = data.value !== null && data.value !== undefined ? String(data.value) : "—";
            el.textContent = valStr;
            el.title = valStr;
            el.style.color = data.active ? "#ffffff" : "var(--fg-dim)";
          }
          if (sub) {
            if (data.mode === "ocr_text" || data.mode === "ocr_number") {
              sub.textContent = data.text ? `Extracted: "${data.text}"` : "";
              sub.title = data.text ? `Extracted: "${data.text}"` : "";
            } else {
              sub.textContent = "";
            }
          }
          if (st) {
            st.textContent = data.active ? "Triggered" : "Not triggered";
            st.style.color = data.active ? "var(--neon-grn)" : "var(--fg-dim)";
            if (data.active) st.classList.add("triggered");
            else st.classList.remove("triggered");
          }
        })
        .catch(() => {});
    }, 500);
  }

  function stopTestPoll() {
    if (testTimer) { clearInterval(testTimer); testTimer = null; }
  }

  // ── Panel page (overlay customizer) ─────────────────────────

  let panelDraft = null;
  let panelDirty = false;
  let panelActions = [];
  let panelEdit = null; // { scope:'board'|'utility', index, path: number[] }
  let panelProfileSel = "__default__"; // profile id being edited; "__default__" = main board
  let panelProfileModal = false;       // profile settings dialog open
  let panelViewMode = false;   // true = live device screen shown
  let portalAutoPanel = false; // web portal boot: open live panel instead of dashboard
  let panelLive = null;        // cached GET /api/panel/live
  let panelLiveTimer = null;
  let panelNav = [];           // GROUP nav stack in panel view
  let panelViewSig = "";
  let panelSaveTimer = null;
  let panelSliderTimer = null;
  let mdiCache = {};           // mdi icon name -> unicode char (from /api/mdi/codepoints)
  let mdiFetched = {};         // icon names already requested from /api/mdi/codepoints

  function isLightColor(hex) {
    if (!hex || typeof hex !== "string" || !hex.startsWith("#")) return false;
    let h = hex.slice(1);
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    if (h.length !== 6) return false;
    const r = parseInt(h.slice(0, 2), 16) || 0;
    const g = parseInt(h.slice(2, 4), 16) || 0;
    const b = parseInt(h.slice(4, 6), 16) || 0;
    const yiq = (r * 299 + g * 587 + b * 114) / 1000;
    return yiq >= 150;
  }

  function mdiChar(name) {
    if (!name) return "";
    const key = name.toLowerCase().trim().replace("mdi:", "").replace("mdi-", "");
    if (mdiCache[key]) return mdiCache[key];
    if (mdiCache[name]) return mdiCache[name];
    return "";
  }

  function applyMdiIcons(root) {
    const scope = root || document;
    let elements = [];
    if (scope && scope.nodeType === 1) {
      if (scope.matches && scope.matches(".md[data-md]")) {
        elements.push(scope);
      }
      if (scope.querySelectorAll) {
        elements = elements.concat(Array.from(scope.querySelectorAll(".md[data-md]")));
      }
    } else if (scope && scope.querySelectorAll) {
      elements = Array.from(scope.querySelectorAll(".md[data-md]"));
    }
    elements.forEach((el) => {
      const code = mdiChar(el.getAttribute("data-md") || "");
      if (code) el.textContent = code;
    });
  }

  function mdiPreload(names) {
    const missing = (names || []).filter((n) => n && !mdiCache[n] && !mdiFetched[n]);
    if (!missing.length) return;
    missing.forEach((n) => { mdiFetched[n] = 1; });
    apiFetch(`${API_BASE}/api/mdi/codepoints?names=${encodeURIComponent(missing.join(","))}`)
      .then((r) => r.json())
      .then((map) => {
        if (!map) return;
        mdiCache = Object.assign({}, mdiCache, map);
        applyMdiIcons(document);
      })
      .catch(() => {
        missing.forEach((n) => { delete mdiFetched[n]; });
      });
  }

  let _fetchPanelBusy = false;
  function fetchPanel() {
    if (_fetchPanelBusy) {
      if (portalAutoPanel || panelViewMode) {
        portalAutoPanel = false;
        openPanelView();
      }
      return;
    }
    _fetchPanelBusy = true;
    fetchEntities();
    apiFetch(`${API_BASE}/api/panel`)
      .then((r) => r.json())
      .then((data) => {
        panelActions = data.actions || [];
        panelDraft = {
          panel_board: data.panel_board || [],
          panel_utility: data.panel_utility || [],
          panel_sliders: data.panel_sliders || [],
          panel_layout: data.panel_layout || [],
          panel_gauges: data.panel_gauges || { enabled: true },
          media_player_path: data.media_player_path || "",
          hardware_connected: !!data.hardware_connected,
          panel_profiles: data.panel_profiles || [],
        };
        panelDirty = false;
        panelEdit = null;
        if (portalAutoPanel || panelViewMode) {
          portalAutoPanel = false;
          openPanelView();
        } else {
          renderPanel();
        }
      })
      .catch(() => {
        panelDraft = panelDraft || {
          panel_board: [], panel_utility: [], panel_sliders: [],
          panel_layout: [], panel_gauges: { enabled: true }, media_player_path: "",
          panel_profiles: [],
        };
        if (portalAutoPanel || panelViewMode) {
          portalAutoPanel = false;
          openPanelView();
        } else {
          renderPanel();
        }
      })
      .finally(() => { _fetchPanelBusy = false; });
  }

  function savePanelLive() {
    clearTimeout(panelSaveTimer);
    panelSaveTimer = setTimeout(() => {
      if (!panelDraft) return;
      apiFetch(`${API_BASE}/api/panel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(panelDraft),
      }).catch(() => {});
    }, 250);
  }

  function setPanelDirty(on) {
    panelDirty = !!on;
    if (on) {
      panelViewSig = "";
      savePanelLive();
    }
  }

  function isComponentEnabled(component, target) {
    if (!component) return true;
    if (target === "desktop" || target === "local") {
      return component.local !== undefined ? component.local !== false : component.enabled !== false;
    }
    return component.remote !== undefined ? component.remote !== false : component.enabled !== false;
  }

  function layoutOn(id, target) {
    const list = (panelDraft && panelDraft.panel_layout) ? panelDraft.panel_layout : [];
    const row = list.find((x) => x.id === id);
    if (!row) return true;
    return isComponentEnabled(row, target);
  }

  function setLayoutTargetOn(id, target, on) {
    if (!panelDraft) return;
    if (!panelDraft.panel_layout) panelDraft.panel_layout = [];
    let row = panelDraft.panel_layout.find((x) => x.id === id);
    if (!row) {
      row = { id: id, enabled: true, local: true, remote: true };
      row[target] = !!on;
      row.enabled = !!(row.local || row.remote);
      panelDraft.panel_layout.push(row);
    } else {
      if (row.local === undefined) row.local = row.enabled !== false;
      if (row.remote === undefined) row.remote = row.enabled !== false;
      row[target] = !!on;
      row.enabled = !!(row.local || row.remote);
    }
    if (id === "gauges") {
      panelDraft.panel_gauges = panelDraft.panel_gauges || {};
      panelDraft.panel_gauges.enabled = row.enabled;
    }
    setPanelDirty(true);
    renderPanel();
  }

  function setLayoutOn(id, on) {
    if (!panelDraft) return;
    if (!panelDraft.panel_layout) panelDraft.panel_layout = [];
    let row = panelDraft.panel_layout.find((x) => x.id === id);
    if (!row) {
      row = { id: id, enabled: on, local: on, remote: on };
      panelDraft.panel_layout.push(row);
    } else {
      row.enabled = on;
      row.local = on;
      row.remote = on;
    }
    setPanelDirty(true);
    renderPanel();
  }

  function sliderOn(id) {
    const row = (panelDraft.panel_sliders || []).find((x) => x.id === id);
    return row ? row.enabled !== false : true;
  }

  function setSliderOn(id, on) {
    if (!panelDraft.panel_sliders) panelDraft.panel_sliders = [];
    let row = panelDraft.panel_sliders.find((x) => x.id === id);
    if (!row) {
      row = { id: id, enabled: on };
      panelDraft.panel_sliders.push(row);
    } else row.enabled = on;
    setPanelDirty(true);
    renderPanel();
  }

  function boardAtPath(path) {
    let list = panelProfileCurrent().board;
    for (let i = 0; i < path.length; i++) {
      const slot = list[path[i]];
      if (!slot) return [];
      if (!slot.children) slot.children = [];
      list = slot.children;
    }
    return list;
  }

  // ── Panel profiles ───────────────────────────────────────────

  function panelProfileCurrent() {
    const cfg = panelViewConfig();
    const list = (panelDraft && panelDraft.panel_profiles) || (cfg && cfg.panel_profiles) || [];
    let profile = null;
    if (panelProfileSel !== "__default__") {
      profile = list.find((x) => x.id === panelProfileSel) || null;
      if (!profile) panelProfileSel = "__default__";
    }
    let board = (panelDraft && panelDraft.panel_board) || (cfg && cfg.panel_board) || [];
    if (profile) {
      if (!Array.isArray(profile.board)) profile.board = [];
      board = profile.board;
    }
    return { board: board, profile: profile };
  }

  function uniqueProfileId() {
    const list = (panelDraft && panelDraft.panel_profiles) || [];
    const ids = {};
    list.forEach((x) => { ids[x.id] = 1; });
    let n = list.length + 1;
    while (ids["prof_" + n]) n++;
    return "prof_" + n;
  }

  function profileSelectHtml() {
    const list = (panelDraft && panelDraft.panel_profiles) || [];
    const isCustom = panelProfileSel !== "__default__" &&
      !!list.find((x) => x.id === panelProfileSel);
    let h = '<div class="panel-profile-row">' +
      '<select class="settings-select" id="panel-profile-sel">' +
      '<option value="__default__"' + (panelProfileSel === "__default__" ? " selected" : "") + '>Default Profile</option>';
    list.forEach((p) => {
      h += '<option value="' + esc(p.id) + '"' + (panelProfileSel === p.id ? " selected" : "") + '>' +
        esc(p.name || p.id) + '</option>';
    });
    h += '</select>' +
      '<button type="button" class="settings-btn" id="panel-profile-create" title="Create new profile">+ New</button>' +
      '<button type="button" class="settings-btn" id="panel-profile-clone" title="Duplicate current profile">Clone</button>' +
      '<button type="button" class="settings-btn" id="panel-profile-edit" title="Profile & Lighting settings">Settings</button>' +
      '<button type="button" class="settings-btn settings-btn-danger" id="panel-profile-quick-del"' + (isCustom ? "" : " disabled") + ' title="Delete profile">Delete</button>' +
      '</div>';
    return h;
  }

  let lightingProvidersData = [];

  async function fetchLightingStatus() {
    try {
      const res = await apiFetch(`${API_BASE}/api/lighting/status`);
      if (res.ok) {
        const data = await res.json();
        lightingProvidersData = data.providers || [];
      }
    } catch (_) {}
  }

  function renderProfileModal() {
    const isDef = (panelProfileSel === "__default__");
    let p = panelProfileCurrent().profile;
    if (isDef) {
      const list = (panelDraft && panelDraft.panel_profiles) || [];
      p = list.find((x) => x.id === "__default__") || { id: "__default__", name: "Default Profile", enabled: true, is_group: true };
    }
    if (!p) return "";
    const on = p.enabled !== false;
    const isGrp = isDef ? true : (p.is_group === true || (!p.exe && p.exe !== undefined));
    const pLighting = p.lighting || {};

    let lightingRowsHtml = "";
    if (lightingProvidersData.length > 0) {
      lightingProvidersData.forEach((prov) => {
        const pid = prov.id;
        const pName = prov.name || pid;
        const conf = pLighting[pid] || {};
        const presets = prov.presets || [];
        const isConnected = prov.connected;
        const statusBadge = isConnected
          ? '<span style="color:var(--neon-grn);font-size:11px;font-weight:600;">● Active</span>'
          : '<span style="color:var(--fg-dim);font-size:11px;">(Offline)</span>';

        if (prov.supports_day_off) {
          // Provider with Day / Night support (e.g. Home Assistant)
          const followDay = conf.follow_daylight !== false;
          const curDayPreset = conf.day_preset || "";
          const curNightPreset = conf.night_preset || conf.preset || "";

          lightingRowsHtml += '<div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:10px;">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">' +
              '<span class="settings-label" style="margin:0;font-weight:700;">' + esc(pName) + '</span>' +
              statusBadge +
            '</div>';

          if (!isDef) {
            lightingRowsHtml += '<div class="settings-control" style="margin-bottom:6px;">' +
              '<label class="settings-label" style="font-size:11px;">Active Preset</label>' +
              '<select class="settings-select prof-light-sel" data-prov="' + esc(pid) + '" data-field="preset">' +
                '<option value="inherit"' + (!conf.preset || conf.preset === "inherit" ? " selected" : "") + '>Inherit Default Baseline</option>';
            presets.forEach((pr) => {
              lightingRowsHtml += '<option value="' + esc(pr.id) + '"' + (conf.preset === pr.id ? " selected" : "") + '>' + esc(pr.name || pr.id) + '</option>';
            });
            lightingRowsHtml += '</select></div>';
          } else {
            lightingRowsHtml += '<div class="settings-toggle-row" style="margin-bottom:8px;">' +
              '<span class="settings-toggle-label" style="font-size:12px;">Observe Daylight Cycle</span>' +
              '<div class="settings-toggle prof-light-day-tog' + (followDay ? ' on' : '') + '" data-prov="' + esc(pid) + '"><div class="settings-toggle-thumb"></div></div>' +
            '</div>' +
            '<div class="settings-control" style="margin-bottom:6px;">' +
              '<label class="settings-label" style="font-size:11px;">Daytime Preset (07:30–19:30)</label>' +
              '<select class="settings-select prof-light-sel" data-prov="' + esc(pid) + '" data-field="day_preset">' +
                '<option value="">(None / No Action)</option>';
            presets.forEach((pr) => {
              lightingRowsHtml += '<option value="' + esc(pr.id) + '"' + (curDayPreset === pr.id ? " selected" : "") + '>' + esc(pr.name || pr.id) + '</option>';
            });
            lightingRowsHtml += '</select></div>' +
            '<div class="settings-control">' +
              '<label class="settings-label" style="font-size:11px;">Nighttime Preset (19:30–07:30)</label>' +
              '<select class="settings-select prof-light-sel" data-prov="' + esc(pid) + '" data-field="night_preset">' +
                '<option value="">(None / No Action)</option>';
            presets.forEach((pr) => {
              lightingRowsHtml += '<option value="' + esc(pr.id) + '"' + (curNightPreset === pr.id ? " selected" : "") + '>' + esc(pr.name || pr.id) + '</option>';
            });
            lightingRowsHtml += '</select></div>';
          }
          lightingRowsHtml += '</div>';
        } else {
          // Standard Provider (e.g. OpenRGB)
          const curPreset = conf.preset || "";
          lightingRowsHtml += '<div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:10px;">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">' +
              '<span class="settings-label" style="margin:0;font-weight:700;">' + esc(pName) + '</span>' +
              statusBadge +
            '</div>' +
            '<div class="settings-control">' +
              '<select class="settings-select prof-light-sel" data-prov="' + esc(pid) + '" data-field="preset">';
          if (!isDef) {
            lightingRowsHtml += '<option value="inherit"' + (!curPreset || curPreset === "inherit" ? " selected" : "") + '>Inherit Default Baseline</option>';
          } else {
            lightingRowsHtml += '<option value="">(None / No Action)</option>';
          }
          presets.forEach((pr) => {
            lightingRowsHtml += '<option value="' + esc(pr.id) + '"' + (curPreset === pr.id ? " selected" : "") + '>' + esc(pr.name || pr.id) + '</option>';
          });
          lightingRowsHtml += '</select></div></div>';
        }
      });
    } else {
      lightingRowsHtml = '<div style="font-size:12px;color:var(--fg-dim);padding:6px 0;">No lighting plugins active. Install OpenRGB or Home Assistant in Plugins.</div>';
    }

    return '<div class="panel-modal-backdrop" id="panel-profile-modal">' +
      '<div class="panel-modal" style="max-width:540px;">' +
      '<div class="panel-modal-header">' +
        '<h3>' + (isDef ? 'Default Profile & Lighting' : 'Profile Settings') + '</h3>' +
        '<span class="panel-modal-subtitle">' + (isDef ? 'Configure base ambient lighting and device defaults' : 'Configure focus switching and profile ambient overrides') + '</span>' +
      '</div>' +
      (!isDef ? ('<div class="settings-control"><label class="settings-label">Profile name</label>' +
      '<input type="text" class="settings-input" id="profile-name" value="' + esc(p.name || "") + '"></div>' +
      '<div class="settings-toggle-row" id="profile-group-row">' +
        '<span class="settings-toggle-label">Group Profile (No linked app)</span>' +
        '<div class="settings-toggle' + (isGrp ? " on" : "") + '" id="profile-group-tog"><div class="settings-toggle-thumb"></div></div>' +
      '</div>' +
      '<span class="settings-hint" style="margin-top:-4px; margin-bottom:6px;">Group profiles are activated by a panel button. App profiles switch on focus.</span>' +
      '<div class="settings-control" id="profile-exe-wrap">' +
        '<label class="settings-toggle-label" style="display:block; margin-bottom:6px;">App Executable</label>' +
        '<div class="settings-picker-row">' +
          '<input type="text" class="settings-input" id="profile-exe" placeholder="e.g. EliteDangerous64.exe" value="' + esc(p.exe || "") + '"' + (isGrp ? " disabled" : "") + '>' +
          '<button type="button" class="settings-btn" id="profile-pick"' + (isGrp ? " disabled" : "") + '>Pick\u2026</button>' +
        '</div>' +
      '</div>' +
      '<div class="settings-toggle-row' + (isGrp ? " disabled" : "") + '" id="profile-tog-row">' +
        '<span class="settings-toggle-label">Auto Switch on Focus</span>' +
        '<div class="settings-toggle' + (on ? " on" : "") + '" id="profile-tog"><div class="settings-toggle-thumb"></div></div>' +
      '</div>' +
      '<span class="settings-hint" style="margin-top:-4px; margin-bottom:6px;">Automatically switches to this profile when the application gains focus (with built-in anti-spam cooldown).</span>') : '') +
      '<div class="settings-control" style="margin-top:10px;border-top:1px solid var(--border);padding-top:10px;">' +
        '<label class="settings-label" style="display:block;margin-bottom:8px;font-size:12px;font-weight:700;color:var(--neon-text);">Ambient Lighting Presets</label>' +
        lightingRowsHtml +
      '</div>' +
      '<div class="panel-modal-actions">' +
      (!isDef ? '<button type="button" class="settings-btn settings-btn-danger" id="profile-delete">Delete</button>' : '') +
      '<div style="flex:1"></div>' +
      '<button type="button" class="settings-btn" id="profile-cancel">Cancel</button>' +
      '<button type="button" class="settings-btn settings-btn-primary" id="profile-save">Save Settings</button>' +
      '</div>' +
      '</div></div>';
  }

  function customConfirm(message, onYes) {
    const backdrop = document.createElement("div");
    backdrop.className = "panel-modal-backdrop";
    backdrop.innerHTML =
      '<div class="panel-modal panel-confirm-modal">' +
      '<h3>Delete</h3>' +
      '<p class="panel-confirm-msg">' + esc(message) + '</p>' +
      '<div class="panel-modal-actions">' +
      '<button type="button" class="settings-btn" id="confirm-cancel">Cancel</button>' +
      '<button type="button" class="settings-btn settings-btn-danger" id="confirm-ok">Delete</button>' +
      '</div>' +
      '</div>';
    document.body.appendChild(backdrop);
    const close = (ok) => {
      backdrop.remove();
      if (ok && onYes) onYes();
    };
    backdrop.addEventListener("click", (ev) => { if (ev.target === backdrop) close(false); });
    backdrop.querySelector("#confirm-cancel").addEventListener("click", () => close(false));
    backdrop.querySelector("#confirm-ok").addEventListener("click", () => close(true));
  }

  let panelPreviewPage = 0;
  let panelPreviewTarget = (typeof IS_APP !== "undefined" && IS_APP) || (typeof IS_MOBILE !== "undefined" && !IS_MOBILE) ? "desktop" : "remote";

  function actionLabel(type) {
    const a = panelActions.find((x) => x.type === type);
    return a ? a.label : type;
  }

  function renderPanel() {
    if (!panelDraft) {
      main.innerHTML =
        '<header>' +
          '<div class="header-left">' +
            '<button class="hamburger" id="hamburger" aria-label="Menu">' +
              '<span class="material-icons-outlined">menu</span>' +
            '</button>' +
            '<div><h1>Panel</h1></div>' +
          '</div>' +
        '</header>' +
        '<section class="settings-content"><p class="settings-placeholder">Loading…</p></section>';
      rebindHamburger();
      return;
    }
    const prevContentScroll = main.querySelector('.settings-content') ? main.querySelector('.settings-content').scrollTop : 0;
    const prevEditorScroll = main.querySelector('.panel-editor-col') ? main.querySelector('.panel-editor-col').scrollTop : 0;

    const hwOn = !!panelDraft.hardware_connected;
    const board = panelProfileCurrent().board;
    const util = panelDraft.panel_utility || [];
    const briOn = hwOn && sliderOn("brightness");

    const headerBtn = '<button class="done-btn" id="done-btn">Done</button>';

    const previewHtml = renderPhonePreviewHtml(panelDraft, panelLive, board, util);

    let html =
      '<header>' +
        '<div class="header-left">' +
          '<button class="hamburger" id="hamburger" aria-label="Menu">' +
            '<span class="material-icons-outlined">menu</span>' +
          '</button>' +
          '<div><h1>Panel Editor</h1></div>' +
        '</div>' +
        headerBtn +
      '</header>' +
      '<section class="settings-content panel-page">' +
        previewHtml +
        '<div class="panel-editor-col">' +
          // Gauges
          sectionCard("Gauges", "speed",
            targetToggleRow("Gauges", "gauges") +
            '<p class="settings-hint">PC stats: CPU · GPU · FPS</p>') +
          // Button box
          sectionCard("Button box", "apps",
            targetToggleRow("Button box", "button_box") +
            profileSelectHtml() +
            renderBoardEditor(board, [])) +
          // Sliders (brightness only when hardware is connected)
          sectionCard("Sliders", "tune",
            targetToggleRow("Sliders section", "sliders") +
            toggleRow("App volume", sliderOn("app_volume"), "panel-tog-vol") +
            toggleRow("Master volume", sliderOn("master_volume"), "panel-tog-mvol") +
            toggleRow("App mixer", sliderOn("app_mixer"), "panel-tog-mix") +
            (hwOn ? toggleRow("Display brightness", sliderOn("brightness"), "panel-tog-bri") : "")) +
          // Utility
          sectionCard("Utility row", "grid_view",
            targetToggleRow("Utility row", "utility") +
            renderUtilityEditor(util)) +
        '</div>' +
        (panelProfileModal ? renderProfileModal() : '') +
        (panelEdit ? renderActionModal() : '') +
      '</section>';

    main.innerHTML = html;
    rebindHamburger();
    wirePanelPage();
    paintPanelRanges(main);

    const newContent = main.querySelector('.settings-content');
    if (newContent && prevContentScroll) newContent.scrollTop = prevContentScroll;
    const newEditor = main.querySelector('.panel-editor-col');
    if (newEditor && prevEditorScroll) newEditor.scrollTop = prevEditorScroll;
  }

  function targetToggleRow(label, sectionId) {
    const locOn = layoutOn(sectionId, "local");
    const remOn = layoutOn(sectionId, "remote");
    return '<div class="panel-target-toggles">' +
      '<span class="settings-toggle-label">' + esc(label) + '</span>' +
      '<div class="panel-target-boxes">' +
        '<label class="panel-target-checkbox" for="panel-chk-' + esc(sectionId) + '-remote" title="Toggle visibility on Remote (Phone panel)">' +
          '<input type="checkbox" id="panel-chk-' + esc(sectionId) + '-remote" class="panel-target-chk" data-section="' + esc(sectionId) + '" data-target="remote"' + (remOn ? ' checked' : '') + '> Remote' +
        '</label>' +
        '<label class="panel-target-checkbox" for="panel-chk-' + esc(sectionId) + '-local" title="Toggle visibility on Local (Desktop Companion / Overlay)">' +
          '<input type="checkbox" id="panel-chk-' + esc(sectionId) + '-local" class="panel-target-chk" data-section="' + esc(sectionId) + '" data-target="local"' + (locOn ? ' checked' : '') + '> Local' +
        '</label>' +
      '</div>' +
    '</div>';
  }

  function sectionCard(title, icon, body) {
    return '<div class="settings-section"><h2 class="settings-section-title">' +
      '<span class="material-icons-outlined" style="font-size:18px;vertical-align:middle;margin-right:6px">' + icon + '</span>' +
      esc(title) + '</h2><div class="settings-card">' + body + '</div></div>';
  }

  function toggleRow(label, on, id) {
    return '<div class="settings-toggle-row">' +
      '<span class="settings-toggle-label">' + esc(label) + '</span>' +
      '<div class="settings-toggle' + (on ? ' on' : '') + '" id="' + id + '">' +
      '<div class="settings-toggle-thumb"></div></div></div>';
  }

  function previewGauge(label, value, max) {
    const v = (value === null || value === undefined) ? 0 : value;
    const pct = Math.max(0, Math.min(100, (v / max) * 100));
    return '<div class="prev-gauge" title="' + esc(label) + '">' +
      '<div class="prev-gring" style="--val:' + pct.toFixed(1) + '%;">' +
        '<span class="prev-gval">' + gaugeNum(v) + '</span>' +
      '</div>' +
    '</div>';
  }

  function panelSliderHtml(id, label, value, min, max) {
    const v = (value === null || value === undefined) ? 0 : value;
    return '<div class="pdev-slider prev-slider" data-slider="' + id + '">' +
      '<div class="pdev-slab">' +
        '<span class="pdev-sname">' + esc(label) + '</span>' +
      '</div>' +
      '<input type="range" class="pdev-range" data-slider="' + id + '" min="' + min + '" max="' + max + '" step="1" value="' + v + '" tabindex="-1" disabled>' +
    '</div>';
  }

  function renderPhonePreviewHtml(cfg, liveData, board, util) {
    const data = liveData || panelLive || {};
    const target = panelPreviewTarget || "desktop";
    const layout = {};
    ((cfg && cfg.panel_layout) || (panelDraft && panelDraft.panel_layout) || []).forEach((r) => {
      if (r && r.id) {
        layout[r.id] = isComponentEnabled(r, target);
      }
    });
    const gOn = layout.gauges !== false;
    const boxOn = layout.button_box !== false;
    const slidOn = layout.sliders !== false;
    const utilOn = layout.utility !== false;
    const sliders = {};
    ((cfg && cfg.panel_sliders) || (panelDraft && panelDraft.panel_sliders) || []).forEach((r) => { if (r && r.id) sliders[r.id] = r.enabled !== false; });
    const hw = !!(data.hardware_connected !== undefined ? data.hardware_connected
      : (panelDraft && panelDraft.hardware_connected));
    const briOn = hw && sliders.brightness !== false;
    const volOn = sliders.app_volume !== false;
    const mvolOn = sliders.master_volume !== false;
    const mixOn = sliders.app_mixer !== false;

    const gauges = data.gauges || {};
    const volume = data.volume || {};
    const prof = panelProfileCurrent();
    const curBoard = board || (prof && prof.board) || [];
    const curUtil = util || (cfg && cfg.panel_utility) || (panelDraft && panelDraft.panel_utility) || [];

    const gaugesHtml = gOn
      ? '<div class="prev-gauges">' +
          panelGauge("CPU", gauges.cpu_temp, gauges.cpu_temp_max || 100, gauges.cpu_temp_unit || "") +
          panelGauge("GPU", gauges.gpu_temp, gauges.gpu_temp_max || 100, gauges.gpu_temp_unit || "") +
          panelGauge("FPS", gauges.fps, gauges.fps_max || gauges.refresh_rate || 60) +
        '</div>'
      : "";

    const numPages = Math.max(1, Math.ceil(curBoard.length / 12));
    if (panelPreviewPage >= numPages) panelPreviewPage = Math.max(0, numPages - 1);
    const trackTransform = 'transform: translateX(-' + (panelPreviewPage * 100) + '%);';

    let frameHtml = '<div class="prev-frame">';
    if (boxOn) {
      frameHtml += '<div class="prev-box" id="prev-box-wheel" title="Scroll mousewheel over widgets to switch pages">' +
        '<div class="prev-track" style="' + trackTransform + '">' +
          boardPagesHtml(curBoard, null) +
        '</div>' +
      '</div>';
    }
    if (slidOn && (volOn || mvolOn || mixOn || briOn)) {
      frameHtml += '<div class="prev-sliders">' +
        (volOn ? panelSliderHtml("app_volume", "App Volume", volume.volume, 0, 100) : "") +
        (mvolOn ? panelSliderHtml("master_volume", "Master Volume", data.master_volume, 0, 100) : "") +
        (mixOn ? appMixerHtml(data.app_volumes || []) : "") +
        (briOn ? panelSliderHtml("brightness", "Brightness", data.brightness, 0, 4) : "") +
      '</div>';
    }
    frameHtml += '</div>';

    let screenHtml = '<div class="prev-screen">';
    screenHtml += gaugesHtml;
    screenHtml += frameHtml;
    screenHtml += '<div class="prev-footer-group">';
    if (utilOn) {
      screenHtml += '<div class="prev-util"><div class="pdev-grid">' + utilTilesHtml(curUtil) + '</div></div>';
    }
    screenHtml += '<div class="prev-core"><div class="pdev-grid">' + coreTilesHtml(data) + '</div></div>';
    screenHtml += '</div>';
    screenHtml += '</div>';

    return '<div class="panel-preview-col">' +
      '<div class="panel-preview-header">' +
        '<h2 class="panel-preview-title">PANEL PREVIEW</h2>' +
        '<div class="panel-preview-target-toggle">' +
          '<button type="button" class="preview-target-btn' + (target === "desktop" ? " active" : "") + '" data-target="desktop" title="Preview Desktop Companion / Local settings">Desktop</button>' +
          '<button type="button" class="preview-target-btn' + (target === "remote" ? " active" : "") + '" data-target="remote" title="Preview Phone / Remote settings">Phone</button>' +
        '</div>' +
      '</div>' +
      '<div class="panel-phone-frame">' +
        screenHtml +
      '</div>' +
    '</div>';
  }

  function sessionTokenQuery() {
    let savedTok = "";
    try { savedTok = localStorage.getItem("iris_session") || ""; } catch (_) {}
    if (!savedTok) {
      try {
        const m = document.cookie.match(/(?:^|;\s*)iris_session=([^;]+)/);
        if (m) savedTok = decodeURIComponent(m[1]);
      } catch (_) {}
    }
    return savedTok ? "&session=" + encodeURIComponent(savedTok) : "";
  }

  function renderBoardEditor(list, path) {
    const tokQs = sessionTokenQuery();
    let h = '<div class="panel-slot-list" data-path="' + path.join(",") + '">';
    const PAGE = Math.max(4, (typeof getPanelLayoutSpec === "function" && getPanelLayoutSpec().pageSize) || 12);
    for (let pg = 0; pg < list.length; pg += PAGE) {
      const pageNum = Math.floor(pg / PAGE) + 1;
      if (pg === 0) {
        h += '<div class="panel-slot-page-sep panel-slot-page-first" id="panel-editor-page-1" style="display:none;scroll-margin-top:20px;"></div>';
      } else {
        h += '<div class="panel-slot-page-sep" id="panel-editor-page-' + pageNum + '">' +
          '<span class="panel-slot-page-header-title">Page ' + pageNum + '</span>' +
          '</div>';
      }
      const chunk = list.slice(pg, pg + PAGE);
      chunk.forEach((slot, i) => {
        const idx = pg + i;
        let appPath = slot.app_icon_path || (slot.type === "SHORTCUT" ? slot.shortcut_path : "") || ((slot.entity === "media.player" || slot.entity === "media.eject" || slot.type === "MEDIA_EJECT") ? ((panelDraft && panelDraft.media_player_path) || "") : "") || "";
        const brandSvg = typeof getMediaPlayerBrandIcon === "function" ? getMediaPlayerBrandIcon(appPath) : null;
        let slotIcon = slot.icon;
        let slotName = slot.name;
        if (slot.type === "AUDIO OUTPUT") {
          const curDev = ((panelLive && panelLive.default_audio_output) || "").trim().toLowerCase();
          const altId = (slot.audio_input_device_id_alt || "").trim().toLowerCase();
          const isAlt = !!(altId && curDev && (curDev === altId || curDev.includes(altId) || altId.includes(curDev)));
          slotIcon = isAlt ? (slot.audio_alt_icon || "headphones") : (slot.audio_primary_icon || slot.icon || "speaker");
          if (!slotName || slotName === "Audio") {
            slotName = isAlt ? (slot.audio_input_device_name_alt || "Headphones") : (slot.audio_input_device_name || "Speakers");
          }
        }
        let thumb = "";
        if (brandSvg) {
          thumb = '<span class="panel-slot-thumb-brand">' + brandSvg + '</span>';
        } else if (appPath) {
          thumb = '<img class="panel-slot-thumb-img" src="' + API_BASE + '/api/panel/icon?path=' + encodeURIComponent(appPath) + tokQs + '" alt="">';
        } else if (slotIcon) {
          thumb = '<span class="md" data-md="' + esc(slotIcon) + '">' + esc(mdiChar(slotIcon)) + '</span>';
        }
        h += '<div class="panel-slot-tile" draggable="true" data-act="edit" data-i="' + idx + '" data-path="' + path.join(",") + '" role="button" tabindex="0">' +
          '<div class="panel-slot-top">' +
            '<div class="panel-slot-drag-handle" title="Drag to reorder"><span class="material-icons-outlined">drag_indicator</span></div>' +
            '<div class="panel-slot-thumb">' + thumb + '</div>' +
          '</div>' +
          '<div class="panel-slot-info">' +
            '<span class="panel-slot-name">' + esc(slotName || "(unnamed)") + '</span>' +
            '<span class="panel-slot-type">' + esc(actionLabel(slot.type)) + '</span>' +
          '</div>' +
          '</div>';
        if (slot.type === "GROUP" && slot.children && slot.children.length) {
          h += '<div class="panel-slot-children">' + renderBoardEditor(slot.children, path.concat([idx])) + '</div>';
        }
      });
    }
    h += '<button type="button" class="settings-btn panel-add-btn" data-act="add">+ Add action</button></div>';
    return h;
  }

  function renderUtilityEditor(util) {
    let h = '<div class="panel-util-grid">';
    for (let i = 0; i < 4; i++) {
      const s = util[i] || { type: "EMPTY", name: "" };
      h += '<button type="button" class="panel-util-tile" data-i="' + i + '">' +
        '<span class="panel-util-label">Slot ' + (i + 1) + '</span>' +
        '<span class="panel-slot-name">' + esc(s.name || s.type || "Empty") + '</span>' +
        '<span class="panel-slot-type">' + esc(actionLabel(s.type)) + '</span>' +
      '</button>';
    }
    h += '</div>';
    return h;
  }

  const CATEGORIZED_MDI_ICONS = {
    home: [
      "home", "home-outline", "home-lightbulb", "lightbulb", "lightbulb-on",
      "lightbulb-outline", "power", "power-plug", "power-socket-us", "power-socket-eu",
      "fan", "ceiling-fan", "air-conditioner", "thermometer", "thermostat",
      "door", "door-open", "door-closed", "window-closed", "window-open",
      "bed", "sofa", "television", "television-classic", "robot-vacuum",
      "lock", "lock-open", "camera", "cctv", "solar-power",
      "garage", "garage-open", "sprinkler", "gauge", "water",
      "water-pump", "radiator", "blinds", "microwave", "fridge",
      "washing-machine", "shield-home", "stove", "fire", "flash"
    ],
    work: [
      "briefcase", "briefcase-outline", "laptop", "laptop-mac", "desktop-tower-monitor",
      "desktop-mac", "monitor", "keyboard", "keyboard-outline", "mouse",
      "mouse-variant", "printer", "scanner", "file-document", "file-document-outline",
      "file-pdf-box", "folder", "folder-open", "email", "email-outline",
      "email-open", "calendar", "calendar-check", "calendar-clock", "calendar-month",
      "chart-bar", "chart-line", "chart-pie", "phone", "phone-in-talk",
      "headset", "calculator", "clipboard-text", "clipboard-check", "badge-account",
      "card-account-details", "account-group", "archive", "cloud-upload", "cloud-download",
      "database", "server", "code-tags", "code-braces", "hammer", "wrench"
    ],
    gaming: [
      "gamepad-variant", "gamepad-variant-outline", "gamepad", "controller-classic", "controller-classic-outline",
      "space-invaders", "sword", "sword-cross", "shield", "shield-star",
      "crosshairs", "crosshairs-gps", "target", "bullseye", "bullseye-arrow",
      "dice-6", "dice-multiple", "cards-playing-outline", "chess-knight", "chess-queen",
      "steam", "headset", "speedometer", "steering", "rocket-launch",
      "airplane", "radar", "skull", "ghost", "fire",
      "flare", "trophy", "medal", "crown", "diamond",
      "heart", "heart-multiple", "ray-vertex", "pistol", "nuke"
    ],
    lifestyle: [
      "heart-pulse", "heart", "fitness", "dumbbell", "run",
      "walk", "bike", "car", "car-sports", "car-electric",
      "music", "music-note", "headphones", "speaker", "speaker-bluetooth",
      "coffee", "coffee-outline", "food", "food-fork-drink", "pizza",
      "glass-cocktail", "weather-sunny", "weather-night", "weather-rainy", "weather-partly-cloudy",
      "airplane", "camera-iris", "tshirt-crew", "shopping", "cart",
      "wallet", "movie-open", "palette", "book-open-page-variant", "compass"
    ],
    system: [
      "cpu-64-bit", "expansion-card", "chip", "memory", "harddisk",
      "wifi", "bluetooth", "battery-charging", "battery-high", "power",
      "volume-high", "volume-medium", "volume-low", "volume-off", "volume-mute",
      "tune", "cog", "cog-outline", "bell", "bell-ring",
      "shield-check", "database", "cloud", "sync", "layers",
      "application", "apps", "play-pause", "skip-next", "skip-previous",
      "stop", "restart", "refresh", "alert-circle", "check-circle",
      "eye", "eye-off", "lock", "lock-open", "chart-bell-curve"
    ]
  };

  const ALL_MDI_ICONS = Array.from(new Set([
    ...CATEGORIZED_MDI_ICONS.home,
    ...CATEGORIZED_MDI_ICONS.work,
    ...CATEGORIZED_MDI_ICONS.gaming,
    ...CATEGORIZED_MDI_ICONS.lifestyle,
    ...CATEGORIZED_MDI_ICONS.system
  ]));
  const COMMON_MDI_ICONS = ALL_MDI_ICONS;

  const COMMON_QUICK_APPS = [
    { name: "Spotify", path: "Spotify.exe", brand: "spotify" },
    { name: "Apple Music", path: "AppleMusic.exe", brand: "applemusic" },
    { name: "VLC", path: "vlc.exe", brand: "vlc" },
    { name: "Media Player", path: "wmplayer.exe", brand: "wmplayer" },
    { name: "Chrome", path: "chrome.exe", icon: "google-chrome" },
    { name: "Discord", path: "Discord.exe", icon: "forum" },
    { name: "Steam", path: "steam.exe", icon: "steam" },
    { name: "Notepad", path: "notepad.exe", icon: "note-text" },
    { name: "Calculator", path: "calc.exe", icon: "calculator" },
    { name: "Terminal", path: "wt.exe", icon: "console" },
  ];

  function buildEntityOptions(targetType, curEntity, filterPlugin, searchQuery) {
    let entOptHtml = '<option value=""' + (!curEntity ? ' selected' : '') + '>(None / Standalone Action)</option>';
    const domains = {};
    const q = (searchQuery || "").trim().toLowerCase();
    const plgFilter = filterPlugin || "all";

    (panelEntities || []).forEach((ent) => {
      const entPlg = ent.plugin || (ent.id && ent.id.includes(".") ? ent.id.split(".")[0] : "core");
      if (plgFilter !== "all" && entPlg !== plgFilter) return;

      if (q) {
        const matchName = (ent.name || "").toLowerCase().includes(q);
        const matchId = (ent.id || "").toLowerCase().includes(q);
        const matchDomain = (ent.domain || "").toLowerCase().includes(q);
        if (!matchName && !matchId && !matchDomain) return;
      }

      // If filtering by specific plugin or searching, include all matching entities from that plugin
      if (plgFilter === "all" && !q) {
        let include = false;
        if (targetType === "HOTKEY") {
          include = ent.type === "action" || ent.type === "shortcut" || ent.writable || ent.plugin === "openrgb" || ent.id.startsWith("openrgb.");
        } else if (targetType === "TOGGLE") {
          include = ent.type === "status" || ent.type === "toggle" || ent.writable || ent.plugin === "openrgb" || ent.id.startsWith("openrgb.");
        } else if (targetType === "SENSOR") {
          include = ent.type === "data" || ent.type === "sensor" || !ent.writable;
        } else {
          include = true;
        }
        if (!include) return;
      }

      const d = ent.domain || (entPlg ? entPlg.toUpperCase() : "Other");
      if (!domains[d]) domains[d] = [];
      domains[d].push(ent);
    });

    Object.keys(domains).forEach((d) => {
      entOptHtml += '<optgroup label="' + esc(d) + '">';
      domains[d].forEach((ent) => {
        const sel = (curEntity && (ent.id === curEntity || ent.state_key === curEntity)) ? " selected" : "";
        const label = ent.name || ent.id;
        const typeStr = ent.type ? ` (${ent.type})` : "";
        entOptHtml += '<option value="' + esc(ent.id) + '"' + sel + '>' + esc(label) + esc(typeStr) + '</option>';
      });
      entOptHtml += '</optgroup>';
    });
    return entOptHtml;
  }

  function renderActionModal() {
    const ctx = panelEdit;
    const isUtil = ctx.scope === "utility" || ctx.scope === "util";
    let slot = { name: "", type: "HOTKEY", icon: "gesture-tap-button", color: "", show_name: true, show_icon: true, show_state: true };
    if (isUtil) {
      slot = Object.assign(slot, (panelDraft.panel_utility || [])[ctx.index] || {});
    } else {
      const list = boardAtPath(ctx.path || []);
      if (ctx.index >= 0 && list[ctx.index]) slot = Object.assign(slot, list[ctx.index]);
    }
    const allowGroup = !isUtil && ctx.scope === "board";
    let curType = slot.type || "HOTKEY";
    if (curType === "PLUGIN_BUTTON" || curType === "REST" || curType.startsWith("MEDIA_")) curType = "TOGGLE";

    const typeOptions = [
      { type: "HOTKEY", label: "Button" },
      { type: "TOGGLE", label: "Toggle Button" },
      { type: "SHORTCUT", label: "App / Shortcut" },
      { type: "AUDIO OUTPUT", label: "Audio Device Switcher" },
      { type: "SENSOR", label: "Status / Sensor" },
      { type: "EMPTY", label: "Empty / Spacer" },
      { type: "GROUP", label: "Group / Profile Link" },
    ].filter((a) => allowGroup || a.type !== "GROUP");

    let curEntity = slot.entity || (slot.plugin && slot.button_id ? (slot.plugin + "." + slot.button_id) : "");
    if (!curEntity && slot.openrgb_profile) {
      const matchEnt = (panelEntities || []).find((e) => e.openrgb_profile === slot.openrgb_profile || e.name === slot.openrgb_profile);
      if (matchEnt) curEntity = matchEnt.id;
    }
    const showName = (slot.show_name !== false);
    const showIcon = (slot.show_icon !== false);
    const isMediaPlayPause = (curEntity === "media.play_pause");
    const isOpenRGBProfile = (curEntity && curEntity.startsWith("openrgb.")) || !!slot.openrgb_profile;
    const isMediaEject = (curEntity === "media.player" || curEntity === "media.eject" || curType === "MEDIA_EJECT");
    const isAnyMediaControl = (isMediaPlayPause || curEntity === "media.next" || curEntity === "media.prev" || isMediaEject || isOpenRGBProfile);
    const isShortcut = (curType === "SHORTCUT");
    const useAppIcon = (isShortcut || isMediaEject) && (slot.use_app_icon !== undefined ? !!slot.use_app_icon : (isShortcut || !!slot.app_icon_path));
    const showAlbumArt = isMediaEject && (slot.show_album_art !== undefined ? !!slot.show_album_art : true);
    const entObj = curEntity ? (panelEntities || []).find((e) => e.id === curEntity) : null;
    const isActionEntity = entObj && (entObj.type === "action" || entObj.type === "shortcut") && !isOpenRGBProfile;
    const hasStateCapability = !isMediaPlayPause && !isActionEntity && (curType === "TOGGLE" || curType === "SENSOR" || (entObj && (entObj.type === "status" || entObj.type === "data" || !!entObj.state_key || !!entObj.openrgb_profile)));
    const showState = (slot.show_state !== false);
    const showProgressFill = (slot.show_progress_fill !== false);
    const showKeys = (curType !== "EMPTY" && curType !== "AUDIO OUTPUT") && !isAnyMediaControl;

    const initColor = slot.color || "";
    const colorHexVal = (initColor && initColor.startsWith("#") && (initColor.length === 7 || initColor.length === 4))
      ? initColor : "#48B2E9";
    let curIcon = (slot.icon || "gesture-tap-button").trim();
    if (curIcon === "application") curIcon = "apps";
    const curIconChar = mdiChar(curIcon);
    const curHotkey = slot.hotkey || ((slot.keys && slot.keys.length) ? slot.keys.join(",") : "");

    let badgeStyle = "";
    if (initColor) {
      if (initColor.startsWith("#")) {
        badgeStyle = ' style="background:' + esc(initColor) + '; border-color:' + esc(initColor) + '; color:' + (isLightColor(initColor) ? '#0a0a0a' : '#ffffff') + '; box-shadow:0 0 8px ' + esc(initColor) + '66;"';
      } else if (initColor === "RAINBOW") {
        badgeStyle = ' style="background:linear-gradient(135deg, #ff0000, #ff7f00, #ffff00, #00ff00, #0000ff, #8b00ff); border-color:#ffffff; color:#0a0a0a; box-shadow:0 0 8px rgba(255,255,255,0.4);"';
      }
    }

    const customIconPath = slot.app_icon_path || ((slot.entity === "media.player" || slot.entity === "media.eject" || slot.type === "MEDIA_EJECT") ? ((panelDraft && panelDraft.media_player_path) || "") : "") || "";
    const brandSvg = typeof getMediaPlayerBrandIcon === "function" ? getMediaPlayerBrandIcon(customIconPath) : null;
    const tokQs = sessionTokenQuery();

    let iconBadgeInner = brandSvg
      ? '<span class="pe-brand-icon-preview" style="width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;">' + brandSvg + '</span>'
      : (customIconPath
        ? '<img class="pe-icon-live-img" id="pe-icon-live-img" src="' + API_BASE + '/api/panel/icon?path=' + encodeURIComponent(customIconPath) + tokQs + '" alt="">'
        : '<span class="md" id="pe-icon-live" data-md="' + esc(curIcon) + '">' + esc(curIconChar) + '</span>');

    const entOptHtml = buildEntityOptions(curType, curEntity);

    // Group entities by plugin / domain for 2-step plugin + searchable entity picker in button modal
    let curEntityPlugin = "all";
    if (curEntity) {
      const matchEnt = (panelEntities || []).find((e) => e.id === curEntity || e.state_key === curEntity);
      if (matchEnt && matchEnt.plugin) {
        curEntityPlugin = matchEnt.plugin;
      } else if (slot.plugin) {
        curEntityPlugin = slot.plugin;
      } else if (curEntity.includes(".")) {
        curEntityPlugin = curEntity.split(".")[0];
      }
    }

    const buttonPluginGroups = { "all": "All Sources" };
    (panelEntities || []).forEach((ent) => {
      const plg = ent.plugin || (ent.id && ent.id.includes(".") ? ent.id.split(".")[0] : "core");
      const dName = ent.domain || plg.toUpperCase();
      if (!buttonPluginGroups[plg]) buttonPluginGroups[plg] = dName;
    });

    let buttonPluginOptionsHtml = Object.keys(buttonPluginGroups).map((k) => '<option value="' + esc(k) + '"' + (k === curEntityPlugin ? ' selected' : '') + '>' + esc(buttonPluginGroups[k]) + '</option>').join("");

    let h = '<div class="panel-modal-backdrop" id="panel-modal">' +
      '<div class="panel-modal panel-modal-wide">' +
      '<div class="panel-modal-header">' +
        '<h3>' + (isUtil ? ("Edit Utility Button (Slot " + (ctx.index + 1) + ")") : (ctx.index < 0 ? "Add Action" : ("Edit Action (Slot " + (ctx.index + 1) + ")"))) + '</h3>' +
        '<span class="panel-modal-subtitle">Configure entity, appearance, and card display</span>' +
      '</div>' +
      '<div class="panel-modal-body-grid" id="pe-body-grid">' +

        /* Column 1: Config */
        '<div class="panel-modal-col">' +
          '<div class="settings-control" id="pe-name-wrap"><label class="settings-label">Name</label>' +
          '<input type="text" class="settings-input" id="pe-name" value="' + esc(slot.name || "") + '" placeholder="e.g. Play/Pause, Elite, Mute"></div>' +

          '<div class="settings-control" id="pe-type-wrap"><label class="settings-label">Card Type</label>' +
          '<select class="settings-select" id="pe-type">';
    typeOptions.forEach((a) => {
      h += '<option value="' + esc(a.type) + '"' + (a.type === curType ? " selected" : "") + ">" + esc(a.label) + "</option>";
    });
    h += '</select></div>' +

          '<div class="settings-control" id="pe-entity-wrap">' +
            '<label class="settings-label">Entity (Optional / Quick-Fill)</label>' +
            '<div class="settings-picker-row" style="gap:6px;margin-bottom:6px">' +
              '<select class="settings-select" id="pe-entity-plugin" style="width:140px;flex:0 0 auto">' +
                buttonPluginOptionsHtml +
              '</select>' +
              '<input type="text" class="settings-input" id="pe-entity-search" placeholder="Search entities..." style="flex:1">' +
            '</div>' +
            '<select class="settings-select" id="pe-entity"></select>' +
            '<span class="settings-hint">Filter by plugin and search to auto-populate defaults and bind live telemetry.</span>' +
          '</div>' +

          '<div class="settings-control" id="pe-group-profile-wrap" style="display:none">' +
            '<label class="settings-label">Target Profile</label>' +
            '<div class="settings-picker-row">' +
              '<select class="settings-select" id="pe-group-profile">' +
                '<option value="">Select a profile...</option>';
    ((panelDraft && panelDraft.panel_profiles) || []).forEach((pr) => {
      h += '<option value="' + esc(pr.id) + '"' + ((slot.target_profile || slot.profile_id) === pr.id ? " selected" : "") + '>' + esc(pr.name || pr.id) + '</option>';
    });
    h +=     '</select>' +
              '<button type="button" class="settings-btn" id="pe-new-profile-btn">+ New</button>' +
            '</div>' +
            '<span class="settings-hint">Switches the panel board to this profile when pressed.</span>' +
          '</div>' +

          '<div class="settings-control" id="pe-path-wrap" style="display:none"><label class="settings-label" id="pe-path-label">App / Shortcut / URL path</label>' +
          '<div class="settings-picker-row">' +
          '<input type="text" class="settings-input" id="pe-path" value="' + esc(slot.shortcut_path || "") + '" placeholder="e.g. https://youtube.com or C:\\Windows\\notepad.exe">' +
          '<button type="button" class="settings-btn" id="pe-browse">Browse</button></div></div>' +
          '<div class="settings-control" id="pe-args-wrap" style="display:none"><label class="settings-label">Arguments / Switches (Optional)</label>' +
          '<input type="text" class="settings-input" id="pe-args" value="' + esc(slot.shortcut_args || "") + '" placeholder="e.g. /k &quot;cd /d C:\\dir&quot; or --flag">' +
          '<span class="settings-hint">Passed directly to executable on launch.</span></div>' +

          '<div class="settings-control" id="pe-audio-output-wrap" style="display:none">' +
            '<label class="settings-label">Primary Audio Device (Default)</label>' +
            '<div style="display:flex;gap:6px;margin-bottom:8px;">' +
              '<select class="settings-select" id="pe-audio-primary" style="flex:1;">' +
                '<option value="">Select primary device...</option>' +
                (audioOutputDevices || []).map((d) => '<option value="' + esc(d.id) + '"' + ((slot.audio_input_device_id === d.id) ? ' selected' : '') + '>' + esc(d.name) + '</option>').join('') +
              '</select>' +
              '<input type="text" class="settings-input" id="pe-audio-primary-icon" value="' + esc(slot.audio_primary_icon || "speaker") + '" placeholder="speaker" style="width:85px;" title="Primary Icon (MDI glyph)">' +
            '</div>' +
            '<label class="settings-label">Alternate Audio Device (Toggle)</label>' +
            '<div style="display:flex;gap:6px;">' +
              '<select class="settings-select" id="pe-audio-alt" style="flex:1;">' +
                '<option value="">Select alternate device...</option>' +
                (audioOutputDevices || []).map((d) => '<option value="' + esc(d.id) + '"' + ((slot.audio_input_device_id_alt === d.id) ? ' selected' : '') + '>' + esc(d.name) + '</option>').join('') +
              '</select>' +
              '<input type="text" class="settings-input" id="pe-audio-alt-icon" value="' + esc(slot.audio_alt_icon || "headphones") + '" placeholder="headphones" style="width:85px;" title="Alternate Icon (MDI glyph)">' +
            '</div>' +
            '<span class="settings-hint">Tapping this button switches Windows playback between these two devices.</span>' +
          '</div>' +

          '<div class="settings-control" id="pe-keys-wrap"' + (showKeys ? "" : ' style="display:none"') + '>' +
            '<label class="settings-label">Hotkey (Trigger Keystroke)</label>' +
            '<div class="pe-hotkey-input-row">' +
              '<input type="text" class="settings-input pe-hotkey-input" id="pe-keys" value="' + esc(curHotkey) + '" placeholder="Space, Enter, F13, Ctrl+1...">' +
              '<button type="button" class="settings-btn pe-hotkey-capture-btn" id="pe-hotkey-capture-btn" title="Press a key combo to record it">Capture</button>' +
            '</div>' +
          '</div>' +
        '</div>' +

        /* Column 2: Visual Styling & Card Display */
        '<div class="panel-modal-col" id="pe-visual-col">' +
          '<div class="settings-control" id="pe-icon-source-control">' +
            '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">' +
              '<label class="settings-label" style="margin:0;">Icon Source</label>' +
              '<div class="pe-icon-mode-tabs">' +
                '<button type="button" class="pe-icon-mode-tab active" id="pe-mode-auto" data-mode="auto">Auto</button>' +
                '<button type="button" class="pe-icon-mode-tab" id="pe-mode-mdi" data-mode="mdi">MDI</button>' +
                '<button type="button" class="pe-icon-mode-tab" id="pe-mode-custom" data-mode="custom">Custom File</button>' +
              '</div>' +
            '</div>' +

            /* Mode 1: Auto (App / Website Icon) */
            '<div class="pe-icon-mode-pane" id="pe-pane-auto">' +
              '<div class="settings-appicon-row" style="margin-top:2px;">' +
                '<img class="settings-appicon-preview" id="pe-appicon-preview" alt="" hidden>' +
                '<span class="settings-hint" id="pe-appicon-status">Auto-detected from URL or app executable.</span>' +
              '</div>' +
            '</div>' +

            /* Mode 2: MDI Icon */
            '<div class="pe-icon-mode-pane" id="pe-pane-mdi" style="display:none;">' +
              '<div class="pe-icon-container">' +
                '<div class="pe-icon-input-row" id="pe-icon-trigger-row">' +
                  '<span class="pe-icon-live-badge" id="pe-icon-live-badge" title="Active Icon Preview (Click to browse MDI icons)"' + badgeStyle + '>' +
                    iconBadgeInner +
                  '</span>' +
                  '<input type="text" class="settings-select pe-icon-select" id="pe-icon" value="' + esc(curIcon && curIcon !== "application" && curIcon !== "apps" ? curIcon : "toggle-switch") + '" placeholder="Select MDI icon..." readonly>' +
                  '<button type="button" class="settings-btn pe-icon-clear-btn" id="pe-icon-clear-btn" title="Reset MDI icon">✕</button>' +
                '</div>' +
                '<div class="pe-icon-popup" id="pe-icon-popup" style="display:none">' +
                  '<div class="pe-icon-search-row">' +
                    '<span class="material-icons-outlined pe-icon-search-icon">search</span>' +
                    '<input type="text" class="settings-input pe-icon-search-box" id="pe-icon-search" placeholder="Search icons..." autocomplete="off">' +
                  '</div>' +
                  '<div class="pe-icon-cat-bar">' +
                    '<button type="button" class="pe-icon-cat-pill active" data-cat="all">All</button>' +
                    '<button type="button" class="pe-icon-cat-pill" data-cat="home">Home</button>' +
                    '<button type="button" class="pe-icon-cat-pill" data-cat="work">Work</button>' +
                    '<button type="button" class="pe-icon-cat-pill" data-cat="gaming">Gaming</button>' +
                    '<button type="button" class="pe-icon-cat-pill" data-cat="lifestyle">Lifestyle</button>' +
                    '<button type="button" class="pe-icon-cat-pill" data-cat="system">System</button>' +
                  '</div>' +
                  '<div class="pe-icon-grid-scroll">' +
                    '<div class="pe-icon-grid" id="pe-icon-grid"></div>' +
                  '</div>' +
                '</div>' +
              '</div>' +
            '</div>' +

            /* Mode 3: Custom File (.ico, .png, .exe, .lnk) */
            '<div class="pe-icon-mode-pane" id="pe-pane-custom" style="display:none;">' +
              '<div class="pe-icon-input-row">' +
                '<span class="pe-icon-live-badge" id="pe-custom-live-badge" title="Custom File Icon Preview">' +
                  (customIconPath ? '<img class="pe-icon-live-img" src="' + API_BASE + '/api/panel/icon?path=' + encodeURIComponent(customIconPath) + sessionTokenQuery() + '" alt="">' : '<span class="md" data-md="image-outline"></span>') +
                '</span>' +
                '<input type="text" class="settings-input" id="pe-custom-icon-path" value="' + esc(customIconPath || "") + '" placeholder="e.g. C:\\icons\\game.ico, .png, .exe" readonly>' +
                '<button type="button" class="settings-btn" id="pe-custom-browse-btn">Browse</button>' +
                '<button type="button" class="settings-btn pe-icon-clear-btn" id="pe-custom-clear-btn" title="Clear custom file icon">✕</button>' +
              '</div>' +
            '</div>' +
          '</div>' +

          '<div class="settings-control">' +
            '<label class="settings-label">Tile Background Color</label>' +
            '<div class="pe-color-container">' +
              '<div class="pe-color-input-row">' +
                '<label class="pe-color-btn" for="pe-color-picker" id="pe-color-btn" title="Pick Color">' +
                  '<span class="material-icons-outlined pe-color-icon">colorize</span>' +
                  '<input type="color" class="pe-color-picker" id="pe-color-picker" value="' + esc(colorHexVal) + '" title="Pick Color">' +
                '</label>' +
                '<input type="text" class="settings-input pe-color-hex" id="pe-color" value="' + esc(initColor) + '" placeholder="#HEX, RAINBOW, or empty">' +
              '</div>' +
              '<div class="pe-swatches-grid">' +
                '<button type="button" class="pe-swatch" data-color="#48B2E9" style="background:#48B2E9" title="Iris Neon Cyan"></button>' +
                '<button type="button" class="pe-swatch" data-color="#A855F7" style="background:#A855F7" title="Iris Purple"></button>' +
                '<button type="button" class="pe-swatch" data-color="#7C3AED" style="background:#7C3AED" title="Iris Violet"></button>' +
                '<button type="button" class="pe-swatch" data-color="#00ff88" style="background:#00ff88" title="Neon Emerald"></button>' +
                '<button type="button" class="pe-swatch" data-color="#ff3355" style="background:#ff3355" title="Neon Red"></button>' +
                '<button type="button" class="pe-swatch" data-color="#ffb703" style="background:#ffb703" title="Amber Gold"></button>' +
                '<button type="button" class="pe-swatch" data-color="#0d0e10" style="background:#0d0e10" title="OLED Deep Black"></button>' +
                '<button type="button" class="pe-swatch pe-swatch-rainbow" data-color="RAINBOW" title="Rainbow Sheen">🌈</button>' +
                '<button type="button" class="pe-swatch pe-swatch-clear" data-color="" title="Clear / Theme Default">✕</button>' +
              '</div>' +
            '</div>' +
          '</div>' +

          /* Display Options Card (Home Assistant Style) */
          '<div class="settings-control pe-display-options-card">' +
            '<label class="settings-label" style="margin-bottom:8px">BUTTON CARD OPTIONS</label>' +
            '<div class="pe-display-toggles-grid">' +
              '<label class="pe-display-toggle-row">' +
                '<input type="checkbox" id="pe-show-name"' + (showName ? " checked" : "") + '>' +
                '<span class="pe-toggle-label">Show Name</span>' +
                '<span class="pe-toggle-hint">Bottom rectangle bar</span>' +
              '</label>' +
              '<label class="pe-display-toggle-row">' +
                '<input type="checkbox" id="pe-show-icon"' + (showIcon ? " checked" : "") + '>' +
                '<span class="pe-toggle-label">Show Icon</span>' +
                '<span class="pe-toggle-hint">Center icon / text</span>' +
              '</label>' +
              '<label class="pe-display-toggle-row" id="pe-show-album-art-row"' + (isMediaEject ? "" : ' style="display:none"') + '>' +
                '<input type="checkbox" id="pe-show-album-art"' + (showAlbumArt ? " checked" : "") + '>' +
                '<span class="pe-toggle-label">Display Album Art</span>' +
                '<span class="pe-toggle-hint">Background when playing</span>' +
              '</label>' +
              '<label class="pe-display-toggle-row" id="pe-show-state-row"' + (hasStateCapability ? "" : ' style="display:none"') + '>' +
                '<input type="checkbox" id="pe-show-state"' + (showState ? " checked" : "") + '>' +
                '<span class="pe-toggle-label">Show State</span>' +
                '<span class="pe-toggle-hint">Top status bar</span>' +
              '</label>' +
              '<label class="pe-display-toggle-row" id="pe-show-progress-fill-row">' +
                '<input type="checkbox" id="pe-show-progress-fill"' + (showProgressFill ? " checked" : "") + '>' +
                '<span class="pe-toggle-label">Progress Fill</span>' +
                '<span class="pe-toggle-hint">Vertical bar for numbers</span>' +
              '</label>' +
            '</div>' +
          '</div>' +

        '</div>' +

      '</div>' +

      '<div class="panel-modal-actions">' +
      (ctx.scope === "board" && ctx.index >= 0 ?
        '<div class="panel-modal-sub">' +
        '<button type="button" class="settings-btn" id="pe-up">▲ Move up</button>' +
        '<button type="button" class="settings-btn" id="pe-down">▼ Move down</button>' +
        '<button type="button" class="settings-btn" id="pe-delete">Delete</button>' +
        '</div>' : '') +
      '<button type="button" class="settings-btn" id="pe-cancel">Cancel</button>' +
      '<button type="button" class="settings-btn settings-btn-primary" id="pe-save">Save</button>' +
      '</div></div></div>';
    return h;
  }

  function wirePanelPage() {
    const launch = document.getElementById("launch-btn");
    if (launch) {
      launch.addEventListener("click", () => {
        savePanelLive();
        const qs = sessionTokenQuery();
        const sep = qs.startsWith("&") ? "&" : (qs ? "?" + qs : "");
        const panelUrl = window.location.origin + window.location.pathname + "?view=panel" + (sep ? "&" + sep.replace(/^[?&]/, "") : "");
        window.open(
          panelUrl,
          "IrisPhonePanel",
          "width=222,height=650,menubar=no,toolbar=no,location=no,status=no,resizable=yes"
        );
      });
    }

    function bindTog(id, fn) {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("click", () => fn(!el.classList.contains("on")));
    }
    document.querySelectorAll(".panel-target-chk").forEach((chk) => {
      chk.addEventListener("change", () => {
        const sectionId = chk.getAttribute("data-section");
        const target = chk.getAttribute("data-target"); // "local" or "remote"
        setLayoutTargetOn(sectionId, target, chk.checked);
      });
    });

    document.querySelectorAll(".preview-target-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        panelPreviewTarget = btn.getAttribute("data-target") || "desktop";
        renderPanel();
      });
    });

    bindTog("panel-tog-vol", (on) => setSliderOn("app_volume", on));
    bindTog("panel-tog-mvol", (on) => setSliderOn("master_volume", on));
    bindTog("panel-tog-mix", (on) => setSliderOn("app_mixer", on));
    bindTog("panel-tog-bri", (on) => setSliderOn("brightness", on));

    // Mousewheel over the preview button widget box to switch pages and scroll editor bookmark
    const prevBoxWheel = document.getElementById("prev-box-wheel");
    if (prevBoxWheel) {
      prevBoxWheel.addEventListener("wheel", (e) => {
        e.preventDefault();
        const curBoard = panelProfileCurrent().board || [];
        const numPages = Math.max(1, Math.ceil(curBoard.length / 12));
        if (numPages <= 1) return;

        if (e.deltaY > 0) {
          panelPreviewPage = (panelPreviewPage + 1) % numPages;
        } else if (e.deltaY < 0) {
          panelPreviewPage = (panelPreviewPage - 1 + numPages) % numPages;
        }

        const track = document.querySelector(".prev-track");
        if (track) {
          track.style.transform = 'translateX(-' + (panelPreviewPage * 100) + '%)';
        } else {
          renderPanel();
        }

        // Scroll the details editor column to the corresponding page bookmark
        const targetPage = panelPreviewPage + 1;
        const bookmark = document.getElementById("panel-editor-page-" + targetPage);
        if (bookmark && targetPage > 1) {
          bookmark.scrollIntoView({ behavior: "smooth", block: "start" });
        } else {
          const firstSlotTile = main.querySelector(".panel-slot-tile[data-i='0']");
          if (firstSlotTile) {
            firstSlotTile.scrollIntoView({ behavior: "smooth", block: "start" });
          } else {
            const editorCol = main.querySelector(".panel-editor-col");
            if (editorCol) editorCol.scrollTo({ top: 0, behavior: "smooth" });
          }
        }
      }, { passive: false });
    }

    let prevDragSource = null;
    let isPrevDragging = false;

    document.querySelectorAll(".prev-screen .pdev-tile").forEach((tile) => {
      const list = tile.getAttribute("data-list");
      const idx = parseInt(tile.getAttribute("data-idx") || "-1", 10);

      tile.addEventListener("click", (e) => {
        if (isPrevDragging) {
          isPrevDragging = false;
          return;
        }
        e.preventDefault();
        e.stopPropagation();
        const action = tile.getAttribute("data-action");
        if (action === "slot" && list === "board" && idx >= 0) {
          panelEdit = { scope: "board", index: idx, path: [] };
          renderPanel();
        } else if (action === "slot" && list === "util" && idx >= 0) {
          panelEdit = { scope: "utility", index: idx, path: [] };
          renderPanel();
        }
      });

      tile.addEventListener("dragstart", (e) => {
        isPrevDragging = true;
        prevDragSource = { list: list, index: idx };
        tile.classList.add("is-dragging");
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = "move";
          e.dataTransfer.setData("text/plain", String(idx));
        }
      });

      tile.addEventListener("dragover", (e) => {
        if (!prevDragSource || prevDragSource.list !== list) return;
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
        const rect = tile.getBoundingClientRect();
        const isAfter = (e.clientX >= rect.left + rect.width / 2);
        if (isAfter) {
          tile.classList.add("drop-after");
          tile.classList.remove("drop-before");
        } else {
          tile.classList.add("drop-before");
          tile.classList.remove("drop-after");
        }
      });

      tile.addEventListener("dragleave", () => {
        tile.classList.remove("drop-before", "drop-after");
      });

      tile.addEventListener("drop", (e) => {
        e.preventDefault();
        tile.classList.remove("drop-before", "drop-after");
        if (!prevDragSource || prevDragSource.list !== list) return;
        const fromIdx = prevDragSource.index;
        if (fromIdx === idx) return;

        let targetArray = null;
        if (list === "board") {
          targetArray = panelProfileCurrent().board;
        } else if (list === "util") {
          targetArray = (panelDraft && panelDraft.panel_utility) || [];
        }

        if (targetArray) {
          while (targetArray.length <= Math.max(fromIdx, idx)) {
            targetArray.push({ type: "EMPTY" });
          }
          const item = targetArray[fromIdx] || { type: "EMPTY" };
          const targetItem = targetArray[idx] || { type: "EMPTY" };

          targetArray[fromIdx] = targetItem;
          targetArray[idx] = item;

          while (targetArray.length > 12 && targetArray[targetArray.length - 1].type === "EMPTY") {
            targetArray.pop();
          }

          prevDragSource = null;
          panelEdit = null;
          setPanelDirty(true);
          renderPanel();
        }
      });

      tile.addEventListener("dragend", () => {
        isPrevDragging = false;
        prevDragSource = null;
        document.querySelectorAll(".prev-screen .pdev-tile").forEach((t) => {
          t.classList.remove("is-dragging", "drop-before", "drop-after");
        });
      });
    });

    let slotDragSource = null;

    document.querySelectorAll(".panel-slot-list").forEach((listEl) => {
      const pathStr = listEl.getAttribute("data-path") || "";
      const path = pathStr ? pathStr.split(",").map((x) => parseInt(x, 10)) : [];
      
      const addBtn = listEl.querySelector(".panel-add-btn");
      if (addBtn) {
        addBtn.addEventListener("click", () => {
          panelEdit = { scope: "board", index: -1, path: path };
          renderPanel();
        });
      }

      const tiles = listEl.querySelectorAll(".panel-slot-tile");
      tiles.forEach((tile) => {
        const idx = parseInt(tile.getAttribute("data-i") || "-1", 10);
        let isDragging = false;

        tile.addEventListener("click", (e) => {
          if (isDragging) { isDragging = false; return; }
          if (e.target.closest(".panel-slot-drag-handle")) return;
          panelEdit = { scope: "board", index: idx, path: path };
          renderPanel();
        });

        tile.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            panelEdit = { scope: "board", index: idx, path: path };
            renderPanel();
          }
        });

        // Mouse HTML5 Drag & Drop
        tile.addEventListener("dragstart", (e) => {
          isDragging = true;
          slotDragSource = { path: pathStr, index: idx };
          tile.classList.add("is-dragging");
          if (e.dataTransfer) {
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", String(idx));
          }
        });

        tile.addEventListener("dragover", (e) => {
          if (!slotDragSource || slotDragSource.path !== pathStr) return;
          e.preventDefault();
          if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
          const rect = tile.getBoundingClientRect();
          const isAfter = (e.clientX >= rect.left + rect.width / 2);
          if (isAfter) {
            tile.classList.add("drop-after");
            tile.classList.remove("drop-before");
          } else {
            tile.classList.add("drop-before");
            tile.classList.remove("drop-after");
          }
        });

        tile.addEventListener("dragleave", () => {
          tile.classList.remove("drop-before", "drop-after");
        });

        tile.addEventListener("drop", (e) => {
          e.preventDefault();
          tile.classList.remove("drop-before", "drop-after");
          if (!slotDragSource || slotDragSource.path !== pathStr) return;
          const fromIdx = slotDragSource.index;
          if (fromIdx === idx) return;

          const rect = tile.getBoundingClientRect();
          const isAfter = (e.clientX >= rect.left + rect.width / 2);
          const list = boardAtPath(path);

          const item = list.splice(fromIdx, 1)[0];
          let insertAt = idx;
          if (fromIdx < idx) {
            insertAt = isAfter ? idx : idx - 1;
          } else {
            insertAt = isAfter ? idx + 1 : idx;
          }
          insertAt = Math.max(0, Math.min(insertAt, list.length));
          list.splice(insertAt, 0, item);

          slotDragSource = null;
          panelEdit = null;
          setPanelDirty(true);
          renderPanel();
        });

        tile.addEventListener("dragend", () => {
          isDragging = false;
          slotDragSource = null;
          document.querySelectorAll(".panel-slot-tile").forEach((t) => {
            t.classList.remove("is-dragging", "drop-before", "drop-after");
          });
        });

        // Touch drag-and-drop support for mobile touch screens
        const handle = tile.querySelector(".panel-slot-drag-handle");
        if (handle) {
          let touchActive = false;
          let currentTargetTile = null;
          let lastIsAfter = false;

          handle.addEventListener("touchstart", (e) => {
            touchActive = true;
            slotDragSource = { path: pathStr, index: idx };
            tile.classList.add("is-dragging");
          }, { passive: true });

          handle.addEventListener("touchmove", (e) => {
            if (!touchActive || !slotDragSource) return;
            const touch = e.touches[0];
            if (!touch) return;
            const elUnder = document.elementFromPoint(touch.clientX, touch.clientY);
            const targetTile = elUnder ? elUnder.closest(".panel-slot-tile") : null;

            document.querySelectorAll(".panel-slot-tile").forEach((t) => {
              if (t !== tile) t.classList.remove("drop-before", "drop-after");
            });

            if (targetTile && targetTile !== tile && targetTile.getAttribute("data-path") === pathStr) {
              currentTargetTile = targetTile;
              const rect = targetTile.getBoundingClientRect();
              lastIsAfter = (touch.clientX >= rect.left + rect.width / 2);
              if (lastIsAfter) targetTile.classList.add("drop-after");
              else targetTile.classList.add("drop-before");
            } else {
              currentTargetTile = null;
            }
          }, { passive: true });

          const endTouch = () => {
            if (!touchActive) return;
            touchActive = false;
            tile.classList.remove("is-dragging");
            if (currentTargetTile && slotDragSource && slotDragSource.path === pathStr) {
              const fromIdx = slotDragSource.index;
              const toIdx = parseInt(currentTargetTile.getAttribute("data-i") || "-1", 10);
              if (fromIdx !== toIdx && toIdx >= 0) {
                const list = boardAtPath(path);
                const item = list.splice(fromIdx, 1)[0];
                let insertAt = toIdx;
                if (fromIdx < toIdx) {
                  insertAt = lastIsAfter ? toIdx : toIdx - 1;
                } else {
                  insertAt = lastIsAfter ? toIdx + 1 : toIdx;
                }
                insertAt = Math.max(0, Math.min(insertAt, list.length));
                list.splice(insertAt, 0, item);
                setPanelDirty(true);
                renderPanel();
              }
            }
            slotDragSource = null;
            document.querySelectorAll(".panel-slot-tile").forEach((t) => {
              t.classList.remove("is-dragging", "drop-before", "drop-after");
            });
          };

          handle.addEventListener("touchend", endTouch);
          handle.addEventListener("touchcancel", endTouch);
        }
      });
    });

    document.querySelectorAll(".panel-util-tile").forEach((btn) => {
      btn.addEventListener("click", () => {
        panelEdit = { scope: "utility", index: parseInt(btn.getAttribute("data-i"), 10), path: [] };
        renderPanel();
      });
    });



    const profSel = document.getElementById("panel-profile-sel");
    if (profSel) {
      profSel.addEventListener("change", () => {
        panelProfileSel = profSel.value;
        panelEdit = null;
        panelProfileModal = false;
        renderPanel();
      });
    }
    const profCreate = document.getElementById("panel-profile-create");
    if (profCreate) {
      profCreate.addEventListener("click", () => {
        if (!panelDraft.panel_profiles) panelDraft.panel_profiles = [];
        const p = { id: uniqueProfileId(), name: "New Profile", exe: "", enabled: true, board: [] };
        panelDraft.panel_profiles.push(p);
        panelProfileSel = p.id;
        panelEdit = null;
        panelProfileModal = true;
        setPanelDirty(true);
        renderPanel();
      });
    }
    const profClone = document.getElementById("panel-profile-clone");
    if (profClone) {
      profClone.addEventListener("click", () => {
        if (!panelDraft.panel_profiles) panelDraft.panel_profiles = [];
        const current = panelProfileCurrent();
        const srcProf = current.profile;
        const srcBoard = current.board;
        const newId = uniqueProfileId();
        const newName = srcProf ? ((srcProf.name || srcProf.id) + " (Copy)") : "Default (Copy)";
        const newProf = {
          id: newId,
          name: newName,
          is_group: srcProf ? !!srcProf.is_group : true,
          exe: srcProf ? (srcProf.exe || "") : "",
          enabled: srcProf ? (srcProf.enabled !== false) : true,
          board: JSON.parse(JSON.stringify(srcBoard || []))
        };
        panelDraft.panel_profiles.push(newProf);
        panelProfileSel = newId;
        panelEdit = null;
        panelProfileModal = false;
        setPanelDirty(true);
        renderPanel();
      });
    }
    const profQuickDel = document.getElementById("panel-profile-quick-del");
    if (profQuickDel) {
      profQuickDel.addEventListener("click", () => {
        const p = panelProfileCurrent().profile;
        if (!p) return;
        customConfirm('Delete Profile "' + (p.name || p.id) + '"? This cannot be undone.', () => {
          panelDraft.panel_profiles = (panelDraft.panel_profiles || []).filter((x) => x.id !== p.id);
          panelProfileSel = "__default__";
          panelProfileModal = false;
          panelEdit = null;
          setPanelDirty(true);
          renderPanel();
        });
      });
    }
    const profEdit = document.getElementById("panel-profile-edit");
    if (profEdit) {
      profEdit.addEventListener("click", () => {
        fetchLightingStatus().then(() => {
          panelEdit = null;
          panelProfileModal = true;
          renderPanel();
        });
      });
    }

    const profName = document.getElementById("profile-name");
    if (profName) profName.focus();
    const profGrpTog = document.getElementById("profile-group-tog");
    if (profGrpTog) {
      profGrpTog.addEventListener("click", () => {
        const isGrp = profGrpTog.classList.toggle("on");
        const exeEl = document.getElementById("profile-exe");
        const pickBtn = document.getElementById("profile-pick");
        const autoTogRow = document.getElementById("profile-tog-row");
        if (exeEl) exeEl.disabled = isGrp;
        if (pickBtn) pickBtn.disabled = isGrp;
        if (autoTogRow) autoTogRow.classList.toggle("disabled", isGrp);
      });
    }
    const profTog = document.getElementById("profile-tog");
    if (profTog) {
      profTog.addEventListener("click", () => profTog.classList.toggle("on"));
    }
    const profPick = document.getElementById("profile-pick");
    if (profPick) {
      profPick.addEventListener("click", () => {
        browseExe((path) => {
          if (!path) return;
          const exeEl = document.getElementById("profile-exe");
          if (exeEl) exeEl.value = path.split(/[\\/]/).pop();
        });
      });
    }
    const profCancel = document.getElementById("profile-cancel");
    if (profCancel) {
      profCancel.addEventListener("click", () => {
        panelProfileModal = false;
        renderPanel();
      });
    }

    // Toggle daylight switches in profile modal
    document.querySelectorAll(".prof-light-day-tog").forEach((tog) => {
      tog.addEventListener("click", () => tog.classList.toggle("on"));
    });

    const profSave = document.getElementById("profile-save");
    if (profSave) {
      profSave.addEventListener("click", () => {
        const isDef = (panelProfileSel === "__default__");
        if (!panelDraft.panel_profiles) panelDraft.panel_profiles = [];
        let p = isDef
          ? panelDraft.panel_profiles.find((x) => x.id === "__default__")
          : panelProfileCurrent().profile;

        if (isDef && !p) {
          p = { id: "__default__", name: "Default Profile", enabled: true, is_group: true, board: [] };
          panelDraft.panel_profiles.push(p);
        }
        if (!p) return;

        if (!isDef) {
          const isGrp = document.getElementById("profile-group-tog").classList.contains("on");
          p.name = document.getElementById("profile-name").value.trim();
          p.is_group = isGrp;
          p.exe = isGrp ? "" : document.getElementById("profile-exe").value.trim();
          p.enabled = isGrp ? true : document.getElementById("profile-tog").classList.contains("on");
        }

        // Collect generic provider lighting settings
        const lightingMap = {};
        document.querySelectorAll(".prof-light-sel").forEach((sel) => {
          const provId = sel.dataset.prov;
          const field = sel.dataset.field || "preset";
          if (!lightingMap[provId]) lightingMap[provId] = {};
          lightingMap[provId][field] = sel.value;
        });
        document.querySelectorAll(".prof-light-day-tog").forEach((tog) => {
          const provId = tog.dataset.prov;
          if (!lightingMap[provId]) lightingMap[provId] = {};
          lightingMap[provId].follow_daylight = tog.classList.contains("on");
        });

        p.lighting = lightingMap;
        panelProfileModal = false;
        setPanelDirty(true);
        renderPanel();
      });
    }
    const profDel = document.getElementById("profile-delete");
    if (profDel) {
      profDel.addEventListener("click", () => {
        const p = panelProfileCurrent().profile;
        if (!p) return;
        customConfirm('Delete Profile "' + (p.name || p.id) + '"?', () => {
          panelDraft.panel_profiles = (panelDraft.panel_profiles || []).filter((x) => x.id !== p.id);
          panelProfileSel = "__default__";
          panelProfileModal = false;
          panelEdit = null;
          setPanelDirty(true);
          renderPanel();
        });
      });
    }

    wireActionModal();
    document.querySelectorAll("img.panel-slot-thumb-img").forEach((im) => {
      im.addEventListener("error", () => {
        const md = document.createElement("span");
        md.className = "md";
        md.setAttribute("data-md", "apps");
        md.style.cssText = "font-size:18px;margin-right:8px;flex-shrink:0;color:var(--neon);";
        im.replaceWith(md);
        applyMdiIcons(md);
      });
    });
    const prevCol = document.querySelector(".panel-preview-col");
    if (prevCol) {
      applyMdiIcons(prevCol);
      paintPanelRanges(prevCol);
      prevCol.querySelectorAll("img.pdev-iapp").forEach((im) => {
        im.addEventListener("error", () => {
          const raw = im.getAttribute("data-fallback") || "apps";
          const fb = (raw === "application" || !raw) ? "apps" : raw;
          const md = document.createElement("span");
          md.className = "md";
          md.setAttribute("data-md", fb);
          im.replaceWith(md);
          applyMdiIcons(md);
        });
      });
      const need = ["monitor", "speedometer", "microphone", "cog"];
      const b = panelProfileCurrent().board || [];
      const u = (panelDraft && panelDraft.panel_utility) || [];
      b.forEach((s) => { if (s && s.icon) need.push(s.icon); });
      u.forEach((s) => { if (s && s.icon) need.push(s.icon); });
      mdiPreload(need);

      // Synchronized mouseover between button box editor and preview
      const clearSyncHover = () => {
        document.querySelectorAll(".sync-hover").forEach((el) => el.classList.remove("sync-hover"));
      };

      document.querySelectorAll(".panel-slot-tile").forEach((tile) => {
        const idx = tile.getAttribute("data-i");
        const path = tile.getAttribute("data-path") || "";
        if (path === "") {
          tile.addEventListener("mouseenter", () => {
            clearSyncHover();
            tile.classList.add("sync-hover");
            const prevTile = document.querySelector('.panel-phone .pdev-tile[data-list="preview-box"][data-idx="' + idx + '"]');
            if (prevTile) prevTile.classList.add("sync-hover");
          });
          tile.addEventListener("mouseleave", clearSyncHover);
        }
      });

      document.querySelectorAll(".panel-util-tile").forEach((tile) => {
        const idx = tile.getAttribute("data-i");
        tile.addEventListener("mouseenter", () => {
          clearSyncHover();
          tile.classList.add("sync-hover");
          const prevTile = document.querySelector('.panel-phone .pdev-tile[data-list="util"][data-idx="' + idx + '"]');
          if (prevTile) prevTile.classList.add("sync-hover");
        });
        tile.addEventListener("mouseleave", clearSyncHover);
      });

      document.querySelectorAll('.panel-phone .pdev-tile[data-list="preview-box"]').forEach((tile) => {
        const idx = tile.getAttribute("data-idx");
        tile.addEventListener("mouseenter", () => {
          clearSyncHover();
          tile.classList.add("sync-hover");
          const editTile = document.querySelector('.panel-slot-tile[data-path=""][data-i="' + idx + '"]');
          if (editTile) editTile.classList.add("sync-hover");
        });
        tile.addEventListener("mouseleave", clearSyncHover);
      });

      document.querySelectorAll('.panel-phone .pdev-tile[data-list="util"]').forEach((tile) => {
        const idx = tile.getAttribute("data-idx");
        tile.addEventListener("mouseenter", () => {
          clearSyncHover();
          tile.classList.add("sync-hover");
          const editTile = document.querySelector('.panel-util-tile[data-i="' + idx + '"]');
          if (editTile) editTile.classList.add("sync-hover");
        });
        tile.addEventListener("mouseleave", clearSyncHover);
      });
    }
  }

  // ── Panel view (live device screen) ─────────────────────────

  function ensurePanelOverlay() {
    let ov = document.getElementById("panel-view");
    if (!ov) {
      ov = document.createElement("div");
      ov.id = "panel-view";
      ov.className = "panel-view-overlay";
      document.body.appendChild(ov);
    }
    return ov;
  }

  function openPanelView() {
    panelViewMode = true;
    panelNav = [];
    panelViewSig = "";
    updateViewportMode();
    ensurePanelOverlay();
    renderPanelView();
    fetchPanelLive();
    ssArmForPanelView();
  }

  function exitPanelView() {
    panelViewMode = false;
    panelNav = [];
    panelViewSig = "";
    const ov = document.getElementById("panel-view");
    if (ov) ov.remove();
    ssDisarmForPanelView();
  }

  function panelViewConfig() {
    return (panelLive && panelLive.config) || panelDraft || {};
  }

  function slotSig(s) {
    if (!s) return "";
    return [
      s.type || "",
      s.name || "",
      s.icon || "",
      s.color || "",
      s.hotkey || "",
      s.shortcut_path || "",
      s.app_icon_path || "",
      s.entity || s.entity_id || "",
      s.show_name !== false ? 1 : 0,
      s.show_icon !== false ? 1 : 0,
      s.show_state !== false ? 1 : 0,
      s.show_progress_fill !== false ? 1 : 0,
      s.use_app_icon ? 1 : 0,
      s.show_album_art ? 1 : 0,
      s.profile_id || "",
      (s.children || []).length,
    ].join("|");
  }

  function panelViewSignature() {
    const cfg = panelViewConfig();
    const activeProfiles = (panelLive && panelLive.active_profiles) || [];
    const currentBoardSlots = currentBoard();
    const boardSig = currentBoardSlots.map(slotSig).join(";");
    const utilSig = (cfg.panel_utility || []).map(slotSig).join(";");
    const lay = (cfg.panel_layout || []).map((r) => r.id + "=E:" + (r.enabled !== false ? 1 : 0) + ",L:" + (r.local !== false ? 1 : 0) + ",R:" + (r.remote !== false ? 1 : 0)).join(";");
    const sl = (cfg.panel_sliders || []).map((r) => r.id + "=" + (r.enabled === false ? 0 : 1)).join(",");
    // Orientation must be part of the signature: boardPagesHtml bakes the
    // landscape button permutation in at render time, so a rotation (or the iOS
    // PWA cold-start portrait misreport) must trigger a re-render, not just the
    // live CSS classes.
    const ori = (document.documentElement.classList.contains("is-landscape") ? "1" : "0") +
      (document.documentElement.classList.contains("is-oled") ? "1" : "0");
    return JSON.stringify([
      ori,
      activeProfiles.join(","),
      panelNav.map((g) => g.name || g.type || "").join(">"),
      boardSig,
      utilSig,
      lay,
      sl,
      cfg.media_player_path || "",
      (cfg.panel_gauges || {}).enabled === false ? 0 : 1,
      !!(panelLive && panelLive.hardware_connected),
      JSON.stringify((panelLive && panelLive.warnings) || {}),
    ]);
  }

  let _panelLiveConfigVersion = null;
  let _panelLiveCachedConfig = null;
  let _fetchPanelLiveBusy = false;

  function fetchPanelLive() {
    if (_fetchPanelLiveBusy) return;
    _fetchPanelLiveBusy = true;
    const url = _panelLiveConfigVersion
      ? `${API_BASE}/api/panel/live?cv=${encodeURIComponent(_panelLiveConfigVersion)}`
      : `${API_BASE}/api/panel/live`;
    apiFetch(url)
      .then((r) => r.json())
      .then((data) => {
        if (data.config) {
          _panelLiveCachedConfig = data.config;
          if (data.config_version) _panelLiveConfigVersion = data.config_version;
          if (typeof data.config.screensaver_timeout !== "undefined") {
            try { localStorage.setItem("iris_screensaver_timeout", String(data.config.screensaver_timeout)); } catch (e) {}
            if (panelViewMode && !ssActive) resetScreensaverTimer();
          }
        } else if (_panelLiveCachedConfig) {
          data.config = _panelLiveCachedConfig;
        }
        panelLive = data;
        if (data.config && typeof data.config.keep_alive !== "undefined") {
          applyKeepAlive(data.config.keep_alive);
        }
        if (data.config && data.config.theme && typeof window.applyTheme === "function") {
          window.applyTheme(data.config.theme);
        }

        // Live in-place DOM updates for all views (Desktop preview & Phone overlay)
        updatePanelView();

        if (!panelViewMode) return;

        if (panelViewMode && !panelEdit && data.config) {
          panelDraft = {
            panel_board: data.config.panel_board || [],
            panel_utility: data.config.panel_utility || [],
            panel_sliders: data.config.panel_sliders || [],
            panel_layout: data.config.panel_layout || [],
            panel_gauges: data.config.panel_gauges || { enabled: true },
            media_player_path: data.config.media_player_path || "",
            hardware_connected: !!data.hardware_connected,
            panel_profiles: data.config.panel_profiles || [],
          };
        } else if (!panelDraft && data.config) {
          panelDraft = {
            panel_board: data.config.panel_board || [],
            panel_utility: data.config.panel_utility || [],
            panel_sliders: data.config.panel_sliders || [],
            panel_layout: data.config.panel_layout || [],
            panel_gauges: data.config.panel_gauges || { enabled: true },
            media_player_path: data.config.media_player_path || "",
            hardware_connected: !!data.hardware_connected,
            panel_profiles: data.config.panel_profiles || [],
          };
        }
        const sig = panelViewSignature();
        if (sig !== panelViewSig) {
          panelViewSig = sig;
          renderPanelView();
        }
      })
      .catch(() => {})
      .finally(() => {
        _fetchPanelLiveBusy = false;
      });
  }

  function panelMixerChanged(apps) {
    const domPids = Array.from(document.querySelectorAll(".pdev-slider[data-slider^='sess_']"))
      .map((el) => el.querySelector("input") ? parseInt(el.querySelector("input").getAttribute("data-pid"), 10) : null)
      .filter((p) => !Number.isNaN(p));
    const livePids = apps.map((a) => a.pid).filter((p) => p !== null && p !== undefined);
    if (domPids.length !== livePids.length) return true;
    return domPids.some((p) => livePids.indexOf(p) === -1);
  }

  let boxScrollLeft = 0;
  // Set by the orientation-flip handler to the data-page number currently on
  // screen; renderPanelView scrolls back to that same page after it rebuilds
  // the panel in the new orientation.
  let pendingPanelPage = null;
  let lastNotifKey = "";
  let pendingNotifSlide = false;
  let notifDismissTimer = null;
  let notifOpen = false;
  let notifReturnPage = 1; // page the user was on before the notification slide

  function notifKey() {
    const n = (panelLive && panelLive.notification) || null;
    if (!n || (!n.title && !n.body)) return "";
    return (n.timestamp || "") + "|" + (n.theme || "") + "|" + (n.app || "") + "|" + (n.title || "") + "|" + (n.body || "");
  }

  function linkifyText(text) {
    if (!text) return "";
    const escaped = esc(text);
    const urlPattern = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']+)/gi;
    return escaped.replace(urlPattern, (match) => {
      let targetUrl = match;
      if (!/^https?:\/\//i.test(targetUrl)) {
        targetUrl = "https://" + targetUrl;
      }
      return '<span class="pv-notif-link" role="button" tabindex="0" data-url="' + esc(targetUrl) + '">' + match + '</span>';
    });
  }

  function openUrlOnPc(e, el) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const url = el ? el.getAttribute("data-url") : "";
    if (!url) return;

    if (el) {
      el.classList.add("is-opening");
      setTimeout(() => el.classList.remove("is-opening"), 1000);
    }

    apiFetch("/api/open_url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url }),
    }).then((res) => res.json())
      .catch((err) => {
        console.warn("[ws_bridge] Failed to open URL on PC:", err);
      });
  }

  document.addEventListener("click", (e) => {
    const link = e.target && e.target.closest(".pv-notif-link");
    if (link) {
      openUrlOnPc(e, link);
    }
    const iconPopup = document.getElementById("pe-icon-popup");
    if (iconPopup && iconPopup.style.display !== "none") {
      if (!e.target.closest(".pe-icon-container")) {
        iconPopup.style.display = "none";
      }
    }
  });

  function notifHtml(n) {
    if (!n || (!n.title && !n.body)) {
      return '<div class="pv-notif-inner pv-notif-empty"><div class="pv-notif-body">No recent notifications</div></div>';
    }
    const rawApp = (n.app || "").trim();
    const appName = (rawApp && rawApp.toLowerCase() !== "unknown") ? rawApp : "System";
    return '<div class="pv-notif-inner">' +
      '<div class="pv-notif-app">' + esc(appName) + '</div>' +
      (n.title ? '<div class="pv-notif-title">' + linkifyText(n.title) + '</div>' : '') +
      (n.body ? '<div class="pv-notif-body">' + linkifyText(n.body) + '</div>' : '') +
    '</div>';
  }

  function notifCardEl() {
    return document.getElementById("pv-notif");
  }

  function openNotifDrawer() {
    const notifCard = notifCardEl();
    if (!notifCard) return;
    notifOpen = true;
    notifCard.classList.add("pv-notif-open");
  }

  function closeNotifDrawer() {
    if (notifDismissTimer) {
      clearTimeout(notifDismissTimer);
      notifDismissTimer = null;
    }
    const notifCard = notifCardEl();
    if (!notifCard) return;
    notifOpen = false;
    notifCard.classList.remove("pv-notif-open");
    notifCard.classList.remove("notif-theme-green", "notif-theme-red", "notif-flash-green", "notif-flash-red", "notif-flash-alert");
    const pNotif = (panelLive && panelLive.notification) || null;
    notifCard.innerHTML = notifHtml(pNotif);
  }

  let activeBoxPage = 1;

  function rememberBoxScroll() {
    const box = document.querySelector(".panel-view-overlay .pv-box");
    if (!box) return;
    const isLand = document.documentElement.classList.contains("is-landscape");
    boxScrollLeft = Math.round(isLand ? box.scrollLeft : box.scrollTop);
    const cur = getCurBoxPage();
    if (cur > 0) activeBoxPage = cur;
  }

  function restoreBoxScroll(forcePage) {
    const box = document.querySelector(".panel-view-overlay .pv-box");
    if (!box) return;
    const targetPage = (forcePage !== undefined && forcePage !== null)
      ? forcePage
      : (activeBoxPage > 0 ? activeBoxPage : 1);

    const isLand = document.documentElement.classList.contains("is-landscape");
    const track = box.querySelector(".pv-track");
    const g = box.querySelector('.pdev-grid[data-page="' + targetPage + '"]');

    if (g) {
      if (isLand) {
        const W = track ? track.offsetWidth : 0;
        const x = g.offsetLeft;
        box.scrollLeft = W - x - g.offsetWidth;
        boxScrollLeft = box.scrollLeft;
      } else {
        const y = track ? (g.offsetTop - track.offsetTop) : g.offsetTop;
        box.scrollTop = y;
        boxScrollLeft = y;
      }
      if (targetPage > 0) activeBoxPage = targetPage;
      return;
    }

    const g1 = box.querySelector('.pdev-grid[data-page="1"]');
    if (g1) {
      if (isLand) {
        const W = track ? track.offsetWidth : 0;
        const x = g1.offsetLeft;
        box.scrollLeft = W - x - g1.offsetWidth;
        boxScrollLeft = box.scrollLeft;
      } else {
        const y = track ? (g1.offsetTop - track.offsetTop) : g1.offsetTop;
        box.scrollTop = y;
        boxScrollLeft = y;
      }
      activeBoxPage = 1;
    }
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
      wsConn = new WebSocket(`${wsProto}//${wsHost}:${wsPort}`);
      wsConn.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          handleLiveBroadcast(msg);
        } catch (_) {}
      };
      wsConn.onclose = () => {
        wsConn = null;
        setTimeout(connectWs, 2500);
      };
      wsConn.onerror = () => {
        try { wsConn.close(); } catch (_) {}
      };
    } catch (_) {}
  }

  function handleLiveBroadcast(msg) {
    if (!msg || !msg.type) return;
    const isAlert = (msg.theme === "alert" || msg.theme === "red" || msg.status === "bad");
    if (msg.type === "notification") {
      screensaverWakeOnEvent();
      if (!isAlert && panelLive) {
        panelLive.notification = msg;
      } else if (isAlert && panelLive) {
        panelLive.notification = null;
      }
      lastNotifKey = notifKey();
      triggerNotificationSlide(normalizeNotifTheme(msg.theme), isAlert, msg);
      if (currentPage === "notifications") {
        fetchNotifications();
      }
    } else if (msg.type === "event") {
      screensaverWakeOnEvent();
      const status = msg.status || "good";
      const theme = status === "bad" ? "red" : (status === "good" ? "green" : "purple");
      if (panelLive) {
        panelLive.notification = null;
      }
      triggerNotificationSlide(theme, true, msg);
    } else if (msg.type === "config") {
      if (msg.config) {
        _panelLiveConfigVersion = null;
        if (!_panelLiveCachedConfig) _panelLiveCachedConfig = {};
        Object.assign(_panelLiveCachedConfig, msg.config);
        if (panelLive) {
          panelLive.config = panelLive.config || {};
          Object.assign(panelLive.config, msg.config);
        }
        if (panelDraft) {
          Object.assign(panelDraft, msg.config);
        }
        if (panelViewMode) {
          _lastAutoFitH = 0;
          renderPanelView();
        }
        resetScreensaverTimer();
      }
    } else if (msg.type === "navigate") {
      if (msg.page) {
        currentPage = msg.page;
        if (msg.page === "library" && msg.tab) {
          libraryTab = msg.tab;
        }
        navItems.forEach((n) => n.classList.toggle("active", n.dataset.page === currentPage));
        renderPage();
      }
      if (msg.action === "new_note" || msg.action === "note") {
        setTimeout(() => openNotepad(null, msg.app || "general"), 150);
      }
      if (msg.viewer_file) {
        setTimeout(() => openLibraryViewer(msg.viewer_file), 150);
      }
    } else if (msg.type === "library_update") {
      if (currentPage === "library") {
        fetchLibraryItems();
      }
    } else if (msg.type === "reload") {
      if ("caches" in window) {
        caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k)))).then(() => {
          window.location.reload(true);
        }).catch(() => {
          window.location.reload(true);
        });
      } else {
        window.location.reload(true);
      }
    }
  }

  function normalizeNotifTheme(theme) {
    theme = (theme || "").toLowerCase();
    if (theme === "alert" || theme === "red") return "alert";
    if (theme === "green") return "green";
    return "purple";
  }

  function notifCardEl() {
    return document.querySelector(".panel-view-overlay #pv-notif");
  }

  function openNotifDrawer() {
    const notifCard = notifCardEl();
    if (notifCard) {
      notifCard.classList.add("pv-notif-open");
    }
    const scrollEl = document.querySelector(".panel-view-overlay .pv-scroll");
    if (scrollEl) {
      scrollEl.scrollTop = 0;
    }
  }

  function closeNotifDrawer() {
    const notifCard = notifCardEl();
    if (notifCard) {
      notifCard.classList.remove("pv-notif-open");
    }
    const scrollEl = document.querySelector(".panel-view-overlay .pv-scroll");
    if (scrollEl) {
      scrollEl.scrollTop = 0;
    }
  }

  function triggerNotificationSlide(theme, isEvent, eventData) {
    if (typeof screensaverWakeOnEvent === "function") {
      screensaverWakeOnEvent();
    }
    const notifCard = notifCardEl();
    if (!notifCard) return;

    if (notifDismissTimer) {
      clearTimeout(notifDismissTimer);
      notifDismissTimer = null;
    }

    if (!theme) {
      const cur = (panelLive && panelLive.notification) || null;
      theme = normalizeNotifTheme(cur && cur.theme);
    }

    const normTheme = (theme === "green" || theme === "red" || theme === "alert") ? theme : "purple";
    const themeCls = normTheme === "alert" ? "red" : normTheme;
    notifCard.classList.remove(
      "notif-shine",
      "notif-flash-purple", "notif-theme-purple",
      "notif-flash-green", "notif-theme-green",
      "notif-flash-red", "notif-theme-red",
      "notif-flash-alert"
    );
    if (isEvent && eventData) {
      notifCard.innerHTML = notifHtml(eventData);
    } else if (!isEvent) {
      const notif = (eventData || (panelLive && panelLive.notification)) || null;
      notifCard.innerHTML = notifHtml(notif);
    }
    void notifCard.offsetWidth;
    notifCard.classList.add("notif-shine", "notif-flash-" + normTheme, "notif-theme-" + themeCls);

    openNotifDrawer();

    notifDismissTimer = setTimeout(() => {
      notifDismissTimer = null;
      closeNotifDrawer();
    }, 5000);
  }

  function getCurBoxPage() {
    const box = document.querySelector(".panel-view-overlay .pv-box");
    if (!box) return (activeBoxPage || 1);
    const track = box.querySelector(".pv-track");
    const pages = Array.from(box.querySelectorAll('.pdev-grid[data-page]'));
    if (!pages.length) return (activeBoxPage || 1);
    const isLand = document.documentElement.classList.contains("is-landscape");
    let closestPage = activeBoxPage || 1;
    let minDiff = Infinity;

    if (isLand) {
      const curScroll = box.scrollLeft;
      const W = track ? track.offsetWidth : 0;
      pages.forEach((p) => {
        const pNum = parseInt(p.getAttribute("data-page"), 10);
        const x = p.offsetLeft;
        const targetScroll = W - x - p.offsetWidth;
        const diff = Math.abs(curScroll - targetScroll);
        if (diff < minDiff) {
          minDiff = diff;
          closestPage = pNum;
        }
      });
    } else {
      const curScroll = box.scrollTop;
      pages.forEach((p) => {
        const pNum = parseInt(p.getAttribute("data-page"), 10);
        const y = track ? (p.offsetTop - track.offsetTop) : p.offsetTop;
        const diff = Math.abs(curScroll - y);
        if (diff < minDiff) {
          minDiff = diff;
          closestPage = pNum;
        }
      });
    }
    return closestPage;
  }

  function getMaxBoxPage() {
    const box = document.querySelector(".panel-view-overlay .pv-box");
    if (!box) return 1;
    const pages = Array.from(box.querySelectorAll('.pdev-grid[data-page]'));
    if (!pages.length) return 1;
    let maxP = 1;
    pages.forEach((p) => {
      const pNum = parseInt(p.getAttribute("data-page"), 10);
      if (pNum > maxP) maxP = pNum;
    });
    return maxP;
  }

  function setupNotifDrawerGestures() {
    const notifCard = document.querySelector(".panel-view-overlay #pv-notif");
    if (notifCard) {
      let nStartX = 0, nStartY = 0, nTracking = false;
      notifCard.addEventListener("touchstart", (e) => {
        if (e.touches.length !== 1) return;
        nTracking = true;
        nStartX = e.touches[0].clientX;
        nStartY = e.touches[0].clientY;
      }, { passive: false });

      notifCard.addEventListener("touchmove", (e) => {
        if (!nTracking || e.touches.length !== 1) return;
        const isLand = document.documentElement.classList.contains("is-landscape");
        if (isLand) {
          e.preventDefault();
        }
      }, { passive: false });

      notifCard.addEventListener("touchend", (e) => {
        if (!nTracking) return;
        nTracking = false;
        const t = e.changedTouches[0];
        const ndx = t.clientX - nStartX;
        const ndy = t.clientY - nStartY;
        // Only swipe LEFT on screen dismisses the toast (no tap dismiss)
        if (ndx < -25 && Math.abs(ndx) > Math.abs(ndy)) {
          closeNotifDrawer();
        }
      }, { passive: false });
    }

    const box = document.querySelector(".panel-view-overlay .pv-box");
    if (!box) return;

    let startX = 0;
    let startY = 0;
    let tracking = false;
    const THRESH = 30;

    box.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) return;
      tracking = true;
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
    }, { passive: false });

    box.addEventListener("touchmove", (e) => {
      if (!tracking || e.touches.length !== 1) return;
      const isLand = document.documentElement.classList.contains("is-landscape");
      if (isLand) {
        e.preventDefault();
      }
    }, { passive: false });

    box.addEventListener("touchend", (e) => {
      if (!tracking) return;
      tracking = false;
      const t = e.changedTouches[0];
      const dx = t.clientX - startX;
      const dy = t.clientY - startY;

      const cur = activeBoxPage || getCurBoxPage();
      const maxP = getMaxBoxPage();

      // Horizontal swipe on physical screen:
      if (Math.abs(dx) > THRESH && Math.abs(dx) > Math.abs(dy)) {
        if (dx > 0) {
          // Swipe RIGHT -> open notification toast (Column 1)
          openNotifDrawer();
        } else {
          // Swipe LEFT -> close notification toast
          closeNotifDrawer();
        }
        return;
      }

      // Vertical swipe on physical screen:
      if (Math.abs(dy) > THRESH && Math.abs(dy) > Math.abs(dx)) {
        if (dy < 0) {
          // Swipe UP -> Next button page
          if (cur < maxP) {
            activeBoxPage = cur + 1;
            restoreBoxScroll(cur + 1);
          }
        } else {
          // Swipe DOWN -> Prev button page
          if (cur > 1) {
            activeBoxPage = cur - 1;
            restoreBoxScroll(cur - 1);
          }
        }
      }
    }, { passive: true });
  }

  let _panelButtonRows = 4;
  let _panelSliderRows = 2;

  function getPanelLayoutSpec(pDraft, dataLive) {
    const prof = pDraft || panelProfileCurrent() || {};
    const cfg = prof.config || (panelLive && panelLive.config) || panelViewConfig() || {};
    const live = dataLive || panelLive || {};
    const isDesktop = document.documentElement.classList.contains("is-desktop-companion");
    const target = isDesktop ? "desktop" : "remote";
    const layout = {};
    (cfg.panel_layout || []).forEach((r) => {
      if (r && r.id) layout[r.id] = isComponentEnabled(r, target);
    });
    const gOn = layout.gauges !== false && (cfg.panel_gauges ? cfg.panel_gauges.enabled !== false : true);
    const boxOn = layout.button_box !== false;
    const slidOn = layout.sliders !== false;
    const utilOn = layout.utility !== false;
    const sliders = {};
    (cfg.panel_sliders || []).forEach((r) => { sliders[r.id] = r.enabled !== false; });
    const hw = !!(live.hardware_connected !== undefined ? live.hardware_connected
      : (panelDraft && panelDraft.hardware_connected));
    const briOn = hw && sliders.brightness !== false;
    const volOn = sliders.app_volume !== false;
    const mvolOn = sliders.master_volume !== false;
    const mixOn = sliders.app_mixer !== false;

    let activeSliderCount = 0;
    if (slidOn) {
      if (volOn) activeSliderCount++;
      if (mvolOn) activeSliderCount++;
      if (briOn) activeSliderCount++;
      if (mixOn) {
        const apps = (live.app_volumes && live.app_volumes.length) ? live.app_volumes.length : 1;
        activeSliderCount += apps;
      }
    }
    const utilRows = utilOn ? 1 : 0;
    const sliderRows = (slidOn && activeSliderCount > 0) ? (activeSliderCount === 1 ? 1 : 2) : 0;
    let buttonRows = 0;
    if (boxOn) {
      if (isDesktop) {
        const boardLen = (prof.board && prof.board.length) ? prof.board.length : ((cfg.panel_board && cfg.panel_board.length) ? cfg.panel_board.length : 12);
        buttonRows = Math.max(1, Math.min(6, Math.ceil(boardLen / 4)));
      } else {
        const baseBudget = gOn ? 6 : 7;
        buttonRows = Math.max(1, baseBudget - utilRows - sliderRows);
      }
    }
    const pageSize = buttonRows * 4;
    return { isDesktop, gOn, boxOn, slidOn, utilOn, volOn, mvolOn, mixOn, briOn, activeSliderCount, sliderRows, utilRows, buttonRows, pageSize };
  }

  function renderPanelView() {
    updateViewportMode();
    const ov = ensurePanelOverlay();
    const data = panelLive || {};
    const cfg = panelViewConfig();

    const layoutSpec = getPanelLayoutSpec(null, data);
    const isDesktop = layoutSpec.isDesktop;
    const gOn = layoutSpec.gOn;
    const utilOn = layoutSpec.utilOn;
    const boxOn = layoutSpec.boxOn;
    const slidOn = layoutSpec.slidOn;
    const volOn = layoutSpec.volOn;
    const mvolOn = layoutSpec.mvolOn;
    const mixOn = layoutSpec.mixOn;
    const briOn = layoutSpec.briOn;
    const buttonRows = layoutSpec.buttonRows;
    const sliderRows = layoutSpec.sliderRows;
    _panelButtonRows = buttonRows;
    _panelSliderRows = sliderRows;

    const hw = !!(data.hardware_connected !== undefined ? data.hardware_connected
      : (panelDraft && panelDraft.hardware_connected));
    const board = panelNav.length
      ? ((panelNav[panelNav.length - 1].children && panelNav[panelNav.length - 1].children.length) ? panelNav[panelNav.length - 1].children : currentBoard())
      : currentBoard();
    const util = cfg.panel_utility || [];
    const gauges = data.gauges || {};
    const volume = data.volume || {};

    const notif = data.notification || null;
    const curNotifKey = notifKey();
    if (!lastNotifKey) {
      lastNotifKey = curNotifKey;
    }

    let statusBarHtml = "";
    if (IS_APP || (window.location.search && window.location.search.includes("view=panel"))) {
      const featAlarms = (typeof featureConfig !== "undefined" && featureConfig && featureConfig.alarms) || [];
      const alarms = (cfg.alarms || []).concat(featAlarms);
      const activeAlarm = alarms.some((a) => a.enabled !== false);
      const isPinned = window._desktopPanelPinned || false;
      const portName = data.port || "";

      statusBarHtml = '<div class="pv-status-bar">' +
        '<div class="pv-sb-left">' +
          `<span class="pv-sb-dot ${hw ? 'online' : 'offline'}"></span>` +
          (hw && portName ? `<span class="pv-sb-port">${esc(portName)}</span>` : '') +
        '</div>' +
        '<div class="pv-sb-right">' +
          `<span class="pv-sb-alarm ${activeAlarm ? 'active' : ''}"><span class="material-icons-outlined">alarm</span></span>` +
          `<button type="button" class="pv-sb-pin ${isPinned ? 'pinned' : ''}" id="pv-sb-pin" title="${isPinned ? 'Unpin window' : 'Pin on top'}">` +
            `<span class="material-icons-outlined">push_pin</span>` +
          '</button>' +
        '</div>' +
      '</div>';
    }

    let html = '<div class="pv-screen">' + statusBarHtml;
    const gaugesHtml = gOn
      ? '<div class="pv-gauges">' +
        panelGauge("CPU", gauges.cpu_temp, gauges.cpu_temp_max || 100, gauges.cpu_temp_unit || "") +
        panelGauge("GPU", gauges.gpu_temp, gauges.gpu_temp_max || 100, gauges.gpu_temp_unit || "") +
        panelGauge("FPS", gauges.fps, gauges.fps_max || gauges.refresh_rate || 60) +
        '</div>'
      : "";
    let frameHtml = "";
    if (boxOn) {
      const isDesktop = document.documentElement.classList.contains("is-desktop-companion");
      const notifHtmlStr = (!isDesktop)
        ? '<div class="pv-notif-card" id="pv-notif">' + notifHtml(notif) + '</div>'
        : '';
      frameHtml = '<div class="pv-frame">' +
        notifHtmlStr +
        '<div class="pv-box">' +
          '<div class="pv-track">' +
            boardPagesHtml(board, buttonRows) +
          '</div>' +
        '</div>' +
      '</div>';
    }

    let sideHtml = "";
    if (slidOn && (volOn || mvolOn || mixOn || briOn)) {
      sideHtml = '<div class="pv-side"><div class="pv-sliders">' +
        (volOn ? panelSliderHtml("app_volume", "App Volume", volume.volume, 0, 100) : "") +
        (mvolOn ? panelSliderHtml("master_volume", "Master Volume", data.master_volume, 0, 100) : "") +
        (mixOn ? appMixerHtml(data.app_volumes || []) : "") +
        (briOn ? panelSliderHtml("brightness", "Brightness", data.brightness, 0, 4) : "") +
      '</div></div>';
    }

    // Portrait structure for BOTH orientations (landscape is this page rotated):
    // gauges pinned permanently; frame + side inside .pv-scroll; util/core pinned below.
    if (gaugesHtml) {
      html += gaugesHtml;
    }
    if (frameHtml || sideHtml) {
      html += '<div class="pv-scroll">';
      if (frameHtml) html += frameHtml;
      if (sideHtml) html += sideHtml;
      html += '</div>';
    }
    if (utilOn) {
      html += '<div class="pv-util"><div class="pdev-grid">' + utilTilesHtml(util) + '</div></div>';
    }
    if (isDesktop ? utilOn : true) {
      html += '<div class="pv-core"><div class="pdev-grid">' + coreTilesHtml(data) + '</div></div>';
    }
    html += '</div>';

    rememberBoxScroll();
    _lastBtnStatesSig = "";
    ov.innerHTML = html;
    applyMdiIcons(ov);
    const need = ["microphone-off"];
    ov.querySelectorAll(".md[data-md]").forEach((el) => need.push(el.getAttribute("data-md")));
    mdiPreload(need);
    wirePanelView();
    paintPanelRanges(ov);
    // Size button page (4×3 — landscape is this page rotated), then restore scroll.
    layoutPanelBox(ov);
    requestAnimationFrame(() => {
      layoutPanelBox(ov);
      if (pendingPanelPage !== null) {
        restoreBoxScroll(pendingPanelPage);
        pendingPanelPage = null;
      } else {
        restoreBoxScroll();
      }
    });
    // Cold start PWA multi-pass stabilization (catches delayed orientation/safe-area settling)
    setTimeout(() => { updateViewportMode(); layoutPanelBox(ov); restoreBoxScroll(); }, 60);
    setTimeout(() => { updateViewportMode(); layoutPanelBox(ov); restoreBoxScroll(); }, 200);
    panelViewSig = panelViewSignature();
  }

  let _lastAutoFitH = 0;
  function autoFitCompanionWindow() {
    if (!panelViewMode || !window.pywebview || !window.pywebview.api || !window.pywebview.api.resize_to_content) return;
    if (!document.documentElement.classList.contains("is-desktop-companion")) return;

    const screenEl = document.querySelector(".is-desktop-companion .pv-screen");
    if (!screenEl) return;

    const contentH = Math.ceil(Math.max(screenEl.scrollHeight, screenEl.offsetHeight));
    // Measure OS window non-client frame difference (outer vs inner viewport)
    const frameDelta = (window.outerHeight && window.innerHeight && window.outerHeight > window.innerHeight)
      ? (window.outerHeight - window.innerHeight)
      : 24;

    const targetH = contentH + Math.max(24, frameDelta) + 8;
    if (Math.abs(targetH - _lastAutoFitH) >= 4) {
      _lastAutoFitH = targetH;
      window.pywebview.api.resize_to_content(targetH);
    }
  }

  function layoutPanelBox(ov) {
    const root = ov || document.getElementById("panel-view");
    if (!root) return;
    const box = root.querySelector(".pv-box");
    if (!box) {
      requestAnimationFrame(autoFitCompanionWindow);
      return;
    }
    // Portrait is the ONLY sizing reference; landscape is the same page rotated
    // 90°, so this one path serves both orientations. After rotation the box
    // measures the phone's short edge and the tile matches portrait exactly.
    const isLand = document.documentElement.classList.contains("is-landscape");
    const cols = 4;
    const rows = _panelButtonRows || 4;
    const sliderRows = _panelSliderRows !== undefined ? _panelSliderRows : 2;
    const gap = 8;
    const trackGap = 8;
    box.style.width = "";
    box.style.height = "";
    const axis = isLand ? (window.innerHeight || 393) : (window.innerWidth || 393);
    const expectedW = Math.max(220, Math.min(Math.round(axis), 393) - 32);
    let pageW = Math.round(box.clientWidth);
    if (!pageW || pageW < 80 || Math.abs(pageW - expectedW) > 30) {
      pageW = expectedW;
    }
    const tile = Math.max(36, Math.floor((pageW - (cols - 1) * gap) / cols));
    const page = tile * cols + gap * (cols - 1);
    const boxH = tile * rows + gap * (rows - 1);
    const sliderBoxH = sliderRows > 0 ? (tile * sliderRows + gap * (sliderRows - 1)) : 0;
    box.style.setProperty("--pv-cols", String(cols));
    box.style.setProperty("--pv-rows", String(rows));
    box.style.setProperty("--pv-gap", gap + "px");
    box.style.setProperty("--pv-track-gap", trackGap + "px");
    box.style.setProperty("--pv-tile", tile + "px");
    box.style.setProperty("--pv-page", page + "px");
    box.style.setProperty("--pv-box-h", boxH + "px");
    root.style.setProperty("--pv-tile", tile + "px");
    root.style.setProperty("--pv-gap", gap + "px");
    root.style.setProperty("--pv-grid-w", page + "px");
    root.style.setProperty("--pv-slider-box-h", sliderBoxH + "px");
    root.style.setProperty("--pv-slider-item-h", tile + "px");
    document.documentElement.style.setProperty("--pv-grid-w", page + "px");
    // Expose the button-box height to the whole overlay so the notification
    // toast (.pv-notif, a sibling of .pv-box in the frame) can fill it.
    root.style.setProperty("--pv-box-h", boxH + "px");
    if (isLand) {
      box.style.height = boxH + "px";
    }
    requestAnimationFrame(autoFitCompanionWindow);
  }

  window.addEventListener("resize", () => {
    if (!panelViewMode) return;
    const ov = document.getElementById("panel-view");
    if (!ov) return;
    layoutPanelBox(ov);
    restoreBoxScroll();
  });
  window.addEventListener("orientationchange", () => {
    if (!panelViewMode) return;
    const ov = document.getElementById("panel-view");
    if (ov) {
      layoutPanelBox(ov);
      restoreBoxScroll();
    }
    setTimeout(() => {
      const ov2 = document.getElementById("panel-view");
      if (!ov2) return;
      layoutPanelBox(ov2);
      restoreBoxScroll();
    }, 50);
  });

  function gaugeNum(value) {
    const v = (value === null || value === undefined) ? 0 : Math.round(value);
    return String(v);
  }

  const GAUGE_CIRCUMFERENCE = 163.36;

  function panelGauge(label, value, max, unit) {
    const v = (value === null || value === undefined) ? 0 : value;
    const m = max || 100;
    const pct = Math.max(0, Math.min(100, (v / m) * 100));
    const offset = GAUGE_CIRCUMFERENCE - (pct / 100) * GAUGE_CIRCUMFERENCE;
    return '<div class="pdev-gauge">' +
      '<div class="pdev-gring" data-gauge="' + esc(label) + '" style="--val:' + pct.toFixed(1) + '%;">' +
        '<svg class="pdev-gsvg" viewBox="0 0 60 60">' +
          '<defs>' +
            '<linearGradient id="pdev-ggrad" class="pdev-ggrad" x1="0%" y1="0%" x2="100%" y2="100%">' +
              '<stop offset="0%" stop-color="var(--theme-color-1, #48B2E9)" />' +
              '<stop offset="100%" stop-color="var(--theme-color-2, #B23AF6)" />' +
            '</linearGradient>' +
          '</defs>' +
          '<circle class="pdev-gtrack" cx="30" cy="30" r="26" fill="none" />' +
          '<circle class="pdev-garc" cx="30" cy="30" r="26" fill="none" ' +
            'stroke-dasharray="' + GAUGE_CIRCUMFERENCE + '" ' +
            'stroke-dashoffset="' + offset.toFixed(2) + '" />' +
        '</svg>' +
        '<span class="pdev-gval"><span class="pdev-gnum" data-gvalue="' + esc(label) + '">' + gaugeNum(v) + '</span></span>' +
      '</div>' +
      '<span class="pdev-glabel" data-glabel="' + esc(label) + '">' + esc(label) + (unit ? ' ' + esc(unit) : '') + '</span>' +
    '</div>';
  }

  function boardPagesHtml(board, rows) {
    let h = "";
    const list = board || [];
    const btnRows = rows || _panelButtonRows || 4;
    const PAGE = btnRows * 4;
    const isSubPanel = (panelNav && panelNav.length > 0);
    const totalTiles = list.length;
    const numPages = isSubPanel
      ? Math.max(1, Math.ceil((totalTiles + 1) / PAGE))
      : Math.max(1, Math.ceil(totalTiles / PAGE));
    const isLand = document.documentElement.classList.contains("is-landscape");

    // Page 1..N: Button Pages
    for (let pg = 0; pg < numPages; pg++) {
      const pageNum = pg + 1;
      h += '<div class="pdev-grid" data-page="' + pageNum + '">';

      for (let p = 0; p < PAGE; p++) {
        const slotOffset = isLand ? ((3 - (p % 4)) * btnRows + Math.floor(p / 4)) : p;

        if (isSubPanel && pg === 0 && slotOffset === 0) {
          h += '<button type="button" class="pdev-tile pdev-back" data-nav="back" title="Back">' +
            '<span class="md" data-md="arrow-left"></span></button>';
          continue;
        }

        let itemIndex;
        if (isSubPanel) {
          if (pg === 0) {
            itemIndex = slotOffset - 1;
          } else {
            itemIndex = (PAGE - 1) + (pg - 1) * PAGE + slotOffset;
          }
        } else {
          itemIndex = pg * PAGE + slotOffset;
        }

        const s = (itemIndex >= 0 && itemIndex < totalTiles) ? list[itemIndex] : null;
        if (!s || s.type === "EMPTY") {
          h += '<button type="button" class="pdev-tile pdev-empty-tile" data-action="slot" data-list="board" data-idx="' + (itemIndex >= 0 ? itemIndex : 0) + '"></button>';
        } else {
          h += panelTileHtml(s, "board", itemIndex);
        }
      }
      h += '</div>';
    }
    return h;
  }

  function utilTilesHtml(util) {
    let h = "";
    const list = util && util.length ? util : [];
    for (let i = 0; i < 4; i++) {
      const s = list[i];
      if (!s || s.type === "EMPTY") {
        h += '<button type="button" class="pdev-tile pdev-empty-tile" data-action="slot" data-list="util" data-idx="' + i + '"></button>';
        continue;
      }
      h += panelTileHtml(s, "util", i);
    }
    return h;
  }

  function formatTileTitle(name) {
    if (!name) return "";
    const str = String(name).trim();
    if (str.length >= 10) {
      return str.slice(0, 7) + "...";
    }
    return str;
  }

  function parseProgressPercentage(val, valLabel, minBound, maxBound) {
    let num = null;
    let isPct = false;

    if (typeof val === "number" && !isNaN(val)) {
      num = val;
    } else if (typeof val === "string" && val.trim()) {
      const str = val.trim();
      if (str.includes("%")) isPct = true;
      const match = str.match(/[-+]?[0-9]*\.?[0-9]+/);
      if (match) num = parseFloat(match[0]);
    }

    if (num === null && typeof valLabel === "string" && valLabel.trim()) {
      const str = valLabel.trim();
      if (str.includes("%")) isPct = true;
      const match = str.match(/[-+]?[0-9]*\.?[0-9]+/);
      if (match) num = parseFloat(match[0]);
    }

    if (num === null || isNaN(num)) return null;

    const min = (minBound !== undefined && minBound !== null && minBound !== "") ? parseFloat(minBound) : 0;
    const max = (maxBound !== undefined && maxBound !== null && maxBound !== "") ? parseFloat(maxBound) : null;

    let pct = 0;
    if (isPct) {
      pct = num;
    } else if (max !== null && max > min) {
      pct = ((num - min) / (max - min)) * 100;
    } else if (num >= 0 && num <= 1.0 && (typeof val === "number" || (typeof val === "string" && val.startsWith("0.")))) {
      pct = num * 100;
    } else if (num >= 0 && num <= 100) {
      pct = num;
    } else if (num > 100) {
      pct = Math.min(100, num);
    } else {
      pct = 0;
    }

    return Math.max(0, Math.min(100, pct));
  }

  function panelTileHtml(s, listName, idx) {
    let icon = s.icon || "toggle-switch";
    if (icon === "application") icon = "apps";
    const color = s.color || "";
    const isGroup = s.type === "GROUP";
    const showName = (s.show_name !== false);
    const showIcon = (s.show_icon !== false);
    const showState = (s.show_state !== false);
    const useAppIcon = (s.use_app_icon !== false && (s.use_app_icon || s.type === "SHORTCUT" || !!s.app_icon_path));
    const showAlbumArt = !!s.show_album_art;

    let appPath = s.app_icon_path || (s.type === "SHORTCUT" ? s.shortcut_path : "") || "";
    if (!appPath && (s.entity === "media.player" || s.entity === "media.eject" || s.type === "MEDIA_EJECT")) {
      appPath = (panelLive && panelLive.config && panelLive.config.media_player_path) || (panelDraft && panelDraft.media_player_path) || "";
    }
    if (!appPath && s.icon && (s.icon.includes(".exe") || s.icon.includes("/") || s.icon.includes("\\"))) {
      appPath = s.icon;
    }
    const tokQs = sessionTokenQuery();
    let colorPlate = "";
    let glyphStyle = "";
    if (color) {
      if (color.startsWith("#")) {
        colorPlate = '<span class="pdev-color-plate" style="background:' + esc(color) + ';"></span>';
        glyphStyle = ' style="color:' + (isLightColor(color) ? '#0a0a0a' : '#ffffff') + ';"';
      } else if (color === "RAINBOW") {
        colorPlate = '<span class="pdev-color-plate" style="background:linear-gradient(135deg, #ff0000, #ff7f00, #ffff00, #00ff00, #0000ff, #8b00ff);"></span>';
        glyphStyle = ' style="color:#0a0a0a;"';
      }
    }

    let topBar = "";
    let nameBar = "";
    let albumArtPlate = "";
    let progressFillPlate = "";
    let extraTileClass = "";
    let extraTileStyle = "";
    let statusRing = "";
    let warnFlashOverlay = "";

    const entKey = s.entity || (s.plugin && s.button_id ? (s.plugin + "." + s.button_id) : "");
    let bState = (panelLive && (
      (panelLive.entity_states && panelLive.entity_states[entKey]) ||
      (panelLive.plugin_button_states && (panelLive.plugin_button_states[entKey] || panelLive.plugin_button_states[(s.plugin || "") + ":" + (s.button_id || "")]))
    )) || {};

    const mediaState = (panelLive && panelLive.entity_states && panelLive.entity_states["media.player"]) || {};
    const isMediaPlaying = !!(mediaState && (mediaState.active || mediaState.status === "playing" || mediaState.playback_status === "playing"));
    const isMediaPaused = !!(mediaState && (mediaState.status === "paused" || mediaState.playback_status === "paused"));

    let tileTitle = s.name;
    if (s.entity === "media.play_pause") {
      icon = isMediaPlaying ? "pause" : "play";
      tileTitle = isMediaPlaying ? "PAUSE" : "PLAY";
    } else if (s.entity === "media.next") {
      icon = "skip-next";
    } else if (s.entity === "media.prev") {
      icon = "skip-previous";
    } else if (s.entity === "media.player" || s.entity === "media.eject" || s.type === "MEDIA_EJECT") {
      if (!tileTitle || tileTitle === "Player" || tileTitle === "Media Player") {
        tileTitle = getMediaPlayerAppName(appPath);
      }
    } else if (s.type === "AUDIO OUTPUT") {
      const curDev = ((panelLive && panelLive.default_audio_output) || "").trim().toLowerCase();
      const altId = (s.audio_input_device_id_alt || "").trim().toLowerCase();
      const isAlt = !!(altId && curDev && (curDev === altId || curDev.includes(altId) || altId.includes(curDev)));
      icon = isAlt ? (s.audio_alt_icon || "headphones") : (s.audio_primary_icon || "speaker");
      const curDevName = isAlt ? (s.audio_input_device_name_alt || "Headphones") : (s.audio_input_device_name || "Speakers");
      if (!tileTitle || tileTitle === "Audio") {
        tileTitle = curDevName;
      }
      bState = {
        active: isAlt,
        label: isAlt ? ((s.labels && s.labels.on) || s.audio_input_device_name_alt || "ALT") : ((s.labels && s.labels.off) || s.audio_input_device_name || "PRIMARY")
      };
    }

    if (showAlbumArt && mediaState.has_art) {
      const artUrl = API_BASE + '/api/media/art?t=' + encodeURIComponent(mediaState.art_id || Date.now()) + tokQs;
      albumArtPlate = '<span class="pdev-album-art-bg" style="background-image:url(\'' + esc(artUrl) + '\');"></span>';
      extraTileClass += " has-album-art" + (isMediaPlaying ? " is-playing" : (isMediaPaused ? " is-paused" : ""));
    }

    const isElite = (s.plugin === "elite_dangerous");
    const hasLiveState = (bState.active !== undefined || bState.label !== undefined || bState.value !== undefined);
    const isOn = !!bState.active;
    if (isOn && !isElite) extraTileClass += " pdev-active has-halo";
    if (isElite) extraTileClass += " pdev-no-halo";

    const labels = s.labels || {};
    const colors = s.colors || {};
    const activeColor = colors.on || "var(--neon-grn)";
    const inactiveColor = colors.off || "var(--fg-dim)";
    const badgeColor = isOn ? activeColor : inactiveColor;

    // Progress Bar Fill calculation for numerical values / strings
    const entObj = entKey ? (panelEntities || []).find((e) => e.id === entKey || e.state_key === entKey) : null;
    const progressVal = (bState.value !== undefined && bState.value !== null) ? bState.value : (s.value !== undefined ? s.value : null);
    const progressLabel = bState.label || (typeof progressVal === "string" ? progressVal : "");
    const slotMin = (s.fill_min !== undefined) ? s.fill_min : (entObj ? entObj.min : (bState.min !== undefined ? bState.min : 0));
    const slotMax = (s.fill_max !== undefined) ? s.fill_max : (entObj ? entObj.max : (bState.max !== undefined ? bState.max : null));
    const fillPct = parseProgressPercentage(progressVal, progressLabel, slotMin, slotMax);

    const isProgressActive = (s.show_progress_fill !== false) && (fillPct !== null);
    if (isProgressActive) {
      colorPlate = ""; // Progress bar drives the color fill — suppress solid 100% full-tile mask
      glyphStyle = "";
      const fillColor = s.color || activeColor || "var(--theme-color-1, #48B2E9)";
      progressFillPlate = '<span class="pdev-progress-fill" style="--fill-pct:' + fillPct.toFixed(1) + '%; --fill-color:' + esc(fillColor) + ';"></span>';
      extraTileClass += " has-progress-fill" + (fillPct >= 99.5 ? " has-fill-100" : "");
    }

    if (isOn && !colorPlate && !albumArtPlate && !isElite) {
      extraTileStyle = ' style="border-color:' + esc(activeColor) + '; box-shadow:0 0 10px ' + esc(activeColor) + '44;"';
    } else if ((colorPlate || albumArtPlate) && !isElite) {
      if (isOn) {
        statusRing = '<span class="pdev-status-ring" style="--ring-color:' + esc(activeColor) + ';"></span>';
      }
    }

    if (isGroup) {
      topBar = '<span class="pdev-group-bar">GROUP</span>';
      extraTileClass += " has-group-bar";
    } else if (s.entity !== "media.play_pause" && showState && (hasLiveState || labels.on || labels.off || fillPct !== null)) {
      let lblText = bState.label;
      if (!lblText && bState.value !== undefined && bState.value !== null) {
        lblText = (typeof bState.value === "number") ? `${bState.value}` : String(bState.value);
      }
      if (!lblText && fillPct !== null) {
        lblText = fillPct.toFixed(0) + "%";
      }
      if (!lblText) {
        lblText = isOn ? (labels.on || "ON") : (labels.off || "OFF");
      }
      if (lblText) {
        topBar = '<span class="pdev-group-bar pdev-status-bar" style="color:' + esc(badgeColor) + ';">' + esc(lblText) + '</span>';
        extraTileClass += " has-group-bar has-status-bar";
      }
    }

    const warnMap = (panelLive && panelLive.warnings) || {};
    const warn = warnMap[entKey] || warnMap[(s.plugin || "") + ":" + (s.button_id || "")];
    if (warn && warn.color) {
      extraTileClass += " pdev-warning";
      const warnText = isLightColor(warn.color) ? "#0a0a0a" : "#ffffff";
      extraTileStyle = ' style="--warn-color:' + esc(warn.color) + '; color:' + warnText + ';"';
      glyphStyle = ' style="color:' + warnText + ';"';
      warnFlashOverlay = '<span class="pdev-warn-flash"></span>';
      if (warn.message) {
        topBar = '<span class="pdev-group-bar pdev-status-bar" style="color:' + warnText + ';">' + esc(warn.message) + '</span>';
        extraTileClass += " has-group-bar has-status-bar";
      }
    }

    if (showName && showIcon && tileTitle) {
      nameBar = '<span class="pdev-name-bar">' + esc(formatTileTitle(tileTitle)) + '</span>';
      extraTileClass += " has-name-bar";
    }

    let glyph = "";
    if (showIcon) {
      if (useAppIcon && (appPath || s.entity === "media.player" || s.entity === "media.eject" || s.type === "MEDIA_EJECT")) {
        const targetPath = appPath || (panelLive && panelLive.config && panelLive.config.media_player_path) || (panelDraft && panelDraft.media_player_path) || "";
        const brandSvg = typeof getMediaPlayerBrandIcon === "function" ? getMediaPlayerBrandIcon(targetPath) : null;
        if (brandSvg) {
          glyph = '<span class="pdev-ibrand pdev-iapp">' + brandSvg + '</span>' +
            '<span class="pdev-iapp-overlay"></span>';
        } else if (targetPath) {
          glyph = '<img class="pdev-iapp" src="' + API_BASE + '/api/panel/icon?path=' + encodeURIComponent(targetPath) + tokQs +
            '" alt="" data-fallback="' + esc(icon || "apps") + '">' +
            '<span class="pdev-iapp-overlay"></span>';
        } else {
          glyph = '<span class="md" data-md="' + esc(icon || "apps") + '"' + glyphStyle + '>' + esc(mdiChar(icon || "apps")) + '</span>';
        }
      } else {
        glyph = '<span class="md" data-md="' + esc(icon || "apps") + '"' + glyphStyle + '>' + esc(mdiChar(icon || "apps")) + '</span>';
      }
    } else {
      const centerTitle = (showName && (s.name || s.type)) ? (s.name || s.type) : (s.name || "");
      glyph = centerTitle ? ('<span class="pdev-text-only"' + glyphStyle + '>' + esc(formatTileTitle(centerTitle)) + '</span>') : "";
    }

    return '<button type="button" class="pdev-tile' + (isGroup ? " pdev-group" : "") + extraTileClass + '"' +
      extraTileStyle +
      ' data-action="slot" data-list="' + listName + '" data-idx="' + idx + '"' +
      ' title="' + esc(s.name || "") + '">' +
      colorPlate +
      progressFillPlate +
      albumArtPlate +
      warnFlashOverlay +
      statusRing +
      topBar +
      glyph +
      nameBar +
    '</button>';
  }

  function panelSliderHtml(id, label, value, min, max) {
    const v = (value === null || value === undefined) ? 0 : value;
    return '<div class="pdev-slider" data-slider="' + id + '">' +
      '<div class="pdev-slab">' +
        '<span class="pdev-sname">' + esc(label) + '</span>' +
      '</div>' +
      '<input type="range" class="pdev-range" data-slider="' + id + '" min="' + min + '" max="' + max + '" step="1" value="' + v + '"></div>';
  }

  function appMixerHtml(apps) {
    if (!apps || !apps.length) {
      return '<div class="pdev-slider pdev-mixer-empty">' +
        '<div class="pdev-slab"><span class="pdev-sname">No apps playing</span></div></div>';
    }
    let h = "";
    apps.slice(0, 12).forEach((a) => {
      const pid = a.pid;
      const name = a.name || "Application";
      const v = (a.volume === null || a.volume === undefined) ? 0 : a.volume;
      h += '<div class="pdev-slider" data-slider="sess_' + pid + '">' +
        '<div class="pdev-slab">' +
          '<span class="pdev-sname">' + esc(name) + '</span>' +
        '</div>' +
        '<input type="range" class="pdev-range" data-slider="sess_' + pid + '"' +
        ' data-pid="' + pid + '" min="0" max="100" step="1" value="' + v + '"></div>';
    });
    return h;
  }

  function coreTilesHtml(data) {
    const dispOn = !!data.pc_stats_manual;
    const ovOn = !!data.overlay_on;
    return '<button type="button" class="pdev-tile pdev-core-tile' + (dispOn ? " pdev-active" : "") + '" data-core="display" title="PC stats display">' +
        '<span class="md" data-md="monitor"></span></button>' +
      '<button type="button" class="pdev-tile pdev-core-tile' + (ovOn ? " pdev-active" : "") + '" data-core="overlay" title="Stats overlay">' +
        '<span class="md" data-md="speedometer"></span></button>' +
      '<button type="button" class="pdev-tile pdev-core-tile" data-core="mic" title="Microphone mute">' +
        '<span class="md" data-md="microphone"></span></button>' +
      '<button type="button" class="pdev-tile pdev-core-tile" data-core="settings" title="Settings">' +
        '<span class="md" data-md="cog"></span></button>';
  }

  function currentBoard() {
    if (panelNav && panelNav.length > 0) {
      const top = panelNav[panelNav.length - 1];
      if (top && top.children && top.children.length) return top.children;
    }
    const prof = panelProfileCurrent();
    if (prof && prof.board && prof.board.length) return prof.board;
    const cfg = panelViewConfig();
    return (cfg && cfg.panel_board) || [];
  }


  // ── Screenshot phone-side functions ──────────────────────────────────

  function doScreenshotRequest(slot) {
    const startTs = Date.now();
    apiFetch(`${API_BASE}/api/panel/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot: slot }),
    })
    .then(() => pollScreenshotReady(startTs, 0))
    .catch(() => {});
  }

  function pollScreenshotReady(startTs, attempt) {
    if (attempt > 60) return;  // 30 s hard timeout
    setTimeout(() => {
      apiFetch(`${API_BASE}/api/screenshot/latest`)
        .then((r) => r.json())
        .then((data) => {
          if (data.available && data.ts * 1000 > startTs) {
            openScreenshotViewer(data);
          } else {
            pollScreenshotReady(startTs, attempt + 1);
          }
        })
        .catch(() => {});
    }, 500);
  }

  function openScreenshotViewer(data) {
    const existing = document.getElementById("iris-screenshot-viewer");
    if (existing) existing.remove();
    const ts = new Date(data.ts * 1000).toLocaleTimeString();
    const el = document.createElement("div");
    el.id = "iris-screenshot-viewer";
    el.innerHTML =
      `<div class="ssv-bar">` +
        `<span class="ssv-ts">${ts}</span>` +
        `<button class="ssv-close" aria-label="Close">&#x2715;</button>` +
      `</div>` +
      `<img src="data:image/jpeg;base64,${data.img}" alt="Screenshot" draggable="false">`;
    document.body.appendChild(el);
    el.querySelector(".ssv-close").addEventListener("click", () => el.remove());
    // Swipe-down to dismiss
    let startY = 0;
    el.addEventListener("touchstart", (e) => {
      startY = e.touches[0].clientY;
    }, { passive: true });
    el.addEventListener("touchend", (e) => {
      if (e.changedTouches[0].clientY - startY > 80) el.remove();
    }, { passive: true });
    // Wake screensaver if needed
    if (typeof screensaverWakeOnEvent === "function") screensaverWakeOnEvent();
  }

  function runSlotAction(slot) {
    if (!slot) return;
    if (slot.type === "EMPTY") return;
    if (slot.type === "GROUP") {
      const targetProf = slot.target_profile || slot.profile_id;
      if (targetProf) {
        const fromPage = (activeBoxPage > 0) ? activeBoxPage : getCurBoxPage();
        panelNav.push({ prevProfile: panelProfileSel, returnPage: fromPage });
        panelProfileSel = targetProf;
        activeBoxPage = 1;
        if (panelViewMode) renderPanelView(); else renderPanel();
      }
      apiFetch(`${API_BASE}/api/panel/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: slot }),
      }).catch(() => {});
      return;
    }
    // SCREENSHOT — POST action to trigger Tk capture, then poll for the image
    if (slot.type === "SCREENSHOT" || slot.entity === "system.screenshot") {
      doScreenshotRequest(slot);
      return;
    }
    if (slot.type === "AUDIO OUTPUT") {
      apiFetch(`${API_BASE}/api/panel/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: slot }),
      }).then(() => {
        setTimeout(fetchPanelLive, 50);
        setTimeout(fetchPanelLive, 250);
      }).catch(() => {});
      return;
    }
    apiFetch(`${API_BASE}/api/panel/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot: slot }),
    }).catch(() => {});
  }

  function coreAction(core, tile) {
    if (core === "settings") {
      if (isDesktopEnvironment()) {
        apiFetch(`${API_BASE}/api/panel/core`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tile: "settings" }),
        }).catch(() => {});
        return;
      }
      exitPanelView();
      currentPage = "settings";
      renderPage();
      return;
    }
    apiFetch(`${API_BASE}/api/panel/core`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tile: core }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d) return;
        if (core === "mic") {
          tile.classList.toggle("pdev-active", !!d.state);
          tile.classList.toggle("pdev-muted", !!d.state);
          const ic = tile.querySelector(".md");
          if (ic) ic.setAttribute("data-md", d.state ? "microphone-off" : "microphone");
          applyMdiIcons(tile);
        } else {
          tile.classList.toggle("pdev-active", !!d.state);
        }
      })
      .catch(() => {});
  }

  let immersiveActivated = false;

  function triggerImmersiveMode() {
    if (immersiveActivated) return;
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      const req = document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen;
      if (req) {
        req.call(document.documentElement)
          .then(() => { immersiveActivated = true; })
          .catch(() => {});
      }
    }
  }

  document.addEventListener("pointerdown", () => {
    if (panelViewMode && (IS_MOBILE || isAndroid || isIOS)) {
      triggerImmersiveMode();
    }
  }, { passive: true });

  function wirePanelView() {
    // Status bar pin toggle for desktop companion window
    const pinBtn = document.getElementById("pv-sb-pin");
    if (pinBtn) {
      pinBtn.onclick = (e) => {
        e.stopPropagation();
        window._desktopPanelPinned = !window._desktopPanelPinned;
        pinBtn.classList.toggle("pinned", window._desktopPanelPinned);
        pinBtn.title = window._desktopPanelPinned ? "Unpin window" : "Pin on top";
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_pinned) {
          window.pywebview.api.set_pinned(window._desktopPanelPinned);
        }
      };
      if (window.pywebview && window.pywebview.api && window.pywebview.api.is_pinned && window._desktopPanelPinned === undefined) {
        window.pywebview.api.is_pinned().then((p) => {
          window._desktopPanelPinned = !!p;
          pinBtn.classList.toggle("pinned", window._desktopPanelPinned);
          pinBtn.title = window._desktopPanelPinned ? "Unpin window" : "Pin on top";
        }).catch(() => {});
      }
    }

    // App-icon tiles: if the exe icon can't be extracted, fall back to MDI.
    document.querySelectorAll("img.pdev-iapp").forEach((im) => {
      im.addEventListener("error", () => {
        const raw = im.getAttribute("data-fallback") || "apps";
        const fb = (raw === "application" || !raw) ? "apps" : raw;
        const md = document.createElement("span");
        md.className = "md";
        md.setAttribute("data-md", fb);
        im.replaceWith(md);
        applyMdiIcons(md);
      });
    });
    const notifCard = document.getElementById("pv-notif");
    if (notifCard) {
      notifCard.addEventListener("click", (e) => {
        if (e && e.target && e.target.closest(".pv-notif-link")) return;
        closeNotifDrawer();
        activeBoxPage = notifReturnPage;
        restoreBoxScroll(notifReturnPage);
      });
    }
    setupNotifDrawerGestures();
    const tiles = document.querySelectorAll(".pdev-tile");
    tiles.forEach((tile) => {
      if (tile.getAttribute("data-nav") === "back") {
        tile.addEventListener("click", () => {
          const prev = panelNav.pop();
          if (prev) {
            if (prev.prevProfile) panelProfileSel = prev.prevProfile;
            activeBoxPage = prev.returnPage || 1;
          }
          panelViewSig = panelViewSignature();
          if (panelViewMode) renderPanelView(); else renderPanel();
        });
        return;
      }
      const core = tile.getAttribute("data-core");
      if (core) {
        tile.addEventListener("click", () => coreAction(core, tile));
        return;
      }
      if (tile.getAttribute("data-action") === "slot") {
        tile.addEventListener("click", () => {
          const list = tile.getAttribute("data-list");
          const idx = parseInt(tile.getAttribute("data-idx"), 10);
          let s = null;
          if (list === "util") {
            s = (panelViewConfig().panel_utility || [])[idx];
          } else {
            s = currentBoard()[idx];
          }
          runSlotAction(s);
        });
      }
    });

    const pbox = document.querySelector(".panel-view-overlay .pv-box");
    if (pbox) {
      let scrollDebounce = null;
      pbox.addEventListener("scroll", () => {
        clearTimeout(scrollDebounce);
        scrollDebounce = setTimeout(() => {
          const cur = getCurBoxPage();
          if (cur > 0) activeBoxPage = cur;
        }, 100);
      }, { passive: true });
    }

    wireSliderInputs(document);
  }

  function wireSliderInputs(container) {
    const root = container || document;
    root.querySelectorAll(".pdev-slider").forEach((sliderCard) => {
      const rng = sliderCard.querySelector("input[type=range].pdev-range");
      if (!rng || sliderCard._wired) return;
      sliderCard._wired = true;
      rng._wired = true;

      function updateFromPointer(e) {
        const rect = rng.getBoundingClientRect();
        const min = parseFloat(rng.min) || 0;
        const max = parseFloat(rng.max) || 100;
        const isLand = document.documentElement.classList.contains("is-landscape");

        let pct = 0;
        if (isLand) {
          // In landscape (-90deg rotated DOM):
          // Slider track runs along physical Screen-Y (rect.bottom = 0%, rect.top = 100%)
          const clampedY = Math.max(0, Math.min(rect.height, rect.bottom - e.clientY));
          pct = rect.height > 0 ? (clampedY / rect.height) : 0;
        } else {
          // In portrait:
          // Slider track runs along physical Screen-X (rect.left = 0%, rect.right = 100%)
          const clampedX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
          pct = rect.width > 0 ? (clampedX / rect.width) : 0;
        }

        const newVal = Math.round(min + pct * (max - min));
        if (parseFloat(rng.value) !== newVal) {
          rng.value = newVal;
          paintPanelRanges(rng);
          rng.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }

      function isNearThumb(e) {
        const rect = rng.getBoundingClientRect();
        const min = parseFloat(rng.min) || 0;
        const max = parseFloat(rng.max) || 100;
        const curVal = parseFloat(rng.value) || 0;
        const curPct = max > min ? ((curVal - min) / (max - min)) : 0;
        const isLand = document.documentElement.classList.contains("is-landscape");
        const THUMB_RADIUS = 32; // Comfortable grab radius in pixels

        if (isLand) {
          const thumbY = rect.bottom - (curPct * rect.height);
          const thumbX = rect.left + rect.width / 2;
          const dist = Math.hypot(e.clientX - thumbX, e.clientY - thumbY);
          return dist <= THUMB_RADIUS;
        } else {
          const thumbX = rect.left + (curPct * rect.width);
          const thumbY = rect.top + rect.height / 2;
          const dist = Math.hypot(e.clientX - thumbX, e.clientY - thumbY);
          return dist <= THUMB_RADIUS;
        }
      }

      let isDragging = false;

      function onPointerDown(e) {
        if (isNearThumb(e)) {
          isDragging = true;
          try { sliderCard.setPointerCapture(e.pointerId); } catch (_) {}
          updateFromPointer(e);
        } else {
          isDragging = false;
        }
      }

      function onPointerMove(e) {
        if (!isDragging) return;
        updateFromPointer(e);
      }

      function onPointerUp(e) {
        if (isDragging) {
          isDragging = false;
          try { sliderCard.releasePointerCapture(e.pointerId); } catch (_) {}
        }
      }

      sliderCard.addEventListener("pointerdown", onPointerDown);
      sliderCard.addEventListener("pointermove", onPointerMove);
      sliderCard.addEventListener("pointerup", onPointerUp);
      sliderCard.addEventListener("pointercancel", onPointerUp);

      rng.addEventListener("input", () => {
        const id = rng.getAttribute("data-slider");
        const val = parseInt(rng.value, 10);
        paintPanelRanges(rng);
        clearTimeout(panelSliderTimer);
        panelSliderTimer = setTimeout(() => {
          let url;
          let body;
          if (id.indexOf("sess_") === 0) {
            url = "/api/volume/session";
            body = { pid: parseInt(rng.getAttribute("data-pid"), 10), volume: val };
          } else if (id === "brightness") {
            url = "/api/panel/brightness";
            body = { brightness: val };
          } else if (id === "master_volume") {
            url = "/api/volume/master";
            body = { volume: val };
          } else {
            url = "/api/volume";
            body = { volume: val };
          }
          apiFetch(`${API_BASE}${url}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }).catch(() => {});
        }, 150);
      });
    });
  }

  let lastAppMixerSig = "__init__";
  let _lastBtnStatesSig = "";
  let _lastForegroundApp = null;

  function updatePanelView() {
    const data = panelLive || {};
    const gauges = data.gauges || {};
    const volume = data.volume || {};

    // Auto-switch / scroll to focused profile's button box
    const fg = (data.foreground_app || "").toLowerCase().trim().replace(".exe", "");
    if (fg !== _lastForegroundApp) {
      const prevFg = _lastForegroundApp;
      _lastForegroundApp = fg;

      if (panelViewMode && !panelEdit) {
        const cfgP = panelViewConfig();
        const profiles = (cfgP.panel_profiles || []).filter((p) => p && p.enabled !== false);
        const activeIds = data.active_profiles || [];

        let targetPage = 1;
        let matchedProf = null;

        if (fg) {
          matchedProf = profiles.find((p) => {
            if (p.auto_switch === false) return false;
            const pexe = String(p.exe || "").toLowerCase().trim().replace(".exe", "");
            return pexe && (pexe === fg || fg.indexOf(pexe) !== -1 || pexe.indexOf(fg) !== -1);
          });
        }

        if (matchedProf) {
          const profIdx = activeIds.indexOf(matchedProf.id);
          if (profIdx !== -1) {
            targetPage = 1 + profIdx + 1;
            panelNav = [];
          }
        } else if (prevFg && !matchedProf) {
          targetPage = 1;
          panelNav = [];
        }

        if (targetPage) {
          restoreBoxScroll(targetPage);
        }
      }
    }

    updateGauge("CPU", gauges.cpu_temp, gauges.cpu_temp_max || 100, gauges.cpu_temp_unit || "°C");
    updateGauge("GPU", gauges.gpu_temp, gauges.gpu_temp_max || 100, gauges.gpu_temp_unit || "°C");
    updateGauge("FPS", gauges.fps, gauges.fps_max || gauges.refresh_rate || 60, "");

    const isDesktop = document.documentElement.classList.contains("is-desktop-companion");
    const target = isDesktop ? "desktop" : "remote";
    const cfgP = panelViewConfig();
    const sliders = {};
    (cfgP.panel_sliders || []).forEach((r) => { if (r && r.id) sliders[r.id] = r.enabled !== false; });
    const layout = {};
    (cfgP.panel_layout || []).forEach((r) => { if (r && r.id) layout[r.id] = isComponentEnabled(r, target); });

    const slidOn = layout.sliders !== false;
    const volOn = sliders.app_volume !== false;
    const mvolOn = sliders.master_volume !== false;
    const mixOn = sliders.app_mixer !== false;
    const briOn = sliders.brightness !== false;

    const apps = data.app_volumes || [];
    const mixSig = apps.map((a) => `${a.pid}:${a.name}`).join(",");
    const slidersWrap = document.querySelector(".pv-sliders");
    if (slidersWrap && slidOn && mixOn && mixSig !== lastAppMixerSig) {
      lastAppMixerSig = mixSig;
      const volHtml = (volOn ? panelSliderHtml("app_volume", "App Volume", volume.volume, 0, 100) : "");
      const mvolHtml = (mvolOn ? panelSliderHtml("master_volume", "Master Volume", data.master_volume, 0, 100) : "");
      const appHtml = appMixerHtml(apps);
      const briHtml = (briOn ? panelSliderHtml("brightness", "Brightness", data.brightness, 0, 4) : "");
      slidersWrap.innerHTML = volHtml + mvolHtml + appHtml + briHtml;
      paintPanelRanges(slidersWrap);
      wireSliderInputs(slidersWrap);
      requestAnimationFrame(autoFitCompanionWindow);
    }

    const volEl = document.querySelector(".pdev-slider[data-slider='app_volume']");
    if (volEl) {
      const rng = volEl.querySelector("input");
      if (document.activeElement !== rng &&
          volume.volume !== null && volume.volume !== undefined) {
        if (rng && String(rng.value) !== String(volume.volume)) rng.value = volume.volume;
        paintPanelRanges(rng);
      }
    }

    const mvolEl = document.querySelector(".pdev-slider[data-slider='master_volume']");
    if (mvolEl) {
      const rng = mvolEl.querySelector("input");
      if (document.activeElement !== rng &&
          data.master_volume !== null && data.master_volume !== undefined) {
        if (rng && String(rng.value) !== String(data.master_volume)) rng.value = data.master_volume;
        paintPanelRanges(rng);
      }
    }

    document.querySelectorAll(".pdev-slider[data-slider^='sess_']").forEach((el) => {
      const rng = el.querySelector("input");
      if (!rng || document.activeElement === rng) return;
      const pid = parseInt(rng.getAttribute("data-pid"), 10);
      const match = apps.find((a) => a.pid === pid);
      if (match && match.volume !== null && match.volume !== undefined &&
          String(rng.value) !== String(match.volume)) {
        rng.value = match.volume;
        paintPanelRanges(rng);
      }
    });

    const briEl = document.querySelector(".pdev-slider[data-slider='brightness']");
    if (briEl) {
      const rng = briEl.querySelector("input");
      if (document.activeElement !== rng && data.brightness !== null && data.brightness !== undefined) {
        if (rng && String(rng.value) !== String(data.brightness)) rng.value = data.brightness;
        paintPanelRanges(rng);
      }
    }

    const disp = document.querySelectorAll('.pdev-core-tile[data-core="display"]');
    disp.forEach((d) => d.classList.toggle("pdev-active", !!data.pc_stats_manual));

    const ov = document.querySelectorAll('.pdev-core-tile[data-core="overlay"]');
    ov.forEach((o) => o.classList.toggle("pdev-active", !!data.overlay_on));

    const mic = document.querySelectorAll('.pdev-core-tile[data-core="mic"]');
    const isMicMuted = !!(data.entity_states && data.entity_states["system.mic_mute"] && data.entity_states["system.mic_mute"].active);
    mic.forEach((m) => {
      m.classList.toggle("pdev-active", isMicMuted);
      const mIcon = m.querySelector(".md");
      if (mIcon) {
        const ic = isMicMuted ? "microphone-off" : "microphone";
        mIcon.setAttribute("data-md", ic);
        mIcon.textContent = mdiChar(ic);
        mdiPreload([ic]);
        applyMdiIcons(m);
      }
    });

    const notifEl = document.getElementById("pv-notif");
    if (notifEl && !notifDismissTimer) {
      const notif = data.notification || null;
      const newHtml = notifHtml(notif);
      if (notifEl.innerHTML !== newHtml) {
        notifEl.innerHTML = newHtml;
        notifEl.classList.remove("notif-theme-green", "notif-theme-red", "notif-flash-green", "notif-flash-red");
      }
    }

    const curNotifKey = notifKey();
    if (curNotifKey && curNotifKey !== lastNotifKey) {
      lastNotifKey = curNotifKey;
      pendingNotifSlide = false;
      triggerNotificationSlide();
      if (typeof screensaverWakeOnEvent === "function") screensaverWakeOnEvent();
    }

    const mediaState = (data.entity_states && data.entity_states["media.player"]) || {};
    const isMediaPlaying = !!(mediaState && (mediaState.active || mediaState.status === "playing" || mediaState.playback_status === "playing"));
    const isMediaPaused = !!(mediaState && (mediaState.status === "paused" || mediaState.playback_status === "paused"));

    const btnStates = (data.entity_states) || (data.plugin_button_states) || {};
    const btnStatesSig = JSON.stringify(btnStates) + '|' + (isMediaPlaying ? '1' : '0') + '|' + (isMediaPaused ? '1' : '0') + '|' + (mediaState.art_id || '') + '|' + (data.default_audio_output || '');
    if (btnStatesSig !== _lastBtnStatesSig) {
      if (_lastBtnStatesSig !== null && typeof screensaverWakeOnEvent === "function") {
        screensaverWakeOnEvent();
      }
      _lastBtnStatesSig = btnStatesSig;
      document.querySelectorAll(".pdev-tile").forEach((tile) => {
        const idx = parseInt(tile.getAttribute("data-idx"), 10);
        const list = tile.getAttribute("data-list");
        if (isNaN(idx) || !list) return;
        const board = (list === "util") ? ((panelDraft && panelDraft.panel_utility) || []) : currentBoard();
        const s = board[idx];
        if (s) {
          const entKey = s.entity || (s.plugin && s.button_id ? (s.plugin + "." + s.button_id) : "");
          let bState = btnStates[entKey] || btnStates[(s.plugin || "") + ":" + (s.button_id || "")] || {};
          let isOn = !!bState.active;

          if (s.type === "AUDIO OUTPUT") {
            const curDev = ((data.default_audio_output) || "").trim().toLowerCase();
            const altId = (s.audio_input_device_id_alt || "").trim().toLowerCase();
            const isAlt = !!(altId && curDev && (curDev === altId || curDev.includes(altId) || altId.includes(curDev)));
            const audIcon = isAlt ? (s.audio_alt_icon || "headphones") : (s.audio_primary_icon || "speaker");
            const curDevName = isAlt ? (s.audio_input_device_name_alt || "Headphones") : (s.audio_input_device_name || "Speakers");
            const audTitle = (!s.name || s.name === "Audio") ? curDevName : s.name;
            const audLabel = isAlt ? ((s.labels && s.labels.on) || s.audio_input_device_name_alt || "ALT") : ((s.labels && s.labels.off) || s.audio_input_device_name || "PRIMARY");

            isOn = isAlt;
            bState = { active: isAlt, label: audLabel };

            const iconEl = tile.querySelector(".md");
            if (iconEl && iconEl.getAttribute("data-md") !== audIcon) {
              iconEl.setAttribute("data-md", audIcon);
              iconEl.textContent = mdiChar(audIcon);
              mdiPreload([audIcon]);
              applyMdiIcons(tile);
            }
            const nameBarEl = tile.querySelector(".pdev-name-bar");
            if (nameBarEl) {
              nameBarEl.textContent = formatTileTitle(audTitle);
            }
            const textOnlyEl = tile.querySelector(".pdev-text-only");
            if (textOnlyEl) {
              textOnlyEl.textContent = formatTileTitle(audTitle);
            }
          }

          const isElite = (s.plugin === "elite_dangerous");
          tile.classList.toggle("pdev-active", isOn && !isElite);
          tile.classList.toggle("has-halo", isOn && !isElite);
          tile.classList.toggle("pdev-no-halo", isElite);

          const colors = s.colors || {};
          const activeColor = colors.on || "var(--neon-grn)";
          const inactiveColor = colors.off || "var(--fg-dim)";
          const badgeColor = isOn ? activeColor : inactiveColor;

          if (isOn && !s.color && !isElite) {
            tile.style.borderColor = activeColor;
            tile.style.boxShadow = "0 0 10px " + activeColor + "44";
          } else if (!s.color || isElite) {
            tile.style.borderColor = "";
            tile.style.boxShadow = "";
          }

          const ring = tile.querySelector(".pdev-status-ring");
          if (ring) {
            if (isOn && !isElite) {
              ring.style.setProperty("--ring-color", activeColor);
              ring.style.display = "";
            } else {
              ring.style.display = "none";
            }
          }

          // Update progress fill plate
          const entObj = entKey ? (panelEntities || []).find((e) => e.id === entKey || e.state_key === entKey) : null;
          const progressVal = (bState.value !== undefined && bState.value !== null) ? bState.value : (s.value !== undefined ? s.value : null);
          const progressLabel = bState.label || (typeof progressVal === "string" ? progressVal : "");
          const slotMin = (s.fill_min !== undefined) ? s.fill_min : (entObj ? entObj.min : (bState.min !== undefined ? bState.min : 0));
          const slotMax = (s.fill_max !== undefined) ? s.fill_max : (entObj ? entObj.max : (bState.max !== undefined ? bState.max : null));
          const fillPct = parseProgressPercentage(progressVal, progressLabel, slotMin, slotMax);

          const isProgressActive = (s.show_progress_fill !== false) && (fillPct !== null);
          let progEl = tile.querySelector(".pdev-progress-fill");
          const colorPlateEl = tile.querySelector(".pdev-color-plate");
          if (isProgressActive) {
            if (colorPlateEl) colorPlateEl.style.display = "none";
            const fillColor = s.color || activeColor || "var(--theme-color-1, #48B2E9)";
            if (!progEl) {
              progEl = document.createElement("span");
              progEl.className = "pdev-progress-fill";
              tile.insertBefore(progEl, tile.firstChild);
            }
            progEl.style.setProperty("--fill-pct", fillPct.toFixed(1) + "%");
            progEl.style.setProperty("--fill-color", fillColor);
            tile.classList.add("has-progress-fill");
            tile.classList.toggle("has-fill-100", fillPct >= 99.5);
          } else {
            if (colorPlateEl) colorPlateEl.style.display = "";
            if (progEl) progEl.remove();
            tile.classList.remove("has-progress-fill", "has-fill-100");
          }

          // Update status bar
          const statusBar = tile.querySelector(".pdev-status-bar");
          if (statusBar) {
            const labels = s.labels || {};
            let lblText = bState.label;
            if (!lblText && bState.value !== undefined && bState.value !== null) {
              lblText = (typeof bState.value === "number") ? `${bState.value}` : String(bState.value);
            }
            if (!lblText && fillPct !== null) {
              lblText = fillPct.toFixed(0) + "%";
            }
            if (!lblText) {
              lblText = isOn ? (labels.on || "ON") : (labels.off || "OFF");
            }
            if (lblText) {
              statusBar.textContent = lblText;
              statusBar.style.color = badgeColor;
            }
          }

          // Update Play/Pause dynamic icon & name text
          if (s.entity === "media.play_pause") {
            const ppIcon = isMediaPlaying ? "pause" : "play";
            const ppTitle = isMediaPlaying ? "PAUSE" : "PLAY";
            const iconEl = tile.querySelector(".md");
            if (iconEl && iconEl.getAttribute("data-md") !== ppIcon) {
              iconEl.setAttribute("data-md", ppIcon);
              iconEl.textContent = mdiChar(ppIcon);
              mdiPreload([ppIcon]);
              applyMdiIcons(tile);
            }
            const nameBarEl = tile.querySelector(".pdev-name-bar");
            if (nameBarEl) {
              nameBarEl.textContent = formatTileTitle(ppTitle);
            }
            const textOnlyEl = tile.querySelector(".pdev-text-only");
            if (textOnlyEl) {
              textOnlyEl.textContent = formatTileTitle(ppTitle);
            }
          }

          // Update Media Player dynamic app name
          if (s.entity === "media.player" || s.entity === "media.eject" || s.type === "MEDIA_EJECT") {
            const mAppPath = s.app_icon_path || (panelLive && panelLive.config && panelLive.config.media_player_path) || (panelDraft && panelDraft.media_player_path) || "";
            const playerName = (!s.name || s.name === "Player" || s.name === "Media Player") ? getMediaPlayerAppName(mAppPath) : s.name;
            const nameBarEl = tile.querySelector(".pdev-name-bar");
            if (nameBarEl) {
              nameBarEl.textContent = formatTileTitle(playerName);
            }
            const textOnlyEl = tile.querySelector(".pdev-text-only");
            if (textOnlyEl) {
              textOnlyEl.textContent = formatTileTitle(playerName);
            }
          }

          // Update live album art
          const showArt = s.show_album_art !== undefined ? !!s.show_album_art : (s.entity === "media.player" || s.entity === "media.eject" || s.type === "MEDIA_EJECT");
          let artBg = tile.querySelector(".pdev-album-art-bg");
          if (showArt && mediaState.has_art && mediaState.art_id) {
            const tokQs = sessionTokenQuery();
            const artUrl = API_BASE + '/api/media/art?t=' + encodeURIComponent(mediaState.art_id) + tokQs;
            if (!artBg) {
              artBg = document.createElement("span");
              artBg.className = "pdev-album-art-bg";
              tile.insertBefore(artBg, tile.firstChild);
            }
            if (artBg.getAttribute("data-art-id") !== String(mediaState.art_id)) {
              artBg.setAttribute("data-art-id", String(mediaState.art_id));
              artBg.style.backgroundImage = "url('" + artUrl + "')";
            }
            tile.classList.add("has-album-art");
            tile.classList.toggle("is-playing", isMediaPlaying);
            tile.classList.toggle("is-paused", isMediaPaused);
          } else {
            if (artBg) artBg.remove();
            tile.classList.remove("has-album-art", "is-playing", "is-paused");
          }
        }
      });
    }

    // Live status bar updates (COM dot / Port / Clock)
    const sbDot = document.querySelector(".pv-sb-dot");
    const sbPort = document.querySelector(".pv-sb-port");
    const sbAlarm = document.querySelector(".pv-sb-alarm");
    const hw = !!(data.hardware_connected !== undefined ? data.hardware_connected : (panelDraft && panelDraft.hardware_connected));
    if (sbDot) {
      sbDot.classList.toggle("online", hw);
      sbDot.classList.toggle("offline", !hw);
    }
    if (sbPort) {
      const pName = data.port || "";
      sbPort.textContent = (hw && pName) ? pName : "";
      sbPort.style.display = (hw && pName) ? "" : "none";
    }
    if (sbAlarm) {
      const featAlarms = (typeof featureConfig !== "undefined" && featureConfig && featureConfig.alarms) || [];
      const alarms = (cfg.alarms || []).concat(featAlarms);
      const activeAlarm = alarms.some((a) => a.enabled !== false);
      sbAlarm.classList.toggle("active", activeAlarm);
    }
    autoFitCompanionWindow();
  }

  // Auto-hide companion window on focus loss when unpinned
  window.addEventListener("blur", () => {
    if (panelViewMode && !window._desktopPanelPinned && window.pywebview && window.pywebview.api && window.pywebview.api.hide_on_blur) {
      setTimeout(() => {
        if (!document.hasFocus() && !window._desktopPanelPinned) {
          window.pywebview.api.hide_on_blur();
        }
      }, 120);
    }
  });

  // Re-evaluate auto-fit and resync config on focus/re-show
  window.addEventListener("focus", () => {
    if (panelViewMode && document.documentElement.classList.contains("is-desktop-companion")) {
      _panelLiveConfigVersion = null;
      _lastAutoFitH = 0;
      fetchPanelLive();
      autoFitCompanionWindow();
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && panelViewMode) {
      _panelLiveConfigVersion = null;
      _lastAutoFitH = 0;
      fetchPanelLive();
      autoFitCompanionWindow();
    }
  });

  let _lastGaugeVals = {};
  function updateGauge(label, value, max, unit) {
    const v = (value === null || value === undefined) ? 0 : value;
    const m = max || 100;
    const key = `${label}|${v}|${m}|${unit || ''}`;
    if (_lastGaugeVals[label] === key) return;
    _lastGaugeVals[label] = key;

    const pct = Math.max(0, Math.min(100, (v / m) * 100));
    const offset = GAUGE_CIRCUMFERENCE - (pct / 100) * GAUGE_CIRCUMFERENCE;
    const ringEls = document.querySelectorAll('.pdev-gring[data-gauge="' + label + '"]');
    ringEls.forEach((ringEl) => {
      ringEl.style.setProperty("--val", pct.toFixed(1) + "%");
      const arc = ringEl.querySelector(".pdev-garc");
      if (arc) arc.style.strokeDashoffset = offset.toFixed(2);
    });
    const numEls = document.querySelectorAll('.pdev-gnum[data-gvalue="' + label + '"]');
    numEls.forEach((numEl) => { numEl.textContent = gaugeNum(v); });
    if (unit) {
      const lblEls = document.querySelectorAll('.pdev-glabel[data-glabel="' + label + '"]');
      lblEls.forEach((lblEl) => { lblEl.textContent = label + " " + unit; });
    }
  }

  function paintPanelRanges(scope) {
    let ranges;
    if (scope && scope.matches && scope.matches("input[type=range].pdev-range")) {
      ranges = [scope];
    } else if (scope && scope.querySelectorAll) {
      ranges = scope.querySelectorAll("input[type=range].pdev-range");
    } else {
      ranges = document.querySelectorAll("input[type=range].pdev-range");
    }
    ranges.forEach((rng) => {
      const min = parseFloat(rng.min) || 0;
      const max = parseFloat(rng.max) || 100;
      const val = parseFloat(rng.value) || 0;
      const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;
      rng.style.setProperty("--fill", pct.toFixed(1) + "%");
    });
  }

  let _isBrowsingFile = false;

  function browseExe(cb) {
    if (_isBrowsingFile) return;
    _isBrowsingFile = true;
    apiFetch(API_BASE + "/api/dialog/browse?type=exe" + sessionTokenQuery())
      .then((r) => r.json())
      .then((d) => {
        _isBrowsingFile = false;
        cb(d && d.ok && d.path ? d.path : null);
      })
      .catch(() => {
        _isBrowsingFile = false;
        cb(null);
      });
  }

  function browseCustomIcon(cb) {
    if (_isBrowsingFile) return;
    _isBrowsingFile = true;
    apiFetch(API_BASE + "/api/dialog/browse?type=icon" + sessionTokenQuery())
      .then((r) => r.json())
      .then((d) => {
        _isBrowsingFile = false;
        cb(d && d.ok && d.path ? d.path : null);
      })
      .catch(() => {
        _isBrowsingFile = false;
        cb(null);
      });
  }

  function wireActionModal() {
    const modal = document.getElementById("panel-modal");
    if (!modal || !panelEdit) return;
    const typeEl = document.getElementById("pe-type");
    if (!typeEl) return;
    const appIconPreview = document.getElementById("pe-appicon-preview");
    const appIconStatus = document.getElementById("pe-appicon-status");

    // Live color picker and swatches wiring
    const colorInput = document.getElementById("pe-color");
    const colorBtn = document.getElementById("pe-color-btn");
    const colorPicker = document.getElementById("pe-color-picker");
    const colorRainbow = document.getElementById("pe-color-rainbow");
    const colorClear = document.getElementById("pe-color-clear");
    const liveBadge = document.getElementById("pe-icon-live-badge");

    const updateLiveBadgeColor = (c) => {
      if (!liveBadge) return;
      if (c && c.startsWith("#")) {
        liveBadge.style.background = c;
        liveBadge.style.borderColor = c;
        liveBadge.style.color = isLightColor(c) ? "#0a0a0a" : "#ffffff";
        liveBadge.style.boxShadow = `0 0 8px ${c}66`;
      } else if (c === "RAINBOW") {
        liveBadge.style.background = "linear-gradient(135deg, #ff0000, #ff7f00, #ffff00, #00ff00, #0000ff, #8b00ff)";
        liveBadge.style.borderColor = "#ffffff";
        liveBadge.style.color = "#0a0a0a";
        liveBadge.style.boxShadow = "0 0 8px rgba(255,255,255,0.4)";
      } else {
        liveBadge.style.background = "";
        liveBadge.style.borderColor = "";
        liveBadge.style.color = "";
        liveBadge.style.boxShadow = "";
      }
    };

    const updateColorBtn = (c) => {
      if (!colorBtn) return;
      const icon = colorBtn.querySelector(".pe-color-icon");
      if (c && c.startsWith("#")) {
        colorBtn.style.background = c;
        colorBtn.style.borderColor = c;
        const fg = isLightColor(c) ? "#0a0a0a" : "#ffffff";
        colorBtn.style.color = fg;
        if (icon) icon.style.color = fg;
      } else if (c === "RAINBOW") {
        colorBtn.style.background = "linear-gradient(135deg, #ff0000, #ff7f00, #ffff00, #00ff00, #0000ff, #8b00ff)";
        colorBtn.style.borderColor = "#ffffff";
        colorBtn.style.color = "#0a0a0a";
        if (icon) icon.style.color = "#0a0a0a";
      } else {
        colorBtn.style.background = "";
        colorBtn.style.borderColor = "";
        colorBtn.style.color = "";
        if (icon) icon.style.color = "";
      }
    };

    if (colorInput) {
      const initC = colorInput.value.trim();
      updateColorBtn(initC);
      updateLiveBadgeColor(initC);
    }

    if (colorInput && colorBtn && colorPicker) {
      colorBtn.addEventListener("click", () => colorPicker.click());
      colorPicker.addEventListener("input", (e) => {
        const val = e.target.value;
        colorInput.value = val;
        updateColorBtn(val);
        updateLiveBadgeColor(val);
      });
      if (colorRainbow) {
        colorRainbow.addEventListener("click", () => {
          colorInput.value = "RAINBOW";
          updateColorBtn("RAINBOW");
          updateLiveBadgeColor("RAINBOW");
        });
      }
      if (colorClear) {
        colorClear.addEventListener("click", () => {
          colorInput.value = "";
          updateColorBtn("");
          updateLiveBadgeColor("");
        });
      }
      colorInput.addEventListener("input", () => {
        const val = colorInput.value.trim();
        updateColorBtn(val);
        updateLiveBadgeColor(val);
      });
      modal.querySelectorAll(".pe-swatch").forEach((sw) => {
        sw.addEventListener("click", () => {
          const c = sw.getAttribute("data-color") || "";
          colorInput.value = c;
          if (c.startsWith("#") && (c.length === 7 || c.length === 4)) {
            colorPicker.value = c;
          }
          updateColorBtn(c);
          updateLiveBadgeColor(c);
        });
      });
    }

    // Visual Icon Selector wiring (HA-Style Floating Dropdown Popup + Custom Icon Browse)
    const iconInput = document.getElementById("pe-icon");
    const iconLiveBadge = document.getElementById("pe-icon-live-badge");
    const iconBrowseBtn = document.getElementById("pe-icon-browse-btn");
    const iconClearBtn = document.getElementById("pe-icon-clear-btn");
    const iconPopup = document.getElementById("pe-icon-popup");
    const iconSearch = document.getElementById("pe-icon-search");
    const iconGrid = document.getElementById("pe-icon-grid");
    let activeIconCategory = "all";
    let iconSearchTimer = null;

    const modalSlot = (panelEdit && (panelEdit.scope === "utility" || panelEdit.scope === "util"))
      ? ((panelDraft.panel_utility || [])[panelEdit.index] || {})
      : ((boardAtPath(panelEdit.path || [])[panelEdit.index]) || {});
    let customSelectedIconPath = (modalSlot && modalSlot.app_icon_path) || "";
    let curEntity = (modalSlot && (modalSlot.entity || (modalSlot.plugin && modalSlot.button_id ? (modalSlot.plugin + "." + modalSlot.button_id) : ""))) || "";
    if (!curEntity && modalSlot && modalSlot.openrgb_profile) {
      const matchEnt = (panelEntities || []).find((e) => e.openrgb_profile === modalSlot.openrgb_profile || e.name === modalSlot.openrgb_profile);
      if (matchEnt) curEntity = matchEnt.id;
    }

    function loadCustomIconPreview(path) {
      const p = (path || customSelectedIconPath || "").trim();
      const badge = document.getElementById("pe-icon-live-badge");
      if (!badge) return;
      if (!p) {
        if (badge._blobUrl) { URL.revokeObjectURL(badge._blobUrl); badge._blobUrl = null; }
        const nm = (iconInput ? iconInput.value : "") || "apps";
        badge.innerHTML = '<span class="md" id="pe-icon-live" data-md="' + esc(nm) + '">' + esc(mdiChar(nm)) + '</span>';
        mdiPreload([nm]);
        applyMdiIcons(badge);
        return;
      }
      customSelectedIconPath = p;
      apiFetch(API_BASE + "/api/panel/icon?path=" + encodeURIComponent(p) + sessionTokenQuery())
        .then((r) => {
          if (!r.ok) throw new Error("icon");
          const detectedColor = r.headers.get("X-Detected-Color");
          if (detectedColor && colorInput && (!colorInput.value || colorInput.value === "#000000" || colorInput.value === "transparent")) {
            colorInput.value = detectedColor;
            updateColorBtn(detectedColor);
            updateLiveBadgeColor(detectedColor);
          }
          return r.blob();
        })
        .then((blob) => {
          if (badge._blobUrl) URL.revokeObjectURL(badge._blobUrl);
          badge._blobUrl = URL.createObjectURL(blob);
          badge.innerHTML = '<img class="pe-icon-live-img" id="pe-icon-live-img" src="' + badge._blobUrl + '" alt="">';
        })
        .catch(() => {
          if (badge._blobUrl) { URL.revokeObjectURL(badge._blobUrl); badge._blobUrl = null; }
          badge.innerHTML = '<span class="md" id="pe-icon-live" data-md="apps"></span>';
          applyMdiIcons(badge);
        });
    }

    function updateLiveIcon(name) {
      const nm = (name || "").trim();
      const badge = document.getElementById("pe-icon-live-badge");
      if (!badge) return;
      if (customSelectedIconPath) {
        loadCustomIconPreview(customSelectedIconPath);
      } else if (nm) {
        if (badge._blobUrl) {
          URL.revokeObjectURL(badge._blobUrl);
          badge._blobUrl = null;
        }
        badge.innerHTML = '<span class="md" id="pe-icon-live" data-md="' + esc(nm) + '">' + esc(mdiChar(nm)) + '</span>';
        mdiPreload([nm]);
        applyMdiIcons(badge);
      } else {
        if (badge._blobUrl) {
          URL.revokeObjectURL(badge._blobUrl);
          badge._blobUrl = null;
        }
        badge.innerHTML = '<span class="md" id="pe-icon-live" data-md="border-none-variant" style="opacity:0.4;"></span>';
        mdiPreload(["border-none-variant"]);
        applyMdiIcons(badge);
      }
      if (iconGrid) {
        iconGrid.querySelectorAll(".pe-icon-item").forEach((item) => {
          item.classList.toggle("active", item.getAttribute("data-icon") === nm && !customSelectedIconPath);
        });
      }
    }

    if (customSelectedIconPath) {
      loadCustomIconPreview(customSelectedIconPath);
    } else if (iconInput) {
      updateLiveIcon(iconInput.value);
    }
    function syncIconClearBtn() {
      const peClear = document.getElementById("pe-icon-clear-btn");
      if (peClear && iconInput) {
        peClear.style.display = (iconInput.value && iconInput.value !== "toggle-switch") ? "" : "";
      }
    }

    if (iconClearBtn) {
      iconClearBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (iconInput) iconInput.value = "toggle-switch";
        updateLiveIcon("toggle-switch");
        if (iconPopup) iconPopup.style.display = "none";
      });
    }

    function getBaseIconList(cat) {
      if (cat && cat !== "all" && CATEGORIZED_MDI_ICONS[cat]) {
        return CATEGORIZED_MDI_ICONS[cat];
      }
      return ALL_MDI_ICONS;
    }

    function renderIconsToGrid(icons, activeName) {
      if (!iconGrid) return;
      let h = "";
      (icons || []).forEach((item) => {
        const ic = typeof item === "string" ? item : item.name;
        const ch = (typeof item === "object" && item.char) ? item.char : "";
        if (ch) mdiCache[ic] = ch;
        const aliases = (typeof item === "object" && item.aliases && item.aliases.length)
          ? ' (aliases: ' + item.aliases.join(", ") + ')' : "";
        h += '<button type="button" class="pe-icon-item' + (ic === activeName && !customSelectedIconPath ? " active" : "") + '" data-icon="' + esc(ic) + '" title="' + esc(ic) + esc(aliases) + '">' +
          '<span class="md" data-md="' + esc(ic) + '">' + esc(ch) + '</span>' +
        '</button>';
      });
      if (!icons || !icons.length) {
        h = '<div style="grid-column:1/-1;text-align:center;padding:16px;font-size:12px;color:var(--fg-dim);">No matching icons found</div>';
      }
      iconGrid.innerHTML = h;
      applyMdiIcons(iconGrid);

      iconGrid.querySelectorAll(".pe-icon-item").forEach((item) => {
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          const ic = item.getAttribute("data-icon");
          customSelectedIconPath = "";
          if (iconInput) iconInput.value = ic;
          updateLiveIcon(ic);
          if (iconPopup) iconPopup.style.display = "none";
          syncIconClearBtn();
        });
      });
    }

    function filterAndRenderIcons(q, cat) {
      const query = (q || "").trim().toLowerCase();
      const base = getBaseIconList(cat);
      let list = base;
      if (query) {
        list = base.filter((ic) => ic.toLowerCase().includes(query));
      }
      renderIconsToGrid(list, (iconInput ? iconInput.value : "").trim());
      mdiPreload(list.slice(0, 100));
      applyMdiIcons(iconGrid);
    }

    function searchMdiIcons(query, category) {
      const q = (query || "").trim();
      const cat = category || activeIconCategory;
      apiFetch(`${API_BASE}/api/mdi/search?q=${encodeURIComponent(q)}&cat=${encodeURIComponent(cat)}&limit=120`)
        .then((r) => r.json())
        .then((data) => {
          if (data && data.ok && data.icons && data.icons.length) {
            renderIconsToGrid(data.icons, (iconInput ? iconInput.value : "").trim());
          }
        })
        .catch(() => {});
    }

    function toggleIconPopup() {
      if (!iconPopup) return;
      const isOpen = iconPopup.style.display !== "none";
      if (isOpen) {
        iconPopup.style.display = "none";
      } else {
        iconPopup.style.display = "flex";
        if (iconSearch) iconSearch.value = "";
        filterAndRenderIcons("", activeIconCategory);
        searchMdiIcons("", activeIconCategory);
        setTimeout(() => { if (iconSearch) iconSearch.focus(); }, 50);
      }
    }

    if (iconInput) {
      iconInput.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleIconPopup();
      });
    }
    if (iconLiveBadge) {
      iconLiveBadge.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleIconPopup();
      });
    }

    if (iconSearch) {
      iconSearch.addEventListener("input", () => {
        clearTimeout(iconSearchTimer);
        const query = iconSearch.value.trim();
        filterAndRenderIcons(query, activeIconCategory);
        iconSearchTimer = setTimeout(() => {
          searchMdiIcons(query, activeIconCategory);
        }, 150);
      });
      iconSearch.addEventListener("click", (e) => {
        e.stopPropagation();
      });
    }

    const catPills = modal.querySelectorAll(".pe-icon-cat-pill");
    catPills.forEach((pill) => {
      pill.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        catPills.forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        activeIconCategory = pill.getAttribute("data-cat") || "all";
        const query = iconSearch ? iconSearch.value.trim() : "";
        filterAndRenderIcons(query, activeIconCategory);
        searchMdiIcons(query, activeIconCategory);
      });
    });

    // Icon Mode Tabs wiring (Auto, MDI, Custom File)
    const modeTabs = modal.querySelectorAll(".pe-icon-mode-tab");
    const paneAuto = document.getElementById("pe-pane-auto");
    const paneMdi = document.getElementById("pe-pane-mdi");
    const paneCustom = document.getElementById("pe-pane-custom");
    const customIconPathInput = document.getElementById("pe-custom-icon-path");
    const customLiveBadge = document.getElementById("pe-custom-live-badge");
    const customBrowseBtn = document.getElementById("pe-custom-browse-btn");
    const customClearBtn = document.getElementById("pe-custom-clear-btn");

    let currentIconMode = "auto";
    if (modalSlot && modalSlot.use_app_icon === false) {
      if (customSelectedIconPath && customSelectedIconPath !== modalSlot.shortcut_path) {
        currentIconMode = "custom";
      } else {
        currentIconMode = "mdi";
      }
    } else if (modalSlot && modalSlot.type && modalSlot.type !== "SHORTCUT" && modalSlot.type !== "MEDIA_EJECT" && !(modalSlot.entity && modalSlot.entity.startsWith("media."))) {
      if (customSelectedIconPath) {
        currentIconMode = "custom";
      } else {
        currentIconMode = "mdi";
      }
    }

    function setIconMode(mode) {
      currentIconMode = mode;
      modeTabs.forEach((tab) => {
        tab.classList.toggle("active", tab.getAttribute("data-mode") === mode);
      });
      if (paneAuto) paneAuto.style.display = (mode === "auto") ? "" : "none";
      if (paneMdi) paneMdi.style.display = (mode === "mdi") ? "" : "none";
      if (paneCustom) paneCustom.style.display = (mode === "custom") ? "" : "none";
      if (iconPopup && mode !== "mdi") iconPopup.style.display = "none";
    }

    modeTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        setIconMode(tab.getAttribute("data-mode"));
      });
    });
    setIconMode(currentIconMode);

    function updateCustomFilePreview(p) {
      if (!customLiveBadge) return;
      if (!p) {
        if (customLiveBadge._blobUrl) { URL.revokeObjectURL(customLiveBadge._blobUrl); customLiveBadge._blobUrl = null; }
        customLiveBadge.innerHTML = '<span class="md" data-md="image-outline"></span>';
        mdiPreload(["image-outline"]);
        applyMdiIcons(customLiveBadge);
        return;
      }
      apiFetch(API_BASE + "/api/panel/icon?path=" + encodeURIComponent(p) + sessionTokenQuery())
        .then((r) => {
          if (!r.ok) throw new Error("icon");
          const detectedColor = r.headers.get("X-Detected-Color");
          if (detectedColor && colorInput && (!colorInput.value || colorInput.value === "#000000" || colorInput.value === "transparent")) {
            colorInput.value = detectedColor;
            updateColorBtn(detectedColor);
            updateLiveBadgeColor(detectedColor);
          }
          return r.blob();
        })
        .then((blob) => {
          if (customLiveBadge._blobUrl) URL.revokeObjectURL(customLiveBadge._blobUrl);
          customLiveBadge._blobUrl = URL.createObjectURL(blob);
          customLiveBadge.innerHTML = '<img class="pe-icon-live-img" src="' + customLiveBadge._blobUrl + '" alt="">';
        })
        .catch(() => {
          customLiveBadge.innerHTML = '<span class="md" data-md="image-outline"></span>';
          applyMdiIcons(customLiveBadge);
        });
    }

    if (customBrowseBtn) {
      customBrowseBtn.addEventListener("click", () => {
        browseCustomIcon((p) => {
          if (p) {
            customSelectedIconPath = p;
            if (customIconPathInput) customIconPathInput.value = p;
            updateCustomFilePreview(p);
          }
        });
      });
    }

    if (customClearBtn) {
      customClearBtn.addEventListener("click", () => {
        customSelectedIconPath = "";
        if (customIconPathInput) customIconPathInput.value = "";
        updateCustomFilePreview("");
      });
    }

    if (customSelectedIconPath) {
      updateCustomFilePreview(customSelectedIconPath);
    }

    function loadAppIcon() {
      const p = (document.getElementById("pe-path") ? document.getElementById("pe-path").value : "").trim() ||
        (modalSlot.app_icon_path || ((modalSlot.entity === "media.player" || modalSlot.entity === "media.eject" || modalSlot.type === "MEDIA_EJECT") ? ((panelDraft && panelDraft.media_player_path) || "") : "") || "");
      if (!p) { appIconPreview.hidden = true; return; }
      const brandSvg = typeof getMediaPlayerBrandIcon === "function" ? getMediaPlayerBrandIcon(p) : null;
      if (brandSvg) {
        if (appIconPreview._blobUrl) { URL.revokeObjectURL(appIconPreview._blobUrl); appIconPreview._blobUrl = null; }
        appIconPreview.hidden = true;
        let wrap = document.getElementById("pe-appicon-svg-wrap");
        if (!wrap) {
          wrap = document.createElement("span");
          wrap.id = "pe-appicon-svg-wrap";
          wrap.className = "pe-appicon-svg-wrap";
          appIconPreview.parentNode.insertBefore(wrap, appIconPreview);
        }
        wrap.innerHTML = brandSvg;
        wrap.style.display = "inline-flex";
        if (appIconStatus) appIconStatus.textContent = "Brand vector icon loaded.";
        return;
      }
      const wrap = document.getElementById("pe-appicon-svg-wrap");
      if (wrap) wrap.style.display = "none";
      apiFetch(API_BASE + "/api/panel/icon?path=" + encodeURIComponent(p) + sessionTokenQuery())
        .then((r) => {
          if (!r.ok) throw new Error("icon");
          const detectedColor = r.headers.get("X-Detected-Color");
          if (detectedColor && colorInput && (!colorInput.value || colorInput.value === "#000000" || colorInput.value === "transparent")) {
            colorInput.value = detectedColor;
            updateColorBtn(detectedColor);
            updateLiveBadgeColor(detectedColor);
          }
          return r.blob();
        })
        .then((blob) => {
          if (appIconPreview._blobUrl) URL.revokeObjectURL(appIconPreview._blobUrl);
          appIconPreview._blobUrl = URL.createObjectURL(blob);
          appIconPreview.src = appIconPreview._blobUrl;
          appIconPreview.hidden = false;
        })
        .catch(() => { appIconPreview.hidden = true; });
    }
    let curEntityPlugin = "all";
    if (curEntity) {
      const matchEnt = (panelEntities || []).find((e) => e.id === curEntity || e.state_key === curEntity);
      if (matchEnt && matchEnt.plugin) {
        curEntityPlugin = matchEnt.plugin;
      } else if (modalSlot && modalSlot.plugin) {
        curEntityPlugin = modalSlot.plugin;
      } else if (curEntity.includes(".")) {
        curEntityPlugin = curEntity.split(".")[0];
      }
    }

    const syncFields = () => {
      const t = typeEl.value;
      const showGroupProf = t === "GROUP";
      const showPath = t === "SHORTCUT";
      const showAppIcon = t === "SHORTCUT";
      const showEnt = t === "TOGGLE" || t === "SENSOR" || t === "HOTKEY";
      const isAppShortcut = t === "SHORTCUT";
      const isEmpty = t === "EMPTY";

      const nameWrap = document.getElementById("pe-name-wrap");
      if (nameWrap) nameWrap.style.display = isEmpty ? "none" : "";
      const grpProfWrap = document.getElementById("pe-group-profile-wrap");
      if (grpProfWrap) grpProfWrap.style.display = showGroupProf ? "" : "none";
      const entWrap = document.getElementById("pe-entity-wrap");
      if (entWrap) entWrap.style.display = showEnt ? "" : "none";
      const pathWrap = document.getElementById("pe-path-wrap");
      if (pathWrap) pathWrap.style.display = showPath ? "" : "none";
      const argsWrap = document.getElementById("pe-args-wrap");
      if (argsWrap) argsWrap.style.display = showPath ? "" : "none";
      const entSelectEl = document.getElementById("pe-entity");
      const entPluginEl = document.getElementById("pe-entity-plugin");
      const entSearchEl = document.getElementById("pe-entity-search");

      const refreshEntityOptions = (targetEntity) => {
        if (!entSelectEl) return;
        const curVal = targetEntity !== undefined ? targetEntity : (curEntity || (entSelectEl ? entSelectEl.value : ""));
        const pFilter = entPluginEl ? entPluginEl.value : "all";
        const sQuery = entSearchEl ? entSearchEl.value : "";
        entSelectEl.innerHTML = buildEntityOptions(t, curVal, pFilter, sQuery);
        if (curVal && entSelectEl.querySelector(`option[value="${curVal}"]`)) {
          entSelectEl.value = curVal;
        } else {
          entSelectEl.value = "";
        }
        if (isAppShortcut || showGroupProf || isEmpty) {
          entSelectEl.value = "";
        }
      };

      if (entPluginEl && !entPluginEl._initialized) {
        entPluginEl._initialized = true;
        if (curEntityPlugin && curEntityPlugin !== "all") {
          entPluginEl.value = curEntityPlugin;
        }
      }
      refreshEntityOptions(curEntity);
      if (entPluginEl && !entPluginEl._wired) {
        entPluginEl._wired = true;
        entPluginEl.addEventListener("change", () => {
          refreshEntityOptions(curEntity);
        });
      }
      if (entSearchEl && !entSearchEl._wired) {
        entSearchEl._wired = true;
        entSearchEl.addEventListener("input", () => {
          refreshEntityOptions(curEntity);
        });
      }

      const entId = entSelectEl ? entSelectEl.value.trim() : "";
      const isMediaPlayPause = (entId === "media.play_pause");
      const isMediaEject = (entId === "media.player" || entId === "media.eject" || t === "MEDIA_EJECT");
      const isAnyMediaControl = (isMediaPlayPause || entId === "media.next" || entId === "media.prev" || isMediaEject);
      const isAudio = t === "AUDIO OUTPUT";
      const audioWrap = document.getElementById("pe-audio-output-wrap");
      if (audioWrap) audioWrap.style.display = isAudio ? "" : "none";

      const showKeys = (t !== "EMPTY" && t !== "AUDIO OUTPUT") && !isAnyMediaControl;
      const keysWrap = document.getElementById("pe-keys-wrap");
      if (keysWrap) keysWrap.style.display = showKeys ? "" : "none";

      const modeAutoTab = document.getElementById("pe-mode-auto");
      const hasAutoIcon = (isAppShortcut || isMediaEject);
      if (modeAutoTab) modeAutoTab.style.display = hasAutoIcon ? "" : "none";
      if (!hasAutoIcon && currentIconMode === "auto") {
        setIconMode("mdi");
      }

      const iconSourceControl = document.getElementById("pe-icon-source-control");
      if (iconSourceControl) iconSourceControl.style.display = isAudio ? "none" : "";

      const visualCol = document.getElementById("pe-visual-col");
      const bodyGrid = document.getElementById("pe-body-grid");
      const modalCard = modal.querySelector(".panel-modal");
      const hideVisual = isEmpty;
      if (visualCol) visualCol.style.display = hideVisual ? "none" : "";
      if (bodyGrid) bodyGrid.style.gridTemplateColumns = (hideVisual || isAudio) ? "1fr" : "";
      if (modalCard) modalCard.style.maxWidth = (hideVisual || isAudio) ? "480px" : "";

      if (hasAutoIcon) {
        try { loadAppIcon(); } catch (e) { appIconPreview.hidden = true; }
      } else if (appIconPreview) appIconPreview.hidden = true;
    };
    typeEl.addEventListener("change", syncFields);
    syncFields();

    // Entity Quick-Fill auto-population
    const entSelect = document.getElementById("pe-entity");
    if (entSelect) {
      entSelect.addEventListener("change", () => {
        const entId = entSelect.value.trim();
        curEntity = entId;
        const found = (panelEntities || []).find((e) => e.id === entId);
        if (found) {
          const nameInp = document.getElementById("pe-name");
          if (nameInp && (!nameInp.value || nameInp.value === "New Action" || nameInp.value === "HUD Overlay")) nameInp.value = found.name;
          if (found.icon && iconInput) {
            iconInput.value = found.icon;
            updateLiveIcon(found.icon);
          }
          if (found.color && colorInput && !found.id.startsWith("media.")) {
            colorInput.value = found.color;
            updateColorBtn(found.color);
            updateLiveBadgeColor(found.color);
          } else if ((!found.color || found.id.startsWith("media.")) && colorInput) {
            colorInput.value = "";
            updateColorBtn("");
            updateLiveBadgeColor("");
          }
          if (found.default_hotkey && !found.id.startsWith("media.")) {
            const keysInp = document.getElementById("pe-keys");
            if (keysInp) keysInp.value = found.default_hotkey;
          } else if (found.id.startsWith("media.")) {
            const keysInp = document.getElementById("pe-keys");
            if (keysInp) keysInp.value = "";
          }
          if (found.id === "media.player" || found.id === "media.eject") {
            const nameEl = document.getElementById("pe-name");
            if (nameEl) nameEl.value = getMediaPlayerAppName();
            const appIconInp = document.getElementById("pe-use-app-icon");
            if (appIconInp) appIconInp.checked = true;
            const artInp = document.getElementById("pe-show-album-art");
            if (artInp) artInp.checked = true;
          }
          if (found.openrgb_profile || found.plugin === "openrgb" || found.id.startsWith("openrgb.")) {
            if (typeEl.value !== "HOTKEY" && typeEl.value !== "TOGGLE") {
              typeEl.value = "HOTKEY";
            }
          } else if (found.type === "data") typeEl.value = "SENSOR";
          else if (found.type === "action") typeEl.value = "HOTKEY";
          else if (found.type === "shortcut") typeEl.value = "SHORTCUT";
          else if (found.type === "status" || found.writable) typeEl.value = "TOGGLE";
          else typeEl.value = "SENSOR";
          syncFields();
        } else {
          curEntity = "";
          syncFields();
        }
      });
    }

    document.getElementById("pe-browse").addEventListener("click", () => {
      browseExe((p) => {
        if (p) {
          document.getElementById("pe-path").value = p;
          const nameInp = document.getElementById("pe-name");
          if (nameInp && (!nameInp.value || nameInp.value === "New Action")) {
            const rawBase = p.split(/[\\/]/).pop() || "";
            nameInp.value = rawBase.replace(/\.[^/.]+$/, "");
          }
          loadAppIcon();
        }
      });
    });
    let iconTimer = null;
    document.getElementById("pe-path").addEventListener("input", () => {
      clearTimeout(iconTimer);
      iconTimer = setTimeout(() => {
        const pathVal = (document.getElementById("pe-path") ? document.getElementById("pe-path").value : "").trim();
        const isUrl = pathVal.startsWith("http://") || pathVal.startsWith("https://") || (pathVal.includes(".") && (pathVal.includes("/") || !pathVal.includes("\\")) && !pathVal.endsWith(".exe"));
        const nameInp = document.getElementById("pe-name");
        if (isUrl && nameInp && (!nameInp.value || nameInp.value === "New Action")) {
          try {
            let u = pathVal.startsWith("http") ? pathVal : ("https://" + pathVal);
            let host = new URL(u).hostname.replace(/^www\./i, "");
            let domainName = host.split(".")[0];
            if (domainName) nameInp.value = domainName.charAt(0).toUpperCase() + domainName.slice(1);
          } catch (_) {}
        }
        loadAppIcon();
      }, 400);
    });

    // Hotkey capture: toggle via Capture button; input always typable
    (function() {
      var keysInp = document.getElementById("pe-keys");
      var capBtn = document.getElementById("pe-hotkey-capture-btn");
      if (!keysInp || !capBtn) return;
      var capturing = false;
      var CODE_MAP = {
        "Digit1":"1","Digit2":"2","Digit3":"3","Digit4":"4","Digit5":"5",
        "Digit6":"6","Digit7":"7","Digit8":"8","Digit9":"9","Digit0":"0",
        "KeyA":"a","KeyB":"b","KeyC":"c","KeyD":"d","KeyE":"e","KeyF":"f",
        "KeyG":"g","KeyH":"h","KeyI":"i","KeyJ":"j","KeyK":"k","KeyL":"l",
        "KeyM":"m","KeyN":"n","KeyO":"o","KeyP":"p","KeyQ":"q","KeyR":"r",
        "KeyS":"s","KeyT":"t","KeyU":"u","KeyV":"v","KeyW":"w","KeyX":"x",
        "KeyY":"y","KeyZ":"z",
        "F1":"F1","F2":"F2","F3":"F3","F4":"F4","F5":"F5","F6":"F6",
        "F7":"F7","F8":"F8","F9":"F9","F10":"F10","F11":"F11","F12":"F12",
        "F13":"F13","F14":"F14","F15":"F15","F16":"F16","F17":"F17","F18":"F18",
        "F19":"F19","F20":"F20","F21":"F21","F22":"F22","F23":"F23","F24":"F24",
        "Space":"Space","Enter":"Enter","Backspace":"Backspace","Tab":"Tab","Escape":"Esc",
        "Delete":"Delete","Insert":"Insert","Home":"Home","End":"End",
        "PageUp":"PageUp","PageDown":"PageDown",
        "ArrowUp":"Up","ArrowDown":"Down","ArrowLeft":"Left","ArrowRight":"Right",
        "CapsLock":"CapsLock","NumLock":"NumLock","ScrollLock":"ScrollLock",
        "Minus":"-","Equal":"=","BracketLeft":"[","BracketRight":"]",
        "Semicolon":";","Quote":"'","Backquote":"`","Backslash":"\\",
        "Comma":",","Period":".","Slash":"/",
        "Numpad0":"Numpad0","Numpad1":"Numpad1","Numpad2":"Numpad2",
        "Numpad3":"Numpad3","Numpad4":"Numpad4","Numpad5":"Numpad5",
        "Numpad6":"Numpad6","Numpad7":"Numpad7","Numpad8":"Numpad8","Numpad9":"Numpad9",
        "NumpadEnter":"NumpadEnter","NumpadAdd":"NumpadAdd","NumpadSubtract":"NumpadSubtract",
        "NumpadMultiply":"NumpadMultiply","NumpadDivide":"NumpadDivide",
        "NumpadDecimal":"NumpadDecimal"
      };
      function validateHotkeyConflict(hotkeyVal) {
        if (!hotkeyVal || typeof hotkeyVal !== "string") return null;
        var cand = hotkeyVal.trim().toLowerCase().replace(/\s+/g, "");
        if (!cand || cand === "conflict!!") return null;

        var cfgO = (typeof panelLive !== "undefined" && panelLive.config) || (typeof featureConfig !== "undefined" && featureConfig) || {};
        var overlayHk = (cfgO.hotkey_overlay || "Ctrl+Alt+I").trim().toLowerCase().replace(/\s+/g, "");
        var toolbarHk = (cfgO.hotkey_toolbar || "Ctrl+Alt+T").trim().toLowerCase().replace(/\s+/g, "");

        if (cand === overlayHk) return "Overlay Shortcut";
        if (cand === toolbarHk) return "Toolbar Shortcut";

        var draft = (typeof panelDraft !== "undefined" && panelDraft) || {};
        var editIdx = (panelEdit && panelEdit.index !== undefined) ? panelEdit.index : -1;
        var editScope = (panelEdit && panelEdit.scope) || "board";

        var mainBoard = draft.panel_board || [];
        for (var i = 0; i < mainBoard.length; i++) {
          if (editScope === "board" && editIdx === i) continue;
          var s = mainBoard[i];
          var sHk = (s && (s.hotkey || s.default_hotkey) || "").trim().toLowerCase().replace(/\s+/g, "");
          if (sHk && sHk === cand) return s.name || ("Button " + (i + 1));
        }

        var profiles = draft.panel_profiles || [];
        for (var p = 0; p < profiles.length; p++) {
          var prof = profiles[p];
          var pBoard = (prof && prof.board) || [];
          for (var j = 0; j < pBoard.length; j++) {
            if (editScope === prof.id && editIdx === j) continue;
            var ps = pBoard[j];
            var psHk = (ps && (ps.hotkey || ps.default_hotkey) || "").trim().toLowerCase().replace(/\s+/g, "");
            if (psHk && psHk === cand) return ps.name || (prof.name || "Profile Button");
          }
        }
        return null;
      }

      var conflictTimer = null;
      function checkAndApplyConflict(val) {
        var conflict = validateHotkeyConflict(val);
        if (conflict) {
          clearTimeout(conflictTimer);
          keysInp.value = "Conflict !!";
          keysInp.style.borderColor = "#ff3355";
          keysInp.style.color = "#ff3355";
          keysInp.setAttribute("title", "Conflicts with " + conflict);
          conflictTimer = setTimeout(function() {
            keysInp.style.borderColor = "";
            keysInp.style.color = "";
          }, 2200);
          return true;
        } else {
          keysInp.style.borderColor = "";
          keysInp.style.color = "";
          keysInp.removeAttribute("title");
          return false;
        }
      }

      function setCapture(on) {
        capturing = on;
        capBtn.textContent = on ? "Recording..." : "Capture";
        capBtn.classList.toggle("pe-hotkey-capture-active", on);
        keysInp.readOnly = on;
        if (on) keysInp.focus();
      }
      capBtn.addEventListener("click", function() { setCapture(!capturing); });
      keysInp.addEventListener("keydown", function(e) {
        if (!capturing) {
          // Auto-pair quotes: typing " inserts "" with the caret between them.
          if (e.key === '"') {
            e.preventDefault();
            var val = keysInp.value, start = keysInp.selectionStart, end = keysInp.selectionEnd;
            if (start === end) {
              keysInp.value = val.slice(0, start) + '""' + val.slice(end);
              keysInp.setSelectionRange(start + 1, start + 1);
            } else {
              keysInp.value = val.slice(0, start) + '"' + val.slice(start, end) + '"' + val.slice(end);
              keysInp.setSelectionRange(start + 1, end + 1);
            }
            return;
          }
          return;
        }
        if (e.key === "Escape") { setCapture(false); e.preventDefault(); return; }
        if (e.key === "Backspace" || e.key === "Delete") { keysInp.value = ""; e.preventDefault(); return; }
        var mod = [];
        if (e.ctrlKey) mod.push("Ctrl");
        if (e.altKey) mod.push("Alt");
        if (e.shiftKey) mod.push("Shift");
        var token = CODE_MAP[e.code];
        if (!token) return;
        var candHk = mod.length ? mod.join("+") + "+" + token : token;
        setCapture(false);
        e.preventDefault();
        if (!checkAndApplyConflict(candHk)) {
          keysInp.value = candHk;
        }
      });
      keysInp.addEventListener("input", function() {
        var val = this.value.trim();
        if (val && val !== "Conflict !!") {
          checkAndApplyConflict(val);
        }
      });
      keysInp.addEventListener("blur", function() { if (capturing) setCapture(false); });
    })();

    const peNewProf = document.getElementById("pe-new-profile-btn");
    if (peNewProf) {
      peNewProf.addEventListener("click", () => {
        if (!panelDraft.panel_profiles) panelDraft.panel_profiles = [];
        const pName = (document.getElementById("pe-name") ? document.getElementById("pe-name").value.trim() : "") || "New Group Profile";
        const newProf = {
          id: uniqueProfileId(),
          name: pName,
          is_group: true,
          exe: "",
          enabled: true,
          board: []
        };
        panelDraft.panel_profiles.push(newProf);
        setPanelDirty(true);
        const sel = document.getElementById("pe-group-profile");
        if (sel) {
          const opt = document.createElement("option");
          opt.value = newProf.id;
          opt.textContent = newProf.name;
          opt.selected = true;
          sel.appendChild(opt);
        }
      });
    }

    document.getElementById("pe-cancel").addEventListener("click", () => {
      panelEdit = null;
      renderPanel();
    });
    const moveSlot = (delta) => {
      const list = boardAtPath(panelEdit.path || []);
      const j = panelEdit.index + delta;
      if (j < 0 || j >= list.length) return;
      const t = list[panelEdit.index]; list[panelEdit.index] = list[j]; list[j] = t;
      panelEdit = null;
      setPanelDirty(true);
      renderPanel();
    };
    const upBtn = document.getElementById("pe-up");
    if (upBtn) upBtn.addEventListener("click", () => moveSlot(-1));
    const downBtn = document.getElementById("pe-down");
    if (downBtn) downBtn.addEventListener("click", () => moveSlot(1));
    const delBtn = document.getElementById("pe-delete");
    if (delBtn) delBtn.addEventListener("click", () => {
      const list = boardAtPath(panelEdit.path || []);
      list.splice(panelEdit.index, 1);
      panelEdit = null;
      setPanelDirty(true);
      renderPanel();
    });
    document.getElementById("pe-save").addEventListener("click", () => {
      const t = document.getElementById("pe-type").value;
      const isApp = t === "SHORTCUT";
      const isGroup = t === "GROUP";
      const isEmpty = t === "EMPTY";
      const canHaveEntity = (t === "TOGGLE" || t === "SENSOR" || t === "HOTKEY");
      const entId = canHaveEntity && document.getElementById("pe-entity") ? document.getElementById("pe-entity").value.trim() : "";
      const entObj = entId ? (panelEntities || []).find((e) => e.id === entId) : null;
      const isActionEntity = entObj && (entObj.type === "action" || entObj.type === "shortcut");
      const hasStateCapability = canHaveEntity && !isActionEntity && (t === "TOGGLE" || t === "SENSOR" || (entObj && (entObj.type === "status" || entObj.type === "data" || !!entObj.state_key)));

      const isMediaEject = (entId === "media.player" || entId === "media.eject" || t === "MEDIA_EJECT");
      const showName = document.getElementById("pe-show-name") ? document.getElementById("pe-show-name").checked : true;
      const showIcon = document.getElementById("pe-show-icon") ? document.getElementById("pe-show-icon").checked : true;
      const showAlbumArt = isMediaEject && document.getElementById("pe-show-album-art") ? document.getElementById("pe-show-album-art").checked : false;
      const showState = (hasStateCapability && document.getElementById("pe-show-state")) ? document.getElementById("pe-show-state").checked : false;
      const showProgressFill = document.getElementById("pe-show-progress-fill") ? document.getElementById("pe-show-progress-fill").checked : true;
      const selectedMdi = document.getElementById("pe-icon") ? document.getElementById("pe-icon").value.trim() : "";

      let finalIcon = "toggle-switch";
      let finalAppIconPath = null;
      let finalUseAppIcon = false;

      if (currentIconMode === "auto") {
        finalUseAppIcon = true;
        finalIcon = "application";
        finalAppIconPath = isApp ? (document.getElementById("pe-path").value.trim() || null) : null;
      } else if (currentIconMode === "custom") {
        finalUseAppIcon = true;
        finalIcon = "apps";
        finalAppIconPath = customSelectedIconPath || null;
      } else { // "mdi"
        finalUseAppIcon = false;
        finalIcon = selectedMdi || "toggle-switch";
        finalAppIconPath = null;
      }

      const entSelectEl = document.getElementById("pe-entity");
      const entPluginEl = document.getElementById("pe-entity-plugin");
      const resolvedEntId = (canHaveEntity && entSelectEl && entSelectEl.value) ? entSelectEl.value.trim() : (modalSlot.entity || curEntity || "");
      let targetEntObj = resolvedEntId ? (panelEntities || []).find((e) => e.id === resolvedEntId || e.state_key === resolvedEntId || (e.plugin && e.button_id && `${e.plugin}.${e.button_id}` === resolvedEntId)) : null;

      if (!targetEntObj && resolvedEntId && resolvedEntId.includes(".")) {
        const [p, b] = resolvedEntId.split(".", 2);
        targetEntObj = (panelEntities || []).find((e) => (e.plugin === p || e.id.startsWith(p + ".")) && (e.button_id === b || e.state_key === b || e.id === resolvedEntId));
      }

      const slot = {
        name: (document.getElementById("pe-name") ? document.getElementById("pe-name").value.trim() : ""),
        type: t,
        show_name: showName,
        show_icon: showIcon,
        use_app_icon: finalUseAppIcon,
        show_album_art: showAlbumArt,
        show_state: showState,
        show_progress_fill: showProgressFill,
        icon: finalIcon,
        app_icon_path: finalAppIconPath,
        color: (document.getElementById("pe-color") ? document.getElementById("pe-color").value.trim() : ""),
      };
      if (resolvedEntId) {
        slot.entity = resolvedEntId;
        const [defaultPlg, defaultBid] = resolvedEntId.includes(".") ? resolvedEntId.split(".", 2) : [resolvedEntId, ""];
        slot.plugin = defaultPlg;
        slot.button_id = defaultBid;
        slot.state_key = defaultBid;
      }
      if (targetEntObj) {
        if (targetEntObj.plugin) slot.plugin = targetEntObj.plugin;
        if (targetEntObj.button_id) slot.button_id = targetEntObj.button_id;
        if (targetEntObj.openrgb_profile) slot.openrgb_profile = targetEntObj.openrgb_profile;
        if (targetEntObj.action_id) slot.action_id = targetEntObj.action_id;
        if (targetEntObj.state_key) slot.state_key = targetEntObj.state_key;
        if (targetEntObj.labels) slot.labels = targetEntObj.labels;
        if (targetEntObj.color) slot.colors = { on: targetEntObj.color };
      } else if (modalSlot && (modalSlot.plugin || modalSlot.state_key)) {
        if (modalSlot.plugin) slot.plugin = modalSlot.plugin;
        if (modalSlot.button_id) slot.button_id = modalSlot.button_id;
        if (modalSlot.state_key) slot.state_key = modalSlot.state_key;
        if (modalSlot.labels) slot.labels = modalSlot.labels;
        if (modalSlot.colors) slot.colors = modalSlot.colors;
      }
      if (t === "SHORTCUT") {
        slot.shortcut_path = document.getElementById("pe-path").value.trim();
        const sArgs = document.getElementById("pe-args") ? document.getElementById("pe-args").value.trim() : "";
        if (sArgs) slot.shortcut_args = sArgs;
        if (currentIconMode === "auto") {
          slot.app_icon_path = slot.shortcut_path || null;
        }
      }
      if (t === "AUDIO OUTPUT") {
        const primSel = document.getElementById("pe-audio-primary");
        const altSel = document.getElementById("pe-audio-alt");
        slot.audio_input_device_id = primSel ? primSel.value : "";
        slot.audio_input_device_name = (primSel && primSel.value && primSel.selectedOptions && primSel.selectedOptions[0]) ? primSel.selectedOptions[0].text : "";
        slot.audio_input_device_id_alt = altSel ? altSel.value : "";
        slot.audio_input_device_name_alt = (altSel && altSel.value && altSel.selectedOptions && altSel.selectedOptions[0]) ? altSel.selectedOptions[0].text : "";
        slot.audio_primary_icon = (document.getElementById("pe-audio-primary-icon") ? document.getElementById("pe-audio-primary-icon").value.trim() : "") || "speaker";
        slot.audio_alt_icon = (document.getElementById("pe-audio-alt-icon") ? document.getElementById("pe-audio-alt-icon").value.trim() : "") || "headphones";
        slot.icon = slot.audio_primary_icon;
        if (!slot.name) slot.name = "Audio";
      }
      if (t === "GROUP") {
        const grpProfEl = document.getElementById("pe-group-profile");
        slot.target_profile = (grpProfEl && grpProfEl.value) ? grpProfEl.value : "";
        slot.profile_id = slot.target_profile;
      }
      if (t !== "EMPTY" && t !== "AUDIO OUTPUT") {
        let val = document.getElementById("pe-keys") ? document.getElementById("pe-keys").value.trim() : "";
        if (val === "Conflict !!") val = "";
        slot.hotkey = val;
        const numList = val.split(",").map((x) => parseInt(x.trim(), 10)).filter((n) => !isNaN(n));
        slot.keys = numList.length ? numList : (val ? [val] : []);
      }
      if (panelEdit.scope === "utility" || panelEdit.scope === "util") {
        if (!panelDraft.panel_utility) panelDraft.panel_utility = [{}, {}, {}, {}];
        while (panelDraft.panel_utility.length < 4) panelDraft.panel_utility.push({ type: "EMPTY" });
        panelDraft.panel_utility[panelEdit.index] = slot;
      } else {
        const list = boardAtPath(panelEdit.path || []);
        if (panelEdit.index < 0) list.push(slot);
        else {
          if (slot.type === "GROUP" && list[panelEdit.index] && list[panelEdit.index].children) {
            slot.children = list[panelEdit.index].children;
          }
          list[panelEdit.index] = slot;
        }
      }
      panelEdit = null;
      setPanelDirty(true);
      renderPanel();
    });
  }

  function wireWizard() {
    document.querySelectorAll(".vision-step").forEach((el) => {
      if (el.style.cursor === "pointer") {
        el.addEventListener("click", () => {
          wizardStep = parseInt(el.dataset.step, 10);
          renderVisionWizard();
        });
      }
    });

    const cancelBtn = document.getElementById("wizard-cancel-btn");
    if (cancelBtn) cancelBtn.addEventListener("click", exitWizard);

    const backBtn = document.getElementById("wizard-back-btn");
    if (backBtn) {
      backBtn.addEventListener("click", () => {
        wizardStep = Math.max(1, wizardStep - 1);
        renderVisionWizard();
      });
    }

    const nextBtn = document.getElementById("wizard-next-btn");
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (!collectStep()) return;
        wizardStep += 1;
        renderVisionWizard();
      });
    }

    const captureBtn = document.getElementById("capture-btn");
    if (captureBtn) captureBtn.addEventListener("click", runCapture);

    if (wizardStep === 2) {
      const isOcr = visionDraft.mode === "ocr_text" || visionDraft.mode === "ocr_number";
      if (!isOcr) initEyedropper();

      document.querySelectorAll(".vision-mode-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
          const cat = tab.dataset.modeCat;
          if (cat === "pixel") {
            visionDraft.mode = "color_percentage";
          } else if (cat === "ocr_text") {
            visionDraft.mode = "ocr_text";
            if (!visionDraft.ocr_pattern && wizardCapture && wizardCapture.detected_text) {
              visionDraft.ocr_pattern = wizardCapture.detected_text.trim();
            }
          } else if (cat === "ocr_number") {
            visionDraft.mode = "ocr_number";
          }
          renderVisionWizard();
        });
      });

      document.querySelectorAll(".ocr-word-chip").forEach((chip) => {
        chip.addEventListener("click", () => {
          visionDraft.ocr_pattern = chip.dataset.word;
          document.querySelectorAll(".ocr-word-chip").forEach((c) => c.classList.remove("selected"));
          chip.classList.add("selected");
          const patInput = document.getElementById("wz-step2-pattern");
          if (patInput) patInput.value = chip.dataset.word;
        });
      });

      const patInput = document.getElementById("wz-step2-pattern");
      if (patInput) {
        patInput.addEventListener("input", () => {
          visionDraft.ocr_pattern = patInput.value;
        });
      }

      const copyBtn = document.getElementById("ocr-copy-btn");
      if (copyBtn) {
        copyBtn.addEventListener("click", () => {
          const text = wizardCapture ? (wizardCapture.detected_text || "") : "";
          if (!text) return;
          copyTextNative(text).then(() => {
            copyBtn.innerHTML = '<span class="material-icons-outlined" style="color:var(--neon-grn)">check</span>';
            setTimeout(() => {
              copyBtn.innerHTML = '<span class="material-icons-outlined">content_copy</span>';
            }, 1500);
          }).catch(() => {});
        });
      }
    }

    const exeInput = document.getElementById("wizard-exe");
    if (exeInput) {
      exeInput.addEventListener("input", () => {
        visionDraft.exe = exeInput.value.trim();
      });
    }

    if (wizardStep === 4 || (wizardStep === 5 && visionDraft && visionDraft.id)) wireConfigureStep();

    const saveBtn = document.getElementById("wizard-save-btn");
    if (saveBtn) saveBtn.addEventListener("click", saveWizard);

    if (wizardStep === 5) startTestPoll();
  }

  function collectStep() {
    const nameInput = document.getElementById("wz-name");
    if (nameInput) {
      visionDraft.name = nameInput.value.trim();
      visionDraft.event_name = visionDraft.name;
    }
    const patStep2 = document.getElementById("wz-step2-pattern");
    if (patStep2) {
      visionDraft.ocr_pattern = patStep2.value.trim();
    }
    const patStep4 = document.getElementById("wz-ocr-pattern");
    if (patStep4) {
      visionDraft.ocr_pattern = patStep4.value.trim();
    }
    if (wizardStep === 1 && !wizardCapture) {
      const st = document.getElementById("capture-status");
      if (st) st.textContent = "Capture a region first.";
      return false;
    }
    if (wizardStep === 3 && !visionDraft.exe) {
      const exe = document.getElementById("wizard-exe");
      if (exe) exe.focus();
      return false;
    }
    return true;
  }

  function wireConfigureStep() {
    const recaptureBtn = document.getElementById("wz-recapture");
    if (recaptureBtn) recaptureBtn.addEventListener("click", () => runCapture({ preservePixel: true }));

    const modeSel = document.getElementById("wz-mode");
    if (modeSel) modeSel.addEventListener("change", () => {
      visionDraft.mode = modeSel.value;
      renderVisionWizard();
    });
    const ocrPat = document.getElementById("wz-ocr-pattern");
    if (ocrPat) ocrPat.addEventListener("input", () => {
      visionDraft.ocr_pattern = ocrPat.value;
    });
    const ocrMatch = document.getElementById("wz-ocr-match-type");
    if (ocrMatch) ocrMatch.addEventListener("change", () => {
      visionDraft.ocr_match_type = ocrMatch.value;
    });
    const ocrCase = document.getElementById("wz-ocr-case");
    if (ocrCase) ocrCase.addEventListener("click", () => {
      visionDraft.ocr_case_sensitive = ocrCase.classList.toggle("on");
    });
    const colorInput = document.getElementById("wz-color");
    const colorHex = document.getElementById("wz-color-hex");
    if (colorInput) colorInput.addEventListener("input", () => {
      visionDraft.color = colorInput.value;
      if (colorHex) colorHex.value = colorInput.value;
    });
    if (colorHex) colorHex.addEventListener("input", () => {
      visionDraft.color = colorHex.value;
      if (colorInput) colorInput.value = colorHex.value;
    });
    const tol = document.getElementById("wz-tolerance");
    if (tol) tol.addEventListener("input", () => {
      visionDraft.tolerance = parseFloat(tol.value) || 0;
    });
    const thr = document.getElementById("wz-threshold");
    if (thr) thr.addEventListener("input", () => {
      visionDraft.threshold = parseFloat(thr.value) || 0;
    });
    const dir = document.getElementById("wz-direction");
    if (dir) dir.addEventListener("change", () => {
      visionDraft.direction = dir.value;
    });
    const rate = document.getElementById("wz-poll-rate");
    if (rate) rate.addEventListener("input", () => {
      visionDraft.poll_rate = parseFloat(rate.value) || 1;
    });
    const cool = document.getElementById("wz-cooldown");
    if (cool) cool.addEventListener("input", () => {
      visionDraft.cooldown_s = parseFloat(cool.value) || 0;
    });
    const en = document.getElementById("wz-name");
    if (en) en.addEventListener("input", () => {
      visionDraft.name = en.value.trim();
      visionDraft.event_name = visionDraft.name;
    });
    const em = document.getElementById("wz-event-msg");
    if (em) em.addEventListener("input", () => {
      visionDraft.event_message = em.value.trim();
    });
    const out = document.getElementById("wz-output");
    if (out) out.addEventListener("click", () => {
      visionDraft.output_display = out.classList.toggle("on");
    });
    const fn = document.getElementById("wz-flash-name");
    if (fn) fn.addEventListener("click", () => {
      visionDraft.flash_name = fn.classList.toggle("on");
    });
    const ps = document.getElementById("wz-play-sound");
    if (ps) ps.addEventListener("click", () => {
      visionDraft.play_sound = ps.classList.toggle("on");
    });
    const fg = document.getElementById("wz-require-fg");
    if (fg) fg.addEventListener("click", () => {
      visionDraft.require_foreground = fg.classList.toggle("on");
    });
  }

  function initEyedropper() {
    const canvas = document.getElementById("vision-preview-canvas");
    if (!canvas) return;
    const img = new Image();
    img.onload = function () {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0);
      canvas.addEventListener("click", (e) => {
        const rect = canvas.getBoundingClientRect();
        const scaleX = img.naturalWidth / rect.width;
        const scaleY = img.naturalHeight / rect.height;
        const x = Math.floor((e.clientX - rect.left) * scaleX);
        const y = Math.floor((e.clientY - rect.top) * scaleY);
        if (x < 0 || y < 0 || x >= img.naturalWidth || y >= img.naturalHeight) return;
        const px = ctx.getImageData(x, y, 1, 1).data;
        const hex = "#" + [px[0], px[1], px[2]].map((v) =>
          v.toString(16).padStart(2, "0")).join("");
        visionDraft.color = hex;
        visionDraft.pixel = {
          x_pct: Math.round((x / img.naturalWidth) * 1000) / 10,
          y_pct: Math.round((y / img.naturalHeight) * 1000) / 10,
        };
        const swatch = document.getElementById("vision-swatch");
        const hexEl = document.getElementById("vision-color-hex");
        if (swatch) swatch.style.background = hex;
        if (hexEl) hexEl.textContent = hex;
      });
    };
    img.src = "data:image/png;base64," + wizardCapture.screenshot_b64;
  }

  async function runCapture(opts) {
    if (window.pywebview && window.pywebview.api) {
      try { await window.pywebview.api.hide_panel(); } catch (_) {}
    }
    const btn = document.getElementById("capture-btn");
    const status = document.getElementById("capture-status");
    if (btn) { btn.disabled = true; btn.textContent = "Drag a region on screen…"; }
    if (status) status.textContent = "";
    try {
      const res = await apiFetch(`${API_BASE}/api/vision/capture`, { method: "POST" });
      if (res.status === 403) {
        if (btn) { btn.disabled = false; btn.textContent = "Capture Region"; }
        if (status) status.textContent = "Region capture is only available from the desktop panel.";
        return;
      }
      if (res.status === 409) {
        if (btn) { btn.disabled = false; btn.textContent = "Capture Region"; }
        if (status) status.textContent = "A capture is already in progress — try again.";
        return;
      }
      const data = await res.json();
      if (data.cancelled) {
        if (status) status.textContent = "Cancelled — try again.";
      } else {
        wizardCapture = data;
        Object.assign(visionDraft, {
          exe: data.exe || "",
          anchor: data.anchor,
          region: data.region,
        });
        if (!(opts && opts.preservePixel)) {
          visionDraft.pixel = { x_pct: 50, y_pct: 50 };
        }
        if (visionDraft && visionDraft.id) {
          renderVisionWizard();
        } else {
          wizardStep = 2;
          renderVisionWizard();
        }
      }
    } catch (_) {
      if (status) status.textContent = "Capture failed — try again.";
    } finally {
      if (window.pywebview && window.pywebview.api) {
        try { await window.pywebview.api.show_panel(); } catch (_) {}
      }
    }
  }

  function saveWizard() {
    const nameInput = document.getElementById("wz-name");
    if (nameInput) {
      visionDraft.name = nameInput.value.trim();
      visionDraft.event_name = visionDraft.name;
    }
    stopTestPoll();
    const body = Object.assign({}, visionDraft);
    if (!body.anchor || !body.region) {
      alert("A captured region is required.");
      wizardStep = 1;
      renderVisionWizard();
      return;
    }
    const done = () => {
      visionInWizard = false;
      visionDraft = null;
      wizardCapture = null;
      fetchVision();
      renderPage();
    };
    const url = body.id
      ? `${API_BASE}/api/vision/sensors/${encodeURIComponent(body.id)}`
      : `${API_BASE}/api/vision/sensors`;
    apiFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) throw new Error("save failed");
        done();
      })
      .catch(() => alert("Save failed"));
  }

  function exitWizard() {
    stopTestPoll();
    visionInWizard = false;
    visionDraft = null;
    wizardCapture = null;
    fetchVision();
    renderPage();
  }

  function renderDashboard() {
    const userName = featureConfig.user_name || "";
    const greeting = featureConfig.feature_greeting !== false
      ? `<span class="dash-greeting">Welcome back${userName ? ", " + esc(userName) : ""}</span>`
      : "";
    const connected = deviceStatus.connected;
    const port = deviceStatus.port || "—";

    const plugins = Object.keys(pluginsConfig).filter((p) => p !== "vision");
    const pluginNames = {};
    const pluginIcons = {};
    plugins.forEach((p) => {
      pluginNames[p] = pluginsConfig[p].display_name || p;
      pluginIcons[p] = (pluginsConfig[p] || {}).icon || "extension";
    });

    const pluginCards = plugins.map((p) => {
      const cfg = pluginsConfig[p] || {};
      const statusLabel = cfg.status_label || "Unknown";
      const statusCode = cfg.status_code || "inactive";
      const color = STATUS_COLORS[statusCode] || "var(--fg-dim)";
      return `
        <div class="dash-plugin" data-name="${esc(p)}">
          <div class="dash-plugin-icon">
            <span class="material-icons-outlined">${pluginIcons[p]}</span>
          </div>
          <div class="dash-plugin-info">
            <span class="dash-plugin-name">${esc(pluginNames[p])}</span>
            <span class="dash-plugin-status" style="color:${color}">${esc(statusLabel)}</span>
          </div>
          <span class="material-icons-outlined plugin-tile-arrow" style="margin-left:auto">chevron_right</span>
        </div>`;
    }).join("");

    main.innerHTML = `
      <header>
        <div class="header-left">
          <button class="hamburger" id="hamburger" aria-label="Menu">
            <span class="material-icons-outlined">menu</span>
          </button>
          <div>
            <h1>Dashboard</h1>
          </div>
        </div>
        <button class="done-btn" id="done-btn">Done</button>
      </header>
      <section class="content dash-content">
        <div class="dash-hero">
          <div class="dash-hero-text">
            ${greeting}
            <span class="dash-status-line">
              <span class="dash-status-dot" style="background:${connected ? "var(--neon-grn)" : "var(--neon-red)"}"></span>
              Iris Device: ${connected ? "Online" : "Offline"} &bull; ${esc(port)}
            </span>
          </div>
        </div>
        <div class="dash-plugins">
          ${pluginCards || '<div class="card"><p style="color:var(--fg-dim);margin:0">No plugins detected</p></div>'}
        </div>
      </section>`;

    main.querySelectorAll(".dash-plugin").forEach((el) => {
      el.addEventListener("click", () => {
        selectedPlugin = el.dataset.name;
        currentPage = "plugins";
        fetchConfig();
        renderPage();
      });
    });

    var dashDoneBtn = document.getElementById("done-btn");
    if (dashDoneBtn) {
      dashDoneBtn.addEventListener("click", () => {
        if (typeof window.pywebview !== "undefined" && window.pywebview.api && window.pywebview.api.close_window) {
          window.pywebview.api.close_window();
        }
      });
    }

    rebindHamburger();
  }

  function renderPlaceholder() {
    var name = currentPage.replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    var subtitle = "Coming soon";
    if (settingsRenderer) {
      var page = settingsRenderer.getPage(currentPage);
      if (page) {
        name = page.title || name;
        subtitle = page.subtitle || subtitle;
      }
    }
    main.innerHTML =
      '<header>' +
        '<div class="header-left">' +
          '<button class="hamburger" id="hamburger" aria-label="Menu">' +
            '<span class="material-icons-outlined">menu</span>' +
          '</button>' +
          '<div>' +
            '<h1>' + esc(name) + '</h1>' +
          '</div>' +
        '</div>' +
        '<button class="done-btn" id="done-btn">Done</button>' +
      '</header>' +
      '<section class="settings-content settings-empty">' +
        '<div class="settings-placeholder">' +
          '<span class="material-icons-outlined">construction</span>' +
          '<p>' + esc(subtitle) + '</p>' +
        '</div>' +
      '</section>';
    rebindHamburger();
  }

  // ── Helpers ─────────────────────────────────────────────────

  function rebindHamburger() {
    const h = document.getElementById("hamburger");
    if (h) {
      h.addEventListener("click", toggleNav);
    }
    const d = document.getElementById("done-btn");
    if (d) {
      d.addEventListener("click", () => {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.close_panel) {
          window.pywebview.api.close_panel();
        } else if (IS_MOBILE && !IS_APP) {
          portalAutoPanel = true;
          fetchPanel();
          openPanelView();
        } else {
          currentPage = "dashboard";
          renderPage();
        }
      });
    }
  }

  function pluginDataCard(title, rows) {
    const filtered = rows.filter(([, v]) => v !== undefined && v !== null && v !== "");
    if (!filtered.length) return "";
    const lines = filtered
      .map(([k, v]) => `<div class="plugin-data-row"><span class="plugin-data-label">${esc(k)}</span><span class="plugin-data-value">${esc(String(v))}</span></div>`)
      .join("");
    return `<div class="plugin-data-card"><div class="plugin-data-heading">${esc(title)}</div>${lines}</div>`;
  }

  function renderPluginData(name) {
    const ps = pluginState[name];
    const liveState = (ps && ps.state) || {};
    const liveStatus = (ps && ps.status) || {};
    const liveLayout = ps && ps.layout;
    const hasLiveData = Object.keys(liveState).length > 0 || Object.keys(liveStatus).length > 0;

    const snap = pluginSnapshots[name];
    const s = hasLiveData ? liveState : ((snap && snap.state) || {});
    const st = hasLiveData ? liveStatus : ((snap && snap.status) || {});
    const layout = liveLayout || (snap && snap.layout);
    const hasAnyData = Object.keys(s).length > 0 || Object.keys(st).length > 0;

    if (!hasAnyData) {
      return `<div class="plugin-data-unavailable">No data available yet</div>`;
    }

    if (layout) {
      return layout.map((g) => {
        const rows = g.fields.map((f) => {
          const src = f.source === "status" ? st : s;
          let val = src[f.key];
          if (typeof val === "boolean") {
            const d = f.display || "yes_no";
            if (d === "up_down") val = val ? "Up" : "Down";
            else if (d === "down_up") val = val ? "Down" : "Up";
            else if (d === "on_off") val = val ? "On" : "Off";
            else if (d === "deployed_retracted") val = val ? "Deployed" : "Retracted";
            else val = val ? "Yes" : "No";
          }
          return [f.label, val];
        });
        return pluginDataCard(g.title, rows);
      }).join("");
    }

    const stateRows = Object.entries(s).map(([k, v]) => [
      k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()), v,
    ]);
    const statusRows = Object.entries(st).map(([k, v]) => [
      k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      typeof v === "boolean" ? (v ? "Yes" : "No") : v,
    ]);
    let html = pluginDataCard("State", stateRows);
    html += pluginDataCard("Status", statusRows);
    return html || `<div class="plugin-data-unavailable">No data available yet</div>`;
  }

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  // ── Window drag (frameless) — restricted to header above gradient line ──

  let dragState = null;

  document.addEventListener("mousedown", (e) => {
    // Check if the click is on an interactive control
    const isInteractive = e.target.closest("button, a, input, select, textarea, label, canvas, .pdev-tile, .pdev-slider, .pdev-range, .pdev-swatch, .done-btn, .hamburger, .refresh-btn, .nav-item, .ssv-btn-icon, .ssv-close, .ssv-hint, .ssv-text-box");
    if (isInteractive) return;

    // Allow window drag across all non-interactive areas in panel view mode, or headers in settings
    const inDraggableArea = panelViewMode || !!e.target.closest("header, .header-left, .logo, .ssv-bar, .panel-view-overlay, .pv-screen, .pv-scroll, .pv-frame, .pv-gauges, .pv-side, .pv-util, .pv-box, .pv-track");
    if (!inDraggableArea) return;

    dragState = { startX: e.screenX, startY: e.screenY };
  });

  document.addEventListener("mousemove", (e) => {
    if (!dragState) return;
    const dx = e.screenX - dragState.startX;
    const dy = e.screenY - dragState.startY;
    dragState.startX = e.screenX;
    dragState.startY = e.screenY;
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.move_window(dx, dy);
    }
  });

  document.addEventListener("mouseup", () => {
    dragState = null;
  });

  // ── Screensaver ──────────────────────────────────────────────
  const SS_AUTO_LOCK_RELEASE_MS = 10 * 60 * 1000; // 10 mins idle -> release wake lock to OS
  let ssAutoLockTimer = null;

  // Active on live companion screen (panelViewMode)
  function getScreensaverTimeoutMs() {
    let val = 2; // Default 2 minutes
    try {
      const stored = localStorage.getItem("iris_screensaver_timeout");
      if (stored) {
        let n = Number(stored);
        if (!isNaN(n)) {
          if (n >= 60) n = Math.round(n / 60); // Migrate legacy seconds -> minutes
          val = Math.max(1, Math.min(10, n));
        }
      }
    } catch (e) {}

    const cfg = (typeof _panelLiveCachedConfig !== "undefined" && _panelLiveCachedConfig) || (typeof panelLive !== "undefined" && panelLive && panelLive.config);
    if (cfg && typeof cfg.screensaver_timeout !== "undefined") {
      let n = Number(cfg.screensaver_timeout);
      if (!isNaN(n)) {
        if (n >= 60) n = Math.round(n / 60); // Migrate legacy seconds -> minutes
        val = Math.max(1, Math.min(10, n));
        try { localStorage.setItem("iris_screensaver_timeout", String(val)); } catch (e) {}
      }
    }
    if (isNaN(val) || val < 1) val = 1;
    return val * 60 * 1000; // minutes to ms
  }

  const SS_PULSE_INTERVAL_MS = 30 * 1000; // pulse appearance every 30s
  const SS_PULSE_VISIBLE_MS  = 6 * 1000;  // hold visible for 6s before fading to black

  let ssIdleTimer    = null; // idle timeout -> showScreensaver()
  let ssPulseTimer   = null; // 30s recurring pulse
  let ssFadeOutTimer = null; // 6s timer to fade to black
  let ssActive       = false;

  function ssEl() { return document.getElementById("iris-screensaver"); }

  function pulseScreensaverLock() {
    const el = ssEl();
    if (!el || !ssActive) return;
    const lockEl = el.querySelector(".ssv-clean-lock");
    if (!lockEl) return;

    // Pixel shift within ±20px horizontal and ±30px vertical to protect OLED subpixels
    const offsetX = (Math.random() * 40 - 20).toFixed(1);
    const offsetY = (Math.random() * 60 - 30).toFixed(1);
    lockEl.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
    lockEl.style.opacity = "1";

    if (ssFadeOutTimer) clearTimeout(ssFadeOutTimer);
    ssFadeOutTimer = setTimeout(function () {
      if (ssActive && lockEl) {
        lockEl.style.opacity = "0"; // Smooth fade to pure black (OLED pixels off)
      }
    }, SS_PULSE_VISIBLE_MS);
  }

  function resetScreensaverTimer() {
    if (IS_APP || window.pywebview || isDesktopEnvironment() || !IS_MOBILE || !panelViewMode) return;
    requestWakeLock();
    if (ssActive) {
      // Any real interaction wakes the screensaver
      hideScreensaver();
      return;
    }
    if (ssIdleTimer) clearTimeout(ssIdleTimer);
    const timeoutMs = getScreensaverTimeoutMs();
    if (panelViewMode && timeoutMs > 0) {
      ssIdleTimer = setTimeout(showScreensaver, timeoutMs);
    }
  }

  function showScreensaver() {
    if (IS_APP || window.pywebview || isDesktopEnvironment() || !IS_MOBILE || !panelViewMode) return;
    const timeoutMs = getScreensaverTimeoutMs();
    if (timeoutMs <= 0) return;
    ssActive = true;
    const el = ssEl();
    if (!el) return;
    el.setAttribute("aria-hidden", "false");
    el.classList.add("ss-visible");
    document.body.style.overflow = "hidden";

    // Immediate initial pulse on lock
    pulseScreensaverLock();
    if (ssPulseTimer) clearInterval(ssPulseTimer);
    ssPulseTimer = setInterval(pulseScreensaverLock, SS_PULSE_INTERVAL_MS);
  }

  function hideScreensaver() {
    ssActive = false;
    requestWakeLock();
    if (ssIdleTimer) { clearTimeout(ssIdleTimer); ssIdleTimer = null; }
    if (ssPulseTimer) { clearInterval(ssPulseTimer); ssPulseTimer = null; }
    if (ssFadeOutTimer) { clearTimeout(ssFadeOutTimer); ssFadeOutTimer = null; }
    const el = ssEl();
    if (!el) return;
    el.classList.remove("ss-visible");
    el.setAttribute("aria-hidden", "true");
    const lockEl = el.querySelector(".ssv-clean-lock");
    if (lockEl) {
      lockEl.style.opacity = "0";
      lockEl.style.transform = "translate(0px, 0px)";
    }
    document.body.style.overflow = "";
    // Re-arm idle timer for next cycle
    const timeoutMs = getScreensaverTimeoutMs();
    if (panelViewMode && timeoutMs > 0) {
      ssIdleTimer = setTimeout(showScreensaver, timeoutMs);
    }
  }

  // Wake the screensaver on incoming notifications or status events
  function screensaverWakeOnEvent() {
    hideScreensaver();
    resetScreensaverTimer();
    try { requestWakeLock(); } catch (_) {}
  }

  // ── First-Run Ambient Lighting Setup Wizard ───────────────────
  let _lightingWizardShown = false;

  async function checkLightingWizard() {
    if (_lightingWizardShown || IS_MOBILE) return;
    try {
      const res = await apiFetch(`${API_BASE}/api/lighting/status`);
      if (!res.ok) return;
      const data = await res.json();
      const providers = data.providers || [];
      const connected = providers.filter((p) => p.connected);
      if (!connected.length) return;

      const cfg = featureConfig || {};
      const lCfg = cfg.ambient_lighting;
      // Trigger if ambient_lighting is undefined or not explicitly configured
      if (!lCfg || lCfg._wizard_completed === undefined) {
        _lightingWizardShown = true;
        showLightingSetupWizard(connected);
      }
    } catch (_) {}
  }

  function showLightingSetupWizard(connectedProviders) {
    const existing = document.getElementById("lighting-setup-modal");
    if (existing) existing.remove();

    const provNames = connectedProviders.map((p) => esc(p.name)).join(" & ");
    const hasHA = connectedProviders.some((p) => p.id === "ha");
    const hasOpenRGB = connectedProviders.some((p) => p.id === "openrgb");

    let modalHtml = '<div class="panel-modal-backdrop" id="lighting-setup-modal" style="z-index:99999;">' +
      '<div class="panel-modal" style="max-width:520px;">' +
        '<div class="panel-modal-header" style="display:flex;align-items:center;gap:8px;">' +
          '<span class="material-icons-outlined" style="font-size:24px;color:var(--neon-text);">auto_awesome</span>' +
          '<div>' +
            '<h3 style="margin:0;font-size:16px;">Ambient Lighting Setup</h3>' +
            '<span class="panel-modal-subtitle">Detected: ' + provNames + '</span>' +
          '</div>' +
        '</div>' +
        '<div style="padding:12px 0;display:flex;flex-direction:column;gap:12px;">' +
          '<p style="font-size:12.5px;color:var(--fg);margin:0;line-height:1.5;">' +
            'Iris has detected active lighting hardware. Would you like to configure your ambient lighting defaults?' +
          '</p>' +
          '<div style="background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:8px;padding:12px;display:flex;flex-direction:column;gap:10px;">' +
            '<div class="settings-toggle-row">' +
              '<span class="settings-toggle-label" style="font-size:12.5px;">Sync with Iris Visual Theme</span>' +
              '<div class="settings-toggle on" id="wz-light-sync"><div class="settings-toggle-thumb"></div></div>' +
            '</div>' +
            '<span class="settings-hint" style="margin-top:-6px;">Derives the highest luminance color from your active theme for PC hardware LEDs' + (hasHA ? ' & smart bulbs' : '') + '.</span>' +
            '<div class="settings-toggle-row">' +
              '<span class="settings-toggle-label" style="font-size:12.5px;">Follow Daylight Cycle</span>' +
              '<div class="settings-toggle on" id="wz-light-day"><div class="settings-toggle-thumb"></div></div>' +
            '</div>' +
            '<span class="settings-hint" style="margin-top:-6px;">Automatically turns ceiling/office lights OFF during daytime hours (07:30–19:30) while PC LEDs stay lit.</span>' +
          '</div>' +
        '</div>' +
        '<div class="panel-modal-actions" style="margin-top:8px;">' +
          '<button type="button" class="settings-btn" id="wz-light-skip">Not Now</button>' +
          '<button type="button" class="settings-btn" id="wz-light-config"><span class="material-icons-outlined" style="font-size:16px;">tune</span> Configure Presets</button>' +
          '<button type="button" class="settings-btn primary" id="wz-light-apply"><span class="material-icons-outlined" style="font-size:16px;">check</span> Enable Ambient</button>' +
        '</div>' +
      '</div>' +
    '</div>';

    const wrap = document.createElement("div");
    wrap.innerHTML = modalHtml;
    document.body.appendChild(wrap);

    const syncTog = document.getElementById("wz-light-sync");
    const dayTog = document.getElementById("wz-light-day");
    const skipBtn = document.getElementById("wz-light-skip");
    const cfgBtn = document.getElementById("wz-light-config");
    const applyBtn = document.getElementById("wz-light-apply");

    if (syncTog) syncTog.addEventListener("click", () => syncTog.classList.toggle("on"));
    if (dayTog) dayTog.addEventListener("click", () => dayTog.classList.toggle("on"));

    const close = () => { if (wrap.parentNode) wrap.parentNode.removeChild(wrap); };

    if (skipBtn) {
      skipBtn.addEventListener("click", () => {
        const patch = { ambient_lighting: Object.assign({}, featureConfig.ambient_lighting || {}, { _wizard_completed: true }) };
        saveFeature(patch);
        close();
      });
    }

    if (cfgBtn) {
      cfgBtn.addEventListener("click", () => {
        const patch = { ambient_lighting: Object.assign({}, featureConfig.ambient_lighting || {}, { _wizard_completed: true }) };
        saveFeature(patch);
        close();
        // Open Default Profile settings modal
        panelProfileSel = "__default__";
        fetchLightingStatus().then(() => {
          panelEdit = null;
          panelProfileModal = true;
          if (currentPage !== "panel") {
            if (typeof window.navigateToPage === "function") window.navigateToPage("panel");
            else renderPage();
          } else {
            renderPanel();
          }
        });
      });
    }

    if (applyBtn) {
      applyBtn.addEventListener("click", () => {
        const syncOn = syncTog ? syncTog.classList.contains("on") : true;
        const dayOn = dayTog ? dayTog.classList.contains("on") : true;
        const patch = {
          ambient_lighting: {
            sync_theme: syncOn,
            follow_daylight: dayOn,
            _wizard_completed: true
          }
        };
        saveFeature(patch);
        close();
      });
    }
  }

  // Called inline from openPanelView()
  function ssArmForPanelView() {
    if (IS_APP || !panelViewMode) return;
    requestWakeLock();
    if (ssIdleTimer) clearTimeout(ssIdleTimer);
    const timeoutMs = getScreensaverTimeoutMs();
    if (timeoutMs > 0) {
      ssIdleTimer = setTimeout(showScreensaver, timeoutMs);
    }
  }

  // Called inline from exitPanelView()
  function ssDisarmForPanelView() {
    hideScreensaver();
    if (ssIdleTimer) { clearTimeout(ssIdleTimer); ssIdleTimer = null; }
    if (ssPulseTimer) { clearInterval(ssPulseTimer); ssPulseTimer = null; }
    if (ssFadeOutTimer) { clearTimeout(ssFadeOutTimer); ssFadeOutTimer = null; }
  }

  // Touch/interaction resets idle timer or wakes screensaver
  (function () {
    function onActivity(e) {
      // If screensaver is active, consume the first touch to wake (don't pass through)
      if (ssActive) {
        try { e.preventDefault(); } catch (_) {}
        try { e.stopPropagation(); } catch (_) {}
        hideScreensaver();
        return;
      }
      resetScreensaverTimer();
    }
    document.addEventListener("touchstart", onActivity, { passive: false, capture: true });
    document.addEventListener("pointerdown", onActivity, { passive: false, capture: true });
    document.addEventListener("touchmove",  onActivity, { passive: false, capture: true });
    document.addEventListener("click",      onActivity, { capture: true });

    const ssOverlay = document.getElementById("iris-screensaver");
    if (ssOverlay) {
      function unlockTap(e) {
        try { e.preventDefault(); } catch (_) {}
        try { e.stopPropagation(); } catch (_) {}
        hideScreensaver();
      }
      ssOverlay.addEventListener("touchstart", unlockTap, { passive: false, capture: true });
      ssOverlay.addEventListener("pointerdown", unlockTap, { passive: false, capture: true });
      ssOverlay.addEventListener("click", unlockTap, { capture: true });
    }
  })();

  // ── Init ────────────────────────────────────────────────────

  window.addEventListener("resize", () => {
    updateViewportMode();
  });
  window.addEventListener("orientationchange", () => {
    updateViewportMode();
    setTimeout(updateViewportMode, 100);
    setTimeout(updateViewportMode, 300);
  });
  updateViewportMode();
  startPolling();
})();
