/* Iris v3 — HTML UI script */

(function () {
  "use strict";

  // ── Platform detection ──────────────────────────────────────

  const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (isIOS) {
    document.documentElement.setAttribute("data-theme", "ios");
  }

  const API_BASE = window.location.protocol === "file:" ? "http://localhost:15502" : window.location.origin;
  const POLL_MS = 1000;

  // True inside the desktop app's panel window (pywebview). Only that window
  // may see the Network page / access token / QR code.
  const IS_APP = !!(window.pywebview && window.pywebview.api);

  // The portal's "straight to panel" landing is for phones only. The desktop
  // (browser or the desktop app window) still opens the dashboard.
  const IS_MOBILE = (window.matchMedia && window.matchMedia("(max-width: 768px)").matches) || isIOS;

  // Auth is carried by the loopback session or the login session cookie; the
  // access token is never embedded in the page any more.
  const IRIS_TOKEN = "";

  function apiFetch(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign({}, opts.headers || {});
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
        currentPage = page;
        selectedPlugin = null;
        if (page === "panel") {
          // Re-entering Panel from the sidebar shows the editor again.
          panelViewMode = false;
          panelNav = [];
          if (panelLiveTimer) { clearInterval(panelLiveTimer); panelLiveTimer = null; }
        } else {
          exitPanelView();
        }
        renderPage();
        if (page === "features" || page === "alarms" || page === "settings") fetchConfig();
        else if (page === "plugins") fetchPluginsConfig();
        else if (page === "vision") fetchVision();
        else if (page === "panel") fetchPanel();
        else { visionInWizard = false; stopTestPoll(); }
      }
      closeNav();
    });
  });

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

  // ── Data fetching ───────────────────────────────────────────

  async function fetchState() {
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
    pollTimer = setTimeout(fetchState, POLL_MS);
  }

  function startPolling() {
    settingsRenderer = new SettingsRenderer(API_BASE);
    settingsRenderer.loadPages().then(function () {
      if (IS_APP || !IS_MOBILE) {
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
    });
    fetchState();
    fetchPluginsConfig();
    fetchDeviceStatus();
  }

  // ── Page rendering ──────────────────────────────────────────

  function renderPage() {
    if (currentPage === "dashboard") {
      renderDashboard();
    } else if (currentPage === "alarms") {
      alarms = featureConfig.alarms || [];
      renderAlarms();
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

  async function fetchConfig() {
    try {
      const res = await apiFetch(`${API_BASE}/api/config`);
      if (res.ok) {
        featureConfig = await res.json();
        if (currentPage === "features" || currentPage === "alarms" || currentPage === "settings") renderPage();
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

  async function fetchPluginsConfig() {
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
        renderPage();
      });
    });

    rebindHamburger();
  }

  function renderPluginSettings(name) {
    var p = pluginsConfig[name] || {};

    var contentHtml = "";
    if (settingsRenderer) {
      contentHtml = settingsRenderer.renderPluginPage(name, p, pluginSnapshots[name], pluginState[name]);
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
          savePluginField(pluginName, field, value);
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
    apiFetch(`${API_BASE}/api/plugins/config/${name}`, {
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

  function mdiChar(name) {
    if (mdiCache[name]) return mdiCache[name];
    return "?";
  }

  function applyMdiIcons(root) {
    const scope = root || document;
    scope.querySelectorAll(".md[data-md]").forEach((el) => {
      el.textContent = mdiChar(el.getAttribute("data-md") || "");
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
      .catch(() => {});
  }

  function fetchPanel() {
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
        };
        if (portalAutoPanel) {
          portalAutoPanel = false;
          openPanelView();
        } else {
          renderPanel();
        }
      });
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
    if (on) savePanelLive();
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
    let list = panelDraft.panel_board;
    for (let i = 0; i < path.length; i++) {
      const slot = list[path[i]];
      if (!slot) return [];
      if (!slot.children) slot.children = [];
      list = slot.children;
    }
    return list;
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
    const gOn = layoutOn("gauges") && (panelDraft.panel_gauges || {}).enabled !== false;
    const boxOn = layoutOn("button_box");
    const slidOn = layoutOn("sliders");
    const utilOn = layoutOn("utility");
    const hwOn = !!panelDraft.hardware_connected;
    const board = panelDraft.panel_board || [];
    const util = panelDraft.panel_utility || [];
    const briOn = hwOn && sliderOn("brightness");

    // In the app the header button is "Done" (closes the window via
    // rebindHamburger). On the web portal it is "Launch" -> live panel view.
    const headerBtn = IS_APP
      ? '<button class="done-btn" id="done-btn">Done</button>'
      : '<button class="done-btn" id="launch-btn">Launch</button>';

    const previewHtml =
      '<div class="panel-preview-col">' +
        '<h2 class="panel-preview-title">Preview</h2>' +
        '<div class="panel-phone">' +
          '<div class="panel-phone-sb"><span>COM</span><span class="material-icons-outlined" style="font-size:14px">push_pin</span><span>--:--</span></div>' +
          (gOn ? '<div class="panel-phone-gauges"><div class="pg"></div><div class="pg"></div><div class="pg"></div></div>' : '') +
          (boxOn ? '<div class="panel-phone-grid">' + previewTiles(board.slice(0, 8)) + '</div>' : '') +
          (slidOn ? '<div class="panel-phone-sliders">' +
            (sliderOn("app_volume") ? '<div class="pps-lab">App Volume</div><div class="pps-bar"></div>' : '') +
            (sliderOn("master_volume") ? '<div class="pps-lab">Master Volume</div><div class="pps-bar"></div>' : '') +
            (briOn ? '<div class="pps-lab">Brightness</div><div class="pps-bar"></div>' : '') +
          '</div>' : '') +
          (utilOn ? '<div class="panel-phone-util">' + previewTiles(util, true) + '</div>' : '') +
          '<div class="panel-phone-core">' +
            '<div class="ppt locked"></div><div class="ppt locked"></div>' +
            '<div class="ppt locked"></div><div class="ppt locked"></div>' +
          '</div>' +
        '</div>' +
        '<p class="panel-preview-hint">Preview · core row fixed</p>' +
      '</div>';

    let html =
      '<header>' +
        '<div class="header-left">' +
          '<button class="hamburger" id="hamburger" aria-label="Menu">' +
            '<span class="material-icons-outlined">menu</span>' +
          '</button>' +
          '<div><h1>Panel</h1></div>' +
        '</div>' +
        headerBtn +
      '</header>' +
      '<section class="settings-content panel-page">' +
        '<div class="panel-editor-col">';

    // Gauges
    html += sectionCard("Gauges", "speed",
      toggleRow("Show gauges", gOn, "panel-tog-gauges") +
      '<p class="settings-hint">PC stats: CPU · GPU · FPS</p>');

    // Button box
    html += sectionCard("Button box", "apps",
      toggleRow("Show button box", boxOn, "panel-tog-box") +
      (boxOn ? renderBoardEditor(board, []) : ''));

    // Sliders (brightness only when hardware is connected)
    html += sectionCard("Sliders", "tune",
      toggleRow("Show sliders section", slidOn, "panel-tog-sliders") +
      (slidOn ? (
        toggleRow("App volume", sliderOn("app_volume"), "panel-tog-vol") +
        toggleRow("Master volume", sliderOn("master_volume"), "panel-tog-mvol") +
        toggleRow("App mixer", sliderOn("app_mixer"), "panel-tog-mix") +
        (hwOn ? toggleRow("Display brightness", sliderOn("brightness"), "panel-tog-bri") : "")
      ) : ''));

    // Utility
    html += sectionCard("Utility row", "grid_view",
      toggleRow("Show utility row", utilOn, "panel-tog-util") +
      (utilOn ? renderUtilityEditor(util) : ''));

    html +=
        '</div>' +
        previewHtml +
        (panelEdit ? renderActionModal() : '') +
      '</section>';

    main.innerHTML = html;
    rebindHamburger();
    wirePanelPage();
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

  function previewTiles(slots, four) {
    let h = "";
    const n = four ? 4 : Math.max(slots.length, 1);
    for (let i = 0; i < (four ? 4 : Math.min(n, 8)); i++) {
      const s = slots[i];
      if (!s || s.type === "EMPTY") h += '<div class="ppt empty"></div>';
      else h += '<div class="ppt" title="' + esc(s.name || s.type || "") + '"></div>';
    }
    return h;
  }

  function renderBoardEditor(list, path) {
    let h = '<div class="panel-slot-list" data-path="' + path.join(",") + '">';
    list.forEach((slot, i) => {
      h += '<button type="button" class="panel-slot-tile" data-act="edit" data-i="' + i + '">' +
        '<span class="panel-slot-text">' +
          '<span class="panel-slot-name">' + esc(slot.name || "(unnamed)") + '</span>' +
          '<span class="panel-slot-type">' + esc(actionLabel(slot.type)) + '</span>' +
        '</span>' +
        '<span class="material-icons-outlined panel-slot-chev">chevron_right</span>' +
        '</button>';
      if (slot.type === "GROUP" && slot.children && slot.children.length) {
        h += '<div class="panel-slot-children">' + renderBoardEditor(slot.children, path.concat([i])) + '</div>';
      }
    });
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
        '<span class="panel-slot-type">' + esc(actionLabel(s.type || "EMPTY")) + '</span>' +
        '</button>';
    }
    h += '</div>';
    return h;
  }

  function renderActionModal() {
    const ctx = panelEdit;
    let slot = { name: "", type: "SHORTCUT", icon: "application", color: "" };
    if (ctx.scope === "utility") {
      slot = Object.assign(slot, (panelDraft.panel_utility || [])[ctx.index] || {});
    } else {
      const list = boardAtPath(ctx.path || []);
      if (ctx.index >= 0 && list[ctx.index]) slot = Object.assign(slot, list[ctx.index]);
    }
    const allowGroup = ctx.scope === "board";
    const options = panelActions.filter((a) => allowGroup || a.type !== "GROUP");
    let h = '<div class="panel-modal-backdrop" id="panel-modal">' +
      '<div class="panel-modal">' +
      '<h3>' + (ctx.index < 0 ? "Add action" : "Edit action") + '</h3>' +
      '<div class="settings-control"><label class="settings-label">Name</label>' +
      '<input type="text" class="settings-input" id="pe-name" value="' + esc(slot.name || "") + '"></div>' +
      '<div class="settings-control"><label class="settings-label">Type</label>' +
      '<select class="settings-select" id="pe-type">';
    options.forEach((a) => {
      h += '<option value="' + esc(a.type) + '"' + (a.type === slot.type ? " selected" : "") + ">" + esc(a.label) + "</option>";
    });
    h += '</select></div>' +
      '<div class="settings-control"><label class="settings-label">Icon (mdi name)</label>' +
      '<input type="text" class="settings-input" id="pe-icon" value="' + esc(slot.icon || "") + '"></div>' +
      '<div class="settings-control"><label class="settings-label">Color (#hex or empty)</label>' +
      '<input type="text" class="settings-input" id="pe-color" value="' + esc(slot.color || "") + '"></div>' +
      '<div class="settings-control" id="pe-path-wrap"><label class="settings-label">Shortcut path</label>' +
      '<div class="settings-picker-row">' +
      '<input type="text" class="settings-input" id="pe-path" value="' + esc(slot.shortcut_path || "") + '">' +
      '<button type="button" class="settings-btn" id="pe-browse">Browse</button></div></div>' +
      '<div class="settings-control" id="pe-appicon-wrap" style="display:none"><label class="settings-label">App icon</label>' +
      '<div class="settings-appicon-row">' +
        '<img class="settings-appicon-preview" id="pe-appicon-preview" alt="" hidden>' +
        '<span class="settings-hint" id="pe-appicon-status">Pulled automatically from the executable.</span>' +
      '</div></div>' +
      '<div class="settings-control" id="pe-entity-wrap"><label class="settings-label">HA entity id</label>' +
      '<input type="text" class="settings-input" id="pe-entity" value="' + esc(slot.entity_id || "") + '"></div>' +
      '<div class="settings-control" id="pe-keys-wrap"><label class="settings-label">Hotkey VKs (comma-separated)</label>' +
      '<input type="text" class="settings-input" id="pe-keys" value="' + esc((slot.keys || []).join(",")) + '"></div>' +
      '<div class="settings-control" id="pe-profile-wrap"><label class="settings-label">OpenRGB / plugin profile</label>' +
      '<input type="text" class="settings-input" id="pe-profile" value="' + esc(slot.openrgb_profile || slot.profile || "") + '"></div>' +
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
        openPanelView();
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

    document.querySelectorAll(".panel-slot-list").forEach((listEl) => {
      const pathStr = listEl.getAttribute("data-path") || "";
      const path = pathStr ? pathStr.split(",").map((x) => parseInt(x, 10)) : [];
      listEl.querySelectorAll(".panel-slot-tile, .panel-add-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const act = btn.getAttribute("data-act");
          const i = parseInt(btn.getAttribute("data-i") || "-1", 10);
          if (act === "add") {
            panelEdit = { scope: "board", index: -1, path: path };
            renderPanel();
          } else if (act === "edit") {
            panelEdit = { scope: "board", index: i, path: path };
            renderPanel();
          }
        });
      });
    });

    document.querySelectorAll(".panel-util-tile").forEach((btn) => {
      btn.addEventListener("click", () => {
        panelEdit = { scope: "utility", index: parseInt(btn.getAttribute("data-i"), 10), path: [] };
        renderPanel();
      });
    });

    wireActionModal();
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
    if (panelLiveTimer) clearInterval(panelLiveTimer);
    panelLiveTimer = setInterval(fetchPanelLive, 1000);
  }

  function exitPanelView() {
    panelViewMode = false;
    panelNav = [];
    panelViewSig = "";
    if (panelLiveTimer) { clearInterval(panelLiveTimer); panelLiveTimer = null; }
    panelLive = null;
    const ov = document.getElementById("panel-view");
    if (ov) ov.remove();
  }

  function panelViewConfig() {
    return (panelLive && panelLive.config) || panelDraft || {};
  }

  function panelViewSignature() {
    const cfg = panelViewConfig();
    const board = panelNav.length
      ? (panelNav[panelNav.length - 1].children || [])
      : (cfg.panel_board || []);
    const keys = board.map((s) => (s.type || "") + ":" + (s.name || ""));
    const lay = (cfg.panel_layout || []).map((r) => r.id + "=" + (r.enabled === false ? 0 : 1)).join(",");
    const sl = (cfg.panel_sliders || []).map((r) => r.id + "=" + (r.enabled === false ? 0 : 1)).join(",");
    return JSON.stringify([
      panelNav.map((g) => g.name || g.type || "").join(">"),
      keys,
      lay,
      sl,
      (cfg.panel_gauges || {}).enabled === false ? 0 : 1,
      !!(panelLive && panelLive.hardware_connected),
    ]);
  }

  function fetchPanelLive() {
    apiFetch(`${API_BASE}/api/panel/live`)
      .then((r) => r.json())
      .then((data) => {
        panelLive = data;
        if (!panelViewMode) return;
        if (!panelDraft && data.config) {
          panelDraft = {
            panel_board: data.config.panel_board || [],
            panel_utility: data.config.panel_utility || [],
            panel_sliders: data.config.panel_sliders || [],
            panel_layout: data.config.panel_layout || [],
            panel_gauges: data.config.panel_gauges || { enabled: true },
            media_player_path: data.config.media_player_path || "",
            hardware_connected: !!data.hardware_connected,
          };
        }
        const sig = panelViewSignature();
        if (sig !== panelViewSig || panelMixerChanged(data.app_volumes || [])) {
          panelViewSig = sig;
          renderPanelView();
        } else {
          updatePanelView();
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

    let html = '<div class="pv-screen">';
    html += '<div class="pv-scroll">';
    if (gOn) {
      html += '<div class="pv-gauges">' +
        panelGauge("CPU", gauges.cpu_temp, 100, "°C") +
        panelGauge("GPU", gauges.gpu_temp, 100, "°C") +
        panelGauge("FPS", gauges.fps, 240, "") +
      '</div>';
    }
    html += '<div class="pv-frame">';
    if (boxOn) {
      html += '<div class="pv-box"><div class="pdev-grid">' + boardTilesHtml(board) + '</div></div>';
    }
    html += '<div class="pv-side">';
    if (slidOn) {
      html += '<div class="pv-sliders">' +
        (volOn ? panelSliderHtml("app_volume", "App Volume", volume.volume, 0, 100) : "") +
        (mvolOn ? panelSliderHtml("master_volume", "Master Volume", data.master_volume, 0, 100) : "") +
        (mixOn ? appMixerHtml(data.app_volumes || []) : "") +
        (briOn ? panelSliderHtml("brightness", "Brightness", data.brightness, 0, 4) : "") +
      '</div>';
    }
    html += '</div>';
    html += '</div>';
    html += '</div>';
    if (utilOn) {
      html += '<div class="pv-util"><div class="pdev-grid">' + utilTilesHtml(util) + '</div></div>';
    }
    html += '<div class="pv-core"><div class="pdev-grid">' + coreTilesHtml(data) + '</div></div>';
    html += '</div>';

    ov.innerHTML = html;
    applyMdiIcons(ov);
    const need = ["microphone-off"];
    ov.querySelectorAll(".md[data-md]").forEach((el) => need.push(el.getAttribute("data-md")));
    mdiPreload(need);
    wirePanelView();
    paintPanelRanges(ov);
    fitLandscapeSliders(ov);
    panelViewSig = panelViewSignature();
  }

  function fitLandscapeSliders(ov) {
    if (!ov) return;
    const side = ov.querySelector(".pv-side");
    if (!side) return;
    const isL = window.matchMedia && window.matchMedia("(max-width: 768px) and (orientation: landscape)").matches;
    if (!isL) {
      side.style.width = "";
      return;
    }
    const card = ov.querySelector(".pv-side .pv-sliders");
    if (!card) return;
    side.style.width = card.offsetHeight + "px";
  }

  window.addEventListener("resize", () => {
    if (!panelViewMode) return;
    const ov = document.getElementById("panel-view");
    if (ov) fitLandscapeSliders(ov);
  });

  function gaugeNum(value) {
    const v = (value === null || value === undefined) ? 0 : Math.round(value);
    return String(v);
  }

  function panelGauge(label, value, max, unit) {
    const v = (value === null || value === undefined) ? 0 : value;
    const pct = Math.max(0, Math.min(100, (v / max) * 100));
    const CIRC = 2 * Math.PI * 16;
    const arc = (pct / 100) * CIRC;
    const gid = 'ggrad-' + String(label).toLowerCase().replace(/[^a-z0-9_-]/g, '');
    return '<div class="pdev-gauge">' +
      '<svg viewBox="0 0 40 40" class="pdev-gsvg">' +
        '<defs><linearGradient id="' + gid + '" x1="0%" y1="0%" x2="100%" y2="0%">' +
          '<stop offset="0%" stop-color="#B23AF6"></stop>' +
          '<stop offset="100%" stop-color="#79E8FC"></stop>' +
        '</linearGradient></defs>' +
        '<circle class="pdev-gtrack" cx="20" cy="20" r="16"></circle>' +
        '<circle class="pdev-garc" cx="20" cy="20" r="16" data-gauge="' + esc(label) + '" style="stroke:url(#' + gid + ');stroke-dasharray:' +
          arc.toFixed(1) + ' ' + CIRC.toFixed(1) + '"></circle>' +
      '</svg>' +
      '<span class="pdev-gval"><span class="pdev-gnum" data-gvalue="' + esc(label) + '">' + gaugeNum(v) + '</span></span>' +
      '<span class="pdev-glabel">' + esc(label) + (unit ? ' ' + esc(unit) : '') + '</span>' +
    '</div>';
  }

  function boardTilesHtml(board) {
    let h = "";
    if (panelNav.length) {
      h += '<button type="button" class="pdev-tile pdev-back" data-nav="back" title="Back">' +
        '<span class="md" data-md="arrow-left"></span></button>';
    }
    if (!board || !board.length) {
      h += '<div class="pdev-empty">No actions yet</div>';
      return h;
    }
    for (let i = 0; i < board.length; i++) {
      const s = board[i];
      if (!s || s.type === "EMPTY") { h += '<span class="pdev-tile pdev-empty-tile"></span>'; continue; }
      h += panelTileHtml(s, "box", i);
    }
    return h;
  }

  function utilTilesHtml(util) {
    let h = "";
    const list = util && util.length ? util : [];
    for (let i = 0; i < 4; i++) {
      const s = list[i];
      if (!s || s.type === "EMPTY") { h += '<span class="pdev-tile pdev-empty-tile"></span>'; continue; }
      h += panelTileHtml(s, "util", i);
    }
    return h;
  }

  function panelTileHtml(s, listName, idx) {
    const icon = s.icon || "help-circle";
    const color = s.color || "";
    const isGroup = s.type === "GROUP";
    const appPath = ((s.type === "SHORTCUT" || s.type === "GROUP") && (s.app_icon_path || s.shortcut_path))
      ? (s.app_icon_path || s.shortcut_path) : "";
    const glyph = appPath
      ? '<img class="pdev-iapp" src="' + API_BASE + '/api/panel/icon?path=' + encodeURIComponent(appPath) +
        '" alt="" data-fallback="' + esc(icon) + '">'
      : '<span class="md" data-md="' + esc(icon) + '"></span>';
    return '<button type="button" class="pdev-tile' + (isGroup ? " pdev-group" : "") + '"' +
      ' data-action="slot" data-list="' + listName + '" data-idx="' + idx + '"' +
      (color ? ' style="background:' + esc(color) + '"' : "") +
      ' title="' + esc(s.name || "") + '">' +
      glyph +
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
    if (panelNav.length) return panelNav[panelNav.length - 1].children || [];
    return (panelViewConfig().panel_board) || [];
  }

  function runSlotAction(slot) {
    if (!slot) return;
    if (slot.type === "EMPTY") return;
    if (slot.type === "GROUP") {
      panelNav.push(slot);
      apiFetch(`${API_BASE}/api/panel/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: slot }),
      }).catch(() => {});
      renderPanelView();
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

  function wirePanelView() {
    // App-icon tiles: if the exe icon can't be extracted, fall back to MDI.
    document.querySelectorAll("img.pdev-iapp").forEach((im) => {
      im.addEventListener("error", () => {
        const md = document.createElement("span");
        md.className = "md";
        md.setAttribute("data-md", im.getAttribute("data-fallback") || "help-circle");
        im.replaceWith(md);
        applyMdiIcons(md);
      });
    });
    const tiles = document.querySelectorAll(".pdev-tile");
    tiles.forEach((tile) => {
      if (tile.getAttribute("data-nav") === "back") {
        tile.addEventListener("click", () => {
          panelNav.pop();
          panelViewSig = panelViewSignature();
          renderPanelView();
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

    updateGauge("CPU", gauges.cpu_temp, 100, "°C");
    updateGauge("GPU", gauges.gpu_temp, 100, "°C");
    updateGauge("FPS", gauges.fps, 240, "");

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

    const disp = document.querySelector('.pdev-core-tile[data-core="display"]');
    if (disp) disp.classList.toggle("pdev-active", !!data.pc_stats_manual);
    const ov = document.querySelector('.pdev-core-tile[data-core="overlay"]');
    if (ov) ov.classList.toggle("pdev-active", !!data.overlay_on);
  }

  function updateGauge(label, value, max, unit) {
    const v = (value === null || value === undefined) ? 0 : value;
    const arcEl = document.querySelector('.pdev-garc[data-gauge="' + label + '"]');
    if (arcEl) {
      const pct = Math.max(0, Math.min(100, (v / max) * 100));
      const CIRC = 2 * Math.PI * 16;
      arcEl.style.strokeDasharray = (pct / 100) * CIRC + " " + CIRC;
    }
    const numEl = document.querySelector('.pdev-gnum[data-gvalue="' + label + '"]');
    if (numEl) numEl.textContent = gaugeNum(v);
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

  function browseExe(cb) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.browse_exe) {
      window.pywebview.api.browse_exe().then(cb).catch(() => cb(null));
    } else cb(null);
  }

  function wireActionModal() {
    const modal = document.getElementById("panel-modal");
    if (!modal || !panelEdit) return;
    const typeEl = document.getElementById("pe-type");
    const appIconPreview = document.getElementById("pe-appicon-preview");
    function loadAppIcon() {
      const p = (document.getElementById("pe-path").value || "").trim();
      if (!p) { appIconPreview.hidden = true; return; }
      apiFetch(API_BASE + "/api/panel/icon?path=" + encodeURIComponent(p))
        .then((r) => { if (!r.ok) throw new Error("icon"); return r.blob(); })
        .then((blob) => { appIconPreview.src = URL.createObjectURL(blob); appIconPreview.hidden = false; })
        .catch(() => { appIconPreview.hidden = true; });
    }
    const syncFields = () => {
      const t = typeEl.value;
      const showPath = t === "SHORTCUT" || t === "GROUP";
      const showEnt = t === "REST";
      const showKeys = t === "HOTKEY";
      const showProf = t === "OPENRGB" || t.indexOf("PLUGIN:") === 0;
      const showAppIcon = t === "SHORTCUT";
      document.getElementById("pe-path-wrap").style.display = showPath ? "" : "none";
      document.getElementById("pe-entity-wrap").style.display = showEnt ? "" : "none";
      document.getElementById("pe-keys-wrap").style.display = showKeys ? "" : "none";
      document.getElementById("pe-profile-wrap").style.display = showProf ? "" : "none";
      document.getElementById("pe-appicon-wrap").style.display = showAppIcon ? "" : "none";
      if (showAppIcon) loadAppIcon(); else appIconPreview.hidden = true;
    };
    typeEl.addEventListener("change", syncFields);
    syncFields();
    document.getElementById("pe-browse").addEventListener("click", () => {
      browseExe((p) => {
        if (p) {
          document.getElementById("pe-path").value = p;
          loadAppIcon();
        }
      });
    });
    let iconTimer = null;
    document.getElementById("pe-path").addEventListener("input", () => {
      clearTimeout(iconTimer);
      iconTimer = setTimeout(loadAppIcon, 400);
    });
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
      const slot = {
        name: document.getElementById("pe-name").value.trim(),
        type: t,
        icon: document.getElementById("pe-icon").value.trim() || "help-circle",
        color: document.getElementById("pe-color").value.trim(),
      };
      if (t === "SHORTCUT" || t === "GROUP") {
        slot.shortcut_path = document.getElementById("pe-path").value.trim();
      }
      if (t === "SHORTCUT") {
        slot.app_icon_path = slot.shortcut_path || null;
      }
      if (t === "GROUP" && !slot.children) slot.children = [];
      if (t === "REST") slot.entity_id = document.getElementById("pe-entity").value.trim();
      if (t === "HOTKEY") {
        slot.keys = document.getElementById("pe-keys").value.split(",")
          .map((x) => parseInt(x.trim(), 10)).filter((n) => !isNaN(n));
      }
      if (t === "OPENRGB") slot.openrgb_profile = document.getElementById("pe-profile").value.trim();
      if (t.indexOf("PLUGIN:") === 0) {
        const parts = t.split(":");
        const cid = parts[2] || "value";
        slot[cid] = document.getElementById("pe-profile").value.trim();
        slot.profile = slot[cid];
      }
      if (panelEdit.scope === "utility") {
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
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.close_panel();
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
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ── Window drag (frameless) ──────────────────────────────────

  let dragState = null;

  document.addEventListener("mousedown", (e) => {
    const noDrag = e.target.closest(
      ".sidebar, .content, a, button, input, select, label, .feat-toggle-row, .feat-toggle, .nav-item, .alarm-toggle, .alarm-day, .alarm-spinner-btn, .settings-toggle-row, .settings-toggle, .settings-slider, .settings-select, .settings-input, .settings-btn, .settings-picker-btn"
    );
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

  // ── Init ────────────────────────────────────────────────────

  startPolling();
})();
