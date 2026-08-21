/* Settings Renderer — unified layout engine for all settings pages.
 *
 * Reads page definitions from settings_pages.json and renders controls
 * with identical styling, spacing, and behaviour. No plugin-specific CSS.
 */

"use strict";

var _escMap = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
var MEDIA_PLAYER_BRAND_ICONS = {
  spotify: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><circle cx="12" cy="12" r="12" fill="#1ED760"/><path d="M17.5 16.2c-.2.3-.6.4-.9.2-2.5-1.5-5.6-1.9-9.3-1-.4.1-.7-.1-.8-.5-.1-.4.1-.7.5-.8 4.1-1 7.6-.5 10.3 1.2.3.2.4.6.2.9zm1.2-2.7c-.3.4-.8.5-1.2.3-2.9-1.8-7.3-2.3-10.7-1.3-.4.1-.9-.1-1-.5-.1-.4.1-.9.5-1 3.9-1.2 8.8-.6 12.1 1.4.4.2.5.7.3 1.1zm.1-2.9c-3.5-2.1-9.2-2.3-12.5-1.3-.5.2-1.1-.1-1.3-.6-.2-.5.1-1.1.6-1.3 3.9-1.2 10.2-1 14.2 1.4.5.3.6.9.3 1.4-.3.5-.9.7-1.3.4z" fill="#000"/></svg>',
  itunes: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#FA243C"/><path d="M16.5 6.2v8.6c0 1.5-1.2 2.7-2.7 2.7s-2.7-1.2-2.7-2.7 1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3V8.8l-5.5 1.2v6c0 1.5-1.2 2.7-2.7 2.7S4.1 17.5 4.1 16s1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3v-8l8.5-1.9v2.5z" fill="#fff"/></svg>',
  applemusic: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#FA243C"/><path d="M16.5 6.2v8.6c0 1.5-1.2 2.7-2.7 2.7s-2.7-1.2-2.7-2.7 1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3V8.8l-5.5 1.2v6c0 1.5-1.2 2.7-2.7 2.7S4.1 17.5 4.1 16s1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3v-8l8.5-1.9v2.5z" fill="#fff"/></svg>',
  "apple music": '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#FA243C"/><path d="M16.5 6.2v8.6c0 1.5-1.2 2.7-2.7 2.7s-2.7-1.2-2.7-2.7 1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3V8.8l-5.5 1.2v6c0 1.5-1.2 2.7-2.7 2.7S4.1 17.5 4.1 16s1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3v-8l8.5-1.9v2.5z" fill="#fff"/></svg>',
  "vlc media player": '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><path d="M12 2l-2.5 7h5L12 2z" fill="#FF8800"/><path d="M9.2 10l-.8 2.5h7.2L14.8 10H9.2z" fill="#FFFFFF"/><path d="M8.1 13.5l-.9 3h9.6l-.9-3H8.1z" fill="#FF8800"/><path d="M6.9 17.5l-1.1 3.5h12.4l-1.1-3.5H6.9z" fill="#FFFFFF"/><path d="M3 21.5h18v1.5H3v-1.5z" fill="#FF8800"/><path d="M5 22h14l-1-1H6l-1 1z" fill="#E65100"/></svg>',
  vlc: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><path d="M12 2l-2.5 7h5L12 2z" fill="#FF8800"/><path d="M9.2 10l-.8 2.5h7.2L14.8 10H9.2z" fill="#FFFFFF"/><path d="M8.1 13.5l-.9 3h9.6l-.9-3H8.1z" fill="#FF8800"/><path d="M6.9 17.5l-1.1 3.5h12.4l-1.1-3.5H6.9z" fill="#FFFFFF"/><path d="M3 21.5h18v1.5H3v-1.5z" fill="#FF8800"/><path d="M5 22h14l-1-1H6l-1 1z" fill="#E65100"/></svg>',
  "windows media player": '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#0078D4"/><circle cx="12" cy="12" r="7.5" fill="#FFB900"/><polygon points="10,8 16,12 10,16" fill="#FFFFFF"/></svg>',
  "media player": '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#0078D4"/><circle cx="12" cy="12" r="7.5" fill="#FFB900"/><polygon points="10,8 16,12 10,16" fill="#FFFFFF"/></svg>',
  wmplayer: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#0078D4"/><circle cx="12" cy="12" r="7.5" fill="#FFB900"/><polygon points="10,8 16,12 10,16" fill="#FFFFFF"/></svg>',
  windowsmediaplayer: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#0078D4"/><circle cx="12" cy="12" r="7.5" fill="#FFB900"/><polygon points="10,8 16,12 10,16" fill="#FFFFFF"/></svg>',
  foobar2000: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><circle cx="12" cy="12" r="11" fill="#2B2B2B" stroke="#888" stroke-width="1"/><circle cx="8.5" cy="10" r="2.5" fill="#fff"/><circle cx="15.5" cy="10" r="2.5" fill="#fff"/><circle cx="9" cy="10" r="1.2" fill="#000"/><circle cx="16" cy="10" r="1.2" fill="#000"/><ellipse cx="12" cy="16" rx="4" ry="2" fill="#fff"/></svg>',
  foobar: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><circle cx="12" cy="12" r="11" fill="#2B2B2B" stroke="#888" stroke-width="1"/><circle cx="8.5" cy="10" r="2.5" fill="#fff"/><circle cx="15.5" cy="10" r="2.5" fill="#fff"/><circle cx="9" cy="10" r="1.2" fill="#000"/><circle cx="16" cy="10" r="1.2" fill="#000"/><ellipse cx="12" cy="16" rx="4" ry="2" fill="#fff"/></svg>',
  musicbee: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><circle cx="12" cy="12" r="11" fill="#FFA000"/><path d="M7 11h10v2H7zM9 15h6v2H9z" fill="#212121"/><circle cx="9" cy="7.5" r="1.5" fill="#212121"/><circle cx="15" cy="7.5" r="1.5" fill="#212121"/><path d="M12 4v3" stroke="#212121" stroke-width="1.5" stroke-linecap="round"/></svg>',
  aimp: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><circle cx="12" cy="12" r="11" fill="#FF5722"/><polygon points="9,6 18,12 9,18" fill="#FFFFFF"/><polygon points="12,9 18,12 12,15" fill="#FFCCBC"/></svg>',
  tidal: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#000"/><g fill="#fff" transform="translate(2, 2) scale(0.833)"><polygon points="6,3 9,6 6,9 3,6"/><polygon points="12,3 15,6 12,9 9,6"/><polygon points="18,3 21,6 18,9 15,6"/><polygon points="12,9 15,12 12,15 9,12"/></g></svg>',
  plexamp: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#1F2326"/><polygon points="8,4 14,12 8,20 12,20 18,12 12,4" fill="#E5A00D"/></svg>',
  winamp: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#1C2128"/><path d="M14 3L6 13h5l-2 8 10-11h-5l2-7z" fill="#FFAA00" stroke="#FF8800" stroke-width="0.5"/></svg>',
  "mpc-hc": '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#1565C0"/><path d="M4 6h16v12H4z" fill="#212121"/><path d="M4 6l3 4h3L7 6h3l3 4h3l-3-4h3l3 4h2V6H4z" fill="#EEEEEE"/><polygon points="10,11 15,14 10,17" fill="#FFFFFF"/></svg>',
  "mpc-be": '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#1565C0"/><path d="M4 6h16v12H4z" fill="#212121"/><path d="M4 6l3 4h3L7 6h3l3 4h3l-3-4h3l3 4h2V6H4z" fill="#EEEEEE"/><polygon points="10,11 15,14 10,17" fill="#FFFFFF"/></svg>',
  mpc: '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none"><rect width="24" height="24" rx="5" fill="#1565C0"/><path d="M4 6h16v12H4z" fill="#212121"/><path d="M4 6l3 4h3L7 6h3l3 4h3l-3-4h3l3 4h2V6H4z" fill="#EEEEEE"/><polygon points="10,11 15,14 10,17" fill="#FFFFFF"/></svg>'
};

function getMediaPlayerBrandIcon(nameOrPath) {
  if (!nameOrPath) return null;
  var s = String(nameOrPath).toLowerCase();
  var clean = s.replace(/[\s\-_.]/g, "");
  for (var key in MEDIA_PLAYER_BRAND_ICONS) {
    var cleanKey = key.replace(/[\s\-_.]/g, "");
    if (s.includes(key) || clean.includes(cleanKey)) {
      return MEDIA_PLAYER_BRAND_ICONS[key];
    }
  }
  return null;
}
window.MEDIA_PLAYER_BRAND_ICONS = MEDIA_PLAYER_BRAND_ICONS;
window.getMediaPlayerBrandIcon = getMediaPlayerBrandIcon;

// Auth is carried by the loopback peer or the login session cookie; the
// access token is never embedded in the page any more.
var _IRIS_TOKEN = "";

// True only inside the desktop app's panel window (pywebview). App-only
// settings sections (e.g. Network security) are hidden from phone/browser.
function _isApp() {
  return !!(window.pywebview && window.pywebview.api);
}

function apiFetch(url, opts) {
  opts = opts || {};
  opts.headers = Object.assign({}, opts.headers || {});
  var savedTok = "";
  try { savedTok = localStorage.getItem("iris_session") || ""; } catch (_) {}
  if (savedTok) opts.headers["X-Iris-Session"] = savedTok;
  if (_IRIS_TOKEN) opts.headers["X-Iris-Token"] = _IRIS_TOKEN;
  return fetch(url, opts).then(function (res) {
    if (res.status === 401) {
      // Session expired or unauthenticated remote access -> back to login.
      window.location.href = "/login";
      throw new Error("unauthorized");
    }
    return res;
  });
}

class SettingsRenderer {

  constructor(apiBase) {
    this._apiBase = apiBase;
    this._pages = null;
    this._saveTimers = {};
    this._configCache = {};
    this._pluginConfigCache = {};
  }

  /* ── Public API ─────────────────────────────────────────────── */

  async loadPages() {
    if (this._pages) return this._pages;
    try {
      const res = await apiFetch(this._apiBase + "/api/settings/pages");
      if (res.ok) {
        const data = await res.json();
        this._pages = data.pages || [];
        return this._pages;
      }
    } catch (_) {}
    this._pages = [];
    return this._pages;
  }

  getPage(id) {
    return (this._pages || []).find(function (p) { return p.id === id; });
  }

  getNavItems() {
    return (this._pages || []).map(function (p) {
      return { id: p.id, title: p.title, icon: p.icon, nav_group: p.nav_group };
    });
  }

  /* ── Render a built-in page ─────────────────────────────────── */

