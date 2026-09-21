(function () {
  "use strict";
  // Restricted LAN/mobile deck client. Serves ONLY the live panel + screensaver.
  // No desktop administration surface (settings, library, automations, plugin
  // config, dialogs) is present here — those remain loopback-only in script.js.
  const API_BASE = window.location.origin;
  const IS_APP = false;
  const IS_MOBILE = true;
  const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent || "");
  const isAndroid = /Android/i.test(navigator.userAgent || "");

  let panelDraft = null, panelLive = null, panelViewMode = true, panelNav = [], panelProfileSel = "__default__";
  let panelViewSig = "", panelEntities = [], panelSliderTimer = null, _panelButtonRows = 4, _panelSliderRows = 2;
  let _panelLiveConfigVersion = null, _panelLiveCachedConfig = null, _fetchPanelLiveBusy = false, _lastSeenScreenshotSeq = null;
  let _lastBtnStatesSig = "", _lastForegroundApp = null, panelDraftReady = false;
  let activeBoxPage = 1, pendingPanelPage = null;
  let _isBrowsingFile = false;
  let _lastAutoFitH = 0;
  let coreAction; // assigned below, once, to the LAN-safe implementation

  // Admin-only builder/dashboard state the original renderer reads defensively
  // (e.g. `if (panelEdit) {...}`). The deck never enters edit/design mode or
  // shows the command centre, so these stay permanently inert.
  let panelEdit = null;
  let currentPage = "panel";
  let featureConfig = {};

  function sessionTokenQuery() {
    let tok = "";
    try { tok = localStorage.getItem("iris_session") || ""; } catch (_) {}
    return tok ? "&session=" + encodeURIComponent(tok) : "";
  }

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  function apiFetch(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign({}, opts.headers || {});
    let tok = "";
    try { tok = localStorage.getItem("iris_session") || ""; } catch (_) {}
    if (tok) opts.headers["X-Iris-Session"] = tok;
    return fetch(url, opts).then(function (r) {
      if (r.status === 401) { location.href = "/login"; throw new Error("unauthorized"); }
      return r;
    });
  }

  function getMediaPlayerAppName(path) {
    const p = String(path || "").split(/[\/\\]/).pop();
    return p ? p.replace(/\.exe$/i, "") : "Media Player";
  }
  function getMediaPlayerBrandIcon() { return null; }
  function applyKeepAlive() {}
  function isDesktopEnvironment() { return false; }
  function triggerImmersiveMode() {}
  function panelActionPayload(slot) { return { action_id: slot && slot.action_id ? slot.action_id : "" }; }

  // Desktop-only / server-blocked affordances the original renderer references.
  // The deck is untrusted-by-design (see app/server/auth.py resolve_mobile_action
  // and the LAN API allowlist in app/ws_bridge.py), so these are intentionally
  // inert no-ops rather than restored functionality: opening arbitrary URLs or
  // Explorer folders on the host, screenshot capture/viewing (SCREENSHOT is not
  // in the LAN-safe slot type set), the desktop command-centre dashboard, the
  // in-panel notes/library viewers, and pywebview-only window-fit/pin/hide
  // bridge calls.
  function openUrlOnPc(e) { if (e) { try { e.preventDefault(); } catch (_) {} try { e.stopPropagation(); } catch (_) {} } }
  function doScreenshotRequest() {}
  function openScreenshotViewer() {}
  function updateCommandCentreTelemetry() {}
  function openNotepad() {}
  function openLibraryViewer() { return Promise.resolve(); }
  function autoFitCompanionWindow() {}
  window.pywebview = window.pywebview || undefined;

  function requestWakeLock() {}
  function enableMediaWakeLock() {}
  function disableMediaWakeLock() {}
  function releaseWakeLock() {}

  function exitPanelView() {}
  function renderPanel() {}

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

const MDI_CACHE_VERSION = "v5";

const _MDI_BUILTIN = {
    "account": "\u{F0004}", "airplane": "\u{F001D}", "airplane-landing": "\u{F05D4}", "airplane-takeoff": "\u{F05D5}",
    "alarm": "\u{F0020}", "alarm-light": "\u{F078F}", "alarm-ring": "\u{F078A}", "application": "\u{F08C6}",
    "apps": "\u{F003B}", "arrow-left": "\u{F004D}", "battery-charging": "\u{F0084}", "bell": "\u{F009A}",
    "bell-off": "\u{F009B}", "bell-ring": "\u{F009E}", "bluetooth": "\u{F00AF}", "border-none-variant": "\u{F08A4}",
    "brightness-5": "\u{F00DE}", "brightness-6": "\u{F00DF}", "brightness-7": "\u{F00E0}", "calculator": "\u{F00EC}",
    "camera": "\u{F0100}", "car": "\u{F010B}", "cellphone": "\u{F011C}", "check": "\u{F012C}", "clock": "\u{F0954}",
    "close": "\u{F0156}", "cog": "\u{F0493}", "cog-outline": "\u{F08BB}", "coffee": "\u{F0176}", "compass": "\u{F018B}",
    "controller-classic": "\u{F0B82}", "cpu-64-bit": "\u{F0EE0}", "crosshairs": "\u{F01A3}", "desktop-mac": "\u{F01C4}",
    "desktop-tower-monitor": "\u{F0AAB}", "door": "\u{F081A}", "eject": "\u{F01EA}", "expansion-card": "\u{F08AE}",
    "fan": "\u{F0210}", "file": "\u{F0214}", "flash": "\u{F0241}", "folder": "\u{F024B}", "folder-open": "\u{F0770}",
    "gamepad": "\u{F0296}", "gamepad-variant": "\u{F0297}", "harddisk": "\u{F02CA}", "headphones": "\u{F02CB}",
    "headset": "\u{F02CE}", "heart": "\u{F02D1}", "help-circle": "\u{F02D7}", "home": "\u{F02DC}", "keyboard": "\u{F030C}",
    "lamp": "\u{F06B5}", "layers": "\u{F0328}", "led-strip": "\u{F07D6}", "lightbulb": "\u{F0335}",
    "lightning-bolt": "\u{F140B}", "lock": "\u{F033E}", "memory": "\u{F035B}", "microphone": "\u{F036C}",
    "microphone-off": "\u{F036D}", "microsoft-xbox": "\u{F05B9}", "microsoft-xbox-controller": "\u{F05BA}",
    "monitor": "\u{F0379}", "mouse": "\u{F037D}", "movie": "\u{F0381}", "music": "\u{F075A}", "palette": "\u{F03D8}",
    "pause": "\u{F03E4}", "play": "\u{F040A}", "play-pause": "\u{F040E}", "plus": "\u{F0415}", "power": "\u{F0425}",
    "radar": "\u{F0437}", "radiator": "\u{F0438}", "rocket-launch": "\u{F14DE}", "shield": "\u{F0498}",
    "shield-airplane": "\u{F06BB}", "skip-next": "\u{F04AD}", "skip-previous": "\u{F04AE}",
    "sony-playstation": "\u{F0414}", "speaker": "\u{F04C3}", "speedometer": "\u{F04C5}", "spotify": "\u{F04C7}",
    "star": "\u{F04CE}", "stop": "\u{F04DB}", "sword": "\u{F04E5}", "sync": "\u{F04E6}", "target": "\u{F04FE}",
    "timer": "\u{F13AB}", "tune": "\u{F062E}", "volume-high": "\u{F057E}", "volume-medium": "\u{F0580}",
    "volume-off": "\u{F0581}", "wifi": "\u{F05A9}"
  };

let mdiCache = Object.assign({}, _MDI_BUILTIN);

let mdiFetched = {};

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

function resolveProgressFillColor(slotColor, activeColor) {
    if (slotColor && typeof slotColor === "string" && slotColor.startsWith("#")) {
      let h = slotColor.slice(1);
      if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
      if (h.length === 6) {
        const r = parseInt(h.slice(0, 2), 16) || 0;
        const g = parseInt(h.slice(2, 4), 16) || 0;
        const b = parseInt(h.slice(4, 6), 16) || 0;
        const yiq = (r * 299 + g * 587 + b * 114) / 1000;
        if (yiq >= 30) return slotColor; // Valid non-black custom color
      }
    }
    if (activeColor && typeof activeColor === "string" && activeColor.startsWith("#") && activeColor !== "#555555") {
      return activeColor;
    }
    return "var(--theme-color-1, #48B2E9)";
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

function preloadBoardIcons(items) {
    if (!items || !items.length) return;
    const names = [];
    function walk(list) {
      (list || []).forEach((s) => {
        if (!s) return;
        if (s.icon && !s.icon.includes(".") && !s.icon.includes("/") && !s.icon.includes("\\")) names.push(s.icon);
        if (s.icon_off && !s.icon_off.includes(".") && !s.icon_off.includes("/") && !s.icon_off.includes("\\")) names.push(s.icon_off);
        if (s.audio_primary_icon && !s.audio_primary_icon.includes(".")) names.push(s.audio_primary_icon);
        if (s.audio_alt_icon && !s.audio_alt_icon.includes(".")) names.push(s.audio_alt_icon);
        if (s.children && s.children.length) walk(s.children);
      });
    }
    walk(items);
    if (names.length) mdiPreload(names);
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
        try { localStorage.setItem("iris_mdi_cache", JSON.stringify(mdiCache)); } catch (_) {}
        applyMdiIcons(document);
      })
      .catch(() => {
        missing.forEach((n) => { delete mdiFetched[n]; });
      });
  }

