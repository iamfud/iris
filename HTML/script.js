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

  // Auth token injected into the served document by ws_bridge. Every API
  // request must carry it.
  const IRIS_TOKEN = (document.querySelector('meta[name="iris-token"]') || {}).content || "";

  function apiFetch(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign({}, opts.headers || {});
    if (IRIS_TOKEN) opts.headers["X-Iris-Token"] = IRIS_TOKEN;
    return fetch(url, opts);
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

  let volumeState = { app: null, volume: null };
  let volumeTimer = null;

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
        renderPage();
        if (page === "features" || page === "alarms" || page === "network") fetchConfig();
        else if (page === "plugins") fetchPluginsConfig();
        else if (page === "vision") fetchVision();
        else { visionInWizard = false; stopTestPoll(); stopVolumePoll(); }
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
    settingsRenderer.loadPages().then(function () { renderPage(); });
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
        if (currentPage === "features" || currentPage === "alarms" || currentPage === "network") renderPage();
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

  // ── Panel page (active-app volume) ──────────────────────────

  function renderPanel() {
    main.innerHTML =
      '<header>' +
        '<div class="header-left">' +
          '<button class="hamburger" id="hamburger" aria-label="Menu">' +
            '<span class="material-icons-outlined">menu</span>' +
          '</button>' +
          '<div>' +
            '<h1>Panel</h1>' +
          '</div>' +
        '</div>' +
        '<button class="done-btn" id="done-btn">Done</button>' +
      '</header>' +
      '<section class="settings-content">' +
        '<div class="settings-card vol-tile">' +
          '<div class="vol-heading">' +
            '<span class="material-icons-outlined vol-heading-icon">graphic_eq</span>' +
            '<span>Active App Volume</span>' +
          '</div>' +
          '<div class="vol-app" id="vol-app">—</div>' +
          '<div class="vol-slider-row">' +
            '<input type="range" id="vol-slider" class="settings-slider" min="0" max="100" step="1" value="0" disabled>' +
            '<span class="settings-slider-value" id="vol-value">0%</span>' +
          '</div>' +
        '</div>' +
      '</section>';
    rebindHamburger();
    wireVolume();
    startVolumePoll();
  }

  function wireVolume() {
    const slider = document.getElementById("vol-slider");
    if (!slider) return;
    let saveTimer = null;
    slider.addEventListener("input", () => {
      const val = parseInt(slider.value, 10);
      const valueEl = document.getElementById("vol-value");
      if (valueEl) valueEl.textContent = val + "%";
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        apiFetch(`${API_BASE}/api/volume`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ volume: val }),
        }).catch(() => {});
      }, 150);
    });
  }

  function startVolumePoll() {
    stopVolumePoll();
    volumeTimer = setInterval(() => {
      apiFetch(`${API_BASE}/api/volume`)
        .then((r) => r.json())
        .then((data) => {
          if (!data || typeof data.volume !== "number") return;
          volumeState = data;
          updateVolumeUI();
        })
        .catch(() => {});
    }, 1000);
  }

  function stopVolumePoll() {
    if (volumeTimer) { clearInterval(volumeTimer); volumeTimer = null; }
  }

  function updateVolumeUI() {
    const slider = document.getElementById("vol-slider");
    const appEl = document.getElementById("vol-app");
    const valueEl = document.getElementById("vol-value");
    if (!slider || !appEl) return;
    if (typeof volumeState.volume === "number") {
      slider.value = String(volumeState.volume);
      slider.disabled = false;
      appEl.textContent = volumeState.app || "Application";
      appEl.classList.remove("vol-app-none");
      if (valueEl) valueEl.textContent = volumeState.volume + "%";
    } else {
      slider.value = "0";
      slider.disabled = true;
      appEl.textContent = volumeState.app ? (volumeState.app + " — no audio session") : "No audio session";
      appEl.classList.add("vol-app-none");
      if (valueEl) valueEl.textContent = "—";
    }
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