  renderBuiltInPage(pageId, config, pluginConfig, pluginState, deviceStatus) {
    var page = this.getPage(pageId);
    if (!page) return null;

    this._configCache = config || {};
    this._pluginConfigCache = pluginConfig || {};

    var self = this;
    var html = "";

    if (pageId === "features" && deviceStatus && typeof deviceStatus.connected === "boolean" && !deviceStatus.connected) {
      return '<section class="device-offline">' +
        '<div class="device-offline-tile">' +
          '<span class="material-icons-outlined device-offline-icon">usb</span>' +
          '<p class="device-offline-msg">Please connect your Iris device.</p>' +
        "</div>" +
      "</section>";
    }

    if (page.sections && page.sections.length > 0) {
      var isApp = _isApp();
      html += '<section class="settings-content">';
      page.sections.forEach(function (section) {
        if (section.app_only && !isApp) return;
        html += self._renderSection(section, config);
      });
      html += "</section>";
    } else {
      html += '<section class="settings-content settings-empty">';
      html += '<div class="settings-placeholder">';
      html += '<span class="material-icons-outlined">construction</span>';
      html += "<p>" + self._esc(page.subtitle || "Coming soon") + "</p>";
      html += "</div>";
      html += "</section>";
    }

    return html;
  }

  /* ── Render a plugin settings page ──────────────────────────── */

  renderPluginPage(name, pluginCfg, pluginData, pluginStateData, config) {
    if (config) {
      this._configCache = Object.assign(this._configCache || {}, config);
    }
    var p = pluginCfg || {};
    var capabilities = p.capabilities || {};
    var hasCapabilities = Object.keys(capabilities).length > 0;

    if (!hasCapabilities) {
      return this._renderPluginPageLegacy(name, pluginCfg, pluginData, pluginStateData);
    }

    var LABEL_DEFAULTS = {
      status: "Status",
      configuration: "Configuration",
      buttons: "Button Controls",
      outputs: "Output Routing",
      live_data: "Live Data",
      actions: "Actions",
      diagnostics: "Diagnostics",
    };

    var self = this;
    var html = '<section class="settings-content">';

    var sectionOrder = [
      { key: "status",        render: "_renderPluginStatus" },
      { key: "configuration", render: "_renderPluginConfig" },
      { key: "buttons",       render: "_renderPluginButtons" },
      { key: "outputs",       render: "_renderPluginOutputs" },
      { key: "live_data",     render: "_renderPluginLiveData" },
      { key: "actions",       render: "_renderPluginActions" },
      { key: "diagnostics",   render: "_renderPluginDiagnostics" },
    ];

    sectionOrder.forEach(function (s) {
      if (!capabilities[s.key]) return;
      var content = self[s.render](name, p, pluginData, pluginStateData);
      if (!content) return;
      var label = (p.labels && p.labels[s.key]) || LABEL_DEFAULTS[s.key] || s.key;
      html += '<div class="settings-section">';
      html += '<h2 class="settings-section-title">' + self._esc(label) + '</h2>';
      html += '<div class="settings-card">';
      html += content;
      html += '</div></div>';
    });

    html += "</section>";
    return html;
  }

  /* ── Legacy renderer for plugins without capabilities ───────── */

  _renderPluginPageLegacy(name, pluginCfg, pluginData, pluginStateData) {
    var p = pluginCfg || {};
    var color = this._statusColor(p.status_code);
    var statusLabel = p.status_label || "Unknown";
    var message = p.message || "";
    var ptype = p.type || "service";
    var requirements = p.requirements || [];
    var settings = p.settings || [];

    var self = this;
    var html = '<section class="settings-content">';

    /* Status card */
    html += '<div class="settings-section">';
    html += '<h2 class="settings-section-title">Status</h2>';
    html += '<div class="settings-card">';
    html += '<div class="plugin-status-row">';
    html += '<span class="plugin-status-dot" style="background:' + color + '"></span>';
    html += '<span class="plugin-status-label" style="color:' + color + '">' + this._esc(statusLabel) + "</span>";
    html += '<span class="plugin-status-type">' + this._esc(ptype.charAt(0).toUpperCase() + ptype.slice(1)) + "</span>";
    html += "</div>";
    if (message) {
      html += '<div class="plugin-message">' + this._esc(message) + "</div>";
    }
    if (requirements.length) {
      html += this._renderRequirements(requirements);
    }
    html += "</div></div>";

    /* Configuration card */
    html += '<div class="settings-section">';
    html += '<h2 class="settings-section-title">Configuration</h2>';
    html += '<div class="settings-card">';
    if (settings.length > 0) {
      var pluginCfg = p.config || {};
      settings.forEach(function (section) {
        if (!section.controls || !section.controls.length) return;
        section.controls.forEach(function (ctrl) {
          var values = {};
          values[ctrl.key] = pluginCfg[ctrl.key];
          if (ctrl.key === "enabled") values[ctrl.key] = p.enabled !== false;
          html += self._renderControl(ctrl, values);
        });
      });
    } else {
      html += self._renderControl({
        type: "toggle",
        key: "_plugin_enabled_" + name,
        label: "Enabled",
      }, { _plugin_enabled: p.enabled !== false });
      if (ptype === "app") {
        html += self._renderControl({
          type: "folder_picker",
          key: "_plugin_exe_" + name,
          label: "Target executable",
        }, { _plugin_exe: p.exe_path || p.exe_default || "" });
      }
    }
    html += "</div></div>";

    /* Data card */
    html += '<div class="settings-section">';
    html += '<h2 class="settings-section-title">Live Data</h2>';
    html += '<div class="settings-card">';
    html += this._renderPluginData(name, pluginData, pluginStateData);
    html += "</div></div>";

    html += "</section>";
    return html;
  }

  /* ── Capability-based section renderers ─────────────────────── */

  _renderPluginStatus(name, p, pluginData, pluginStateData) {
    var html = "";

    var statusCode = p.status_code;
    var statusLabel = p.status_label || "Unknown";
    var color = this._statusColor(statusCode);

    html += '<div class="plugin-status-row">';
    html += '<span class="plugin-status-dot" style="background:' + color + '"></span>';
    html += '<span class="plugin-status-label" style="color:' + color + '">' + this._esc(statusLabel) + "</span>";
    html += '<span class="plugin-status-type">' + this._esc((p.type || "service").charAt(0).toUpperCase() + (p.type || "service").slice(1)) + "</span>";
    html += "</div>";

    var fields = p.status_fields || [];
    if (fields.length > 0) {
      var self = this;
      fields.forEach(function (f) {
        if (f.key === "status_code") return;
        var val;
        if (f.source === "lifecycle") {
          val = p[f.key];
        } else {
          var ps = pluginStateData || {};
          var liveState = ps.state || {};
          var liveStatus = ps.status || {};
          val = liveState[f.key] !== undefined ? liveState[f.key] : liveStatus[f.key];
        }
        if (val === undefined || val === null) val = "—";
        html += self._detailRow(f.label, String(val));
      });
    }

    if (p.message) {
      html += '<div class="plugin-message">' + this._esc(p.message) + "</div>";
    }
    if (p.requirements && p.requirements.length) {
      html += this._renderRequirements(p.requirements);
    }
    return html;
  }

  _renderPluginConfig(name, p, pluginData, pluginStateData) {
    var settings = p.settings || [];
    if (settings.length === 0) {
      var html = "";
      html += this._renderControl({
        type: "toggle",
        key: "_plugin_enabled_" + name,
        label: "Enabled",
      }, { _plugin_enabled: p.enabled !== false });
      if ((p.type || "service") === "app") {
        html += this._renderControl({
          type: "folder_picker",
          key: "_plugin_exe_" + name,
          label: "Target executable",
        }, { _plugin_exe: p.exe_path || p.exe_default || "" });
      }
      return html;
    }

    var self = this;
    var pcfg = p.config || {};
    var html = "";
    settings.forEach(function (section) {
      if (!section.controls || !section.controls.length) return;
      section.controls.forEach(function (ctrl) {
        var values = {};
        values[ctrl.key] = pcfg[ctrl.key];
        if (ctrl.key === "enabled") values[ctrl.key] = p.enabled !== false;
        html += self._renderControl(ctrl, values);
      });
    });
    return html;
  }

  _renderPluginOutputs(name, p, pluginData, pluginStateData) {
    var outputDefs = p.outputs_def || [];
    if (outputDefs.length === 0) return "";

    var currentOutputs = p.outputs || {};
    var self = this;
    var html = '<div class="plugin-outputs-hint">Where can this plugin send data?</div>';

    outputDefs.forEach(function (o) {
      var on = currentOutputs[o.id] !== undefined ? currentOutputs[o.id] : (o.enabled !== false);
      var cls = on ? "on" : "";
      html += '<div class="settings-toggle-row plugin-output-row" data-output="' + self._esc(o.id) + '">';
      html += '<span class="settings-toggle-label">' + self._esc(o.label) + "</span>";
      html += '<div class="settings-toggle ' + cls + '" data-output="' + self._esc(o.id) + '">';
      html += '<div class="settings-toggle-thumb"></div>';
      html += "</div>";
      html += "</div>";
    });

    return html;
  }