function defaultCoreSlots() {
    return [
      { name: "PC Stats", type: "CORE", core_action: "display", icon: "monitor", color: "" },
      { name: "Overlay", type: "CORE", core_action: "overlay", icon: "speedometer", color: "" },
      { name: "Mute Mic", type: "CORE", core_action: "mic", icon: "microphone", color: "" },
      { name: "Settings", type: "CORE", core_action: "settings", icon: "cog", color: "" },
    ];
  }

const CORE_ACTION_DEFS = {
    display: { name: "PC Stats", icon: "monitor", label: "PC Stats Display (Matrix / Companion Screen)" },
    overlay: { name: "Overlay", icon: "speedometer", label: "Desktop Overlay (In-game HUD)" },
    mic: { name: "Mute Mic", icon: "microphone", label: "Microphone Mute (Toggle Recording Mic)" },
    settings: { name: "Settings", icon: "cog", label: "Settings Portal (Configuration & Hub)" },
    toolbar: { name: "Toolbar", icon: "dock-top", label: "Quick Toolbar (Desktop Capture & Actions Bar)" },
    lighting: { name: "Lighting Sync", icon: "lightbulb", label: "Lighting Sync (OpenRGB Ambient & Game FX)" },
    colour_picker: { name: "Colour Picker", icon: "eyedropper", label: "Colour Picker (Screen Eyedropper Magnifier)" },
    screenshot: { name: "Screenshot", icon: "camera", label: "Screenshot (Fullscreen Capture)" },
    screenshot_zone: { name: "Snipping Tool", icon: "crop", label: "Snipping Tool (Drag Rectangular Zone)" },
    note: { name: "Iris Note", icon: "note-text", label: "Iris Note" },
    borderless_toggle: { name: "Borderless", icon: "window-maximize", label: "Toggle Borderless (Switch Game Window Mode)" },
    stopwatch: { name: "Stopwatch", icon: "timer-outline", label: "Stopwatch (Desktop Timer)" },
    countdown: { name: "Countdown Timer", icon: "timer-sand", label: "Countdown Timer (Alarm)" },
  };

function isComponentEnabled(component, target) {
    if (!component) return true;
    if (target === "desktop" || target === "local") {
      return component.local !== undefined ? component.local !== false : component.enabled !== false;
    }
    return component.remote !== undefined ? component.remote !== false : component.enabled !== false;
  }

window.mdiChar = mdiChar;

