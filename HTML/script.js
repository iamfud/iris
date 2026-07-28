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
    fetch(`${API_BASE}/api/sounds/preview/${encodeURIComponent(name)}`).catch(() => {});
  }

  function stopPreview() {
    previewingSound = null;
    fetch(`${API_BASE}/api/sounds/stop`).catch(() => {});
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
        if (page === "features" || page === "alarms") fetchConfig();
        else if (page === "plugins") fetchPluginsConfig();
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
      const res = await fetch(`${API_BASE}/api/plugins/state`);
      if (res.ok) {
        const next = await res.json();
        const json = JSON.stringify(next);
        const prev = JSON.stringify(pluginState);
        pluginState = next;
        if (json !== prev) {
          const section = document.querySelector(".content");
          const scrollTop = section ? section.scrollTop : 0;
          renderPage();
          const newSection = document.querySelector(".content");
          if (newSection) newSection.scrollTop = scrollTop;
        }
      }
    } catch (_) {
      // server not running yet — silent fail
    }
  }

  function startPolling() {
    settingsRenderer = new SettingsRenderer(API_BASE);
    settingsRenderer.loadPages().then(function () { renderPage(); });
    fetchState();
    fetchPluginsConfig();
    fetchDeviceStatus();
    pollTimer = setInterval(fetchState, POLL_MS);
    setInterval(fetchPluginsConfig, 30000);
    setInterval(fetchDeviceStatus, 5000);
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
            '<p>' + esc(page.subtitle) + '</p>' +
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
      const res = await fetch(`${API_BASE}/api/config`);
      if (res.ok) {
        featureConfig = await res.json();
        if (currentPage === "features" || currentPage === "alarms") renderPage();
      }
    } catch (_) {}
  }

  async function fetchDeviceStatus() {
    try {
      const res = await fetch(`${API_BASE}/api/status`);
      if (res.ok) {
        deviceStatus = await res.json();
        if (currentPage === "dashboard") renderDashboard();
      }
    } catch (_) {}
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
      fetch(`${API_BASE}/api/config`, {
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
            <p>Configure LED matrix</p>
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
      fetch(`${API_BASE}/api/config`, {
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
            <p>${alarms.length} alarm${alarms.length !== 1 ? "s" : ""}</p>
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
      const res = await fetch(`${API_BASE}/api/plugins/config`);
      if (res.ok) {
        pluginsConfig = await res.json();
        if (currentPage === "plugins") renderPage();
        else if (currentPage === "dashboard") renderDashboard();
      }
    } catch (_) {}
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
            <p>${names.length} installed</p>
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
    var icon = p.icon || "extension";
    var color = STATUS_COLORS[p.status_code] || "var(--fg-dim)";
    var statusLabel = p.status_label || "Unknown";

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
          '<button class="back-btn" id="back-btn">' +
            '<span class="material-icons-outlined">arrow_back</span>' +
          '</button>' +
          '<div>' +
            '<h1>' + esc(p.display_name || name) + '</h1>' +
            '<p style="color:' + color + '">' + esc(statusLabel) + '</p>' +
          '</div>' +
        '</div>' +
        '<button class="done-btn" id="done-btn">Done</button>' +
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

    var hasLiveData = pluginState[name] && pluginState[name].state
      && Object.keys(pluginState[name].state).length > 0;
    if (!hasLiveData && !pluginSnapshots[name]) {
      fetch(API_BASE + "/api/plugins/" + encodeURIComponent(name) + "/snapshot")
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
    fetch(`${API_BASE}/api/plugins/config/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pluginsConfig[name]),
    }).catch(() => {});
  }

  function renderDashboard() {
    const userName = featureConfig.user_name || "";
    const greeting = featureConfig.feature_greeting !== false
      ? `<span class="dash-greeting">Welcome back${userName ? ", " + esc(userName) : ""}</span>`
      : "";
    const connected = deviceStatus.connected;
    const port = deviceStatus.port || "—";
    const lastNotif = deviceStatus.last_notification || "";

    const plugins = Object.keys(pluginsConfig);
    const active = plugins.some((p) => pluginState[p]);
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
            <p class="dash-status-line">
              <span class="dash-status-dot" style="background:${connected ? "var(--neon-grn)" : "var(--neon-red)"}"></span>
              Iris Device: ${connected ? "Online" : "Offline"} &bull; ${esc(port)}
            </p>
          </div>
        </div>
        <button class="done-btn" id="done-btn">Done</button>
      </header>
      <section class="content dash-content">
        <div class="dash-hero">
          <div class="dash-hero-text">
            ${greeting}
            <span class="dash-sub">Iris is ${active ? "active" : "idle"}${lastNotif ? " — " + esc(lastNotif) : ""}</span>
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
            '<p>' + esc(subtitle) + '</p>' +
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