  _renderPluginButtons(name, p, pluginData, pluginStateData, config) {
    var buttons = p.buttons_def || [];
    if (!buttons.length) return "";

    var self = this;
    var profiles = (p && p.panel_profiles) ||
                   (config && config.panel_profiles) ||
                   (this._configCache && this._configCache.panel_profiles) ||
                   (typeof panelDraft !== "undefined" && panelDraft && panelDraft.panel_profiles) ||
                   (typeof featureConfig !== "undefined" && featureConfig && featureConfig.panel_profiles) || [];

    // Find matching profile for this plugin if exists
    var matchingProf = profiles.find(function(prof) {
      if (!prof || typeof prof !== "object") return false;
      var profExe = (prof.exe || "").toLowerCase();
      var profName = (prof.name || "").toLowerCase();
      var pluginExe = (p.exe_default || "").toLowerCase().replace(".exe", "");
      var pluginName = (p.display_name || name || "").toLowerCase();
      return (profExe && pluginExe && (profExe.indexOf(pluginExe) !== -1 || pluginExe.indexOf(profExe.replace(".exe", "")) !== -1)) ||
             (profName && pluginName && (profName.indexOf(pluginName) !== -1 || pluginName.indexOf(profName) !== -1));
    });
    var defaultTargetId = matchingProf ? matchingProf.id : (profiles.length > 0 ? profiles[0].id : "__default__");

    var html = '<div class="plugin-button-studio">';

    // 1. Export Bar
    html += '<div class="plugin-export-bar">';
    html += '<div class="plugin-export-info">';
    html += '<span class="material-icons-outlined plugin-export-icon">grid_view</span>';
    html += '<div>';
    html += '<div class="plugin-export-title">Export to Button Box</div>';
    html += '<div class="plugin-export-desc">Push configured buttons directly into a Button Profile for your device.</div>';
    html += '</div></div>';

    html += '<div class="plugin-export-actions">';
    html += '<label class="plugin-export-target-lbl">Target Profile:</label>';
    html += '<select id="plugin-btn-target-profile" class="settings-select plugin-export-select">';
    html += '<option value="__default__"' + (defaultTargetId === "__default__" ? ' selected' : '') + '>Default Board</option>';
    profiles.forEach(function(prof) {
      var sel = prof.id === defaultTargetId ? ' selected' : '';
      var sub = prof.exe ? prof.exe : (prof.is_group ? "Group" : "App Profile");
      html += '<option value="' + self._esc(prof.id) + '"' + sel + '>' + self._esc(prof.name || prof.id) + ' (' + self._esc(sub) + ')</option>';
    });
    html += '<option value="__new__"' + (defaultTargetId === "__new__" ? ' selected' : '') + '>+ Create New Profile for ' + self._esc(p.display_name) + '</option>';
    html += '</select>';

    html += '<button type="button" class="btn btn-primary btn-export-all" data-plugin="' + self._esc(name) + '" title="Export full 12-button matrix into the selected profile">';
    html += '<span class="material-icons-outlined" style="font-size:16px;vertical-align:middle;margin-right:4px">send</span> Export 12-Button Preset</button>';
    html += '</div></div>';

    // 2. Buttons Grid
    html += '<div class="plugin-buttons-grid">';
    var ps = pluginStateData || {};
    var liveState = ps.state || ps || {};
    var liveStatus = ps.status || {};

    buttons.forEach(function(btn) {
      var skey = btn.state_key || "";
      var val = liveStatus[skey] !== undefined ? liveStatus[skey] : liveState[skey];
      var is_on = false;
      if (typeof val === "boolean") is_on = val;
      else if (typeof val === "number") is_on = val > 0;
      else if (typeof val === "string") is_on = ["down", "deployed", "on", "active", "charging", "true", "yes", "online"].indexOf(val.toLowerCase()) !== -1;

      var labels = btn.labels || {};
      var lblText = is_on ? (labels.on || "ON") : (labels.off || "OFF");
      var colors = btn.colors || {};
      var activeColor = colors.on || "var(--neon-grn)";
      var inactiveColor = colors.off || "var(--fg-dim)";
      var badgeColor = is_on ? activeColor : inactiveColor;
      var activeBg = is_on ? "rgba(0, 255, 136, 0.08)" : "transparent";

      html += '<div class="plugin-btn-card" data-btn-id="' + self._esc(btn.id) + '">';

      // Tile Visual Mockup
      html += '<div class="plugin-btn-tile-preview" style="border-color:' + (is_on ? activeColor : 'var(--bg-card-border)') + '; background:' + activeBg + '">';
      html += '<span class="md" data-md="' + self._esc(btn.icon || 'puzzle') + '"></span>';
      html += '<span class="plugin-btn-tile-title">' + self._esc(btn.name || btn.id) + '</span>';
      html += '<span class="plugin-btn-tile-badge" style="color:' + badgeColor + '; border-color:' + badgeColor + '">' + self._esc(lblText) + '</span>';
      html += '</div>';

      // Info and Controls
      html += '<div class="plugin-btn-details">';
      html += '<div class="plugin-btn-head">';
      html += '<span class="plugin-btn-name">' + self._esc(btn.name || btn.id) + '</span>';
      html += '<span class="plugin-btn-type-pill">' + self._esc(btn.widget_type || 'status_toggle') + '</span>';
      html += '</div>';
      if (btn.description) {
        html += '<div class="plugin-btn-desc">' + self._esc(btn.description) + '</div>';
      }

      html += '<div class="plugin-btn-inputs-row">';
      html += '<div class="plugin-btn-input-group">';
      html += '<label>Hotkey:</label>';
      html += '<input type="text" class="settings-input plugin-btn-hotkey-input" data-plugin="' + self._esc(name) + '" data-btn-id="' + self._esc(btn.id) + '" value="' + self._esc(btn.default_hotkey || '') + '" placeholder="e.g. L">';
      html += '</div>';

      html += '<button type="button" class="btn btn-sm btn-ghost btn-export-single" data-plugin="' + self._esc(name) + '" data-btn-id="' + self._esc(btn.id) + '" title="Send this single button to target profile">';
      html += '<span class="material-icons-outlined" style="font-size:14px;vertical-align:middle;margin-right:2px">add_to_photos</span> Send to Profile</button>';
      html += '</div>';

      html += '</div></div>';
    });

    html += '</div></div>';
    return html;
  }

  _renderPluginLiveData(name, p, pluginData, pluginStateData) {
    return this._renderPluginData(name, pluginData, pluginStateData);
  }

  _renderPluginActions(name, p, pluginData, pluginStateData) {
    var actionDefs = p.actions_def || [];
    if (actionDefs.length === 0) return "";

    var self = this;
    var html = '<div class="plugin-actions-row">';

    actionDefs.forEach(function (a) {
      html += '<button class="settings-btn plugin-action-btn" data-action-id="' + self._esc(a.id) + '"';
      if (a.confirm) html += ' data-confirm="true"';
      html += ">";
      if (a.icon) html += '<span class="material-icons-outlined">' + self._esc(a.icon) + "</span> ";
      html += self._esc(a.label || a.id);
      html += "</button>";
    });

    html += "</div>";
    return html;
  }

  _renderPluginDiagnostics(name, p, pluginData, pluginStateData) {
    var diagFields = p.diagnostics_def || [];
    if (diagFields.length === 0) return "";

    var self = this;
    var html = "";

    diagFields.forEach(function (f) {
      var val;
      if (f.source === "lifecycle") {
        val = p[f.key];
      } else {
        var ps = pluginStateData || {};
        var liveState = ps.state || {};
        var liveStatus = ps.status || {};
        val = liveState[f.key] !== undefined ? liveState[f.key] : liveStatus[f.key];
      }
      if (val === undefined || val === null) val = "—";
      html += self._detailRow(f.label, String(val));
    });

    var rawEvents = ((pluginStateData || {}).state || {})._raw_events;
    if (rawEvents && rawEvents.length > 0) {
      html += '<div class="settings-collapsible raw-events">';
      html += '<a href="#" class="collapse-toggle">';
      html += '&#9654; Raw Events (' + rawEvents.length + ')</a>';
      html += '<div class="collapse-content" style="display:none">';
      html += '<pre style="max-height:400px;overflow:auto;font-size:11px">';
      html += this._esc(JSON.stringify(rawEvents, null, 2));
      html += '</pre></div></div>';
    }

    return html;
  }

  /* ── Section renderer ───────────────────────────────────────── */

  _renderSection(section, config) {
    var self = this;
    var controls = (section.controls && section.controls.length) ? section.controls : [];
    var isWide = !!section.full_width;
    if (!isWide) {
      for (var k = 0; k < controls.length; k++) {
        var t = controls[k].type;
        if (t === "theme" || t === "devices" || t === "table" || t === "media_player_picker" || t === "media_player") {
          isWide = true;
          break;
        }
      }
      if (section.qr_top_right || (section.instructions && section.instructions.length > 2)) {
        isWide = true;
      }
    }

    var sectionClass = "settings-section" + (isWide ? " settings-section-full" : "");
    var html = '<div class="' + sectionClass + '"';
    if (isWide) html += ' data-span="full"';
    html += '>';
    if (section.title) {
      html += '<h2 class="settings-section-title">' + this._esc(section.title) + "</h2>";
    }
    var cardClass = "settings-card";
    if (section.qr_top_right) cardClass += " settings-card-net";
    html += '<div class="' + cardClass + '">';

    var controls = (section.controls && section.controls.length) ? section.controls : [];
    var qr = null;
    if (section.qr_top_right) {
      for (var i = 0; i < controls.length; i++) {
        if (controls[i].type === "qr") { qr = controls[i]; break; }
      }
    }

    if (qr) {
      html += '<div class="settings-qr-fr">' + self._renderControl(qr, config) + "</div>";
    }

    if (section.instructions) {
      html += '<div class="settings-instructions">';
      var items = Array.isArray(section.instructions) ? section.instructions : [section.instructions];
      items.forEach(function (li) {
        html += "<p>" + self._esc(li) + "</p>";
      });
      html += "</div>";
    }

    controls.forEach(function (ctrl) {
      if (qr && ctrl === qr) return;
      html += self._renderControl(ctrl, config);
    });

    html += "</div>";
    html += "</div>";
    return html;
  }

  /* ── Control renderer ───────────────────────────────────────── */

  _renderControl(ctrl, config) {
    switch (ctrl.type) {
      case "toggle":
        return this._renderToggle(ctrl, config);
      case "text":
        return this._renderText(ctrl, config);
      case "password":
        return this._renderPassword(ctrl, config);
      case "select":
        return this._renderSelect(ctrl, config);
      case "slider":
        return this._renderSlider(ctrl, config);
      case "number":
        return this._renderNumber(ctrl, config);
      case "button":
        return this._renderButton(ctrl, config);
      case "info":
        return this._renderInfo(ctrl, config);
      case "qr":
        return this._renderQr(ctrl, config);
      case "devices":
        return this._renderDevices(ctrl, config);
      case "cert_download":
        return this._renderCertDownload(ctrl, config);
      case "apk_download":
        return this._renderApkDownload(ctrl, config);
      case "folder_picker":
        return this._renderFolderPicker(ctrl, config);
      case "file_picker":
        return this._renderFilePicker(ctrl, config);
      case "media_player_picker":
      case "media_player":
        return this._renderMediaPlayerPicker(ctrl, config);
      case "theme":
        return this._renderTheme(ctrl, config);
      default:
        return '<div class="settings-control settings-control-unknown">Unknown: ' + this._esc(ctrl.type) + "</div>";
    }
  }

  /* ── Toggle ─────────────────────────────────────────────────── */

  _renderToggle(ctrl, config) {
    var val = config[ctrl.key];
    var on = val ? "on" : "";
    var html = '<div class="settings-toggle-row"';
    if (ctrl.description) html += ' title="' + this._esc(ctrl.description) + '"';
    html += ">";
    html += '<span class="settings-toggle-label">' + this._esc(ctrl.label) + "</span>";
    html += '<div class="settings-toggle ' + on + '" data-key="' + this._esc(ctrl.key) + '">';
    html += '<div class="settings-toggle-thumb"></div>';
    html += "</div>";
    html += "</div>";
    return html;
  }

  /* ── Text input ─────────────────────────────────────────────── */

  _renderText(ctrl, config) {
    var val = config[ctrl.key] || "";
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<input type="text" class="settings-input" data-key="' + this._esc(ctrl.key) + '"';
    html += ' value="' + this._esc(val) + '"';
    if (ctrl.placeholder) html += ' placeholder="' + this._esc(ctrl.placeholder) + '"';
    html += ">";
    html += "</div>";
    return html;
  }

  /* ── Panel password (set / change) ──────────────────────────── */

  _renderPassword(ctrl, config) {
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<div class="settings-password-row" data-pw-key="' + this._esc(ctrl.key || "") + '">';
    html += '<button type="button" class="settings-btn settings-pw-btn">Loading…</button>';
    html += '<span class="settings-pw-status settings-hint"></span>';
    html += "</div>";
    html += "</div>";
    return html;
  }