function panelProfileCurrent() {
    const cfg = panelViewConfig();
    const list = (panelDraft && panelDraft.panel_profiles) || (cfg && cfg.panel_profiles) || [];
    let profile = null;
    if (panelProfileSel !== "__default__") {
      profile = list.find((x) => x.id === panelProfileSel) || null;
      if (!profile) panelProfileSel = "__default__";
    }
    let board = (panelDraft && panelDraft.panel_board) || (cfg && cfg.panel_board) || [];
    if (!profile && panelDraft && !Array.isArray(panelDraft.panel_board)) {
      panelDraft.panel_board = Array.isArray(board) ? board : [];
      board = panelDraft.panel_board;
    }
    if (profile) {
      if (!Array.isArray(profile.board)) profile.board = [];
      board = profile.board;
    }
    return { board: board, profile: profile };
  }

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
    panelProfileSel = "__default__";
    panelViewSig = "";
    updateViewportMode();
    ensurePanelOverlay();
    renderPanelView();
    fetchPanelLive();
    ssArmForPanelView();
  }

function panelViewConfig() {
    const merged = {};
    const sources = [
      panelDraft,
      (typeof _panelLiveCachedConfig !== "undefined") ? _panelLiveCachedConfig : null,
      panelLive && panelLive.config,
    ];
    sources.forEach((source) => {
      if (!source || typeof source !== "object") return;
      Object.keys(source).forEach((key) => {
        if (Object.prototype.hasOwnProperty.call(source, key)) {
          merged[key] = source[key];
        }
      });
    });
    return merged;
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
    const coreSig = (cfg.panel_core || defaultCoreSlots()).map(slotSig).join(";");
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
      coreSig,
      lay,
      sl,
      cfg.media_player_path || "",
      (cfg.panel_gauges || {}).enabled === false ? 0 : 1,
      !!(panelLive && panelLive.hardware_connected),
      JSON.stringify((panelLive && panelLive.warnings) || {}),
    ]);
  }

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

        // Check if a new screenshot was captured while websocket was disconnected
        if (typeof data.screenshot_seq === "number") {
          if (_lastSeenScreenshotSeq === null) {
            _lastSeenScreenshotSeq = data.screenshot_seq;
          } else if (data.screenshot_seq > _lastSeenScreenshotSeq) {
            _lastSeenScreenshotSeq = data.screenshot_seq;
            if (!document.getElementById("iris-screenshot-viewer")) {
              apiFetch(`${API_BASE}/api/screenshot/latest`)
                .then((r) => r.json())
                .then((sData) => {
                  if (sData && sData.available && sData.img) {
                    screensaverWakeOnEvent();
                    openScreenshotViewer(sData);
                  }
                })
                .catch(() => {});
            }
          }
        }

        // Live in-place DOM updates for all views (Desktop preview & Phone overlay)
        updatePanelView();
        if (currentPage === "command" || currentPage === "dashboard") {
          if (typeof updateCommandCentreTelemetry === "function") {
            updateCommandCentreTelemetry();
          }
        }

        if (!panelViewMode) return;

        if (panelViewMode && !panelEdit && data.config) {
          panelDraft = {
            panel_board: data.config.panel_board || [],
            panel_utility: data.config.panel_utility || [],
            panel_core: data.config.panel_core || defaultCoreSlots(),
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
            panel_core: data.config.panel_core || defaultCoreSlots(),
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
        if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.get_pending_nav === "function") {
          try {
            window.pywebview.api.get_pending_nav().then(function (nav) {
              if (nav && nav.page) {
                window.irisSetPage(nav.page, nav.tab);
                if (nav.action === "new_note" || nav.action === "note") {
                  setTimeout(() => openNotepad(null, nav.app || "general"), 150);
                }
                if (nav.viewer_file) {
                  setTimeout(() => openLibraryViewer(nav.viewer_file), 150);
                }
              }
            }).catch(function () {});
          } catch (_) {}
        }
      })
      .catch(() => {})
      .finally(() => {
        _fetchPanelLiveBusy = false;
      });
  }

let boxScrollLeft = 0;

let lastNotifKey = "";

let pendingNotifSlide = false;

let notifDismissTimer = null;

let notifOpen = false;

let notifReturnPage = 1;

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
    const scrollEl = document.querySelector(".panel-view-overlay .pv-scroll");
    if (scrollEl) scrollEl.scrollTop = 0;
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
    const scrollEl = document.querySelector(".panel-view-overlay .pv-scroll");
    if (scrollEl) scrollEl.scrollTop = 0;
  }

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

