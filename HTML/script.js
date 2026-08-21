/* Iris v3 — HTML UI script */

(function () {
  "use strict";

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js?v=5").catch(() => {});
  }

  // ── Platform detection ──────────────────────────────────────

  const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (isIOS) {
    document.documentElement.setAttribute("data-theme", "ios");
  }
  // Android Chrome reports 0 for safe-area insets (the status bar isn't exposed
  // unless installed as a PWA), so the panel's notch/status-bar clearance has to
  // be supplied explicitly. Mark it so CSS can add the gap the iPhone gets free.
  const isAndroid = /Android/i.test(navigator.userAgent);
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
    let p = pathOrName || (panelLive && panelLive.config && panelLive.config.media_player_path) || (panelDraft && panelDraft.media_player_path) || (config && config.media_player_path) || "";
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
  window.applyTheme = function (theme) {
    theme = theme || {};
    const mode = theme.mode || "iris";
    let c1 = "#B23AF6"; // Accent (gradient start)
    let c2 = "#79E8FC"; // Neon (gradient end / primary active)
    let glow = "rgba(121, 232, 252, 0.35)";

    if (mode === "monochrome") {
      c1 = "#666666";
      c2 = "#FFFFFF";
      glow = "rgba(255, 255, 255, 0.35)";
    } else if (mode === "custom") {
      c1 = theme.accent || "#B23AF6";
      c2 = theme.neon || "#79E8FC";
      glow = (function (hex) {
        if (!hex || hex[0] !== "#" || (hex.length !== 7 && hex.length !== 4)) return "rgba(72,178,233,.35)";
        const r = parseInt(hex.length === 7 ? hex.slice(1, 3) : hex[1] + hex[1], 16) || 0;
        const g = parseInt(hex.length === 7 ? hex.slice(3, 5) : hex[2] + hex[2], 16) || 0;
        const b = parseInt(hex.length === 7 ? hex.slice(5, 7) : hex[3] + hex[3], 16) || 0;
        return `rgba(${r},${g},${b},0.35)`;
      })(c2);
    }

    const root = document.documentElement;
    root.style.setProperty("--theme-color-1", c1);
    root.style.setProperty("--theme-color-2", c2);
    root.style.setProperty("--neon", c2);
    root.style.setProperty("--neon-purple", c1);
    root.style.setProperty("--theme-gradient-h", `linear-gradient(90deg, ${c1} 0%, ${c2} 100%)`);
    root.style.setProperty("--theme-gradient-v", `linear-gradient(180deg, ${c1} 0%, ${c2} 100%)`);
    root.style.setProperty("--theme-gradient-conic", `conic-gradient(${c1} 0deg, ${c2} 360deg)`);
    root.style.setProperty("--scrollbar-thumb", `linear-gradient(180deg, ${c1} 0%, ${c2} 100%)`);
    root.style.setProperty("--scrollbar-thumb-hover", `linear-gradient(180deg, ${c1} 0%, ${c2} 100%)`);
    root.style.setProperty("--theme-glow", glow);
  };

  // True inside the desktop app's panel window (pywebview). Only that window
  // may see the Network page / access token / QR code.
  const IS_APP = !!(window.pywebview && window.pywebview.api);

  // The portal's "straight to panel" landing is for phones only. The desktop
  // (browser or the desktop app window) still opens the dashboard.
  const IS_MOBILE = (window.matchMedia && window.matchMedia("(max-width: 768px)").matches) || isIOS;

  // ── Keep-screen-awake (phones) ──────────────────────────────
  // The live panel should stay lit while the phone is on it. Uses the
  // Screen Wake Lock API (navigator.wakeLock.request) — works on iOS
  // Safari 16.4+ (and iOS 18.4+ in installed PWAs) and Android Chrome 84+.
  // Engaged only on phones — the desktop panel window and desktop browsers
  // skip it. Configurable via the "keep_alive" setting (Settings > Phone),
  // applied on each live poll.
  let keepAliveEnabled = true;
  let wakeLockSentinel = null;
  let videoWakeLock = null;
  let canvasInterval = null;

  function enableMediaWakeLock() {
    if (!keepAliveEnabled) return;
    if (videoWakeLock) {
      if (videoWakeLock.paused) videoWakeLock.play().catch(function () {});
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

      videoWakeLock.play().catch(function () {});
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
    enableMediaWakeLock();
    if (!navigator.wakeLock || !navigator.wakeLock.request) return;
    if (wakeLockSentinel && !wakeLockSentinel.released) return;
    let p;
    try {
      p = navigator.wakeLock.request("screen");
    } catch (e) {
      return;
    }
    if (p && p.then) {
      p.then(function (sentinel) {
        wakeLockSentinel = sentinel;
        sentinel.addEventListener("release", function () {
          if (keepAliveEnabled && document.visibilityState === "visible") {
            requestWakeLock();
          }
        });
      }).catch(function () {});
    }
  }

  function applyKeepAlive(enabled) {
    keepAliveEnabled = enabled !== false;
    if (keepAliveEnabled) {
      requestWakeLock();
    } else {
      releaseWakeLock();
    }
  }

  (function setupKeepScreenAwake() {
    if (!IS_MOBILE || IS_APP) return;
    function onGesture() {
      requestWakeLock();
    }
    document.addEventListener("touchstart", onGesture, true);
    document.addEventListener("pointerdown", onGesture, true);
    document.addEventListener("click", onGesture, true);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") {
        // The wake lock is dropped when the tab is hidden.
        requestWakeLock();
      }
    });
    // Wake Lock needs no user gesture, so request it right away.
    requestWakeLock();
  })();

  // ── Landscape mode ──────────────────────────────────────────
  // Applied by the `is-landscape` class on <html>, not by the media query
  // alone: iOS standalone PWAs can report a portrait viewport on cold start,
  // so (orientation: landscape) may never match. Derived from real viewport
  // dimensions + a coarse-pointer gate (touch phones only, so desktop
  // landscape windows stay unrotated). Re-evaluated on load/resize/rotate.
  function updateViewportMode() {
    const prevLand = document.documentElement.classList.contains("is-landscape");
    const coarse = !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
    const w = window.innerWidth;
    const h = window.innerHeight;
    const isLand = coarse && w > h && Math.min(w, h) <= 768;
    document.documentElement.classList.toggle("is-landscape", isLand);
    // OLED vs LCD: deep blacks only look rich on a true-OLED panel. High
    // dynamic range + wide gamut is the reliable proxy (OLED phones report
    // both, LCD panels generally don't). Drives the is-oled tile styling.
    const isOled = !!(window.matchMedia &&
      window.matchMedia("(dynamic-range: high) and (color-gamut: p3)").matches);
    document.documentElement.classList.toggle("is-oled", isOled);
    // Measured visible viewport, in px. CSS units (100vh/100vw) resolve to the
    // *large* viewport on Android Chrome (the area behind the URL bar), which
    // oversized the rotated screen; innerWidth/innerHeight are the visible area.
    document.documentElement.style.setProperty("--pv-vw", w + "px");
    document.documentElement.style.setProperty("--pv-vh", h + "px");
    if (panelViewMode) {
      const ov = document.getElementById("panel-view");
      if (ov) {
        layoutPanelBox(ov);
        restoreBoxScroll();
      }
      // The grid button order is baked in at render time, so a landscape flip
      // must rebuild the panel (boardPagesHtml reads is-landscape live).
      if (isLand !== prevLand) {
        // Remember which page number is on screen, then scroll back to that
        // same page after the rebuild. IMPORTANT: the track mirror in
        // landscape REVERSES the scroll<->page mapping — a page's snap offset
        // is x in portrait but W-x-width in landscape — so both the selection
        // and the target must use the orientation that matches the DOM being
        // measured (old DOM -> prevLand, new DOM -> isLand). All computed
        // targets land exactly on a real scroll-snap point, so snap won't
        // fight them.
        const box = ov ? ov.querySelector(".pv-box") : null;
        if (box) {
          const track = box.querySelector(".pv-track");
          const W = track ? track.offsetWidth : 0;
          const oldLand = prevLand;
          let curPage = 0;
          let best = Infinity;
          box.querySelectorAll(".pdev-grid").forEach((g) => {
            // offsetParent differs by orientation: the track transform in
            // landscape makes it the grids' offsetParent, so grid.offsetLeft is
            // already track-relative there; in portrait it is offsetParent-
            // relative and needs the track's own offset subtracted.
            const x = track ? (oldLand ? g.offsetLeft : (g.offsetLeft - track.offsetLeft)) : 0;
            const expected = oldLand ? (W - x - g.offsetWidth) : x;
            const d = Math.abs(expected - box.scrollLeft);
            if (d < best) {
              best = d;
              curPage = parseInt(g.getAttribute("data-page") || "0", 10) || 0;
            }
          });
          pendingPanelPage = curPage;
        }
        renderPanelView();
        // Apply the target page NOW, synchronously, to BOTH the DOM scroll and
        // the remembered boxScrollLeft so no later restore can clobber it.
        if (pendingPanelPage !== null) {
          const pbox = ov ? ov.querySelector(".pv-box") : null;
          if (pbox) {
            const g = pbox.querySelector('.pdev-grid[data-page="' + pendingPanelPage + '"]');
            if (g) {
              const track = pbox.querySelector(".pv-track");
              const W = track ? track.offsetWidth : 0;
              const x = track ? (isLand ? g.offsetLeft : (g.offsetLeft - track.offsetLeft)) : 0;
              const pb = pbox.style.scrollBehavior;
              pbox.style.scrollBehavior = "auto";
              boxScrollLeft = isLand ? (W - x - g.offsetWidth) : x;
              pbox.scrollLeft = boxScrollLeft;
              pbox.style.scrollBehavior = pb;
            }
          }
          pendingPanelPage = null;
        }
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
        // Session expired or unauthenticated remote access -> back to login.
        window.location.href = "/login";
        throw new Error("unauthorized");
      }
      return res;
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
          panelViewMode = false;
          panelNav = [];
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
            dataEl.innerHTML = '<span class="plugin-edit-label">DATA</span>' +
              settingsRenderer._renderPluginData(selectedPlugin, snap, next[selectedPlugin]);
          }
        } else if (currentPage === "dashboard") {
          // Only rebuild dashboard when plugin availability/status cards would change.
          var statusChanged = false;
          var names = Object.keys(next);
          for (var i = 0; i < names.length; i++) {
            var n = names[i];
            var a = (prev[n] && prev[n].available) || false;
            var b = (next[n] && next[n].available) || false;
            if (a !== b) { statusChanged = true; break; }
          }
          if (statusChanged || Object.keys(prev).length !== names.length) {
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
    const isPanelParam = params.get("view") === "panel" || params.get("panel") === "1";
    if (isPanelParam) {
      currentPage = "panel";
      portalAutoPanel = true;
      fetchPanel();
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
    settingsRenderer = new SettingsRenderer(API_BASE);
    updateNavForDevice();
    window.addEventListener("resize", updateNavForDevice);
    fetchConfig();
    fetchPanel();
    fetchEntities();
    settingsRenderer.loadPages().then(function (pages) {
      if (!pages || !pages.length) {
        setTimeout(function () {
          settingsRenderer.loadPages().then(renderInitialView).catch(renderInitialView);
        }, 600);
        return;
      }
      renderInitialView();
    }).catch(function () {
      setTimeout(function () {
        settingsRenderer.loadPages().then(renderInitialView).catch(renderInitialView);
      }, 600);
    });
    fetchState();
    fetchPluginsConfig();
    fetchDeviceStatus();
    fetchPanelLive();
    if (!panelLiveTimer) panelLiveTimer = setInterval(fetchPanelLive, 500);
    connectWs();
  }

  // ── Page rendering ──────────────────────────────────────────

  function renderPage() {
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
    } else if (currentPage === "panel") {
      renderPanel();
    } else {
      renderPlaceholder();
    }
    const newSc = main.querySelector('.settings-content') || main.querySelector('.content') || main;
    if (newSc && prevScroll) newSc.scrollTop = prevScroll;
  }

  // ── Declarative page rendering ────────────────────────────────

  function renderDeclarativePage(pageId) {
    var page = settingsRenderer.getPage(pageId);
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

  async function fetchDeviceStatus() {
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

    document.getElementById("back-btn").addEventListener("click", function () {
      selectedPlugin = null;
      renderPage();
    });

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
          }).catch(function () {});
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

  // ── Vision page ──────────────────────────────────────────────

  const VISION_MODES = {
    color_percentage: "Colour Percentage",
    pixel_match: "Pixel Match",
    average_brightness: "Average Brightness",
  };

  const VISION_WIZARD_STEPS = [
    "Capture Region", "Pick Pixel", "App", "Configure", "Test",
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
      require_foreground: false,
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
      const color = disabled ? "var(--fg-dim)"
        : (active ? "var(--neon-grn)" : "var(--neon-red)");
      const valEl = card.querySelector(".vision-card-value");
      if (valEl) {
        valEl.textContent = String(live.value);
        valEl.style.color = color;
      }
      const statusEl = card.querySelector(".vision-card-status");
      if (statusEl) {
        statusEl.textContent = disabled ? "Disabled"
          : (!running ? "App not running"
            : (active ? "Triggered" : "Watching"));
      }
      const dotEl = card.querySelector(".vision-status-dot");
      if (dotEl) dotEl.style.background = color;
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
    const color = !s.enabled ? "var(--fg-dim)"
      : (active ? "var(--neon-grn)" : "var(--neon-red)");
    const statusLabel = !s.enabled ? "Disabled"
      : (running ? (active ? "Triggered" : "Watching") : "App not running");
    return `
      <div class="vision-card" data-id="${esc(s.id)}">
        <div class="vision-card-head">
          <span class="vision-status-dot" style="background:${color}"></span>
          <span class="vision-card-name">${esc(s.name || s.id)}</span>
        </div>
        <div class="vision-card-meta">
          <span class="material-icons-outlined">apps</span>${esc(s.exe || "—")}
        </div>
        <div class="vision-card-mode">${esc(VISION_MODES[s.mode] || s.mode)}${s.require_foreground ? " · Focused" : ""}</div>
        <div class="vision-card-value" style="color:${color}">${value !== null && value !== undefined ? esc(String(value)) : "—"}</div>
        <div class="vision-card-status">${statusLabel}</div>
        <div class="vision-card-actions">
          <span class="vision-toggle-label">Enabled
            <div class="settings-toggle ${s.enabled ? "on" : ""} vision-card-toggle" data-id="${esc(s.id)}">
              <div class="settings-toggle-thumb"></div>
            </div>
          </span>
          <button class="settings-btn vision-card-test" data-id="${esc(s.id)}">Test</button>
          <button class="settings-btn vision-card-edit" data-id="${esc(s.id)}">Edit</button>
          <button class="settings-btn vision-card-del danger" data-id="${esc(s.id)}">Delete</button>
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
    try {
      const res = await apiFetch(`${API_BASE}/api/notifications`);
      if (res.ok) {
        notifData = await res.json();
        if (currentPage === "notifications") {
          renderNotificationsList();
        }
      }
    } catch (_) {}
    clearTimeout(notifTimer);
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

  function openLibraryViewer(filename) {
    const existing = document.getElementById("iris-screenshot-viewer");
    if (existing) existing.remove();
    const item = libraryItems.find(i => i.filename === filename);
    const title = item ? (item.title || item.app) : filename;
    const el = document.createElement("div");
    el.id = "iris-screenshot-viewer";
    el.innerHTML =
      `<div class="ssv-bar">` +
        `<span class="ssv-ts">${escapeHtml(title)}</span>` +
        `<button class="ssv-close" aria-label="Close">&#x2715;</button>` +
      `</div>` +
      `<img src="${API_BASE}/api/library/image/${encodeURIComponent(filename)}" alt="Screenshot" draggable="false">`;
    document.body.appendChild(el);
    el.querySelector(".ssv-close").addEventListener("click", () => el.remove());
    let startY = 0;
    el.addEventListener("touchstart", (e) => { startY = e.touches[0].clientY; }, { passive: true });
    el.addEventListener("touchend", (e) => { if (e.changedTouches[0].clientY - startY > 80) el.remove(); }, { passive: true });
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

  // ── Notepad dialog ────────────────────────────────────────────────────────

  function openNotepad(filename) {
    const existing = document.getElementById("iris-notepad");
    if (existing) existing.remove();

    const el = document.createElement("div");
    el.id = "iris-notepad";
    el.innerHTML = `
      <div class="notepad-dialog">
        <div class="notepad-header">
          <h2>${filename ? 'Edit Note' : 'New Note'}</h2>
          <button class="notepad-close" aria-label="Close">&#x2715;</button>
        </div>
        <div class="notepad-field">
          <label>Title</label>
          <input type="text" id="notepad-title" class="notepad-input" placeholder="Note title…" autocomplete="off">
        </div>
        <div class="notepad-field">
          <label>App</label>
          <div class="notepad-app-row">
            <input type="text" id="notepad-app" class="notepad-input" placeholder="app name" autocomplete="off">
            <select id="notepad-app-select" class="notepad-app-select" title="Pick a running app">
              <option value="">Pick app…</option>
            </select>
          </div>
        </div>
        <div class="notepad-field notepad-field-grow">
          <label>Note</label>
          <textarea id="notepad-body" class="notepad-textarea" placeholder="Write your note here…" spellcheck="true"></textarea>
        </div>
        <div class="notepad-actions">
          <button class="notepad-btn notepad-btn-save" id="notepad-save">Save</button>
          <button class="notepad-btn notepad-btn-cancel" id="notepad-cancel">Cancel</button>
        </div>
      </div>`;
    document.body.appendChild(el);

    const titleEl = document.getElementById("notepad-title");
    const appEl = document.getElementById("notepad-app");
    const appSel = document.getElementById("notepad-app-select");
    const bodyEl = document.getElementById("notepad-body");

    // Load running apps into dropdown
    apiFetch(`${API_BASE}/api/library/running_apps`)
      .then(r => r.json())
      .then(data => {
        (data.apps || []).forEach(a => {
          const opt = document.createElement("option");
          opt.value = a; opt.textContent = a;
          appSel.appendChild(opt);
        });
      }).catch(() => {});

    appSel.addEventListener("change", () => {
      if (appSel.value) { appEl.value = appSel.value; appSel.value = ""; }
    });

    if (filename) {
      // Load existing note
      apiFetch(`${API_BASE}/api/library/note/${encodeURIComponent(filename)}`)
        .then(r => r.json())
        .then(data => {
          titleEl.value = data.title || "";
          appEl.value = data.app || "";
          bodyEl.value = data.content || "";
        }).catch(() => {});
    } else {
      // Default app = current filter or empty
      appEl.value = libraryFilter !== "all" ? libraryFilter : "";
    }

    el.querySelector(".notepad-close").addEventListener("click", () => el.remove());
    document.getElementById("notepad-cancel").addEventListener("click", () => el.remove());
    document.getElementById("notepad-save").addEventListener("click", async () => {
      const payload = {
        title: titleEl.value.trim(),
        app: appEl.value.trim() || "general",
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
          el.remove();
          fetchLibraryItems();  // refresh
        }
      } catch (e) { alert("Save failed."); }
    });
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
          <div class="vision-test-status" id="vision-test-status">Waiting…</div>
          ${renderVisionConfigForm()}
        </div>
      </div>`;
  }

  function renderVisionConfigForm() {
    const d = visionDraft || defaultDraft();
    return `
      <div class="vision-wizard-form">
        <div class="settings-control">
          <label class="settings-label">Sensor Name</label>
          <input type="text" class="settings-input" id="wz-name" value="${esc(d.name || "")}">
        </div>
        <div class="settings-control">
          <label class="settings-label">Event Message</label>
          <input type="text" class="settings-input" id="wz-event-msg" value="${esc(d.event_message || "")}">
        </div>
        <div class="settings-control">
          <label class="settings-label">Mode</label>
          <select class="settings-select" id="wz-mode">
            ${Object.keys(VISION_MODES).map((m) =>
              `<option value="${m}" ${m === d.mode ? "selected" : ""}>${VISION_MODES[m]}</option>`).join("")}
          </select>
        </div>
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
          <label class="settings-label">Threshold</label>
          <input type="number" class="settings-input" id="wz-threshold" value="${esc(String(d.threshold))}" step="0.1">
        </div>
        <div class="settings-control">
          <label class="settings-label">Direction</label>
          <select class="settings-select" id="wz-direction">
            <option value="below" ${d.direction !== "above" ? "selected" : ""}>Below threshold (colour present)</option>
            <option value="above" ${d.direction === "above" ? "selected" : ""}>Above threshold</option>
          </select>
        </div>
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
    return `
      <div class="vision-wizard-pane" id="pane-2">
        <h3>2. Pick Pixel</h3>
        <p>Click on the preview to sample the colour to watch for.
        <span class="vision-swatch" id="vision-swatch" style="background:${esc(visionDraft.color)}"></span>
        <span id="vision-color-hex">${esc(visionDraft.color)}</span></p>
        <canvas id="vision-preview-canvas" class="vision-preview-canvas"></canvas>
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
          const st = document.getElementById("vision-test-status");
          if (el) {
            el.textContent = String(data.value);
            el.style.color = data.active ? "var(--neon-grn)" : "var(--neon-red)";
          }
          if (st) st.textContent = data.active ? "Triggered" : "Not triggered";
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
    if (_fetchPanelBusy) return;
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
        if (portalAutoPanel) {
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
        if (portalAutoPanel) {
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

  function layoutOn(id) {
    const row = (panelDraft.panel_layout || []).find((x) => x.id === id);
    return row ? row.enabled !== false : true;
  }

  function setLayoutOn(id, on) {
    if (!panelDraft.panel_layout) panelDraft.panel_layout = [];
    let row = panelDraft.panel_layout.find((x) => x.id === id);
    if (!row) {
      row = { id: id, enabled: on };
      panelDraft.panel_layout.push(row);
    } else row.enabled = on;
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
    const list = panelDraft ? (panelDraft.panel_profiles || []) : [];
    let profile = null;
    if (panelProfileSel !== "__default__") {
      profile = list.find((x) => x.id === panelProfileSel) || null;
      if (!profile) panelProfileSel = "__default__";
    }
    let board = panelDraft ? (panelDraft.panel_board || []) : [];
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
    const hasProfile = panelProfileSel !== "__default__" &&
      !!list.find((x) => x.id === panelProfileSel);
    let h = '<div class="panel-profile-row">' +
      '<select class="settings-select" id="panel-profile-sel">' +
      '<option value="__default__">Default</option>';
    list.forEach((p) => {
      h += '<option value="' + esc(p.id) + '"' + (panelProfileSel === p.id ? " selected" : "") + '>' +
        esc(p.name || p.id) + '</option>';
    });
    h += '</select>' +
      '<button type="button" class="settings-btn" id="panel-profile-create" title="Create new profile">+ New</button>' +
      '<button type="button" class="settings-btn" id="panel-profile-clone" title="Duplicate current profile">Clone</button>' +
      '<button type="button" class="settings-btn" id="panel-profile-edit"' + (hasProfile ? "" : " disabled") + ' title="Profile settings">Settings</button>' +
      '<button type="button" class="settings-btn settings-btn-danger" id="panel-profile-quick-del"' + (hasProfile ? "" : " disabled") + ' title="Delete profile">Delete</button>' +
      '</div>';
    return h;
  }

  function renderProfileModal() {
    const p = panelProfileCurrent().profile;
    if (!p) return "";
    const on = p.enabled !== false;
    const isGrp = p.is_group === true || (!p.exe && p.exe !== undefined);
    return '<div class="panel-modal-backdrop" id="panel-profile-modal">' +
      '<div class="panel-modal">' +
      '<h3>Profile settings</h3>' +
      '<div class="settings-control"><label class="settings-label">Profile name</label>' +
      '<input type="text" class="settings-input" id="profile-name" value="' + esc(p.name || "") + '"></div>' +
      '<div class="settings-toggle-row" id="profile-group-row">' +
        '<span class="settings-toggle-label">Group Profile (No linked app)</span>' +
        '<div class="settings-toggle' + (isGrp ? " on" : "") + '" id="profile-group-tog"><div class="settings-toggle-thumb"></div></div>' +
      '</div>' +
      '<span class="settings-hint" style="margin-top:-4px; margin-bottom:6px;">Group profiles are activated by a panel button. App profiles are triggered when the specified app is loaded.</span>' +
      '<div class="settings-control" id="profile-exe-wrap">' +
        '<label class="settings-toggle-label" style="display:block; margin-bottom:6px;">App Profile (EXECUTABLE)</label>' +
        '<div class="settings-picker-row">' +
          '<input type="text" class="settings-input" id="profile-exe" placeholder="e.g. EliteDangerous64.exe" value="' + esc(p.exe || "") + '"' + (isGrp ? " disabled" : "") + '>' +
          '<button type="button" class="settings-btn" id="profile-pick"' + (isGrp ? " disabled" : "") + '>Pick\u2026</button>' +
        '</div>' +
      '</div>' +
      '<div class="settings-toggle-row' + (isGrp ? " disabled" : "") + '" id="profile-tog-row">' +
        '<span class="settings-toggle-label">Auto Switch on Focus</span>' +
        '<div class="settings-toggle' + (on ? " on" : "") + '" id="profile-tog"><div class="settings-toggle-thumb"></div></div>' +
      '</div>' +
      '<span class="settings-hint" style="margin-top:-4px; margin-bottom:6px;">Automatically switches to this panel profile when the specified app gains focus.</span>' +
      '<div class="panel-modal-actions">' +
      '<button type="button" class="settings-btn settings-btn-danger" id="profile-delete">Delete</button>' +
      '<div style="flex:1"></div>' +
      '<button type="button" class="settings-btn" id="profile-cancel">Cancel</button>' +
      '<button type="button" class="settings-btn settings-btn-primary" id="profile-save">Save</button>' +
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

    const gOn = layoutOn("gauges") && (panelDraft.panel_gauges || {}).enabled !== false;
    const boxOn = layoutOn("button_box");
    const slidOn = layoutOn("sliders");
    const utilOn = layoutOn("utility");
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
            toggleRow("Show gauges", gOn, "panel-tog-gauges") +
            '<p class="settings-hint">PC stats: CPU · GPU · FPS</p>') +
          // Button box
          sectionCard("Button box", "apps",
            toggleRow("Show button box", boxOn, "panel-tog-box") +
            profileSelectHtml() +
            (boxOn ? renderBoardEditor(board, []) : '')) +
          // Sliders (brightness only when hardware is connected)
          sectionCard("Sliders", "tune",
            toggleRow("Show sliders section", slidOn, "panel-tog-sliders") +
            (slidOn ? (
              toggleRow("App volume", sliderOn("app_volume"), "panel-tog-vol") +
              toggleRow("Master volume", sliderOn("master_volume"), "panel-tog-mvol") +
              toggleRow("App mixer", sliderOn("app_mixer"), "panel-tog-mix") +
              (hwOn ? toggleRow("Display brightness", sliderOn("brightness"), "panel-tog-bri") : "")
            ) : '')) +
          // Utility
          sectionCard("Utility row", "grid_view",
            toggleRow("Show utility row", utilOn, "panel-tog-util") +
            (utilOn ? renderUtilityEditor(util) : '')) +
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

  function previewSliderHtml(id, label, value, min, max) {
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
    const layout = {};
    ((cfg && cfg.panel_layout) || (panelDraft && panelDraft.panel_layout) || []).forEach((r) => { if (r && r.id) layout[r.id] = r.enabled !== false; });
    const gOn = layout.gauges !== false && ((cfg && cfg.panel_gauges) || (panelDraft && panelDraft.panel_gauges) || {}).enabled !== false;
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

    let frameHtml = '<div class="prev-frame">';
    if (boxOn) {
      frameHtml += '<div class="prev-box">' +
        '<div class="prev-track">' +
          boardPagesHtml(curBoard) +
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
    const PAGE = 12; // buttons per device page — separator between pages
    for (let pg = 0; pg < list.length; pg += PAGE) {
      if (pg > 0) h += '<div class="panel-slot-page-sep"></div>';
      const chunk = list.slice(pg, pg + PAGE);
      chunk.forEach((slot, i) => {
        const idx = pg + i;
        const appPath = slot.app_icon_path || (slot.type === "SHORTCUT" ? slot.shortcut_path : "") || ((slot.entity === "media.player" || slot.entity === "media.eject" || slot.type === "MEDIA_EJECT") ? ((panelDraft && panelDraft.media_player_path) || (config && config.media_player_path) || "") : "") || "";
        const brandSvg = typeof getMediaPlayerBrandIcon === "function" ? getMediaPlayerBrandIcon(appPath) : null;
        let thumb = "";
        if (brandSvg) {
          thumb = '<span class="panel-slot-thumb-brand" style="width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;margin-right:8px;flex-shrink:0;">' + brandSvg + '</span>';
        } else if (appPath) {
          thumb = '<img class="panel-slot-thumb-img" src="' + API_BASE + '/api/panel/icon?path=' + encodeURIComponent(appPath) + tokQs + '" alt="" style="width:20px;height:20px;object-fit:contain;border-radius:3px;margin-right:8px;flex-shrink:0;">';
        } else if (slot.icon) {
          thumb = '<span class="md" data-md="' + esc(slot.icon) + '" style="font-size:18px;margin-right:8px;flex-shrink:0;color:var(--neon);">' + esc(mdiChar(slot.icon)) + '</span>';
        }
        h += '<div class="panel-slot-tile" draggable="true" data-act="edit" data-i="' + idx + '" data-path="' + path.join(",") + '" role="button" tabindex="0">' +
          '<div class="panel-slot-drag-handle" title="Drag to reorder"><span class="material-icons-outlined">drag_indicator</span></div>' +
          thumb +
          '<div class="panel-slot-info">' +
            '<span class="panel-slot-name">' + esc(slot.name || "(unnamed)") + '</span>' +
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

  function buildEntityOptions(targetType, curEntity) {
    let entOptHtml = '<option value=""' + (!curEntity ? ' selected' : '') + '>(None / Standalone Action)</option>';
    const domains = {};
    (panelEntities || []).forEach((ent) => {
      let include = false;
      if (targetType === "HOTKEY") {
        // Momentary Button: Actions & momentary triggers (play_pause also available)
        include = (ent.type === "action" || ent.type === "shortcut" || ent.id === "media.play_pause");
      } else if (targetType === "TOGGLE") {
        // Toggle Button: 2-state status toggles (play_pause also available as dynamic toggle)
        include = (ent.type === "status" || ent.type === "toggle" || ent.id === "media.play_pause" || (ent.writable && ent.type !== "action" && ent.type !== "shortcut" && ent.type !== "data"));
      } else if (targetType === "SENSOR") {
        // Status / Sensor: Data telemetry and read-only sensors
        include = (ent.type === "data" || ent.type === "sensor" || (ent.type === "status" && !ent.writable));
      }
      if (!include) return;

      const d = ent.domain || "Other";
      if (!domains[d]) domains[d] = [];
      domains[d].push(ent);
    });

    Object.keys(domains).forEach((d) => {
      entOptHtml += '<optgroup label="' + esc(d) + '">';
      domains[d].forEach((ent) => {
        const sel = (curEntity && ent.id === curEntity) ? " selected" : "";
        entOptHtml += '<option value="' + esc(ent.id) + '"' + sel + '>' + esc(ent.name) + ' (' + esc(ent.type) + ')</option>';
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
      { type: "SENSOR", label: "Status / Sensor" },
      { type: "EMPTY", label: "Empty / Spacer" },
      { type: "GROUP", label: "Group / Profile Link" },
    ].filter((a) => allowGroup || a.type !== "GROUP");

    const curEntity = slot.entity || (slot.plugin && slot.button_id ? (slot.plugin + "." + slot.button_id) : "");
    const showName = (slot.show_name !== false);
    const showIcon = (slot.show_icon !== false);
    const isMediaPlayPause = (curEntity === "media.play_pause");
    const isMediaEject = (curEntity === "media.player" || curEntity === "media.eject" || curType === "MEDIA_EJECT");
    const isAnyMediaControl = (isMediaPlayPause || curEntity === "media.next" || curEntity === "media.prev" || isMediaEject);
    const isShortcut = (curType === "SHORTCUT");
    const useAppIcon = (isShortcut || isMediaEject) && (slot.use_app_icon !== undefined ? !!slot.use_app_icon : (isShortcut || !!slot.app_icon_path));
    const showAlbumArt = isMediaEject && (slot.show_album_art !== undefined ? !!slot.show_album_art : true);
    const entObj = curEntity ? (panelEntities || []).find((e) => e.id === curEntity) : null;
    const isActionEntity = entObj && (entObj.type === "action" || entObj.type === "shortcut");
    const hasStateCapability = !isMediaPlayPause && !isActionEntity && (curType === "TOGGLE" || curType === "SENSOR" || (entObj && (entObj.type === "status" || entObj.type === "data" || !!entObj.state_key)));
    const showState = (slot.show_state !== false);
    const showKeys = (curType === "HOTKEY" || curType === "TOGGLE") && !isAnyMediaControl;

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

    const customIconPath = slot.app_icon_path || ((slot.entity === "media.player" || slot.entity === "media.eject" || slot.type === "MEDIA_EJECT") ? ((panelDraft && panelDraft.media_player_path) || (config && config.media_player_path) || "") : "") || "";
    const brandSvg = typeof getMediaPlayerBrandIcon === "function" ? getMediaPlayerBrandIcon(customIconPath) : null;
    const tokQs = sessionTokenQuery();

    let iconBadgeInner = brandSvg
      ? '<span class="pe-brand-icon-preview" style="width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;">' + brandSvg + '</span>'
      : (customIconPath
        ? '<img class="pe-icon-live-img" id="pe-icon-live-img" src="' + API_BASE + '/api/panel/icon?path=' + encodeURIComponent(customIconPath) + tokQs + '" alt="">'
        : '<span class="md" id="pe-icon-live" data-md="' + esc(curIcon) + '">' + esc(curIconChar) + '</span>');

    const entOptHtml = buildEntityOptions(curType, curEntity);

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
            '<select class="settings-select" id="pe-entity">' + entOptHtml + '</select>' +
            '<span class="settings-hint">Pick a game/system entity to auto-populate defaults and bind live telemetry.</span>' +
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

          '<div class="settings-control" id="pe-quick-apps-wrap" style="display:none">' +
            '<label class="settings-label">Detected / Common Apps</label>' +
            '<div class="pe-app-chips" style="display:flex;gap:6px;margin-top:4px;flex-wrap:wrap">' +
              COMMON_QUICK_APPS.map((app) =>
                '<button type="button" class="settings-btn-mini pe-app-chip" data-name="' + esc(app.name) + '" data-path="' + esc(app.path) + '"' + (app.icon ? ' data-icon="' + esc(app.icon) + '"' : '') + '>' +
                  (app.brand && typeof getMediaPlayerBrandIcon === "function" && getMediaPlayerBrandIcon(app.brand) ? '<span class="pe-chip-brand-svg" style="width:14px;height:14px;display:inline-flex;align-items:center;margin-right:4px;">' + getMediaPlayerBrandIcon(app.brand) + '</span>' : '') +
                  esc(app.name) +
                '</button>'
              ).join("") +
            '</div>' +
          '</div>' +

          '<div class="settings-control" id="pe-path-wrap" style="display:none"><label class="settings-label">Shortcut path</label>' +
          '<div class="settings-picker-row">' +
          '<input type="text" class="settings-input" id="pe-path" value="' + esc(slot.shortcut_path || "") + '" placeholder="e.g. cmd.exe or C:\\Windows\\notepad.exe">' +
          '<button type="button" class="settings-btn" id="pe-browse">Browse</button></div></div>' +
          '<div class="settings-control" id="pe-args-wrap" style="display:none"><label class="settings-label">Arguments / Switches (Optional)</label>' +
          '<input type="text" class="settings-input" id="pe-args" value="' + esc(slot.shortcut_args || "") + '" placeholder="e.g. /k &quot;cd /d C:\\dir&quot; or --flag">' +
          '<span class="settings-hint">Passed directly to executable on launch.</span></div>' +

          '<div class="settings-control" id="pe-keys-wrap"' + (showKeys ? "" : ' style="display:none"') + '>' +
            '<div style="display:flex;align-items:center;gap:6px">' +
              '<label class="settings-label" style="margin:0">Hotkey (Trigger Keystroke)</label>' +
              '<span class="pe-hotkey-help" title="Type or press Capture to record.\n\nSupported keys:\nDigits: 0-9\nLetters: A-Z\nF-keys: F1-F24\nNumpad: Num0-Num9, NumEnter, Num+, Num-, Num*, Num/\nModifiers: Ctrl, Alt, Shift\nOther: Space, Enter, Tab, Esc, Backspace\nNav: Up, Down, Left, Right, Home, End, PgUp, PgDn, Ins, Del\nCombos: Ctrl+1, Alt+F5, Ctrl+Alt+Numpad0\n\nSentences (type text): wrap in quotes.\ne.g. enter &quot;Hello World&quot; enter\npresses Enter, types Hello World, presses Enter.\n\nBackspace clears the field.">?</span>' +
            '</div>' +
            '<div class="pe-hotkey-input-row">' +
              '<input type="text" class="settings-input pe-hotkey-input" id="pe-keys" value="' + esc(curHotkey) + '" placeholder="Space, Enter, F13, Ctrl+1, Enter &quot;Hello World&quot; Enter...">' +
              '<button type="button" class="settings-btn pe-hotkey-capture-btn" id="pe-hotkey-capture-btn" title="Press a key combo to record it">Capture</button>' +
            '</div>' +
            '<div class="pe-key-chips" style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">' +
              '<button type="button" class="settings-btn-mini pe-chip" data-k="1">1</button>' +
              '<button type="button" class="settings-btn-mini pe-chip" data-k="Space">Space</button>' +
              '<button type="button" class="settings-btn-mini pe-chip" data-k="Enter">Enter</button>' +
              '<button type="button" class="settings-btn-mini pe-chip" data-k="F13">F13</button>' +
              '<button type="button" class="settings-btn-mini pe-chip" data-k="Ctrl+1">Ctrl+1</button>' +
              '<button type="button" class="settings-btn-mini pe-chip" data-k="Numpad1">Num1</button>' +
              '<button type="button" class="settings-btn-mini pe-chip" data-k="Ctrl+Space">Ctrl+Space</button>' +
            '</div>' +
          '</div>' +
        '</div>' +

        /* Column 2: Visual Styling & Card Display */
        '<div class="panel-modal-col" id="pe-visual-col">' +
          '<div class="settings-control" id="pe-appicon-wrap" style="display:none"><label class="settings-label">App icon</label>' +
          '<div class="settings-appicon-row">' +
            '<img class="settings-appicon-preview" id="pe-appicon-preview" alt="" hidden>' +
            '<span class="settings-hint" id="pe-appicon-status">Pulled automatically from executable.</span>' +
          '</div></div>' +
          '<div class="settings-control" id="pe-icon-row-wrap">' +
            '<label class="settings-label">Icon</label>' +
            '<div class="pe-icon-container">' +
              '<div class="pe-icon-input-row" id="pe-icon-trigger-row">' +
                '<span class="pe-icon-live-badge" id="pe-icon-live-badge" title="Active Icon Preview (Click to browse MDI icons)"' + badgeStyle + '>' +
                  iconBadgeInner +
                '</span>' +
                '<input type="text" class="settings-select pe-icon-select" id="pe-icon" value="' + esc(customIconPath ? (customIconPath.split(/[\\/]/).pop() || customIconPath) : curIcon) + '" placeholder="Select icon..." readonly>' +
                '<button type="button" class="settings-btn pe-icon-browse-btn" id="pe-icon-browse-btn" title="Choose custom icon (.ico, .exe, .png, .lnk)">Browse</button>' +
                '<button type="button" class="settings-btn settings-btn-secondary pe-icon-clear-btn" id="pe-icon-clear-btn" style="display:none" title="Clear custom icon">Clear</button>' +
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
                '<button type="button" class="pe-swatch" data-color="#16171a" style="background:#16171a" title="LCD Dark Charcoal"></button>' +
                '<button type="button" class="pe-swatch" data-color="#0d0e10" style="background:#0d0e10" title="OLED Deep Black"></button>' +
                '<button type="button" class="pe-swatch pe-swatch-rainbow" data-color="RAINBOW" title="Rainbow Sheen">🌈</button>' +
                '<button type="button" class="pe-swatch pe-swatch-clear" data-color="" title="Clear / Theme Default">✕ Clear</button>' +
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
              '<label class="pe-display-toggle-row pe-sub-toggle-row' + (showIcon ? "" : " disabled") + '" id="pe-use-app-icon-row"' + ((isShortcut || isMediaEject) ? "" : ' style="display:none"') + '>' +
                '<input type="checkbox" id="pe-use-app-icon"' + (useAppIcon ? " checked" : "") + (showIcon ? "" : " disabled") + '>' +
                '<span class="pe-toggle-label">App Icon</span>' +
                '<span class="pe-toggle-hint">Override with app icon</span>' +
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
    bindTog("panel-tog-gauges", (on) => {
      panelDraft.panel_gauges = panelDraft.panel_gauges || {};
      panelDraft.panel_gauges.enabled = on;
      setLayoutOn("gauges", on);
    });
    bindTog("panel-tog-box", (on) => setLayoutOn("button_box", on));
    bindTog("panel-tog-sliders", (on) => setLayoutOn("sliders", on));
    bindTog("panel-tog-util", (on) => setLayoutOn("utility", on));
    bindTog("panel-tog-vol", (on) => setSliderOn("app_volume", on));
    bindTog("panel-tog-mvol", (on) => setSliderOn("master_volume", on));
    bindTog("panel-tog-mix", (on) => setSliderOn("app_mixer", on));
    bindTog("panel-tog-bri", (on) => setSliderOn("brightness", on));

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
        if (panelProfileSel === "__default__") return;
        if (!panelProfileCurrent().profile) return;
        panelEdit = null;
        panelProfileModal = true;
        renderPanel();
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
    const profSave = document.getElementById("profile-save");
    if (profSave) {
      profSave.addEventListener("click", () => {
        const p = panelProfileCurrent().profile;
        if (!p) return;
        const isGrp = document.getElementById("profile-group-tog").classList.contains("on");
        p.name = document.getElementById("profile-name").value.trim();
        p.is_group = isGrp;
        p.exe = isGrp ? "" : document.getElementById("profile-exe").value.trim();
        p.enabled = isGrp ? true : document.getElementById("profile-tog").classList.contains("on");
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
    const lay = (cfg.panel_layout || []).map((r) => r.id + "=" + (r.enabled === false ? 0 : 1)).join(",");
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
      notifKey(),
    ]);
  }

  function fetchPanelLive() {
    apiFetch(`${API_BASE}/api/panel/live`)
      .then((r) => r.json())
      .then((data) => {
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
      .catch(() => {});
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

  function rememberBoxScroll() {
    const box = document.querySelector(".panel-view-overlay .pv-box");
    if (!box) return;
    boxScrollLeft = Math.round(box.scrollLeft);
  }

  function restoreBoxScroll() {
    const box = document.querySelector(".panel-view-overlay .pv-box");
    if (!box) return;
    box.scrollLeft = boxScrollLeft;
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
    if (msg.type === "notification") {
      screensaverWakeOnEvent();
      if (panelLive) {
        panelLive.notification = msg;
      }
      triggerNotificationSlide(normalizeNotifTheme(msg.theme), false, msg);
      pendingNotifSlide = true;
      if (currentPage === "notifications") {
        fetchNotifications();
      }
    } else if (msg.type === "event") {
      screensaverWakeOnEvent();
      const status = msg.status || "good";
      const theme = status === "bad" ? "red" : (status === "good" ? "green" : "purple");
      triggerNotificationSlide(theme, true, msg);
      pendingNotifSlide = true;
    } else if (msg.type === "theme") {
      if (msg.theme && typeof window.applyTheme === "function") {
        window.applyTheme(msg.theme);
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

  function triggerNotificationSlide(theme, isEvent, eventData) {
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

  function setupNotifDrawerGestures() {
    // Swipe handles: the gauges strip and the button box (the box's other axis
    // is the paging scroll; directional guard below keeps the two apart) plus
    // the open drawer itself.
    const handles = Array.from(document.querySelectorAll(".panel-view-overlay .pv-gauges, .panel-view-overlay .pv-box, .panel-view-overlay #pv-notif"));
    if (!handles.length) return;

    let startX = 0;
    let startY = 0;
    let tracking = false;
    const THRESH = 60;

    handles.forEach((h) => {
      h.addEventListener("touchstart", (e) => {
        if (e.touches.length !== 1) return;
        tracking = true;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
      }, { passive: true });

      h.addEventListener("touchend", (e) => {
        if (!tracking) return;
        tracking = false;
        const t = e.changedTouches[0];
        const dx = t.clientX - startX;
        const dy = t.clientY - startY;
        const isLand = document.documentElement.classList.contains("is-landscape");
        // Convert screen-space delta to portrait space (screen is rotated -90deg
        // in landscape: portrait-down = screen-right, portrait-right = screen-down)
        const pdx = isLand ? -dy : dx;
        const pdy = isLand ? dx : dy;
        if (Math.hypot(pdx, pdy) < THRESH) return;
        // The drawer gesture is along portrait-y (down = open, up = close).
        // Ignore portrait-x-dominant swipes — those are button track paging.
        if (Math.abs(pdy) <= Math.abs(pdx)) return;
        if (pdy > 0) {
          openNotifDrawer();
        } else {
          closeNotifDrawer();
        }
      }, { passive: true });
    });
  }

  function renderPanelView() {
    const ov = ensurePanelOverlay();
    const data = panelLive || {};
    const cfg = panelViewConfig();

    const layout = {};
    (cfg.panel_layout || []).forEach((r) => { layout[r.id] = r.enabled !== false; });
    const gOn = layout.gauges !== false && (cfg.panel_gauges || {}).enabled !== false;
    const boxOn = layout.button_box !== false;
    const slidOn = layout.sliders !== false;
    const utilOn = layout.utility !== false;
    const sliders = {};
    (cfg.panel_sliders || []).forEach((r) => { sliders[r.id] = r.enabled !== false; });
    const hw = !!(data.hardware_connected !== undefined ? data.hardware_connected
      : (panelDraft && panelDraft.hardware_connected));
    const briOn = hw && sliders.brightness !== false;
    const volOn = sliders.app_volume !== false;
    const mvolOn = sliders.master_volume !== false;
    const mixOn = sliders.app_mixer !== false;

    const board = panelNav.length
      ? (panelNav[panelNav.length - 1].children || [])
      : (cfg.panel_board || []);
    const util = cfg.panel_utility || [];
    const gauges = data.gauges || {};
    const volume = data.volume || {};

    const notif = data.notification || null;
    const curNotifKey = notifKey();
    if (curNotifKey && curNotifKey !== lastNotifKey) {
      pendingNotifSlide = true;
    }
    lastNotifKey = curNotifKey;
    let html = '<div class="pv-screen">';
    const gaugesHtml = gOn
      ? '<div class="pv-gauges">' +
        panelGauge("CPU", gauges.cpu_temp, gauges.cpu_temp_max || 100, gauges.cpu_temp_unit || "") +
        panelGauge("GPU", gauges.gpu_temp, gauges.gpu_temp_max || 100, gauges.gpu_temp_unit || "") +
        panelGauge("FPS", gauges.fps, gauges.fps_max || gauges.refresh_rate || 60) +
        '</div>'
      : "";
    let frameHtml = '<div class="pv-frame">';
    // Notification drawer overlays the BUTTON widget: it sits at the top of the
    // frame (which is the top of the button box) and fills the whole 12-icon
    // box (height --pv-box-h), sliding down from the direction of the gauges.
    // It never covers the gauges themselves.
    frameHtml += '<div class="pv-notif" id="pv-notif">' + notifHtml(notif) + '</div>';
    if (boxOn) {
      // Button box = horizontal track of page grids. Landscape is the portrait
      // page rotated -90deg, so the DOM is identical; the notif drawer sits at
      // the top of the frame and slides down over this box.
      frameHtml += '<div class="pv-box">' +
        '<div class="pv-track">' +
          boardPagesHtml(board) +
        '</div>' +
      '</div>';
    }
    frameHtml += '<div class="pv-side">';
    if (slidOn) {
      frameHtml += '<div class="pv-sliders">' +
        (volOn ? panelSliderHtml("app_volume", "App Volume", volume.volume, 0, 100) : "") +
        (mvolOn ? panelSliderHtml("master_volume", "Master Volume", data.master_volume, 0, 100) : "") +
        (mixOn ? appMixerHtml(data.app_volumes || []) : "") +
        (briOn ? panelSliderHtml("brightness", "Brightness", data.brightness, 0, 4) : "") +
      '</div>';
    }
    frameHtml += '</div>';
    frameHtml += '</div>';

    // Portrait structure for BOTH orientations (landscape is this page rotated):
    // gauges + frame inside .pv-scroll; util/core pinned below. The notif drawer
    // is inside the frame (over the button widget), not here.
    html += '<div class="pv-scroll">';
    html += gaugesHtml;
    html += frameHtml;
    html += '</div>';
    if (utilOn) {
      html += '<div class="pv-util"><div class="pdev-grid">' + utilTilesHtml(util) + '</div></div>';
    }
    html += '<div class="pv-core"><div class="pdev-grid">' + coreTilesHtml(data) + '</div></div>';
    html += '</div>';

    rememberBoxScroll();
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
      restoreBoxScroll();
      // Orientation flip: jump to the SAME page number that was on screen
      // before the rotation, identified by its data-page.
      if (pendingPanelPage !== null) {
        const pbox = ov.querySelector(".pv-box");
        if (pbox) {
          const g = pbox.querySelector('.pdev-grid[data-page="' + pendingPanelPage + '"]');
          if (g) {
            const track = pbox.querySelector(".pv-track");
            const W = track ? track.offsetWidth : 0;
            const isLand = document.documentElement.classList.contains("is-landscape");
            const x = track ? (isLand ? g.offsetLeft : (g.offsetLeft - track.offsetLeft)) : 0;
            boxScrollLeft = isLand ? (W - x - g.offsetWidth) : x;
            pbox.scrollLeft = boxScrollLeft;
          }
        }
        pendingPanelPage = null;
      }
      if (pendingNotifSlide) {
        pendingNotifSlide = false;
        triggerNotificationSlide();
      }
    });
    panelViewSig = panelViewSignature();
  }

  function layoutPanelBox(ov) {
    const root = ov || document.getElementById("panel-view");
    if (!root) return;
    const box = root.querySelector(".pv-box");
    if (!box) return;
    // Portrait is the ONLY sizing reference; landscape is the same page rotated
    // 90°, so this one path serves both orientations. After rotation the box
    // measures the phone's short edge and the tile matches portrait exactly.
    const isLand = document.documentElement.classList.contains("is-landscape");
    const cols = 4;
    const rows = 3;
    const gap = 8;
    const trackGap = 8;
    box.style.width = "";
    box.style.height = "";
    let pageW = Math.round(box.clientWidth);
    if (!pageW || pageW < 80) {
      const axis = isLand ? (window.innerHeight || 393) : (window.innerWidth || 393);
      pageW = Math.min(Math.round(axis), 393) - 32;
    }
    const tile = Math.max(36, Math.floor((pageW - (cols - 1) * gap) / cols));
    const page = tile * cols + gap * (cols - 1);
    const boxH = tile * rows + gap * (rows - 1);
    box.style.setProperty("--pv-cols", String(cols));
    box.style.setProperty("--pv-rows", String(rows));
    box.style.setProperty("--pv-gap", gap + "px");
    box.style.setProperty("--pv-track-gap", trackGap + "px");
    box.style.setProperty("--pv-tile", tile + "px");
    box.style.setProperty("--pv-page", page + "px");
    box.style.setProperty("--pv-box-h", boxH + "px");
    root.style.setProperty("--pv-tile", tile + "px");
    root.style.setProperty("--pv-gap", gap + "px");
    // Expose the button-box height to the whole overlay so the notification
    // toast (.pv-notif, a sibling of .pv-box in the frame) can fill it.
    root.style.setProperty("--pv-box-h", boxH + "px");
    if (isLand) {
      box.style.height = boxH + "px";
    }
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
            '<linearGradient id="pdev-ggrad" x1="0%" y1="100%" x2="100%" y2="0%">' +
              '<stop offset="0%" stop-color="var(--theme-color-1, #B23AF6)" />' +
              '<stop offset="100%" stop-color="var(--theme-color-2, #79E8FC)" />' +
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

  function boardPagesHtml(board) {
    let h = "";
    const list = board || [];
    const PAGE = 12;
    const totalTiles = list.length;
    const numPages = Math.max(1, Math.ceil(totalTiles / PAGE));
    // Landscape = portrait DOM rotated -90deg (rotate(-90) maps portrait RIGHT
    // to screen-UP, portrait TOP to screen-LEFT), so a 4x3 grid's natural
    // row-major order reads jumbled on screen (4,8,12 / 3,7,11 / ...).
    // Reorder each page's slots so the on-screen reading is 1..12 row-major:
    // DOM position p holds slot perm[p] = (3 - (p % 4)) * 3 + floor(p / 4),
    // i.e. the DOM grid becomes  10 7 4 1 / 11 8 5 2 / 12 9 6 3  (portrait
    // space), which the -90deg rotation displays as 123/456/789/101112.
    const isLand = document.documentElement.classList.contains("is-landscape");

    for (let pg = 0; pg < numPages; pg++) {
      h += '<div class="pdev-grid" data-page="' + pg + '">';
      const startIdx = pg * PAGE;

      for (let p = 0; p < PAGE; p++) {
        const slotOffset = isLand ? (3 - (p % 4)) * 3 + Math.floor(p / 4) : p;
        const i = startIdx + slotOffset;
        if (pg === 0 && panelNav.length && p === 0) {
          h += '<button type="button" class="pdev-tile pdev-back" data-nav="back" title="Back">' +
            '<span class="md" data-md="arrow-left"></span></button>';
          continue;
        }
        const s = list[i];
        if (!s || s.type === "EMPTY") {
          h += '<button type="button" class="pdev-tile pdev-empty-tile" data-action="slot" data-list="board" data-idx="' + i + '"></button>';
        } else {
          h += panelTileHtml(s, "board", i);
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
      appPath = (panelLive && panelLive.config && panelLive.config.media_player_path) || (panelDraft && panelDraft.media_player_path) || (config && config.media_player_path) || "";
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
    let extraTileClass = "";
    let extraTileStyle = "";

    const entKey = s.entity || (s.plugin && s.button_id ? (s.plugin + "." + s.button_id) : "");
    const bState = (panelLive && (
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
    }

    if (showAlbumArt && mediaState.has_art) {
      const artUrl = API_BASE + '/api/media/art?t=' + encodeURIComponent(mediaState.art_id || Date.now()) + tokQs;
      albumArtPlate = '<span class="pdev-album-art-bg" style="background-image:url(\'' + esc(artUrl) + '\');"></span>';
      extraTileClass += " has-album-art" + (isMediaPlaying ? " is-playing" : (isMediaPaused ? " is-paused" : ""));
    }

    const hasLiveState = (bState.active !== undefined || bState.label !== undefined || bState.value !== undefined);
    const isOn = !!bState.active;
    if (isOn) extraTileClass += " pdev-active has-halo";

    const labels = s.labels || {};
    const colors = s.colors || {};
    const activeColor = colors.on || "var(--neon-grn)";
    const inactiveColor = colors.off || "var(--fg-dim)";
    const badgeColor = isOn ? activeColor : inactiveColor;

    if (isOn && !colorPlate && !albumArtPlate) {
      extraTileStyle = ' style="border-color:' + esc(activeColor) + '; box-shadow:0 0 10px ' + esc(activeColor) + '44;"';
    }

    if (isGroup) {
      topBar = '<span class="pdev-group-bar">GROUP</span>';
      extraTileClass += " has-group-bar";
    } else if (s.entity !== "media.play_pause" && showState && (hasLiveState || labels.on || labels.off)) {
      const lblText = bState.label || (isOn ? (labels.on || "ON") : (labels.off || "OFF"));
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
      extraTileStyle = ' style="--warn-color:' + esc(warn.color) + '; border-color:' + esc(warn.color) + '; background:' + esc(warn.color) + '; color:' + warnText + ';"';
      glyphStyle = ' style="color:' + warnText + ';"';
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
        const targetPath = appPath || (panelLive && panelLive.config && panelLive.config.media_player_path) || (panelDraft && panelDraft.media_player_path) || (config && config.media_player_path) || "";
        const brandSvg = typeof getMediaPlayerBrandIcon === "function" ? getMediaPlayerBrandIcon(targetPath) : null;
        if (brandSvg) {
          glyph = '<span class="pdev-ibrand pdev-iapp">' + brandSvg + '</span>' +
            '<span class="pdev-iapp-overlay"></span>';
        } else if (targetPath) {
          glyph = '<img class="pdev-iapp" src="' + API_BASE + '/api/panel/icon?path=' + encodeURIComponent(targetPath) + tokQs +
            '" alt="" data-fallback="' + esc(icon) + '">' +
            '<span class="pdev-iapp-overlay"></span>';
        } else {
          glyph = '<span class="md" data-md="' + esc(icon) + '"' + glyphStyle + '>' + esc(mdiChar(icon)) + '</span>';
        }
      } else {
        glyph = '<span class="md" data-md="' + esc(icon) + '"' + glyphStyle + '>' + esc(mdiChar(icon)) + '</span>';
      }
    } else {
      glyph = '<span class="pdev-text-only"' + glyphStyle + '>' + esc(formatTileTitle(s.name || s.type || "")) + '</span>';
    }

    return '<button type="button" class="pdev-tile' + (isGroup ? " pdev-group" : "") + extraTileClass + '"' +
      extraTileStyle +
      ' draggable="true"' +
      ' data-action="slot" data-list="' + listName + '" data-idx="' + idx + '"' +
      ' title="' + esc(s.name || "") + '">' +
      colorPlate +
      albumArtPlate +
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
        '<div class="pdev-slab"><span class="pdev-sname">' + esc(name) + '</span></div>' +
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
    return panelProfileCurrent().board;
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
        panelNav.push({ prevProfile: panelProfileSel });
        panelProfileSel = targetProf;
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
    if (slot.type === "SCREENSHOT") {
      doScreenshotRequest(slot);
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
      });
    }
    setupNotifDrawerGestures();
    const tiles = document.querySelectorAll(".pdev-tile");
    tiles.forEach((tile) => {
      if (tile.getAttribute("data-nav") === "back") {
        tile.addEventListener("click", () => {
          const prev = panelNav.pop();
          if (prev && prev.prevProfile) {
            panelProfileSel = prev.prevProfile;
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

    document.querySelectorAll("input[type=range].pdev-range").forEach((rng) => {
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
        }, 200);
      });
    });
  }

  function updatePanelView() {
    const data = panelLive || {};
    const gauges = data.gauges || {};
    const volume = data.volume || {};

    updateGauge("CPU", gauges.cpu_temp, gauges.cpu_temp_max || 100, gauges.cpu_temp_unit || "°C");
    updateGauge("GPU", gauges.gpu_temp, gauges.gpu_temp_max || 100, gauges.gpu_temp_unit || "°C");
    updateGauge("FPS", gauges.fps, gauges.fps_max || gauges.refresh_rate || 60, "");

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

    const apps = data.app_volumes || [];
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
      notifEl.innerHTML = notifHtml(notif);
      notifEl.classList.remove("notif-theme-green", "notif-theme-red", "notif-flash-green", "notif-flash-red");
    }

    const curNotifKey = notifKey();
    if (curNotifKey && curNotifKey !== lastNotifKey) {
      lastNotifKey = curNotifKey;
      pendingNotifSlide = true;
    }

    const mediaState = (data.entity_states && data.entity_states["media.player"]) || {};
    const isMediaPlaying = !!(mediaState && (mediaState.active || mediaState.status === "playing" || mediaState.playback_status === "playing"));
    const isMediaPaused = !!(mediaState && (mediaState.status === "paused" || mediaState.playback_status === "paused"));

    const btnStates = (data.entity_states) || (data.plugin_button_states) || {};
    document.querySelectorAll(".pdev-tile").forEach((tile) => {
      const idx = parseInt(tile.getAttribute("data-idx"), 10);
      const list = tile.getAttribute("data-list");
      if (isNaN(idx) || !list) return;
      const board = (list === "util") ? ((panelDraft && panelDraft.panel_utility) || []) : currentBoard();
      const s = board[idx];
      if (s) {
        const entKey = s.entity || (s.plugin && s.button_id ? (s.plugin + "." + s.button_id) : "");
        const bState = btnStates[entKey] || btnStates[(s.plugin || "") + ":" + (s.button_id || "")] || {};
        const isOn = !!bState.active;

        tile.classList.toggle("pdev-active", isOn);
        tile.classList.toggle("has-halo", isOn);

        const colors = s.colors || {};
        const activeColor = colors.on || "var(--neon-grn)";
        const inactiveColor = colors.off || "var(--fg-dim)";
        const badgeColor = isOn ? activeColor : inactiveColor;

        if (isOn && !s.color) {
          tile.style.borderColor = activeColor;
          tile.style.boxShadow = "0 0 10px " + activeColor + "44";
        } else if (!s.color) {
          tile.style.borderColor = "";
          tile.style.boxShadow = "";
        }

        // Update status bar
        const statusBar = tile.querySelector(".pdev-status-bar");
        if (statusBar) {
          const labels = s.labels || {};
          const lblText = bState.label || (isOn ? (labels.on || "ON") : (labels.off || "OFF"));
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
          const mAppPath = s.app_icon_path || (panelLive && panelLive.config && panelLive.config.media_player_path) || (panelDraft && panelDraft.media_player_path) || (config && config.media_player_path) || "";
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

  function updateGauge(label, value, max, unit) {
    const v = (value === null || value === undefined) ? 0 : value;
    const m = max || 100;
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
      const nm = (name || "apps").trim();
      const badge = document.getElementById("pe-icon-live-badge");
      if (!badge) return;
      if (customSelectedIconPath) {
        loadCustomIconPreview(customSelectedIconPath);
      } else {
        if (badge._blobUrl) {
          URL.revokeObjectURL(badge._blobUrl);
          badge._blobUrl = null;
        }
        badge.innerHTML = '<span class="md" id="pe-icon-live" data-md="' + esc(nm) + '">' + esc(mdiChar(nm)) + '</span>';
        mdiPreload([nm]);
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
    syncIconClearBtn();

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

    if (iconBrowseBtn) {
      iconBrowseBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        browseCustomIcon((p) => {
          if (p) {
            customSelectedIconPath = p;
            if (iconInput) iconInput.value = p.split(/[\\/]/).pop() || p;
            loadCustomIconPreview(p);
            if (iconPopup) iconPopup.style.display = "none";
            syncIconClearBtn();
          }
        });
      });
    }

    function syncIconClearBtn() {
      if (iconClearBtn) iconClearBtn.style.display = customSelectedIconPath ? "" : "none";
    }

    if (iconClearBtn) {
      iconClearBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        customSelectedIconPath = "";
        const curName = (iconInput ? iconInput.value : "") || "apps";
        updateLiveIcon(curName);
        syncIconClearBtn();
      });
    }

    if (iconSearch) {
      iconSearch.addEventListener("click", (e) => e.stopPropagation());
      iconSearch.addEventListener("input", (e) => {
        e.stopPropagation();
        const val = iconSearch.value;
        filterAndRenderIcons(val, activeIconCategory);
        clearTimeout(iconSearchTimer);
        iconSearchTimer = setTimeout(() => {
          searchMdiIcons(val, activeIconCategory);
        }, 120);
      });
    }

    if (iconPopup) {
      iconPopup.addEventListener("click", (e) => e.stopPropagation());
      iconPopup.querySelectorAll(".pe-icon-cat-pill").forEach((pill) => {
        pill.addEventListener("click", (e) => {
          e.stopPropagation();
          iconPopup.querySelectorAll(".pe-icon-cat-pill").forEach((p) => p.classList.remove("active"));
          pill.classList.add("active");
          activeIconCategory = pill.getAttribute("data-cat") || "all";
          const query = iconSearch ? iconSearch.value : "";
          filterAndRenderIcons(query, activeIconCategory);
          searchMdiIcons(query, activeIconCategory);
        });
      });
    }

    function loadAppIcon() {
      const p = (document.getElementById("pe-path") ? document.getElementById("pe-path").value : "").trim() ||
        (modalSlot.app_icon_path || ((modalSlot.entity === "media.player" || modalSlot.entity === "media.eject" || modalSlot.type === "MEDIA_EJECT") ? ((panelDraft && panelDraft.media_player_path) || (config && config.media_player_path) || "") : "") || "");
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
      const quickAppsWrap = document.getElementById("pe-quick-apps-wrap");
      if (quickAppsWrap) quickAppsWrap.style.display = isAppShortcut ? "" : "none";
      const pathWrap = document.getElementById("pe-path-wrap");
      if (pathWrap) pathWrap.style.display = showPath ? "" : "none";
      const argsWrap = document.getElementById("pe-args-wrap");
      if (argsWrap) argsWrap.style.display = showPath ? "" : "none";
      const appIconWrap = document.getElementById("pe-appicon-wrap");
      if (appIconWrap) appIconWrap.style.display = showAppIcon ? "" : "none";
      const iconRowWrap = document.getElementById("pe-icon-row-wrap");
      if (iconRowWrap) iconRowWrap.style.display = isAppShortcut ? "none" : "";

      const entSelectEl = document.getElementById("pe-entity");
      if (entSelectEl) {
        const curVal = entSelectEl.value;
        entSelectEl.innerHTML = buildEntityOptions(t, curVal);
        if (isAppShortcut || showGroupProf || isEmpty) {
          entSelectEl.value = "";
        }
      }

      const entId = entSelectEl ? entSelectEl.value.trim() : "";
      const isMediaPlayPause = (entId === "media.play_pause");
      const isMediaEject = (entId === "media.player" || entId === "media.eject" || t === "MEDIA_EJECT");
      const isAnyMediaControl = (isMediaPlayPause || entId === "media.next" || entId === "media.prev" || isMediaEject);
      const isMediaControl = (isMediaPlayPause || entId === "media.next" || entId === "media.prev");
      const showKeys = (t === "HOTKEY" || t === "TOGGLE") && !isAnyMediaControl;

      const keysWrap = document.getElementById("pe-keys-wrap");
      if (keysWrap) keysWrap.style.display = showKeys ? "" : "none";

      if (iconRowWrap) iconRowWrap.style.display = (isAppShortcut || isMediaControl) ? "none" : "";

      const entObj = (panelEntities || []).find((e) => e.id === entId);
      const isActionEntity = entObj && (entObj.type === "action" || entObj.type === "shortcut") && !isMediaPlayPause;
      const hasStateCapability = !isMediaPlayPause && !isActionEntity && (t === "TOGGLE" || t === "SENSOR" || (entObj && (entObj.type === "status" || entObj.type === "data" || !!entObj.state_key)));
      const stateRow = document.getElementById("pe-show-state-row");
      if (stateRow) stateRow.style.display = hasStateCapability ? "" : "none";

      const albumArtRow = document.getElementById("pe-show-album-art-row");
      if (albumArtRow) albumArtRow.style.display = isMediaEject ? "" : "none";

      const useAppIconRow = document.getElementById("pe-use-app-icon-row");
      if (useAppIconRow) useAppIconRow.style.display = (isAppShortcut || isMediaEject) ? "" : "none";

      // Auto-tick App Icon when the type is App/Shortcut and there is no stored
      // preference yet (new action, or pre-feature shortcut), matching the
      // modal's render default above.
      const useAppIconCheckEl = document.getElementById("pe-use-app-icon");
      if (useAppIconCheckEl && isAppShortcut && modalSlot.use_app_icon === undefined) {
        useAppIconCheckEl.checked = true;
      }

      const visualCol = document.getElementById("pe-visual-col");
      const bodyGrid = document.getElementById("pe-body-grid");
      const modalCard = modal.querySelector(".panel-modal");
      const hideVisual = isEmpty;
      if (visualCol) visualCol.style.display = hideVisual ? "none" : "";
      if (bodyGrid) bodyGrid.style.gridTemplateColumns = hideVisual ? "1fr" : "";
      if (modalCard) modalCard.style.maxWidth = hideVisual ? "480px" : "";

      if (showAppIcon) {
        try { loadAppIcon(); } catch (e) { appIconPreview.hidden = true; }
      } else appIconPreview.hidden = true;
    };
    typeEl.addEventListener("change", syncFields);
    syncFields();

    // Gating App Icon checkbox by Show Icon
    const showIconCheck = document.getElementById("pe-show-icon");
    const useAppIconCheck = document.getElementById("pe-use-app-icon");
    const useAppIconRow = document.getElementById("pe-use-app-icon-row");
    if (showIconCheck && useAppIconCheck) {
      showIconCheck.addEventListener("change", () => {
        useAppIconCheck.disabled = !showIconCheck.checked;
        if (useAppIconRow) useAppIconRow.classList.toggle("disabled", !showIconCheck.checked);
      });
    }

    // Entity Quick-Fill auto-population
    const entSelect = document.getElementById("pe-entity");
    if (entSelect) {
      entSelect.addEventListener("change", () => {
        const entId = entSelect.value;
        const found = (panelEntities || []).find((e) => e.id === entId);
        if (found) {
          const nameInp = document.getElementById("pe-name");
          if (nameInp && (!nameInp.value || nameInp.value === "New Action")) nameInp.value = found.name;
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
          if (found.type === "data") typeEl.value = "SENSOR";
          else if (found.type === "action") typeEl.value = "HOTKEY";
          else if (found.type === "shortcut") typeEl.value = "SHORTCUT";
          else if (found.type === "status" || found.writable) typeEl.value = "TOGGLE";
          else typeEl.value = "SENSOR";
          syncFields();
        } else {
          syncFields();
        }
      });
    }

    // Quick App chips wiring
    modal.querySelectorAll(".pe-app-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const name = chip.getAttribute("data-name") || "";
        const path = chip.getAttribute("data-path") || "";
        const icon = chip.getAttribute("data-icon") || "";
        const nameInp = document.getElementById("pe-name");
        if (nameInp) nameInp.value = name;
        const pathInp = document.getElementById("pe-path");
        if (pathInp) pathInp.value = path;
        if (icon && iconInput) {
          iconInput.value = icon;
          updateLiveIcon(icon);
        }
        loadAppIcon();
      });
    });

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
      iconTimer = setTimeout(loadAppIcon, 400);
    });
    // Hotkey chips wiring
    modal.querySelectorAll(".pe-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const k = chip.getAttribute("data-k") || "";
        const keysInp = document.getElementById("pe-keys");
        if (keysInp) keysInp.value = k;
      });
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
        keysInp.value = mod.length ? mod.join("+") + "+" + token : token;
        setCapture(false);
        e.preventDefault();
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
      const useAppIcon = (isApp || isMediaEject) && (document.getElementById("pe-use-app-icon") && !document.getElementById("pe-use-app-icon").disabled)
        ? document.getElementById("pe-use-app-icon").checked
        : false;
      const showAlbumArt = isMediaEject && document.getElementById("pe-show-album-art")
        ? document.getElementById("pe-show-album-art").checked
        : false;
      const showState = (hasStateCapability && document.getElementById("pe-show-state")) ? document.getElementById("pe-show-state").checked : false;

      const slot = {
        name: (document.getElementById("pe-name") ? document.getElementById("pe-name").value.trim() : ""),
        type: t,
        show_name: showName,
        show_icon: showIcon,
        use_app_icon: useAppIcon,
        show_album_art: showAlbumArt,
        show_state: showState,
        icon: isApp ? "application" : (customSelectedIconPath ? "apps" : (document.getElementById("pe-icon").value.trim() || "toggle-switch")),
        app_icon_path: isApp ? (document.getElementById("pe-path").value.trim() || null) : (customSelectedIconPath || null),
        color: (document.getElementById("pe-color") ? document.getElementById("pe-color").value.trim() : ""),
      };
      if (entId) {
        slot.entity = entId;
      }
      if (entObj) {
        if (entObj.plugin) slot.plugin = entObj.plugin;
        if (entObj.button_id) slot.button_id = entObj.button_id;
        if (entObj.state_key) slot.state_key = entObj.state_key;
        if (entObj.labels) slot.labels = entObj.labels;
        if (entObj.color) slot.colors = { on: entObj.color };
      }
      if (t === "SHORTCUT") {
        slot.shortcut_path = document.getElementById("pe-path").value.trim();
        const sArgs = document.getElementById("pe-args") ? document.getElementById("pe-args").value.trim() : "";
        if (sArgs) slot.shortcut_args = sArgs;
        slot.app_icon_path = slot.shortcut_path || null;
      }
      if (t === "GROUP") {
        const grpProfEl = document.getElementById("pe-group-profile");
        slot.target_profile = (grpProfEl && grpProfEl.value) ? grpProfEl.value : "";
        slot.profile_id = slot.target_profile;
      }
      if (t === "TOGGLE" || t === "HOTKEY") {
        const val = document.getElementById("pe-keys").value.trim();
        slot.hotkey = val;
        const numList = val.split(",").map((x) => parseInt(x.trim(), 10)).filter((n) => !isNaN(n));
        slot.keys = numList.length ? numList : [val];
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

    if (wizardStep === 2) initEyedropper();

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

    const plugins = Object.keys(pluginsConfig);
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
        <div class="dash-plugin">
          <div class="dash-plugin-icon">
            <span class="material-icons-outlined">${pluginIcons[p]}</span>
          </div>
          <div class="dash-plugin-info">
            <span class="dash-plugin-name">${pluginNames[p]}</span>
            <span class="dash-plugin-status" style="color:${color}">${esc(statusLabel)}</span>
          </div>
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
          ${pluginCards}
        </div>
      </section>`;
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
    // Only allow window drag if the mousedown starts directly inside the header title bar
    const inHeader = e.target.closest("header");
    if (!inHeader) return;
    const noDrag = e.target.closest("button, a, input, select, textarea, label, .done-btn, .hamburger, .refresh-btn");
    if (noDrag) return;
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

  // Only active on real phone panels (IS_MOBILE && panelViewMode)
  const SS_TIMEOUT_MS  = 5 * 60 * 1000;   // 5 min idle → dim
  const SS_ANIM_MS     = 40 * 1000;        // 40 s between animation cycles while dimmed
  const SS_ANIM_DUR_MS = 4 * 1000;        // each animation sequence lasts ~4 s

  let ssIdleTimer    = null;   // fires → showScreensaver()
  let ssAnimTimer    = null;   // fires → playScreensaverAnim() while dimmed
  let ssActive       = false;

  function ssEl() { return document.getElementById("iris-screensaver"); }

  function resetScreensaverTimer() {
    if (!IS_MOBILE || IS_APP) return;
    if (ssActive) {
      // Any real interaction wakes the screensaver
      hideScreensaver();
      return;
    }
    if (ssIdleTimer) clearTimeout(ssIdleTimer);
    if (panelViewMode) {
      ssIdleTimer = setTimeout(showScreensaver, SS_TIMEOUT_MS);
    }
  }

  function showScreensaver() {
    if (!IS_MOBILE || IS_APP || !panelViewMode) return;
    ssActive = true;
    const el = ssEl();
    if (!el) return;
    el.setAttribute("aria-hidden", "false");
    el.classList.add("ss-visible");
    // Prevent accidental passthrough to underlying panel
    document.body.style.overflow = "hidden";
    // Start periodic animation cycle
    scheduleScreensaverAnim();
  }

  function hideScreensaver() {
    ssActive = false;
    if (ssIdleTimer) { clearTimeout(ssIdleTimer); ssIdleTimer = null; }
    if (ssAnimTimer) { clearTimeout(ssAnimTimer); ssAnimTimer = null; }
    const el = ssEl();
    if (!el) return;
    el.classList.remove("ss-visible", "ss-scanning");
    const wrap = el.querySelector(".ss-fp-wrap");
    if (wrap) wrap.classList.remove("ss-fade-out");
    el.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    // Re-arm idle timer for next cycle
    if (panelViewMode) {
      ssIdleTimer = setTimeout(showScreensaver, SS_TIMEOUT_MS);
    }
  }

  function scheduleScreensaverAnim() {
    // Play immediately on first show, then every SS_ANIM_MS
    if (ssAnimTimer) clearTimeout(ssAnimTimer);
    ssAnimTimer = setTimeout(playScreensaverAnim, 800); // short delay so dim fade finishes first
  }

  function playScreensaverAnim() {
    if (!ssActive) return;
    const el = ssEl();
    if (!el) return;

    // Reset animation state cleanly by removing and re-adding ss-scanning
    el.classList.remove("ss-scanning");
    const wrap = el.querySelector(".ss-fp-wrap");
    if (wrap) wrap.classList.remove("ss-fade-out");

    // Force reflow so animations restart
    void el.offsetWidth;

    el.classList.add("ss-scanning");

    // After animation finishes, fade the fingerprint back out
    if (ssAnimTimer) clearTimeout(ssAnimTimer);
    ssAnimTimer = setTimeout(() => {
      if (!ssActive) return;
      if (wrap) wrap.classList.add("ss-fade-out");
      // Schedule next cycle after the fingerprint fades
      ssAnimTimer = setTimeout(() => {
        if (!ssActive) return;
        el.classList.remove("ss-scanning");
        if (wrap) wrap.classList.remove("ss-fade-out");
        // Pause before next cycle
        ssAnimTimer = setTimeout(playScreensaverAnim, SS_ANIM_MS);
      }, 700);
    }, SS_ANIM_DUR_MS);
  }

  // Wake the screensaver on incoming notifications or status events
  function screensaverWakeOnEvent() {
    if (!ssActive) return;
    hideScreensaver();
  }

  // Called inline from openPanelView()
  function ssArmForPanelView() {
    if (!IS_MOBILE || IS_APP) return;
    if (ssIdleTimer) clearTimeout(ssIdleTimer);
    ssIdleTimer = setTimeout(showScreensaver, SS_TIMEOUT_MS);
  }

  // Called inline from exitPanelView()
  function ssDisarmForPanelView() {
    hideScreensaver();
    if (ssIdleTimer) { clearTimeout(ssIdleTimer); ssIdleTimer = null; }
    if (ssAnimTimer) { clearTimeout(ssAnimTimer); ssAnimTimer = null; }
  }

  // Touch/interaction resets idle timer or wakes screensaver
  (function () {
    function onActivity(e) {
      // If screensaver is active, consume the first touch to wake (don't pass through)
      if (ssActive) {
        e.preventDefault();
        e.stopPropagation();
        hideScreensaver();
        return;
      }
      resetScreensaverTimer();
    }
    document.addEventListener("touchstart", onActivity, { passive: false, capture: true });
    document.addEventListener("touchmove",  onActivity, { passive: false, capture: true });
    document.addEventListener("click",      onActivity, { capture: true });
  })();

  // ── Init ────────────────────────────────────────────────────

  window.addEventListener("resize", () => updateViewportMode());
  window.addEventListener("orientationchange", () => setTimeout(updateViewportMode, 100));
  updateViewportMode();
  startPolling();
})();