  _renderCertDownload(ctrl, config) {
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<div class="settings-password-row">';
    html += '<a href="/api/cert/download" target="_self" class="settings-btn" style="text-decoration:none; display:inline-flex; align-items:center; gap:6px;">';
    html += '<span class="material-icons-outlined" style="font-size:18px;">security</span> Download SSL Certificate';
    html += '</a>';
    if (ctrl.description) {
      html += '<span class="settings-hint">' + this._esc(ctrl.description) + '</span>';
    }
    html += '</div>';
    html += '</div>';
    return html;
  }

  _renderApkDownload(ctrl, config) {
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<div class="settings-password-row">';
    html += '<a href="/Iris.apk" download="Iris.apk" target="_self" class="settings-btn" style="text-decoration:none; display:inline-flex; align-items:center; gap:6px;">';
    html += '<span class="material-icons-outlined" style="font-size:18px;">android</span> Download Iris.apk';
    html += '</a>';
    if (ctrl.description) {
      html += '<span class="settings-hint">' + this._esc(ctrl.description) + '</span>';
    }
    html += '</div>';
    html += '</div>';
    return html;
  }

  /* ── Select dropdown ────────────────────────────────────────── */

  _renderSelect(ctrl, config) {
    var val;
    if (ctrl.value_from) {
      val = config[ctrl.value_from];
    } else {
      val = config[ctrl.key];
    }
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<select class="settings-select" data-key="' + this._esc(ctrl.key) + '"';
    if (ctrl.value_from) html += ' data-value-from="' + this._esc(ctrl.value_from) + '"';
    html += ">";
    if (ctrl.options) {
      var self = this;
      ctrl.options.forEach(function (opt) {
        var sel = opt.value === val ? " selected" : "";
        html += '<option value="' + self._esc(opt.value) + '"' + sel + ">";
        html += self._esc(opt.label);
        html += "</option>";
      });
    }
    html += "</select>";
    html += "</div>";
    return html;
  }

  /* ── Slider ─────────────────────────────────────────────────── */