function normalizeNotifTheme(theme) {
    theme = (theme || "").toLowerCase();
    if (theme === "alert" || theme === "red") return "alert";
    if (theme === "green") return "green";
    return "purple";
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
        const mdx = e.touches[0].clientX - startX;
        const mdy = e.touches[0].clientY - startY;
        if (Math.abs(mdx) > 8 || Math.abs(mdy) > 8) {
          e.preventDefault();
        }
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
    const coreOn = layout.core !== false;
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
    return { isDesktop, gOn, boxOn, slidOn, utilOn, coreOn, volOn, mvolOn, mixOn, briOn, activeSliderCount, sliderRows, utilRows, buttonRows, pageSize };
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
    const coreOn = layoutSpec.coreOn;
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
    const core = cfg.panel_core || defaultCoreSlots();
    preloadBoardIcons(board);
    preloadBoardIcons(util);
    preloadBoardIcons(core);
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
    const cpuVal = (gauges.cpu_pct !== undefined && gauges.cpu_pct !== null && (!gauges.cpu_temp || gauges.cpu_temp_unit === "%"))
      ? gauges.cpu_pct
      : (gauges.cpu_temp !== undefined && gauges.cpu_temp !== null ? gauges.cpu_temp : (gauges.cpu_pct || 0));
    const cpuUnit = (gauges.cpu_pct !== undefined && gauges.cpu_pct !== null && (!gauges.cpu_temp || gauges.cpu_temp_unit === "%"))
      ? "%"
      : (gauges.cpu_temp_unit || "°C");
    const gaugesHtml = gOn
      ? '<div class="pv-gauges">' +
        panelGauge("CPU", cpuVal, 100, cpuUnit) +
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
    if (coreOn && (isDesktop ? utilOn : true)) {
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

function gaugeNum(value, label) {
    if (label === "FPS" || label === "fps") {
      if (value === null || value === undefined || value <= 0 || value === "--" || isNaN(value)) {
        return "—";
      }
      return String(Math.round(value));
    }
    const v = (value === null || value === undefined) ? 0 : Math.round(value);
    return String(v);
  }

const GAUGE_CIRCUMFERENCE = 163.36;

function panelGauge(label, value, max, unit) {
    const isFps = (label === "FPS" || label === "fps");
    const isInvalidFps = isFps && (value === null || value === undefined || value <= 0 || value === "--" || isNaN(value));
    const v = (value === null || value === undefined || isInvalidFps) ? 0 : value;
    const m = max || 100;
    const pct = isInvalidFps ? 0 : Math.max(0, Math.min(100, (v / m) * 100));
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
        '<span class="pdev-gval"><span class="pdev-gnum" data-gvalue="' + esc(label) + '">' + (isInvalidFps ? "—" : gaugeNum(v, label)) + '</span></span>' +
      '</div>' +
      '<span class="pdev-glabel" data-glabel="' + esc(label) + '">' + esc(label) + (unit ? ' ' + esc(unit) : '') + '</span>' +
    '</div>';
  }

function boardPagesHtml(board, rows) {
    let h = "";
    const list = board || [];
    const btnRows = rows || _panelButtonRows || 4;
    const PAGE = btnRows * 4;
    const isSubPanel = (panelNav && panelNav.length > 0) ||
      !!(panelProfileCurrent().profile && panelProfileCurrent().profile.is_group);
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
    const isMediaBtn = (s.entity === "media.player" || s.entity === "media.eject" || s.type === "MEDIA_EJECT");
    const useAppIcon = (s.use_app_icon !== false && (s.use_app_icon || s.type === "SHORTCUT" || !!s.app_icon_path || isMediaBtn));
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
        active: false,
        label: isAlt ? ((s.labels && s.labels.on) || s.audio_input_device_name_alt || "ALT") : ((s.labels && s.labels.off) || s.audio_input_device_name || "PRIMARY")
      };
    } else if (s.entity === "system.mic_mute" || (s.plugin === "system" && s.button_id === "mic_mute")) {
      const isMuted = !!(bState && bState.active);
      icon = isMuted ? "microphone-off" : (s.icon || "microphone");
      if (isMuted) {
        extraTileClass += " pdev-muted";
      }
    }

    if (showAlbumArt && mediaState.has_art) {
      const artUrl = API_BASE + '/api/media/art?t=' + encodeURIComponent(mediaState.art_id || Date.now()) + tokQs;
      albumArtPlate = '<span class="pdev-album-art-bg" style="background-image:url(\'' + esc(artUrl) + '\');"></span>';
      extraTileClass += " has-album-art" + (isMediaPlaying ? " is-playing" : (isMediaPaused ? " is-paused" : ""));
    }

    const isElite = (s.plugin === "elite_dangerous");
    const isAudioOutput = (s.type === "AUDIO OUTPUT");
    const hasLiveState = (bState.active !== undefined || bState.label !== undefined || bState.value !== undefined);
    const isOn = isAudioOutput ? false : !!bState.active;
    if (isOn && !isElite) extraTileClass += " pdev-active has-halo";
    if (isElite || isAudioOutput) extraTileClass += " pdev-no-halo";

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
    let fillColor = "";
    if (isProgressActive) {
      colorPlate = ""; // Progress bar drives the color fill — suppress solid 100% full-tile mask
      glyphStyle = "";
      fillColor = resolveProgressFillColor(s.color, activeColor);
      progressFillPlate = '<span class="pdev-progress-fill" style="--fill-pct:' + fillPct.toFixed(1) + '%; --fill-color:' + esc(fillColor) + ';"></span>';
      extraTileClass += " has-progress-fill" + (fillPct >= 99.5 ? " has-fill-100" : "");
    }

    const isTileLight = (isProgressActive && isLightColor(fillColor) && fillPct >= 45) || (!isProgressActive && color && isLightColor(color));
    if (isTileLight) {
      extraTileClass += " pdev-tile-light";
    }

    if (isOn && !colorPlate && !albumArtPlate && !isElite) {
      extraTileStyle = ' style="border-color:' + esc(activeColor) + '; box-shadow:0 0 10px ' + esc(activeColor) + '44;"';
    } else if ((colorPlate || albumArtPlate) && !isElite) {
      if (isOn) {
        statusRing = '<span class="pdev-status-ring" style="--ring-color:' + esc(activeColor) + ';"></span>';
      }
    }

    const isValueMode = (bState.display_mode === "value" || s.display_mode === "value");

    if (isGroup) {
      topBar = '<span class="pdev-group-bar">GROUP</span>';
      extraTileClass += " has-group-bar";
    } else if (s.entity !== "media.play_pause" && showState && (hasLiveState || labels.on || labels.off || fillPct !== null || isValueMode)) {
      let lblText = bState.label;
      if (isValueMode) {
        lblText = bState.unit || s.unit || bState.label || "";
      } else {
        if (!lblText && bState.value !== undefined && bState.value !== null) {
          lblText = (typeof bState.value === "number") ? `${bState.value}` : String(bState.value);
        }
        if (!lblText && fillPct !== null) {
          lblText = fillPct.toFixed(0) + "%";
        }
        if (!lblText) {
          lblText = isOn ? (labels.on || "ON") : (labels.off || "OFF");
        }
      }
      if (lblText) {
        topBar = '<span class="pdev-group-bar pdev-status-bar" style="color:' + esc(badgeColor) + ';">' + esc(lblText) + '</span>';
        extraTileClass += " has-group-bar has-status-bar";
      }
    }

    const warnMap = (panelLive && panelLive.warnings) || {};
    const warnKeyCol = entKey ? entKey.replace(".", ":") : "";
    const warnKeyDot = entKey ? entKey.replace(":", ".") : "";
    const warnKeyPlg = (s.plugin || "") + ":" + (s.button_id || "");
    const warnKeyPlgDot = (s.plugin || "") + "." + (s.button_id || "");
    const warn = warnMap[entKey] || (warnKeyCol && warnMap[warnKeyCol]) || (warnKeyDot && warnMap[warnKeyDot]) || (warnKeyPlg !== ":" && warnMap[warnKeyPlg]) || (warnKeyPlgDot !== "." && warnMap[warnKeyPlgDot]);
    if (warn && warn.color) {
      extraTileClass += " pdev-warning";
      const warnText = isLightColor(warn.color) ? "#0a0a0a" : "#ffffff";
      extraTileStyle = ' style="--warn-color:' + esc(warn.color) + '; color:' + warnText + ';"';
      glyphStyle = ' style="color:' + warnText + ';"';
      warnFlashOverlay = '<span class="pdev-warn-flash"></span>';
      colorPlate = ""; // Suppress base button plate while warning is active so flash takes full priority
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
    if (isValueMode) {
      const numVal = (bState.value !== undefined && bState.value !== null) ? bState.value : (s.value !== undefined && s.value !== null ? s.value : "--");
      glyph = '<span class="pdev-num-glyph"' + glyphStyle + '>' + esc(String(numVal)) + '</span>';
    } else if (showIcon) {
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

    const isEditingSlot = !!(panelEdit && (panelEdit.scope === listName || (panelEdit.scope === "utility" && listName === "util")) && panelEdit.index === idx);
    if (isEditingSlot) extraTileClass += " is-editing-slot";

    return '<button type="button" class="pdev-tile' + (isGroup ? " pdev-group" : "") + (listName === "core" ? " pdev-core-tile" : "") + extraTileClass + '"' +
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

function coreTilesHtml(data, isPreview) {
    const cfg = panelViewConfig();
    const prof = panelProfileCurrent();
    const coreList = (cfg && cfg.panel_core) || (prof && prof.core) ||
      (panelDraft && panelDraft.panel_core) || defaultCoreSlots();
    preloadBoardIcons(coreList);

    const dispOn = !!(data && data.pc_stats_manual);
    const ovOn = !!(data && data.overlay_on);
    const isMicMuted = !!(data && data.entity_states && data.entity_states["system.mic_mute"] && data.entity_states["system.mic_mute"].active);

    let h = "";
    for (let i = 0; i < 4; i++) {
      const s = coreList[i] || defaultCoreSlots()[i] || { type: "EMPTY" };
      if (s.type === "EMPTY") {
        h += '<button type="button" class="pdev-tile pdev-empty-tile pdev-core-tile" data-action="slot" data-list="core" data-idx="' + i + '"></button>';
        continue;
      }
      if (s.type === "CORE" || !s.type) {
        const act = s.core_action || (i === 0 ? "display" : i === 1 ? "overlay" : i === 2 ? "mic" : "settings");
        const def = CORE_ACTION_DEFS[act] || { name: act, icon: "star-circle" };
        let activeCls = "";
        let ic = s.icon;
        if (act === "display") {
          if (dispOn) activeCls = " pdev-active";
          if (!ic) ic = def.icon;
        } else if (act === "overlay") {
          if (ovOn) activeCls = " pdev-active";
          if (!ic) ic = def.icon;
        } else if (act === "mic" || act === "mic_mute") {
          if (isMicMuted) activeCls = " pdev-active pdev-muted";
          ic = isMicMuted ? "microphone-off" : (s.icon || "microphone");
        } else if (act === "toolbar") {
          const isTb = !!(data && data.entity_states && data.entity_states["system.toolbar"] && data.entity_states["system.toolbar"].active);
          if (isTb) activeCls = " pdev-active";
          if (!ic) ic = def.icon;
        } else if (act === "lighting" || act === "lighting_sync") {
          const isLt = !!(data && data.entity_states && data.entity_states["system.lighting_sync"] && data.entity_states["system.lighting_sync"].active);
          if (isLt) activeCls = " pdev-active";
          if (!ic) ic = def.icon;
        } else {
          if (!ic) ic = def.icon;
        }

        let tileStyle = "";
        let glyphStyle = "";
        let colorPlate = "";
        if (s.color) {
          if (s.color.startsWith("#")) {
            colorPlate = '<span class="pdev-color-plate" style="background:' + esc(s.color) + ';"></span>';
            glyphStyle = ' style="color:' + (isLightColor(s.color) ? '#0a0a0a' : '#ffffff') + ';"';
          } else if (s.color === "RAINBOW") {
            colorPlate = '<span class="pdev-color-plate" style="background:linear-gradient(135deg, #ff0000, #ff7f00, #ffff00, #00ff00, #0000ff, #8b00ff);"></span>';
            glyphStyle = ' style="color:#0a0a0a;"';
          }
        }

        const title = s.name || (act === "display" ? "PC stats display" : act === "overlay" ? "Stats overlay" : act === "mic" ? "Microphone mute" : act === "settings" ? "Settings" : act);

        h += '<button type="button" class="pdev-tile pdev-core-tile' + activeCls + '"' +
          tileStyle +
          ' data-core="' + esc(act) + '" data-action="slot" data-list="core" data-idx="' + i + '"' +
          ' title="' + esc(title) + '">' +
          colorPlate +
          '<span class="md" data-md="' + esc(ic) + '"' + glyphStyle + '>' + esc(mdiChar(ic)) + '</span>' +
          '</button>';
      } else {
        h += panelTileHtml(s, "core", i);
      }
    }
    return h;
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
        body: JSON.stringify(panelActionPayload(slot)),
      }).catch(() => {});
      return;
    }
    if (slot.type === "CORE") {
      coreAction(slot.core_action || "settings", null, slot);
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
        body: JSON.stringify(panelActionPayload(slot)),
      }).then(() => {
        setTimeout(fetchPanelLive, 50);
        setTimeout(fetchPanelLive, 250);
      }).catch(() => {});
      return;
    }
    apiFetch(`${API_BASE}/api/panel/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(panelActionPayload(slot)),
    }).catch(() => {});
  }

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
          } else {
            panelProfileSel = "__default__";
            activeBoxPage = 1;
          }
          panelViewSig = panelViewSignature();
          if (panelViewMode) renderPanelView(); else renderPanel();
        });
        return;
      }
      const core = tile.getAttribute("data-core");
      if (core) {
        tile.addEventListener("click", () => {
          const list = tile.getAttribute("data-list");
          const idx = parseInt(tile.getAttribute("data-idx"), 10);
          let s = null;
          if (list === "util") {
            s = (panelViewConfig().panel_utility || [])[idx];
          } else if (list === "core") {
            s = (panelViewConfig().panel_core || defaultCoreSlots())[idx];
          } else if (Number.isFinite(idx)) {
            s = currentBoard()[idx];
          }
          coreAction(core, tile, s);
        });
        return;
      }
      if (tile.getAttribute("data-action") === "slot") {
        tile.addEventListener("click", () => {
          const list = tile.getAttribute("data-list");
          const idx = parseInt(tile.getAttribute("data-idx"), 10);
          let s = null;
          if (list === "util") {
            s = (panelViewConfig().panel_utility || [])[idx];
          } else if (list === "core") {
            s = (panelViewConfig().panel_core || defaultCoreSlots())[idx];
          } else {
            s = currentBoard()[idx];
          }
          if (s && s.type === "CORE" && s.core_action) {
            coreAction(s.core_action, tile, s);
          } else {
            runSlotAction(s);
          }
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

    const cpuLiveVal = (gauges.cpu_pct !== undefined && gauges.cpu_pct !== null && (!gauges.cpu_temp || gauges.cpu_temp_unit === "%"))
      ? gauges.cpu_pct
      : (gauges.cpu_temp !== undefined && gauges.cpu_temp !== null ? gauges.cpu_temp : (gauges.cpu_pct || 0));
    const cpuLiveUnit = (gauges.cpu_pct !== undefined && gauges.cpu_pct !== null && (!gauges.cpu_temp || gauges.cpu_temp_unit === "%"))
      ? "%"
      : (gauges.cpu_temp_unit || "°C");

    updateGauge("CPU", cpuLiveVal, 100, cpuLiveUnit);
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

    const mic = document.querySelectorAll('.pdev-core-tile[data-core="mic"], .pdev-core-tile[data-core="mic_mute"]');
    const isMicMuted = !!(data.entity_states && data.entity_states["system.mic_mute"] && data.entity_states["system.mic_mute"].active);
    mic.forEach((m) => {
      m.classList.toggle("pdev-active", isMicMuted);
      m.classList.toggle("pdev-muted", isMicMuted);
      const mIcon = m.querySelector(".md");
      if (mIcon) {
        const ic = isMicMuted ? "microphone-off" : "microphone";
        mIcon.setAttribute("data-md", ic);
        mIcon.textContent = mdiChar(ic);
        mdiPreload([ic]);
        applyMdiIcons(m);
      }
    });

    const isTbActive = !!(data.entity_states && data.entity_states["system.toolbar"] && data.entity_states["system.toolbar"].active);
    document.querySelectorAll('.pdev-core-tile[data-core="toolbar"]').forEach((t) => t.classList.toggle("pdev-active", isTbActive));

    const isLtActive = !!(data.entity_states && data.entity_states["system.lighting_sync"] && data.entity_states["system.lighting_sync"].active);
    document.querySelectorAll('.pdev-core-tile[data-core="lighting"], .pdev-core-tile[data-core="lighting_sync"]').forEach((l) => l.classList.toggle("pdev-active", isLtActive));

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
    const warnStates = (data.warnings) || (panelLive && panelLive.warnings) || {};
    const btnStatesSig = JSON.stringify(btnStates) + '|' + JSON.stringify(warnStates) + '|' + (isMediaPlaying ? '1' : '0') + '|' + (isMediaPaused ? '1' : '0') + '|' + (mediaState.art_id || '') + '|' + (data.default_audio_output || '');
    if (btnStatesSig !== _lastBtnStatesSig) {
      _lastBtnStatesSig = btnStatesSig;
      document.querySelectorAll(".pdev-tile").forEach((tile) => {
        const idx = parseInt(tile.getAttribute("data-idx"), 10);
        const list = tile.getAttribute("data-list");
        if (isNaN(idx) || !list) return;
        const board = (list === "util") ? ((panelDraft && panelDraft.panel_utility) || []) :
                      (list === "core") ? ((panelDraft && panelDraft.panel_core) || (panelViewConfig().panel_core) || defaultCoreSlots()) :
                      currentBoard();
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

            isOn = false;
            bState = { active: false, label: audLabel };

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
          } else if (s.entity === "system.mic_mute" || (s.plugin === "system" && s.button_id === "mic_mute")) {
            const isMuted = !!bState.active;
            const micIcon = isMuted ? "microphone-off" : (s.icon || "microphone");
            tile.classList.toggle("pdev-muted", isMuted);
            const iconEl = tile.querySelector(".md");
            if (iconEl && iconEl.getAttribute("data-md") !== micIcon) {
              iconEl.setAttribute("data-md", micIcon);
              iconEl.textContent = mdiChar(micIcon);
              mdiPreload([micIcon]);
              applyMdiIcons(tile);
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
          let fillColor = "";
          if (isProgressActive) {
            if (colorPlateEl) colorPlateEl.style.display = "none";
            fillColor = resolveProgressFillColor(s.color, activeColor);
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

          const isTileLight = (isProgressActive && isLightColor(fillColor) && fillPct >= 45) || (!isProgressActive && s.color && isLightColor(s.color));
          tile.classList.toggle("pdev-tile-light", !!isTileLight);

          const isValueMode = (bState.display_mode === "value" || s.display_mode === "value");

          // Warning state overlay & status override
          const warnKeyCol = entKey ? entKey.replace(".", ":") : "";
          const warnKeyDot = entKey ? entKey.replace(":", ".") : "";
          const warnKeyPlg = (s.plugin || "") + ":" + (s.button_id || "");
          const warnKeyPlgDot = (s.plugin || "") + "." + (s.button_id || "");
          const warn = warnStates[entKey] || (warnKeyCol && warnStates[warnKeyCol]) || (warnKeyDot && warnStates[warnKeyDot]) || (warnKeyPlg !== ":" && warnStates[warnKeyPlg]) || (warnKeyPlgDot !== "." && warnStates[warnKeyPlgDot]);
          let warnFlashEl = tile.querySelector(".pdev-warn-flash");

          if (warn && warn.color) {
            tile.classList.add("pdev-warning");
            const warnText = isLightColor(warn.color) ? "#0a0a0a" : "#ffffff";
            tile.style.setProperty("--warn-color", warn.color);
            tile.style.color = warnText;
            if (colorPlateEl) colorPlateEl.style.display = "none";
            if (!warnFlashEl) {
              warnFlashEl = document.createElement("span");
              warnFlashEl.className = "pdev-warn-flash";
              tile.appendChild(warnFlashEl);
            }
          } else {
            tile.classList.remove("pdev-warning");
            tile.style.removeProperty("--warn-color");
            tile.style.color = "";
            if (colorPlateEl && !isProgressActive) colorPlateEl.style.display = "";
            if (warnFlashEl) warnFlashEl.remove();
          }

          // Update status bar
          const statusBar = tile.querySelector(".pdev-status-bar");
          if (statusBar) {
            if (warn && warn.color && warn.message) {
              const warnText = isLightColor(warn.color) ? "#0a0a0a" : "#ffffff";
              statusBar.textContent = warn.message;
              statusBar.style.color = warnText;
            } else {
              const labels = s.labels || {};
              let lblText = bState.label;
              if (isValueMode) {
                lblText = bState.unit || s.unit || bState.label || "";
              } else {
                if (!lblText && bState.value !== undefined && bState.value !== null) {
                  lblText = (typeof bState.value === "number") ? `${bState.value}` : String(bState.value);
                }
                if (!lblText && fillPct !== null) {
                  lblText = fillPct.toFixed(0) + "%";
                }
                if (!lblText) {
                  lblText = isOn ? (labels.on || "ON") : (labels.off || "OFF");
                }
              }
              if (lblText) {
                statusBar.textContent = lblText;
                statusBar.style.color = badgeColor;
              }
            }
          }

          // Update numerical glyph if in value display mode
          if (isValueMode) {
            const numGlyphEl = tile.querySelector(".pdev-num-glyph");
            const numVal = (bState.value !== undefined && bState.value !== null) ? bState.value : (s.value !== undefined && s.value !== null ? s.value : "--");
            if (numGlyphEl) {
              numGlyphEl.textContent = String(numVal);
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

let _lastGaugeVals = {};

function updateGauge(label, value, max, unit) {
    const isFps = (label === "FPS" || label === "fps");
    const isInvalidFps = isFps && (value === null || value === undefined || value <= 0 || value === "--" || isNaN(value));
    const v = (value === null || value === undefined || isInvalidFps) ? 0 : value;
    const m = max || 100;
    const key = `${label}|${value}|${m}|${unit || ''}`;
    if (_lastGaugeVals[label] === key) return;
    _lastGaugeVals[label] = key;

    const pct = isInvalidFps ? 0 : Math.max(0, Math.min(100, (v / m) * 100));
    const offset = GAUGE_CIRCUMFERENCE - (pct / 100) * GAUGE_CIRCUMFERENCE;
    const ringEls = document.querySelectorAll('.pdev-gring[data-gauge="' + label + '"]');
    ringEls.forEach((ringEl) => {
      ringEl.style.setProperty("--val", pct.toFixed(1) + "%");
      const arc = ringEl.querySelector(".pdev-garc");
      if (arc) arc.style.strokeDashoffset = offset.toFixed(2);
    });
    const numEls = document.querySelectorAll('.pdev-gnum[data-gvalue="' + label + '"]');
    numEls.forEach((numEl) => { numEl.textContent = isInvalidFps ? "—" : gaugeNum(v, label); });
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

function getScreensaverTimeoutMs() {
    let val = 2; // Default 2 minutes
    try {
      const stored = localStorage.getItem("iris_screensaver_timeout");
      if (stored !== null && stored !== undefined) {
        let n = Number(stored);
        if (!isNaN(n)) {
          if (n >= 60) n = Math.round(n / 60); // Migrate legacy seconds -> minutes
          val = Math.max(0, Math.min(20, n));
        }
      }
    } catch (e) {}

    const cfg = (typeof _panelLiveCachedConfig !== "undefined" && _panelLiveCachedConfig) || (typeof panelLive !== "undefined" && panelLive && panelLive.config);
    if (cfg && typeof cfg.screensaver_timeout !== "undefined") {
      let n = Number(cfg.screensaver_timeout);
      if (!isNaN(n)) {
        if (n >= 60) n = Math.round(n / 60); // Migrate legacy seconds -> minutes
        val = Math.max(0, Math.min(20, n));
        try { localStorage.setItem("iris_screensaver_timeout", String(val)); } catch (e) {}
      }
    }
    if (isNaN(val) || val < 0) val = 0;
    if (val === 0) return 0; // 0 = Disabled / Indefinite / Always On
    return val * 60 * 1000; // minutes to ms
  }

const SS_DRIFT_INTERVAL_MS = 60 * 1000;

const SS_CLOCK_INTERVAL_MS = 1000;

let ssIdleTimer    = null;

let ssDriftTimer   = null;

let ssClockTimer   = null;

let ssActive       = false;

function ssEl() { return document.getElementById("iris-screensaver"); }

function updateScreensaverClock() {
    const timeEl = document.getElementById("ssv-clock-time");
    if (!timeEl) return;
    const dateEl = document.getElementById("ssv-clock-date");
    const ampmEl = document.getElementById("ssv-clock-ampm");

    const now = new Date();
    let formatted = false;

    if (typeof Intl !== "undefined" && Intl.DateTimeFormat && typeof Intl.DateTimeFormat.prototype.formatToParts === "function") {
      try {
        const parts = new Intl.DateTimeFormat(navigator.language || "default", {
          hour: "numeric",
          minute: "2-digit"
        }).formatToParts(now);

        let h = "", m = "", ampm = "";
        for (let i = 0; i < parts.length; i++) {
          const p = parts[i];
          if (p.type === "hour") h = p.value;
          else if (p.type === "minute") m = p.value;
          else if (p.type === "dayPeriod") ampm = p.value;
        }
        if (h && m) {
          timeEl.textContent = h + ":" + m;
          if (ampmEl) {
            ampmEl.textContent = ampm ? ampm.toUpperCase() : "";
            ampmEl.style.display = ampm ? "inline-block" : "none";
          }
          formatted = true;
        }
      } catch (_) {}
    }

    if (!formatted) {
      const rawH = now.getHours();
      const rawM = now.getMinutes();
      const hh = rawH < 10 ? "0" + rawH : "" + rawH;
      const mm = rawM < 10 ? "0" + rawM : "" + rawM;
      timeEl.textContent = hh + ":" + mm;
      if (ampmEl) ampmEl.style.display = "none";
    }

    if (dateEl) {
      let dStr = "";
      try {
        dStr = now.toLocaleDateString(navigator.language || "default", {
          weekday: "short",
          month: "short",
          day: "numeric"
        });
      } catch (_) {
        const days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
        const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
        dStr = days[now.getDay()] + ", " + months[now.getMonth()] + " " + now.getDate();
      }
      dateEl.textContent = (dStr || "").toUpperCase();
    }
  }

function driftScreensaverLock() {
    const el = ssEl();
    if (!el || !ssActive) return;
    const lockEl = el.querySelector(".ssv-clean-lock");
    if (!lockEl) return;

    // Pixel shift within ±24px horizontal and ±36px vertical to protect OLED/LCD subpixels
    const offsetX = (Math.random() * 48 - 24).toFixed(1);
    const offsetY = (Math.random() * 72 - 36).toFixed(1);
    lockEl.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
    lockEl.style.opacity = "0.75"; // Gentle dimmed ambient standby
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

    // Immediate initial display and drift on lock
    updateScreensaverClock();
    driftScreensaverLock();

    if (ssClockTimer) clearInterval(ssClockTimer);
    ssClockTimer = setInterval(updateScreensaverClock, SS_CLOCK_INTERVAL_MS);

    if (ssDriftTimer) clearInterval(ssDriftTimer);
    ssDriftTimer = setInterval(driftScreensaverLock, SS_DRIFT_INTERVAL_MS);
  }

function hideScreensaver() {
    ssActive = false;
    requestWakeLock();
    if (ssIdleTimer) { clearTimeout(ssIdleTimer); ssIdleTimer = null; }
    if (ssClockTimer) { clearInterval(ssClockTimer); ssClockTimer = null; }
    if (ssDriftTimer) { clearInterval(ssDriftTimer); ssDriftTimer = null; }
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

function screensaverWakeOnEvent() {
    hideScreensaver();
    resetScreensaverTimer();
    try { requestWakeLock(); } catch (_) {}
  }

function ssArmForPanelView() {
    if (IS_APP || !panelViewMode) return;
    requestWakeLock();
    if (ssIdleTimer) clearTimeout(ssIdleTimer);
    const timeoutMs = getScreensaverTimeoutMs();
    if (timeoutMs > 0) {
      ssIdleTimer = setTimeout(showScreensaver, timeoutMs);
    }
  }

function ssDisarmForPanelView() {
    hideScreensaver();
    if (ssIdleTimer) { clearTimeout(ssIdleTimer); ssIdleTimer = null; }
    if (ssClockTimer) { clearInterval(ssClockTimer); ssClockTimer = null; }
    if (ssDriftTimer) { clearInterval(ssDriftTimer); ssDriftTimer = null; }
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

// ── LAN-safe core action dispatch ────────────────────────────
  // The extracted panel code (runSlotAction) calls `coreAction(core, tile, slot)`.
  // Overriding it here (rather than including the original desktop
  // implementation) ensures LAN core tiles only ever submit an opaque,
  // server-resolved action_id (see resolve_mobile_action() in
  // app/server/auth.py) — never a raw core/tile name.
  coreAction = function (core, tile, slot) {
    if (!slot || !slot.action_id) return;
    apiFetch(API_BASE + "/api/panel/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: slot.action_id }),
    }).then(function () { fetchPanelLive(); }).catch(function () {});
  };

  // ── WebSocket telemetry (read-only refresh trigger; no C2 channel) ──
  function connectWs() {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(scheme + "//" + location.host);
    ws.onopen = function () {
      let s = "";
      try { s = localStorage.getItem("iris_session") || ""; } catch (_) {}
      ws.send(JSON.stringify({ session: s }));
    };
    ws.onmessage = function (e) {
      try {
        const m = JSON.parse(e.data);
        if (["sysinfo", "sensor", "media", "panel_update", "theme", "notification"].indexOf(m.type) >= 0) fetchPanelLive();
      } catch (_) {}
    };
    ws.onclose = function () { setTimeout(connectWs, 2500); };
  }

  function loadPanel() {
    return apiFetch(API_BASE + "/api/panel")
      .then(function (r) { return r.json(); })
      .then(function (cfg) {
        panelDraft = cfg;
        panelDraftReady = true;
        return fetchPanelLive();
      });
  }

  window.addEventListener("resize", () => { updateViewportMode(); });
  window.addEventListener("orientationchange", () => {
    updateViewportMode();
    setTimeout(updateViewportMode, 100);
    setTimeout(updateViewportMode, 300);
  });

  ensurePanelOverlay();
  updateViewportMode();
  loadPanel().catch(function () {});
  setInterval(function () { fetchPanelLive(); }, 1000);
  resetScreensaverTimer();
  connectWs();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js?v=34").catch(function () {});
})();