  _renderSlider(ctrl, config) {
    var val = config[ctrl.key];
    if (val === undefined || val === null) val = ctrl.min || 0;
    var unit = ctrl.unit || "";
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">';
      html += this._esc(ctrl.label);
      html += ' <span class="settings-slider-value" data-display-for="' + this._esc(ctrl.key) + '">' + this._esc(String(val)) + unit + "</span>";
      html += "</label>";
    }
    html += '<input type="range" class="pdev-range" data-key="' + this._esc(ctrl.key) + '"';
    html += ' min="' + (ctrl.min !== undefined ? ctrl.min : 0) + '"';
    html += ' max="' + (ctrl.max !== undefined ? ctrl.max : 100) + '"';
    if (ctrl.step !== undefined) html += ' step="' + ctrl.step + '"';
    html += ' value="' + this._esc(String(val)) + '"';
    html += ">";
    html += "</div>";
    return html;
  }

  _paintSliderFill(sliderEl) {
    var min = parseFloat(sliderEl.min) || 0;
    var max = parseFloat(sliderEl.max) || 100;
    var val = parseFloat(sliderEl.value) || 0;
    var pct = max > min ? ((val - min) / (max - min)) * 100 : 0;
    sliderEl.style.setProperty("--fill", pct.toFixed(1) + "%");
  }

  /* ── Number input ───────────────────────────────────────────── */

  _renderNumber(ctrl, config) {
    var val = config[ctrl.key];
    if (val === undefined || val === null) val = "";
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<div class="settings-number-wrap">';
    html += '<input type="number" class="settings-input settings-number-input" data-key="' + this._esc(ctrl.key) + '"';
    html += ' value="' + this._esc(String(val)) + '"';
    if (ctrl.min !== undefined) html += ' min="' + ctrl.min + '"';
    if (ctrl.max !== undefined) html += ' max="' + ctrl.max + '"';
    if (ctrl.step !== undefined) html += ' step="' + ctrl.step + '"';
    html += ">";
    if (ctrl.unit) html += '<span class="settings-unit">' + this._esc(ctrl.unit) + "</span>";
    html += "</div>";
    html += "</div>";
    return html;
  }

  /* ── Button ─────────────────────────────────────────────────── */

  _renderButton(ctrl) {
    var html = '<div class="settings-control">';
    html += '<button class="settings-btn" data-action="' + this._esc(ctrl.action || "") + '"';
    if (ctrl.target) html += ' data-target="' + this._esc(ctrl.target) + '"';
    html += ">";
    if (ctrl.icon) html += '<span class="material-icons-outlined">' + this._esc(ctrl.icon) + "</span> ";
    html += this._esc(ctrl.label || "Button");
    html += "</button>";
    html += "</div>";
    return html;
  }

  /* ── Info display ───────────────────────────────────────────── */

  _renderInfo(ctrl, config) {
    var val = ctrl.value;
    if (ctrl.key && config[ctrl.key] !== undefined) val = config[ctrl.key];
    var html = '<div class="settings-info-row">';
    if (ctrl.label) {
      html += '<span class="settings-info-label">' + this._esc(ctrl.label) + "</span>";
    }
    html += '<span class="settings-info-value">' + this._esc(String(val || "")) + "</span>";
    html += "</div>";
    return html;
  }

  /* ── QR code ────────────────────────────────────────────────── */

  _renderQr(ctrl, config) {
    var url = ctrl.key ? config[ctrl.key] : (ctrl.value || "");
    var html = '<div class="settings-control settings-qr-wrap">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<img class="settings-qr" data-qr-key="' + this._esc(ctrl.key || "") + '" alt="QR code" hidden>';
    html += '<span class="settings-qr-url">' + this._esc(url || "") + "</span>";
    html += "</div>";
    return html;
  }

  /* ── Paired devices list ────────────────────────────────────── */

  _renderDevices(ctrl, config) {
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    if (ctrl.description) {
      html += '<div class="settings-hint">' + this._esc(ctrl.description) + "</div>";
    }
    html += '<div class="settings-devices" data-devices>';
    html += '<div class="settings-devices-empty">Loading…</div>';
    html += "</div>";
    html += '<button class="settings-btn settings-devices-refresh">';
    html += '<span class="material-icons-outlined">refresh</span> Refresh</button>';
    html += "</div>";
    return html;
  }

  /* ── Folder picker ──────────────────────────────────────────── */

  _renderFolderPicker(ctrl, config) {    var val = config[ctrl.key] || "";
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<div class="settings-picker-wrap">';
    html += '<input type="text" class="settings-input" data-key="' + this._esc(ctrl.key) + '"';
    html += ' value="' + this._esc(val) + '"';
    html += ' placeholder="Browse for folder...">';
    html += '<button class="settings-picker-btn" data-action="browse_folder" data-target="' + this._esc(ctrl.key) + '">';
    html += '<span class="material-icons-outlined">folder_open</span>';
    html += "</button>";
    html += "</div>";
    html += "</div>";
    return html;
  }

  /* ── File picker ────────────────────────────────────────────── */

  _renderFilePicker(ctrl, config) {
    var val = config[ctrl.key] || "";
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<div class="settings-picker-wrap">';
    html += '<input type="text" class="settings-input" data-key="' + this._esc(ctrl.key) + '"';
    html += ' value="' + this._esc(val) + '"';
    html += ' placeholder="Browse for file...">';
    html += '<button class="settings-picker-btn" data-action="browse_file" data-target="' + this._esc(ctrl.key) + '">';
    html += '<span class="material-icons-outlined">folder_open</span>';
    html += "</button>";
    html += "</div>";
    html += "</div>";
    return html;
  }

  /* ── Visual Theme Control ───────────────────────────────────── */

  _renderTheme(ctrl, config) {
    var theme = config.theme || { mode: "iris", accent: "#B23AF6", neon: "#79E8FC" };
    var mode = theme.mode || "iris";
    var accent = theme.accent || "#B23AF6";
    var neon = theme.neon || "#79E8FC";

    var html = '<div class="settings-control theme-engine-control">';
    html += '<label class="settings-label" style="font-weight:700; margin-bottom:8px; display:block;">Visual Theme</label>';
    
    html += '<div class="theme-presets-grid">';
    
    // 1. Iris preset
    html += '<div class="theme-preset-card' + (mode === 'iris' ? ' active' : '') + '" data-theme-mode="iris">';
    html += '<div class="theme-preset-swatch" style="background: linear-gradient(135deg, #B23AF6 0%, #79E8FC 100%);"></div>';
    html += '<div class="theme-preset-info">';
    html += '<span class="theme-preset-title">Iris</span>';
    html += '<span class="theme-preset-desc">Cyberpunk Neon Gradient</span>';
    html += '</div>';
    html += '</div>';

    // 2. Monochrome preset
    html += '<div class="theme-preset-card' + (mode === 'monochrome' ? ' active' : '') + '" data-theme-mode="monochrome">';
    html += '<div class="theme-preset-swatch" style="background: linear-gradient(135deg, #444444 0%, #FFFFFF 100%);"></div>';
    html += '<div class="theme-preset-info">';
    html += '<span class="theme-preset-title">Monochrome</span>';
    html += '<span class="theme-preset-desc">Stealth High-Contrast</span>';
    html += '</div>';
    html += '</div>';

    // 3. Custom preset
    html += '<div class="theme-preset-card' + (mode === 'custom' ? ' active' : '') + '" data-theme-mode="custom">';
    html += '<div class="theme-preset-swatch" style="background: linear-gradient(135deg, ' + this._esc(accent) + ' 0%, ' + this._esc(neon) + ' 100%);" id="theme-custom-swatch"></div>';
    html += '<div class="theme-preset-info">';
    html += '<span class="theme-preset-title">Custom</span>';
    html += '<span class="theme-preset-desc">2-Colour Gradient</span>';
    html += '</div>';
    html += '</div>';

    html += '</div>';

    // Custom Color Pickers
    html += '<div class="theme-custom-pickers" id="theme-custom-pickers"' + (mode === 'custom' ? '' : ' style="display:none;"') + '>';
    html += '<div class="theme-color-input-row">';
    
    html += '<div class="theme-color-field">';
    html += '<label class="settings-label" style="font-size:12px; margin-bottom:4px;">Color 1: Accent</label>';
    html += '<div class="theme-color-picker-wrap">';
    html += '<input type="color" class="theme-color-native" id="theme-accent-color" value="' + this._esc(accent) + '">';
    html += '<input type="text" class="settings-input theme-color-hex" id="theme-accent-hex" value="' + this._esc(accent) + '" maxlength="7">';
    html += '</div>';
    html += '</div>';

    html += '<div class="theme-color-field">';
    html += '<label class="settings-label" style="font-size:12px; margin-bottom:4px;">Color 2: Neon</label>';
    html += '<div class="theme-color-picker-wrap">';
    html += '<input type="color" class="theme-color-native" id="theme-neon-color" value="' + this._esc(neon) + '">';
    html += '<input type="text" class="settings-input theme-color-hex" id="theme-neon-hex" value="' + this._esc(neon) + '" maxlength="7">';
    html += '</div>';
    html += '</div>';

    html += '</div>';
    html += '</div>';

    // Live Preview Showcase
    html += '<div class="theme-preview-box">';
    html += '<div class="theme-preview-header">';
    html += '<span class="theme-preview-title">Live Elements Preview</span>';
    html += '</div>';
    html += '<div class="theme-preview-grid">';
    
    html += '<div class="theme-preview-item">';
    html += '<span class="theme-preview-sub">Header Accent Line</span>';
    html += '<div class="theme-preview-header-line"></div>';
    html += '</div>';

    html += '<div class="theme-preview-item theme-preview-gauge-item">';
    html += '<span class="theme-preview-sub">Gauge Element</span>';
    html += '<div class="theme-preview-gauge-wrap">';
    html += '<div class="theme-preview-gring"><span class="pdev-gval" style="font-size:11px;font-weight:700;"><span class="pdev-gnum">75%</span></span></div>';
    html += '</div>';
    html += '</div>';

    html += '<div class="theme-preview-item">';
    html += '<span class="theme-preview-sub">Scroller Thumb</span>';
    html += '<div class="theme-preview-scroller-wrap">';
    html += '<div class="theme-preview-scroller-thumb"></div>';
    html += '</div>';
    html += '</div>';

    html += '<div class="theme-preview-item">';
    html += '<span class="theme-preview-sub">Active Button</span>';
    html += '<button type="button" class="settings-btn primary theme-preview-btn" style="padding:6px 12px; font-size:12px; width:100%;">Active State</button>';
    html += '</div>';

    html += '</div>';
    html += '</div>';

    // Apply Button
    html += '<div style="display:flex; justify-content:flex-end; gap:8px; margin-top:6px;">';
    html += '<button type="button" class="settings-btn primary" id="theme-apply-btn" style="min-width:140px; padding:10px 20px;">';
    html += '<span class="material-icons-outlined" style="font-size:18px;">palette</span> Apply Theme';
    html += '</button>';
    html += '</div>';

    html += '</div>';
    return html;
  }

  /* ── Media player picker ───────────────────────────────────────── */

  _renderMediaPlayerPicker(ctrl, config) {
    var val = config[ctrl.key] || "";
    var html = '<div class="settings-control media-player-picker-wrap" data-key="' + this._esc(ctrl.key) + '">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    if (ctrl.description) {
      html += '<p class="settings-description">' + this._esc(ctrl.description) + "</p>";
    }

    // Detected player chips row
    html += '<div class="media-player-chips" id="media-player-chips-list">';
    html += '<span class="media-player-detect-loading"><span class="material-icons-outlined" style="font-size:14px;">sync</span> Scanning installed players...</span>';
    html += "</div>";

    // Manual input & browse row with live icon preview
    html += '<div class="media-player-input-row">';
    html += '<div class="media-player-icon-preview" id="media-player-icon-preview"><span class="material-icons-outlined">music_note</span></div>';
    html += '<input type="text" class="settings-input media-player-input" data-key="' + this._esc(ctrl.key) + '"';
    html += ' value="' + this._esc(val) + '" placeholder="Path to player executable (e.g. Spotify.exe, vlc.exe)">';
    html += '<button type="button" class="settings-btn media-player-browse-btn" data-target="' + this._esc(ctrl.key) + '">Browse...</button>';
    html += '<button type="button" class="settings-btn settings-btn-secondary media-player-clear-btn" title="Clear player">Clear</button>';
    html += "</div>";

    html += "</div>";
    return html;
  }

  /* ── Bind events for a rendered page ────────────────────────── */

  bindBuiltInPage(container, pageId, config, saveCallback) {
    var self = this;
    var page = this.getPage(pageId);
    if (!page || !page.sections) return;

    var isApp = _isApp();
    page.sections.forEach(function (section) {
      if (section.app_only && !isApp) return;
      if (!section.controls) return;
      section.controls.forEach(function (ctrl) {
        self._bindControl(container, ctrl, config, saveCallback);
      });
    });
  }

  bindPluginPage(container, name, pluginCfg, savePluginCallback, outputsCallback, actionCallback) {
    var self = this;
    var p = pluginCfg || {};
    var settings = p.settings || [];
    var pcfg = p.config || {};
    var capabilities = p.capabilities || {};
    var hasCapabilities = Object.keys(capabilities).length > 0;

    if (hasCapabilities) {
      /* Bind settings controls */
      if (capabilities.configuration) {
        if (settings.length > 0) {
          settings.forEach(function (section) {
            if (!section.controls) return;
            section.controls.forEach(function (ctrl) {
              self._bindPluginControl(container, ctrl, name, pcfg, savePluginCallback);
            });
          });
        } else {
          self._bindFallbackControls(container, name, p, savePluginCallback);
        }
      }

      /* Bind outputs toggles */
      if (capabilities.outputs) {
        self._bindPluginOutputs(container, name, outputsCallback);
      }

      /* Bind button controls & export */
      if (capabilities.buttons) {
        self._bindPluginButtons(container, name, p);
      }

      /* Bind action buttons */
      if (capabilities.actions) {
        self._bindPluginActions(container, name, p.actions_def, actionCallback);
      }
    } else {
      /* Legacy: no capabilities declared */
      if (settings.length > 0) {
        settings.forEach(function (section) {
          if (!section.controls) return;
          section.controls.forEach(function (ctrl) {
            self._bindPluginControl(container, ctrl, name, pcfg, savePluginCallback);
          });
        });
      } else {
        self._bindFallbackControls(container, name, p, savePluginCallback);
      }
    }
  }

  _bindFallbackControls(container, name, p, savePluginCallback) {
    var self = this;
    var toggle = container.querySelector(".settings-toggle[data-key='_plugin_enabled_" + self._cssEsc(name) + "']");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var on = this.classList.toggle("on");
        savePluginCallback(name, "enabled", on);
      });
    }
    if ((p.type || "service") === "app") {
      var input = container.querySelector(".settings-input[data-key='_plugin_exe_" + self._cssEsc(name) + "']");
      if (input) {
        var exeTimer = null;
        input.addEventListener("input", function () {
          clearTimeout(exeTimer);
          exeTimer = setTimeout(function () {
            savePluginCallback(name, "exe_path", input.value.trim());
          }, 400);
        });
      }
      var browseBtn = container.querySelector(".settings-picker-btn[data-target='_plugin_exe_" + self._cssEsc(name) + "']");
      if (browseBtn) {
        browseBtn.addEventListener("click", function () {
          self._browseExe(name, input, savePluginCallback);
        });
      }
    }
  }

  _bindPluginOutputs(container, name, outputsCallback) {
    if (!outputsCallback) return;
    container.querySelectorAll(".settings-toggle[data-output]").forEach(function (el) {
      el.addEventListener("click", function () {
        var outputId = this.dataset.output;
        var on = this.classList.toggle("on");
        if (outputsCallback) outputsCallback(name, outputId, on);
      });
    });
  }

  _bindPluginButtons(container, name, p) {
    var self = this;
    var targetSelect = container.querySelector("#plugin-btn-target-profile");

    // Apply MDI icons in the preview tiles
    if (typeof applyMdiIcons === "function") {
      applyMdiIcons(container);
    }

    // Helper: collect configured buttons with any custom hotkey inputs
    function getButtonsPayload() {
      var btns = (p.buttons_def || []).map(function(b) {
        var copy = Object.assign({}, b);
        var input = container.querySelector('.plugin-btn-hotkey-input[data-btn-id="' + self._cssEsc(b.id) + '"]');
        if (input && input.value) {
          copy.hotkey = input.value.trim();
        }
        return copy;
      });
      return btns;
    }

    // Export full 12-button preset
    var exportAllBtn = container.querySelector(".btn-export-all");
    if (exportAllBtn) {
      exportAllBtn.addEventListener("click", async function() {
        var profileId = targetSelect ? targetSelect.value : "__default__";
        var btns = getButtonsPayload();
        exportAllBtn.disabled = true;
        var origText = exportAllBtn.innerHTML;
        exportAllBtn.innerHTML = '<span class="material-icons-outlined" style="font-size:16px;vertical-align:middle;margin-right:4px">hourglass_empty</span> Exporting...';

        try {
          var res = await apiFetch(self._apiBase + "/api/panel/export_buttons", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              plugin: name,
              profile_id: profileId,
              profile_name: p.display_name,
              profile_exe: p.exe_default || "",
              buttons: btns,
              replace_all: true
            })
          });
          var data = await res.json();
          if (data && data.ok) {
            exportAllBtn.innerHTML = '<span class="material-icons-outlined" style="font-size:16px;vertical-align:middle;margin-right:4px">check</span> Exported to ' + self._esc(data.target_profile || "Profile") + '!';
            if (typeof fetchPanel === "function") fetchPanel();
            if (typeof fetchConfig === "function") fetchConfig();
            setTimeout(function() {
              exportAllBtn.disabled = false;
              exportAllBtn.innerHTML = origText;
            }, 2000);
          } else {
            alert("Export failed: " + (data ? data.error : "Unknown error"));
            exportAllBtn.disabled = false;
            exportAllBtn.innerHTML = origText;
          }
        } catch (err) {
          alert("Export failed: " + err);
          exportAllBtn.disabled = false;
          exportAllBtn.innerHTML = origText;
        }
      });
    }

    // Export single button
    container.querySelectorAll(".btn-export-single").forEach(function(btn) {
      btn.addEventListener("click", async function() {
        var btnId = this.dataset.btnId;
        var profileId = targetSelect ? targetSelect.value : "__default__";
        var allBtns = getButtonsPayload();
        var targetBtn = allBtns.find(function(b) { return b.id === btnId; });
        if (!targetBtn) return;

        btn.disabled = true;
        var origText = btn.innerHTML;
        btn.innerHTML = '<span class="material-icons-outlined" style="font-size:14px;vertical-align:middle">hourglass_empty</span>';

        try {
          var res = await apiFetch(self._apiBase + "/api/panel/export_buttons", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              plugin: name,
              profile_id: profileId,
              profile_name: p.display_name,
              profile_exe: p.exe_default || "",
              buttons: [targetBtn],
              replace_all: false
            })
          });
          var data = await res.json();
          if (data && data.ok) {
            btn.innerHTML = '<span class="material-icons-outlined" style="font-size:14px;vertical-align:middle">check</span> Sent';
            if (typeof fetchPanel === "function") fetchPanel();
            if (typeof fetchConfig === "function") fetchConfig();
            setTimeout(function() {
              btn.disabled = false;
              btn.innerHTML = origText;
            }, 1500);
          } else {
            alert("Export failed: " + (data ? data.error : "Unknown error"));
            btn.disabled = false;
            btn.innerHTML = origText;
          }
        } catch (err) {
          alert("Export failed: " + err);
          btn.disabled = false;
          btn.innerHTML = origText;
        }
      });
    });
  }

  _bindPluginActions(container, name, actionDefs, actionCallback) {
    if (!actionCallback) return;
    var self = this;
    container.querySelectorAll(".plugin-action-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var actionId = this.dataset.actionId;
        var needsConfirm = this.dataset.confirm;
        if (needsConfirm && !confirm("Run " + actionId + "?")) return;
        if (actionCallback) actionCallback(name, actionId);
      });
    });
  }

  /* ── Plugin data display ────────────────────────────────────── */

  _renderPluginData(name, liveData, pluginStateData) {
    var ps = pluginStateData || {};
    var liveState = ps.state || {};
    var liveStatus = ps.status || {};
    var liveLayout = ps.layout;
    var hasLiveData = Object.keys(liveState).length > 0 || Object.keys(liveStatus).length > 0;
    var s, st;
    if (hasLiveData) {
      s = liveState;
      st = liveStatus;
    } else if (liveData && liveData.state) {
      s = liveData.state;
      st = liveData.status || {};
    } else if (liveData && typeof liveData === "object") {
      s = liveData;
      st = {};
    } else {
      s = {};
      st = {};
    }
    var layout = liveLayout || (liveData && liveData.layout);
    var hasAnyData = Object.keys(s).length > 0 || Object.keys(st).length > 0;

    if (!hasAnyData) {
      return '<div class="plugin-data-unavailable">Waiting for telemetry...</div>';
    }

    function withUnit(f, src, val) {
      if (typeof val === "number" && src[f.key + "_unit"]) {
        return String(val) + " " + src[f.key + "_unit"];
      }
      return val;
    }

    if (layout) {
      var self = this;
      return layout.map(function (g) {
        var rows = g.fields.map(function (f) {
          var src = f.source === "status" ? st : s;
          var val = withUnit(f, src, src[f.key]);
          if (typeof val === "boolean") {
            var d = f.display || "yes_no";
            if (d === "up_down") val = val ? "Up" : "Down";
            else if (d === "down_up") val = val ? "Down" : "Up";
            else if (d === "on_off") val = val ? "On" : "Off";
            else if (d === "deployed_retracted") val = val ? "Deployed" : "Retracted";
            else val = val ? "Yes" : "No";
          }
          return [f.label, val];
        });
        return self._pluginDataCard(g.title, rows);
      }).join("");
    }

    var stateRows = Object.entries(s)
      .filter(function (e) { return !/_unit$|_max$/.test(e[0]); })
      .map(function (e) {
        var val = e[1];
        if (typeof val === "number" && s[e[0] + "_unit"]) val = String(val) + " " + s[e[0] + "_unit"];
        return [e[0].replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); }), val];
      });
    var statusRows = Object.entries(st)
      .filter(function (e) { return !/_unit$|_max$/.test(e[0]); })
      .map(function (e) {
        return [e[0].replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); }),
          typeof e[1] === "boolean" ? (e[1] ? "Yes" : "No") : e[1]];
      });
    var html = this._pluginDataCard("State", stateRows);
    html += this._pluginDataCard("Status", statusRows);
    return html || '<div class="plugin-data-unavailable">No data available yet</div>';
  }

  /* ── Internal helpers ───────────────────────────────────────── */

  _bindControl(container, ctrl, config, saveCallback) {
    var self = this;

    switch (ctrl.type) {
      case "toggle":
        var toggles = container.querySelectorAll(".settings-toggle[data-key='" + self._cssEsc(ctrl.key) + "']");
        toggles.forEach(function (el) {
          el.addEventListener("click", function () {
            var on = this.classList.toggle("on");
            config[ctrl.key] = on;
            saveCallback({ [ctrl.key]: on });
          });
        });
        break;

      case "text":
        var textInput = container.querySelector(".settings-input[data-key='" + self._cssEsc(ctrl.key) + "']");
        if (textInput) {
          var debounce = ctrl.save_debounce_ms || 400;
          var timer = null;
          textInput.addEventListener("input", function () {
            clearTimeout(timer);
            var val = this.value.trim();
            timer = setTimeout(function () {
              config[ctrl.key] = val;
              saveCallback({ [ctrl.key]: val });
            }, debounce);
          });
        }
        break;

      case "password":
        self._bindPasswordControl(container, ctrl);
        break;

      case "select":
        var selectEl = container.querySelector(".settings-select[data-key='" + self._cssEsc(ctrl.key) + "']");
        if (selectEl) {
          selectEl.addEventListener("change", function () {
            var val = this.value;
            var patch = {};
            if (ctrl.options) {
              var opt = ctrl.options.find(function (o) { return o.value === val; });
              if (opt && opt.set) {
                Object.assign(patch, opt.set);
              }
            }
            if (!patch.hasOwnProperty(ctrl.key)) {
              patch[ctrl.key] = val;
            }
            Object.assign(config, patch);
            saveCallback(patch);
          });
        }
        break;

      case "slider":
        var sliderEl = container.querySelector(".pdev-range[data-key='" + self._cssEsc(ctrl.key) + "']");
        if (sliderEl) {
          var unit = ctrl.unit || "";
          self._paintSliderFill(sliderEl);
          sliderEl.addEventListener("input", function () {
            var val = this.value;
            var display = container.querySelector("[data-display-for='" + self._cssEsc(ctrl.key) + "']");
            if (display) display.textContent = val + unit;
            self._paintSliderFill(this);
            clearTimeout(self._saveTimers[ctrl.key]);
            self._saveTimers[ctrl.key] = setTimeout(function () {
              config[ctrl.key] = parseFloat(val);
              saveCallback({ [ctrl.key]: parseFloat(val) });
            }, 200);
          });
        }
        break;

      case "number":
        var numInput = container.querySelector(".settings-number-input[data-key='" + self._cssEsc(ctrl.key) + "']");
        if (numInput) {
          var numTimer = null;
          numInput.addEventListener("input", function () {
            clearTimeout(numTimer);
            numTimer = setTimeout(function () {
              var val = parseFloat(numInput.value);
              if (!isNaN(val)) {
                config[ctrl.key] = val;
                saveCallback({ [ctrl.key]: val });
              }
            }, 400);
          });
        }
        break;

      case "folder_picker":
      case "file_picker":
        var pickerInput = container.querySelector(".settings-input[data-key='" + self._cssEsc(ctrl.key) + "']");
        var pickerBtn = container.querySelector(".settings-picker-btn[data-target='" + self._cssEsc(ctrl.key) + "']");
        if (pickerInput) {
          var pickerTimer = null;
          pickerInput.addEventListener("input", function () {
            clearTimeout(pickerTimer);
            pickerTimer = setTimeout(function () {
              config[ctrl.key] = pickerInput.value.trim();
              saveCallback({ [ctrl.key]: pickerInput.value.trim() });
            }, 400);
          });
        }
        if (pickerBtn) {
          pickerBtn.addEventListener("click", function () {
            var browseType = ctrl.type === "folder_picker" ? "folder" : "exe";
            var apply = function (path) {
              if (path && pickerInput) {
                pickerInput.value = path;
                config[ctrl.key] = path;
                saveCallback({ [ctrl.key]: path });
              }
            };
            if (window.pywebview && window.pywebview.api && window.pywebview.api.browse_folder) {
              window.pywebview.api.browse_folder().then(apply).catch(function () {});
            } else {
              var token = typeof sessionTokenQuery === "function" ? sessionTokenQuery() : "";
              apiFetch((self._apiBase || "") + "/api/dialog/browse?type=" + browseType + token)
                .then(function (r) { return r.json(); })
                .then(function (d) {
                  if (d && d.ok) apply(d.path);
                })
                .catch(function () {});
            }
          });
        }
        break;

      case "theme":
        this._bindTheme(container, ctrl, config, saveCallback);
        break;

      case "media_player_picker":
      case "media_player":
        this._bindMediaPlayerPicker(container, ctrl, config, saveCallback);
        break;

      case "button":
        var buttons = container.querySelectorAll(
          ".settings-btn[data-action='" + ctrl.action + "']");
        buttons.forEach(function (el) {
          el.addEventListener("click", function () {
            if (ctrl.action === "navigate" || ctrl.action === "open_page") {
              var targetPage = ctrl.target || "library";
              if (typeof window.navigateToPage === "function") {
                window.navigateToPage(targetPage);
              } else {
                var navBtn = document.querySelector(".nav-item[data-page='" + targetPage + "']");
                if (navBtn) navBtn.click();
              }
              return;
            }
            if (ctrl.action === "copy_token") {
              apiFetch(self._apiBase + "/api/config")
                .then(function (res) { return res.ok ? res.json() : {}; })
                .then(function (data) {
                  var token = data.http_token || "";
                  if (token && navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(token).then(function () {
                      setTimeout(function () {
                        if (navigator.clipboard.readText) {
                          navigator.clipboard.readText().then(function (t) {
                            if (t === token) navigator.clipboard.writeText("");
                          }).catch(function () {});
                        }
                      }, 30000);
                    }).catch(function () {});
                  }
                })
                .catch(function () {});
              var old = el.textContent;
              el.textContent = "Copied!";
              setTimeout(function () { el.textContent = old; }, 1200);
            }
          });
        });
        break;

      case "qr":
        var imgs = container.querySelectorAll("img.settings-qr");
        imgs.forEach(function (el) {
          apiFetch(self._apiBase + "/api/network/qr")
            .then(function (res) {
              if (!res.ok) throw new Error("qr " + res.status);
              return res.blob();
            })
            .then(function (blob) {
              if (el._blobUrl) URL.revokeObjectURL(el._blobUrl);
              el._blobUrl = URL.createObjectURL(blob);
              el.src = el._blobUrl;
              el.hidden = false;
            })
            .catch(function () {});
        });
        break;

      case "devices":
        var devBox = container.querySelector("[data-devices]");
        var devRefresh = container.querySelector(".settings-devices-refresh");
        if (!devBox) break;

        function renderDeviceRows(devices) {
          if (!devices || !devices.length) {
            devBox.innerHTML =
              '<div class="settings-devices-empty">No devices have paired yet.</div>';
            return;
          }
          var html = "";
          devices.forEach(function (d) {
            html += '<div class="settings-device-row" data-device-id="' + self._esc(d.id) + '">';
            html += '<div class="settings-device-meta">';
            html += '<span class="settings-device-name">' + self._esc(d.name) + "</span>";
            if (d.ua) {
              html += '<span class="settings-device-ua">' + self._esc(d.ua) + "</span>";
            }
            if (d.last_seen) {
              try {
                html += '<span class="settings-device-seen">Last seen ' +
                  new Date(d.last_seen * 1000).toLocaleString() + "</span>";
              } catch (_) {}
            }
            html += "</div>";
            html += '<button class="settings-btn settings-btn-danger device-revoke" data-dev="' +
              self._esc(d.id) + '">Revoke</button>';
            html += "</div>";
          });
          devBox.innerHTML = html;
          devBox.querySelectorAll(".device-revoke").forEach(function (rev) {
            rev.addEventListener("click", function () {
              apiFetch(self._apiBase + "/api/devices/revoke", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id: rev.dataset.dev }),
              })
                .then(function (res) { return res.json(); })
                .then(function (data) { if (data && data.ok) loadDeviceRows(); })
                .catch(function () {});
            });
          });
        }

        function loadDeviceRows() {
          devBox.innerHTML = '<div class="settings-devices-empty">Loading…</div>';
          apiFetch(self._apiBase + "/api/devices")
            .then(function (res) { return res.ok ? res.json() : { ok: false, devices: [] }; })
            .then(function (data) { renderDeviceRows((data && data.devices) || []); })
            .catch(function () {
              devBox.innerHTML =
                '<div class="settings-devices-empty">Could not load devices.</div>';
            });
        }

        loadDeviceRows();
        if (devRefresh) devRefresh.onclick = loadDeviceRows;
        break;
    }
  }

  /* ── Panel password control (set / change dialog) ───────────── */

  _bindPasswordControl(container, ctrl) {
    var self = this;
    var btn = container.querySelector(".settings-pw-btn");
    var status = container.querySelector(".settings-pw-status");
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = "Loading…";
    apiFetch(self._apiBase + "/api/panel/password/status")
      .then(function (res) { return res.ok ? res.json() : { ok: false }; })
      .then(function (info) {
        if (!info || !info.ok) {
          btn.textContent = "Unavailable";
          if (status) status.textContent = "Only available on this PC.";
          return;
        }
        if (!info.available) {
          btn.textContent = "Unavailable";
          if (status) status.textContent = "Password hashing is not installed on this PC.";
          return;
        }
        btn.textContent = info.set ? "Change password" : "Set password";
        if (status) status.textContent = info.set
          ? "A pairing password is set — phones must enter it."
          : "No pairing password set yet — phones cannot connect.";
        btn.disabled = false;
        btn.addEventListener("click", function () {
          self._openPasswordDialog(ctrl, info, btn, status);
        });
      })
      .catch(function () {
        btn.textContent = "Unavailable";
        if (status) status.textContent = "Could not reach the panel.";
      });
  }

  _openPasswordDialog(ctrl, info, btn, status) {
    var self = this;
    var set = !!info.set;
    var minLen = (info && info.min_length) || 4;
    var html =
      '<div class="panel-modal-backdrop" id="pw-modal">' +
        '<div class="panel-modal">' +
          '<h3>' + (set ? "Change panel password" : "Set panel password") + '</h3>' +
          (set ? '<div class="settings-control"><label class="settings-label">Current password</label>' +
            '<input type="password" class="settings-input" id="pw-cur" autocomplete="current-password"></div>' : "") +
          '<div class="settings-control"><label class="settings-label">New password</label>' +
            '<input type="password" class="settings-input" id="pw-new" autocomplete="new-password"></div>' +
          '<div class="settings-control"><label class="settings-label">Confirm new password</label>' +
            '<input type="password" class="settings-input" id="pw-conf" autocomplete="new-password"></div>' +
          '<p class="settings-hint" id="pw-msg" style="display:none"></p>' +
          '<div class="panel-modal-actions">' +
            '<button type="button" class="settings-btn" id="pw-cancel">Cancel</button>' +
            '<button type="button" class="settings-btn settings-btn-primary" id="pw-save">Save</button>' +
          '</div>' +
        '</div>' +
      '</div>';
    var wrap = document.createElement("div");
    wrap.innerHTML = html;
    document.body.appendChild(wrap);

    var cur = wrap.querySelector("#pw-cur");
    var nw = wrap.querySelector("#pw-new");
    var cf = wrap.querySelector("#pw-conf");
    var msg = wrap.querySelector("#pw-msg");
    var save = wrap.querySelector("#pw-save");
    var cancel = wrap.querySelector("#pw-cancel");

    function show(m) {
      msg.textContent = m;
      msg.style.display = m ? "block" : "none";
      msg.style.color = "#ff6b6b";
    }
    function close() {
      if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    }
    function busy(b) {
      save.disabled = b;
      save.textContent = b ? "Saving…" : "Save";
    }
    function submit() {
      var current = cur ? cur.value : "";
      var pw = nw.value;
      if (pw.length < minLen) {
        show("Password must be at least " + minLen + " characters.");
        return;
      }
      if (pw !== cf.value) {
        show("New passwords do not match.");
        return;
      }
      if (set && !current) {
        show("Enter your current password.");
        return;
      }
      busy(true);
      show("");
      var body = { password: pw };
      if (set) body.current = current;
      apiFetch(self._apiBase + "/api/panel/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          if (data && data.ok) {
            close();
            if (btn) {
              btn.textContent = "Change password";
              btn.disabled = false;
            }
            if (status) status.textContent = "A pairing password is set — phones must enter it.";
            return;
          }
          busy(false);
          var m = "Could not save the password.";
          if (data && data.error === "incorrect current password") {
            m = "Current password is incorrect.";
          } else if (data && data.error === "same password") {
            m = "New password must be different from the current one.";
          } else if (data && data.error === "too_short") {
            m = "Password must be at least " + ((data.min_length) || minLen) + " characters.";
          } else if (data && data.error === "password_unavailable") {
            m = "Password hashing is not installed on this PC.";
          }
          show(m);
        })
        .catch(function () {
          busy(false);
          show("Could not reach the panel.");
        });
    }

    save.addEventListener("click", submit);
    cancel.addEventListener("click", close);
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) close();
    });
    [nw, cf].forEach(function (el) {
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter") submit();
      });
    });
    if (cur) cur.focus();
    else nw.focus();
  }

  /* ── Bind a single plugin control ───────────────────────────── */

  _bindPluginControl(container, ctrl, pluginName, pluginConfig, savePluginCallback) {
    var self = this;

    switch (ctrl.type) {
      case "toggle":
        var toggles = container.querySelectorAll(".settings-toggle[data-key='" + self._cssEsc(ctrl.key) + "']");
        toggles.forEach(function (el) {
          el.addEventListener("click", function () {
            var on = this.classList.toggle("on");
            pluginConfig[ctrl.key] = on;
            savePluginCallback(pluginName, ctrl.key, on);
          });
        });
        break;

      case "text":
        var textInput = container.querySelector(".settings-input[data-key='" + self._cssEsc(ctrl.key) + "']");
        if (textInput) {
          var debounce = ctrl.save_debounce_ms || 400;
          var timer = null;
          textInput.addEventListener("input", function () {
            clearTimeout(timer);
            var val = this.value.trim();
            timer = setTimeout(function () {
              pluginConfig[ctrl.key] = val;
              savePluginCallback(pluginName, ctrl.key, val);
            }, debounce);
          });
        }
        break;

      case "password":
        // Panel password lives on the Settings page only; plugin password
        // controls (none in practice) render the same button but do nothing.
        break;

      case "select":
        var selectEl = container.querySelector(".settings-select[data-key='" + self._cssEsc(ctrl.key) + "']");
        if (selectEl) {
          selectEl.addEventListener("change", function () {
            var val = this.value;
            pluginConfig[ctrl.key] = val;
            savePluginCallback(pluginName, ctrl.key, val);
          });
        }
        break;

      case "slider":
        var sliderEl = container.querySelector(".pdev-range[data-key='" + self._cssEsc(ctrl.key) + "']");
        if (sliderEl) {
          var unit = ctrl.unit || "";
          self._paintSliderFill(sliderEl);
          sliderEl.addEventListener("input", function () {
            var val = this.value;
            var display = container.querySelector("[data-display-for='" + self._cssEsc(ctrl.key) + "']");
            if (display) display.textContent = val + unit;
            self._paintSliderFill(this);
            clearTimeout(self._saveTimers[ctrl.key]);
            self._saveTimers[ctrl.key] = setTimeout(function () {
              pluginConfig[ctrl.key] = parseFloat(val);
              savePluginCallback(pluginName, ctrl.key, parseFloat(val));
            }, 200);
          });
        }
        break;

      case "number":
        var numInput = container.querySelector(".settings-number-input[data-key='" + self._cssEsc(ctrl.key) + "']");
        if (numInput) {
          var numTimer = null;
          numInput.addEventListener("input", function () {
            clearTimeout(numTimer);
            numTimer = setTimeout(function () {
              var val = parseFloat(numInput.value);
              if (!isNaN(val)) {
                pluginConfig[ctrl.key] = val;
                savePluginCallback(pluginName, ctrl.key, val);
              }
            }, 400);
          });
        }
        break;

      case "folder_picker":
      case "file_picker":
        var pickerInput = container.querySelector(".settings-input[data-key='" + self._cssEsc(ctrl.key) + "']");
        var pickerBtn = container.querySelector(".settings-picker-btn[data-target='" + self._cssEsc(ctrl.key) + "']");
        if (pickerInput) {
          var pickerTimer = null;
          pickerInput.addEventListener("input", function () {
            clearTimeout(pickerTimer);
            pickerTimer = setTimeout(function () {
              pluginConfig[ctrl.key] = pickerInput.value.trim();
              savePluginCallback(pluginName, ctrl.key, pickerInput.value.trim());
            }, 400);
          });
        }
        if (pickerBtn) {
          pickerBtn.addEventListener("click", function () {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.browse_exe) {
              window.pywebview.api.browse_exe().then(function (path) {
                if (path && pickerInput) {
                  pickerInput.value = path;
                  pluginConfig[ctrl.key] = path;
                  savePluginCallback(pluginName, ctrl.key, path);
                }
              }).catch(function () {});
            }
          });
        }
        break;
    }
  }

  _bindMediaPlayerPicker(container, ctrl, config, saveCallback) {
    var self = this;
    var wrap = container.querySelector('.media-player-picker-wrap[data-key="' + self._cssEsc(ctrl.key) + '"]');
    if (!wrap) return;

    var chipsList = wrap.querySelector("#media-player-chips-list");
    var input = wrap.querySelector(".media-player-input");
    var iconPreview = wrap.querySelector("#media-player-icon-preview");
    var browseBtn = wrap.querySelector(".media-player-browse-btn");
    var clearBtn = wrap.querySelector(".media-player-clear-btn");

    function updateIcon(path) {
      if (!iconPreview) return;
      if (!path) {
        iconPreview.innerHTML = '<span class="material-icons-outlined">music_note</span>';
        return;
      }
      var brandSvg = getMediaPlayerBrandIcon(path);
      if (brandSvg) {
        iconPreview.innerHTML = brandSvg;
        return;
      }
      var token = typeof sessionTokenQuery === "function" ? sessionTokenQuery() : "";
      var iconUrl = (self._apiBase || "") + "/api/panel/icon?path=" + encodeURIComponent(path) + token;
      
      var img = document.createElement("img");
      img.src = iconUrl;
      img.alt = "App Icon";
      img.onload = function () {
        iconPreview.innerHTML = "";
        iconPreview.appendChild(img);
      };
      img.onerror = function () {
        iconPreview.innerHTML = '<span class="material-icons-outlined">play_circle</span>';
      };
    }

    function setPath(p, save) {
      if (input) input.value = p || "";
      config[ctrl.key] = p || "";
      updateIcon(p);
      highlightActiveChip(p);
      if (save && saveCallback) {
        saveCallback({ [ctrl.key]: p || "" });
      }
    }

    function highlightActiveChip(activePath) {
      if (!chipsList) return;
      var norm = (activePath || "").toLowerCase().replace(/\\/g, "/");
      chipsList.querySelectorAll(".media-player-chip").forEach(function (chip) {
        var chipPath = (chip.dataset.path || "").toLowerCase().replace(/\\/g, "/");
        if (norm && chipPath === norm) {
          chip.classList.add("active");
        } else {
          chip.classList.remove("active");
        }
      });
    }

    // Initial icon preview
    updateIcon(input ? input.value : "");

    // Fetch detected players
    apiFetch((self._apiBase || "") + "/api/media/players")
      .then(function (res) { return res.ok ? res.json() : { players: [] }; })
      .then(function (data) {
        if (!chipsList) return;
        var players = data.players || [];
        if (!players.length) {
          chipsList.innerHTML = '<span class="media-player-detect-none">No standard media players detected</span>';
          return;
        }
        var html = '<span class="media-player-chips-label">Detected:</span>';
        players.forEach(function (p) {
          var brandSvg = getMediaPlayerBrandIcon(p.name) || getMediaPlayerBrandIcon(p.path);
          html += '<button type="button" class="media-player-chip" data-path="' + self._esc(p.path) + '" data-name="' + self._esc(p.name) + '" title="' + self._esc(p.path) + '">';
          if (brandSvg) {
            html += '<span class="media-player-chip-icon-svg">' + brandSvg + '</span>';
          } else {
            var token = typeof sessionTokenQuery === "function" ? sessionTokenQuery() : "";
            var iconUrl = (self._apiBase || "") + "/api/panel/icon?path=" + encodeURIComponent(p.path) + token;
            html += '<img class="media-player-chip-icon" src="' + iconUrl + '" alt="">';
          }
          html += '<span>' + self._esc(p.name) + '</span>';
          html += '</button>';
        });
        chipsList.innerHTML = html;
        chipsList.querySelectorAll("img.media-player-chip-icon").forEach(function (img) {
          img.addEventListener("error", function () { this.style.display = "none"; });
        });

        // Wire chip clicks
        chipsList.querySelectorAll(".media-player-chip").forEach(function (chip) {
          chip.addEventListener("click", function () {
            var path = this.dataset.path || "";
            setPath(path, true);
          });
        });
        highlightActiveChip(input ? input.value : "");
      })
      .catch(function () {
        if (chipsList) chipsList.innerHTML = '<span class="media-player-detect-none">Could not scan players</span>';
      });

    // Input debounce
    if (input) {
      var timer = null;
      input.addEventListener("input", function () {
        clearTimeout(timer);
        var val = input.value.trim();
        updateIcon(val);
        highlightActiveChip(val);
        timer = setTimeout(function () {
          config[ctrl.key] = val;
          if (saveCallback) saveCallback({ [ctrl.key]: val });
        }, 400);
      });
    }

    // Browse button
    if (browseBtn) {
      browseBtn.addEventListener("click", function () {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.browse_exe) {
          window.pywebview.api.browse_exe().then(function (path) {
            if (path) setPath(path, true);
          }).catch(function () {});
        } else {
          var token = typeof sessionTokenQuery === "function" ? sessionTokenQuery() : "";
          apiFetch((self._apiBase || "") + "/api/dialog/browse?type=exe" + token)
            .then(function (r) { return r.json(); })
            .then(function (d) {
              if (d && d.ok && d.path) setPath(d.path, true);
            })
            .catch(function () {});
        }
      });
    }

    // Clear button
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        setPath("", true);
      });
    }
  }

  async _browseExe(name, inputEl, savePluginCallback) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.browse_exe) {
      try {
        var path = await window.pywebview.api.browse_exe();
        if (path && inputEl) {
          inputEl.value = path;
          savePluginCallback(name, "exe_path", path);
        }
      } catch (_) {}
    }
  }

  _detailRow(label, value, color) {
    var html = '<div class="plugin-detail-row">';
    html += '<span class="plugin-detail-label">' + this._esc(label) + "</span>";
    html += '<span class="plugin-detail-value"';
    if (color) html += ' style="color:' + color + '"';
    html += ">" + this._esc(value) + "</span>";
    html += "</div>";
    return html;
  }

  _renderRequirements(reqs) {
    var self = this;
    var items = reqs.map(function (r) {
      var icon = r.met ? "check_circle" : "cancel";
      var color = r.met ? "var(--neon-grn)" : "var(--neon-red)";
      return '<div class="plugin-req-row">' +
        '<span class="material-icons-outlined" style="color:' + color + ";font-size:18px\">" + icon + "</span>" +
        '<span class="plugin-req-name">' + self._esc(r.name) + "</span>" +
        '<span class="plugin-req-desc">' + self._esc(r.description) + "</span>" +
        "</div>";
    }).join("");
    return '<div class="plugin-reqs">' + items + "</div>";
  }

  _pluginDataCard(title, rows) {
    var self = this;
    var filtered = rows.filter(function (r) { return r[1] !== undefined && r[1] !== null && r[1] !== ""; });
    if (!filtered.length) return "";
    var lines = filtered.map(function (r) {
      return '<div class="plugin-data-row"><span class="plugin-data-label">' + self._esc(r[0]) +
        '</span><span class="plugin-data-value">' + self._esc(String(r[1])) + "</span></div>";
    }).join("");
    return '<div class="plugin-data-card"><div class="plugin-data-heading">' + this._esc(title) + "</div>" + lines + "</div>";
  }

  _statusColor(code) {
    var colors = {
      running: "var(--neon-grn)",
      connected: "var(--neon-grn)",
      waiting: "var(--fg-dim)",
      disconnected: "var(--neon-red)",
      inactive: "var(--fg-dim)",
      missing: "var(--neon-red)",
      disabled: "var(--neon-red)",
      unknown: "var(--fg-dim)",
    };
    return colors[code] || "var(--fg-dim)";
  }

  _bindTheme(container, ctrl, config, saveCallback) {
    var self = this;
    var theme = config.theme || { mode: "iris", accent: "#B23AF6", neon: "#79E8FC" };
    var currentMode = theme.mode || "iris";
    var currentAccent = theme.accent || "#B23AF6";
    var currentNeon = theme.neon || "#79E8FC";

    var presetCards = container.querySelectorAll(".theme-preset-card");
    var customPickers = container.querySelector("#theme-custom-pickers");
    var customSwatch = container.querySelector("#theme-custom-swatch");
    var accentNative = container.querySelector("#theme-accent-color");
    var accentHex = container.querySelector("#theme-accent-hex");
    var neonNative = container.querySelector("#theme-neon-color");
    var neonHex = container.querySelector("#theme-neon-hex");

    function updatePreviewAndTheme() {
      var themeObj = {
        mode: currentMode,
        accent: currentAccent,
        neon: currentNeon
      };
      config.theme = themeObj;
      if (typeof window.applyTheme === "function") {
        window.applyTheme(themeObj);
      }
      if (customSwatch) {
        customSwatch.style.background = "linear-gradient(135deg, " + currentAccent + " 0%, " + currentNeon + " 100%)";
      }
      var prevGrad = container.querySelector("#theme-preview-grad");
      if (prevGrad) {
        var stops = prevGrad.querySelectorAll("stop");
        if (stops.length >= 2) {
          var c1 = currentMode === "iris" ? "#B23AF6" : (currentMode === "monochrome" ? "#666666" : currentAccent);
          var c2 = currentMode === "iris" ? "#79E8FC" : (currentMode === "monochrome" ? "#FFFFFF" : currentNeon);
          stops[0].setAttribute("stop-color", c1);
          stops[1].setAttribute("stop-color", c2);
        }
      }
      var saveTimer = self._saveTimers["theme"];
      clearTimeout(saveTimer);
      self._saveTimers["theme"] = setTimeout(function () {
        saveCallback({ theme: themeObj });
      }, 300);
    }

    presetCards.forEach(function (card) {
      card.addEventListener("click", function () {
        var mode = this.dataset.themeMode;
        currentMode = mode;
        presetCards.forEach(function (c) { c.classList.remove("active"); });
        card.classList.add("active");

        if (mode === "custom") {
          if (customPickers) customPickers.style.display = "block";
        } else {
          if (customPickers) customPickers.style.display = "none";
        }
        updatePreviewAndTheme();
      });
    });

    if (accentNative && accentHex) {
      accentNative.addEventListener("input", function () {
        currentAccent = accentNative.value;
        accentHex.value = currentAccent;
        updatePreviewAndTheme();
      });
      accentHex.addEventListener("input", function () {
        var val = accentHex.value.trim();
        if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
          currentAccent = val;
          accentNative.value = val;
          updatePreviewAndTheme();
        }
      });
    }

    if (neonNative && neonHex) {
      neonNative.addEventListener("input", function () {
        currentNeon = neonNative.value;
        neonHex.value = currentNeon;
        updatePreviewAndTheme();
      });
      neonHex.addEventListener("input", function () {
        var val = neonHex.value.trim();
        if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
          currentNeon = val;
          neonNative.value = val;
          updatePreviewAndTheme();
        }
      });
    }

    var applyBtn = container.querySelector("#theme-apply-btn");
    if (applyBtn) {
      applyBtn.addEventListener("click", function () {
        updatePreviewAndTheme();
        apiFetch(self._apiBase + "/api/portal/reload", { method: "POST" }).catch(function () {});
        var origHtml = applyBtn.innerHTML;
        applyBtn.innerHTML = '<span class="material-icons-outlined" style="font-size:18px;">check</span> Applied & Synced!';
        setTimeout(function () {
          applyBtn.innerHTML = origHtml;
        }, 1500);
      });
    }
  }

  _esc(s) {
    if (!s) return "";
    return String(s).replace(/[&<>"']/g, function (m) { return _escMap[m]; });
  }

  _cssEsc(s) {
    if (!s) return "";
    if (typeof CSS !== "undefined" && CSS.escape) {
      return CSS.escape(String(s));
    }
    return String(s).replace(/['"\\]/g, "\\$&");
  }
}

/* global helper used by collapse toggles */
function toggleCollapsible(link) {
  var content = link.nextElementSibling;
  if (!content) return false;
  var isHidden = content.style.display === "none";
  content.style.display = isHidden ? "block" : "none";
  link.innerHTML = (isHidden ? "&#9660;" : "&#9654;") + link.innerHTML.slice(1);
  return false;
}

/* Delegated click handling (CSP: no inline onclick handlers). */
document.addEventListener("click", function (e) {
  var t = e.target;
  var link = t && t.closest ? t.closest(".collapse-toggle") : null;
  if (link) {
    e.preventDefault();
    toggleCollapsible(link);
  }
});
