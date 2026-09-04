/* Settings Renderer — unified layout engine for all settings pages.
 *
 * Reads page definitions from settings_pages.json and renders controls
 * with identical styling, spacing, and behaviour. No plugin-specific CSS.
 */

"use strict";

var _escMap = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
var MEDIA_PLAYER_BRAND_ICONS = {
  spotify: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><circle cx="12" cy="12" r="12" fill="#1ED760"/><path d="M17.5 16.2c-.2.3-.6.4-.9.2-2.5-1.5-5.6-1.9-9.3-1-.4.1-.7-.1-.8-.5-.1-.4.1-.7.5-.8 4.1-1 7.6-.5 10.3 1.2.3.2.4.6.2.9zm1.2-2.7c-.3.4-.8.5-1.2.3-2.9-1.8-7.3-2.3-10.7-1.3-.4.1-.9-.1-1-.5-.1-.4.1-.9.5-1 3.9-1.2 8.8-.6 12.1 1.4.4.2.5.7.3 1.1zm.1-2.9c-3.5-2.1-9.2-2.3-12.5-1.3-.5.2-1.1-.1-1.3-.6-.2-.5.1-1.1.6-1.3 3.9-1.2 10.2-1 14.2 1.4.5.3.6.9.3 1.4-.3.5-.9.7-1.3.4z" fill="#000"/></svg>',
  itunes: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#FA243C"/><path d="M16.5 6.2v8.6c0 1.5-1.2 2.7-2.7 2.7s-2.7-1.2-2.7-2.7 1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3V8.8l-5.5 1.2v6c0 1.5-1.2 2.7-2.7 2.7S4.1 17.5 4.1 16s1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3v-8l8.5-1.9v2.5z" fill="#fff"/></svg>',
  applemusic: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#FA243C"/><path d="M16.5 6.2v8.6c0 1.5-1.2 2.7-2.7 2.7s-2.7-1.2-2.7-2.7 1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3V8.8l-5.5 1.2v6c0 1.5-1.2 2.7-2.7 2.7S4.1 17.5 4.1 16s1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3v-8l8.5-1.9v2.5z" fill="#fff"/></svg>',
  "apple music": '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#FA243C"/><path d="M16.5 6.2v8.6c0 1.5-1.2 2.7-2.7 2.7s-2.7-1.2-2.7-2.7 1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3V8.8l-5.5 1.2v6c0 1.5-1.2 2.7-2.7 2.7S4.1 17.5 4.1 16s1.2-2.7 2.7-2.7c.4 0 .8.1 1.2.3v-8l8.5-1.9v2.5z" fill="#fff"/></svg>',
  "vlc media player": '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><path d="M12 2l-2.5 7h5L12 2z" fill="#FF8800"/><path d="M9.2 10l-.8 2.5h7.2L14.8 10H9.2z" fill="#FFFFFF"/><path d="M8.1 13.5l-.9 3h9.6l-.9-3H8.1z" fill="#FF8800"/><path d="M6.9 17.5l-1.1 3.5h12.4l-1.1-3.5H6.9z" fill="#FFFFFF"/><path d="M3 21.5h18v1.5H3v-1.5z" fill="#FF8800"/><path d="M5 22h14l-1-1H6l-1 1z" fill="#E65100"/></svg>',
  vlc: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><path d="M12 2l-2.5 7h5L12 2z" fill="#FF8800"/><path d="M9.2 10l-.8 2.5h7.2L14.8 10H9.2z" fill="#FFFFFF"/><path d="M8.1 13.5l-.9 3h9.6l-.9-3H8.1z" fill="#FF8800"/><path d="M6.9 17.5l-1.1 3.5h12.4l-1.1-3.5H6.9z" fill="#FFFFFF"/><path d="M3 21.5h18v1.5H3v-1.5z" fill="#FF8800"/><path d="M5 22h14l-1-1H6l-1 1z" fill="#E65100"/></svg>',
  "windows media player": '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#0078D4"/><circle cx="12" cy="12" r="7.5" fill="#FFB900"/><polygon points="10,8 16,12 10,16" fill="#FFFFFF"/></svg>',
  "media player": '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#0078D4"/><circle cx="12" cy="12" r="7.5" fill="#FFB900"/><polygon points="10,8 16,12 10,16" fill="#FFFFFF"/></svg>',
  wmplayer: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#0078D4"/><circle cx="12" cy="12" r="7.5" fill="#FFB900"/><polygon points="10,8 16,12 10,16" fill="#FFFFFF"/></svg>',
  windowsmediaplayer: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#0078D4"/><circle cx="12" cy="12" r="7.5" fill="#FFB900"/><polygon points="10,8 16,12 10,16" fill="#FFFFFF"/></svg>',
  foobar2000: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><circle cx="12" cy="12" r="11" fill="#2B2B2B" stroke="#888" stroke-width="1"/><circle cx="8.5" cy="10" r="2.5" fill="#fff"/><circle cx="15.5" cy="10" r="2.5" fill="#fff"/><circle cx="9" cy="10" r="1.2" fill="#000"/><circle cx="16" cy="10" r="1.2" fill="#000"/><ellipse cx="12" cy="16" rx="4" ry="2" fill="#fff"/></svg>',
  foobar: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><circle cx="12" cy="12" r="11" fill="#2B2B2B" stroke="#888" stroke-width="1"/><circle cx="8.5" cy="10" r="2.5" fill="#fff"/><circle cx="15.5" cy="10" r="2.5" fill="#fff"/><circle cx="9" cy="10" r="1.2" fill="#000"/><circle cx="16" cy="10" r="1.2" fill="#000"/><ellipse cx="12" cy="16" rx="4" ry="2" fill="#fff"/></svg>',
  musicbee: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><circle cx="12" cy="12" r="11" fill="#FFA000"/><path d="M7 11h10v2H7zM9 15h6v2H9z" fill="#212121"/><circle cx="9" cy="7.5" r="1.5" fill="#212121"/><circle cx="15" cy="7.5" r="1.5" fill="#212121"/><path d="M12 4v3" stroke="#212121" stroke-width="1.5" stroke-linecap="round"/></svg>',
  aimp: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><circle cx="12" cy="12" r="11" fill="#FF5722"/><polygon points="9,6 18,12 9,18" fill="#FFFFFF"/><polygon points="12,9 18,12 12,15" fill="#FFCCBC"/></svg>',
  tidal: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#000"/><g fill="#fff" transform="translate(2, 2) scale(0.833)"><polygon points="6,3 9,6 6,9 3,6"/><polygon points="12,3 15,6 12,9 9,6"/><polygon points="18,3 21,6 18,9 15,6"/><polygon points="12,9 15,12 12,15 9,12"/></g></svg>',
  plexamp: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#1F2326"/><polygon points="8,4 14,12 8,20 12,20 18,12 12,4" fill="#E5A00D"/></svg>',
  winamp: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#1C2128"/><path d="M14 3L6 13h5l-2 8 10-11h-5l2-7z" fill="#FFAA00" stroke="#FF8800" stroke-width="0.5"/></svg>',
  "mpc-hc": '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#1565C0"/><path d="M4 6h16v12H4z" fill="#212121"/><path d="M4 6l3 4h3L7 6h3l3 4h3l-3-4h3l3 4h2V6H4z" fill="#EEEEEE"/><polygon points="10,11 15,14 10,17" fill="#FFFFFF"/></svg>',
  "mpc-be": '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#1565C0"/><path d="M4 6h16v12H4z" fill="#212121"/><path d="M4 6l3 4h3L7 6h3l3 4h3l-3-4h3l3 4h2V6H4z" fill="#EEEEEE"/><polygon points="10,11 15,14 10,17" fill="#FFFFFF"/></svg>',
  mpc: '<svg viewBox="0 0 24 24" width="24" height="24" style="max-width:100%;max-height:100%;display:block" fill="none"><rect width="24" height="24" rx="5" fill="#1565C0"/><path d="M4 6h16v12H4z" fill="#212121"/><path d="M4 6l3 4h3L7 6h3l3 4h3l-3-4h3l3 4h2V6H4z" fill="#EEEEEE"/><polygon points="10,11 15,14 10,17" fill="#FFFFFF"/></svg>'
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
  return !!(window.pywebview && window.pywebview.api) || (typeof IS_APP !== 'undefined' && IS_APP);
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
      if (typeof IS_MOBILE !== 'undefined' && IS_MOBILE && !_isApp()) {
        // Session expired or unauthenticated remote access -> back to login.
        window.location.href = "/login";
      }
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
    try {
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
        var isCollapsiblePage = (pageId === "settings");
        var renderedIndex = 0;
        html += '<section class="settings-content">';
        
        if (pageId === "settings") {
          var v = window.panelState && window.panelState.app_version ? window.panelState.app_version : "";
          if (v) {
            html += '<div style="column-span:all;text-align:right;color:var(--fg-dim);font-size:12px;margin-bottom:8px;">Iris v' + this._esc(v) + '</div>';
          }
        }
        
        page.sections.forEach(function (section) {
          if (section.app_only && !isApp) return;
          var isOpen = (renderedIndex === 0);
          html += self._renderSection(section, config, isOpen, isCollapsiblePage);
          renderedIndex++;
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
    } catch (err) {
      console.error("[SettingsRenderer] renderBuiltInPage error:", err);
      return '<section class="settings-content settings-empty">' +
        '<div class="settings-placeholder">' +
          '<span class="material-icons-outlined">error_outline</span>' +
          '<p>Unable to load settings page.</p>' +
        '</div>' +
      '</section>';
    }
  }

  /* ── Render a plugin settings page ──────────────────────────── */

  renderPluginPage(name, pluginCfg, pluginData, pluginStateData, config) {
    try {
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
        status: "Connection",
        configuration: "Game Detection",
        buttons: "Button Controls",
        outputs: "Output Routing",
        actions: "Actions",
        diagnostics: "Diagnostics",
      };

      var self = this;

      function buildSectionCard(sKey, renderFn) {
        if (!capabilities[sKey]) return null;
        var content = self[renderFn](name, p, pluginData, pluginStateData, config);
        if (!content) return null;
        var label = (p.labels && p.labels[sKey]) || LABEL_DEFAULTS[sKey] || sKey;
        var html = '<div class="settings-section plugin-section-' + sKey + '">';
        html += '<h2 class="settings-section-title">' + self._esc(label) + '</h2>';
        html += '<div class="settings-card">';
        html += content;
        html += '</div></div>';
        return { key: sKey, html: html };
      }

      var col1Html = "";
      var col2Html = "";
      var col1Height = 0;
      var col2Height = 0;

      function addToCol(colNum, html, estHeight) {
        if (colNum === 1) {
          col1Html += html;
          col1Height += estHeight;
        } else {
          col2Html += html;
          col2Height += estHeight;
        }
      }

      // 1. Column 1: Connection (Status)
      var statusCard = buildSectionCard("status", "_renderPluginStatus");
      if (statusCard) addToCol(1, statusCard.html, 140);

      // 2. Column 2: Output Routing (Outputs)
      var outputsCard = buildSectionCard("outputs", "_renderPluginOutputs");
      if (outputsCard) addToCol(2, outputsCard.html, 160);

      // 3. Column 1: Plugin Specific Controls (Configuration / Game Detection)
      var configCard = buildSectionCard("configuration", "_renderPluginConfig");
      if (configCard) addToCol(1, configCard.html, 180);

      // 4. Column 2: Button Controls (Buttons)
      var buttonsCard = buildSectionCard("buttons", "_renderPluginButtons");
      if (buttonsCard) addToCol(2, buttonsCard.html, 340);

      // Actions & Diagnostics
      var actionsCard = buildSectionCard("actions", "_renderPluginActions");
      if (actionsCard) {
        if (col1Height <= col2Height) addToCol(1, actionsCard.html, 100);
        else addToCol(2, actionsCard.html, 100);
      }
      var diagCard = buildSectionCard("diagnostics", "_renderPluginDiagnostics");
      if (diagCard) {
        if (col1Height <= col2Height) addToCol(1, diagCard.html, 100);
        else addToCol(2, diagCard.html, 100);
      }

      // 5. Below: 2 columns of telemetry category cards, distributed by shortest stack
      if (capabilities.live_data) {
        var telemetryCards = this._getPluginLiveDataCardList(name, p, pluginData, pluginStateData);
        telemetryCards.forEach(function(card) {
          var estH = 50 + (card.fieldCount || 4) * 32;
          if (col1Height <= col2Height) {
            addToCol(1, card.html, estH);
          } else {
            addToCol(2, card.html, estH);
          }
        });
      }

      var html = '<section class="settings-content plugin-settings-layout">';
      html += '<div class="plugin-masonry-container">';
      html += '<div class="plugin-masonry-col plugin-masonry-col-1">' + col1Html + '</div>';
      html += '<div class="plugin-masonry-col plugin-masonry-col-2">' + col2Html + '</div>';
      html += '</div>';
      html += '</section>';
      return html;
    } catch (err) {
      console.error("[SettingsRenderer] renderPluginPage error:", err);
      return '<section class="settings-content settings-empty">' +
        '<div class="settings-placeholder">' +
          '<span class="material-icons-outlined">error_outline</span>' +
          '<p>Unable to load plugin settings.</p>' +
        '</div>' +
      '</section>';
    }
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
          html += self._renderControl(ctrl, values, pluginStateData);
        });
      });
    } else {
      html += self._renderControl({
        type: "toggle",
        key: "_plugin_enabled_" + name,
        label: "Enabled",
      }, { _plugin_enabled: p.enabled !== false }, pluginStateData);
      if (ptype === "app") {
        html += self._renderControl({
          type: "folder_picker",
          key: "_plugin_exe_" + name,
          label: "Target executable",
        }, { _plugin_exe: p.exe_path || p.exe_default || "" }, pluginStateData);
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
          // Check state, then status, then top-level pluginStateData
          val = liveState[f.key] !== undefined ? liveState[f.key] :
                liveStatus[f.key] !== undefined ? liveStatus[f.key] :
                ps[f.key];
        }
        if (val === undefined || val === null) val = "—";
        // Handle list/array values (e.g., profiles)
        if (Array.isArray(val)) {
          val = val.join(", ");
        }
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
    var self = this;
    var pcfg = p.config || {};
    var html = "";

    // Enabled toggle
    html += this._renderControl({
      type: "toggle",
      key: "enabled",
      label: "Enabled",
      description: "Enable or disable this plugin"
    }, { enabled: p.enabled !== false }, pluginStateData);

    if ((p.type || "service") === "app") {
      html += this._renderControl({
        type: "folder_picker",
        key: "exe_path",
        label: "Target executable",
        description: "Executable path for auto-detection"
      }, { exe_path: p.exe_path || p.exe_default || "" }, pluginStateData);
    }

    if (p.theme) {
      html += this._renderControl({
        type: "toggle",
        key: "auto_theme",
        label: "Auto Apply Game Theme",
        description: "Switch Iris to " + (p.theme.description || "game colours") + " when running and restore on exit"
      }, { auto_theme: pcfg.auto_theme !== false }, pluginStateData);
    }

    var settings = p.settings || [];
    settings.forEach(function (section) {
      if (!section.controls || !section.controls.length) return;
      section.controls.forEach(function (ctrl) {
        var values = {};
        values[ctrl.key] = pcfg[ctrl.key] !== undefined ? pcfg[ctrl.key] : (ctrl.default || "");
        html += self._renderControl(ctrl, values, pluginStateData);
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
                   (typeof featureConfig !== "undefined" && featureConfig && featureConfig.panel_profiles) || [];

    // Find matching profile for this plugin
    var matchingProf = profiles.find(function(prof) {
      if (!prof || typeof prof !== "object") return false;
      var profExe = (prof.exe || "").toLowerCase();
      var profName = (prof.name || "").toLowerCase();
      var pluginExe = (p.exe_default || "").toLowerCase().replace(".exe", "");
      var pluginName = (p.display_name || name || "").toLowerCase();
      return (profExe && pluginExe && (profExe.indexOf(pluginExe) !== -1 || pluginExe.indexOf(profExe.replace(".exe", "")) !== -1)) ||
             (profName && pluginName && (profName.indexOf(pluginName) !== -1 || pluginName.indexOf(profName) !== -1));
    });
    var defaultTargetId = matchingProf ? matchingProf.id : (profiles.length > 0 ? profiles[0].id : "__new__");

    var ps = pluginStateData || {};
    var liveState = ps.state || ps || {};
    var liveStatus = ps.status || {};

    var html = '<div class="plugin-button-studio">';

    // Compact export bar
    html += '<div class="plugin-export-bar">';
    html += '<div class="plugin-export-actions">';
    html += '<select id="plugin-btn-target-profile" class="settings-select plugin-export-select">';
    profiles.forEach(function(prof) {
      var sel = prof.id === defaultTargetId ? ' selected' : '';
      var sub = prof.exe ? prof.exe : "App Profile";
      html += '<option value="' + self._esc(prof.id) + '"' + sel + '>' + self._esc(prof.name || prof.id) + ' (' + self._esc(sub) + ')</option>';
    });
    html += '<option value="__new__"' + (defaultTargetId === "__new__" || profiles.length === 0 ? ' selected' : '') + '>+ Create new profile for ' + self._esc(p.display_name) + '</option>';
    html += '</select>';
    html += '<button type="button" class="settings-btn primary btn-export-all" data-plugin="' + self._esc(name) + '">';
    html += '<span class="material-icons-outlined" style="font-size:16px;vertical-align:middle;margin-right:4px">send</span>Export to Profile</button>';
    html += '</div></div>';

    // 4×3 button grid
    html += '<div class="plugin-btn-grid">';
    for (var i = 0; i < 12; i++) {
      var btn = buttons[i];
      if (!btn) {
        html += '<div class="plugin-btn-slot plugin-btn-slot--empty"></div>';
        continue;
      }
      var skey = btn.state_key || "";
      var val = liveStatus[skey] !== undefined ? liveStatus[skey] : liveState[skey];
      var is_on = false;
      if (typeof val === "boolean") is_on = val;
      else if (typeof val === "number") is_on = val > 0;
      else if (typeof val === "string") is_on = ["down","deployed","on","active","charging","true","yes","online"].indexOf(val.toLowerCase()) !== -1;

      var colors = btn.colors || {};
      var onColor  = colors.on  || btn.color || "var(--neon-grn)";
      var offColor = colors.off || "#444444";
      var tileColor = is_on ? onColor : offColor;
      var labels = btn.labels || {};
      var stateLabel = is_on ? (labels.on || "ON") : (labels.off || "OFF");
      var glowStyle = is_on ? ("box-shadow:0 0 10px " + onColor + "44, inset 0 0 6px " + onColor + "22;") : "";
      var borderStyle = "border-color:" + tileColor + ";";
      var iconName = btn.icon || "toggle-switch";
      var iconChar = typeof mdiChar === "function" ? mdiChar(iconName) : "";

      html += '<div class="plugin-btn-slot" data-btn-id="' + self._esc(btn.id) + '" style="' + borderStyle + glowStyle + '">';
      html += '<span class="plugin-btn-slot-badge" style="color:' + tileColor + ';border-bottom-color:' + tileColor + '44;">' + self._esc(stateLabel) + '</span>';
      html += '<span class="plugin-btn-slot-icon md" data-md="' + self._esc(iconName) + '" style="color:' + tileColor + '">' + self._esc(iconChar) + '</span>';
      html += '<span class="plugin-btn-slot-name">' + self._esc(btn.name || btn.id) + '</span>';
      html += '</div>';
    }
    html += '</div>';

    html += '</div>';
    return html;
  }

  _getPluginLiveDataCardList(name, p, pluginData, pluginStateData) {
    var self = this;
    var ps = pluginStateData || {};
    var liveState = ps.state || {};
    var liveStatus = ps.status || {};
    var liveLayout = ps.layout || (pluginData && pluginData.layout);

    // Resolve live value for a field def
    function resolveVal(f) {
      var src = f.source === "status" ? liveStatus : (liveState[f.key] !== undefined ? liveState : liveStatus);
      var raw = src[f.key];
      if (raw === undefined || raw === null || raw === "") return null;
      if (typeof raw === "boolean") {
        var d = f.display || "yes_no";
        var text = raw ? "Yes" : "No";
        if (d === "up_down")            text = raw ? "Up" : "Down";
        if (d === "down_up")            text = raw ? "Down" : "Up";
        if (d === "on_off")             text = raw ? "On" : "Off";
        if (d === "deployed_retracted") text = raw ? "Deployed" : "Retracted";
        if (d === "online_down")        text = raw ? "Online" : "Down";
        var badgeCls = raw ? "plugin-data-badge--on" : "plugin-data-badge--off";
        return '<span class="plugin-data-badge ' + badgeCls + '">' + self._esc(text) + '</span>';
      }
      if (typeof raw === "number" && src[f.key + "_unit"]) return self._esc(raw + " " + src[f.key + "_unit"]);
      return '<span class="plugin-data-val plugin-data-val--live">' + self._esc(String(raw)) + '</span>';
    }

    // Infer a human type string from a live value (or fall back to the field definition)
    function inferType(f) {
      if (f.type) return f.type;
      var src = f.source === "status" ? liveStatus : (liveState[f.key] !== undefined ? liveState : liveStatus);
      var raw = src[f.key];
      if (raw === undefined) return "string";
      var t = typeof raw;
      if (t === "boolean") return "boolean";
      if (t === "number")  return Number.isInteger(raw) ? "integer" : "float";
      return "string";
    }

    // Use the layout from the snapshot/poll when available; fall back to live_data_def layout/fields
    var sections = [];
    var liveDataDef = p.live_data_def || p.live_data || {};
    if (liveLayout && Array.isArray(liveLayout) && liveLayout.length > 0) {
      sections = liveLayout;
    } else if (liveDataDef && liveDataDef.layout && Array.isArray(liveDataDef.layout) && liveDataDef.layout.length > 0) {
      sections = liveDataDef.layout;
    } else if (liveDataDef && liveDataDef.fields && Array.isArray(liveDataDef.fields) && liveDataDef.fields.length > 0) {
      sections = [{ title: liveDataDef.title || "Data", fields: liveDataDef.fields }];
    } else {
      // Auto-build from merged state + status keys
      var stateFields  = Object.keys(liveState).map(function(k) { return { key: k, label: k.replace(/_/g, " ").replace(/\b\w/g, function(c) { return c.toUpperCase(); }), source: "state" }; });
      var statusFields = Object.keys(liveStatus).map(function(k) { return { key: k, label: k.replace(/_/g, " ").replace(/\b\w/g, function(c) { return c.toUpperCase(); }), source: "status" }; });
      if (stateFields.length)  sections.push({ title: "State",  fields: stateFields });
      if (statusFields.length) sections.push({ title: "Status", fields: statusFields });
    }

    var list = [];
    sections.forEach(function(section) {
      if (!section.fields || !section.fields.length) return;
      var cardHtml = '<div class="settings-section plugin-section-telemetry-group">';
      cardHtml += '<h2 class="settings-section-title">' + self._esc(section.title) + '</h2>';
      cardHtml += '<div class="settings-card plugin-telemetry-card">';
      cardHtml += '<table class="plugin-data-table">';
      cardHtml += '<thead><tr><th>Field</th><th>Type</th><th>Value / Status</th></tr></thead>';
      cardHtml += '<tbody>';
      section.fields.forEach(function(f) {
        var valHtml = resolveVal(f);
        var type = inferType(f);
        if (valHtml === null) {
          valHtml = '<span class="plugin-data-val plugin-data-val--empty">—</span>';
        }
        cardHtml += '<tr>';
        cardHtml += '<td class="plugin-data-field">' + self._esc(f.label || f.key) + '</td>';
        cardHtml += '<td class="plugin-data-type">' + self._esc(type) + '</td>';
        cardHtml += '<td class="plugin-data-cell">' + valHtml + '</td>';
        cardHtml += '</tr>';
      });
      cardHtml += '</tbody></table></div></div>';
      list.push({ title: section.title, fieldCount: section.fields.length, html: cardHtml });
    });
    return list;
  }

  _renderPluginLiveDataCards(name, p, pluginData, pluginStateData) {
    var cards = this._getPluginLiveDataCardList(name, p, pluginData, pluginStateData);
    return cards.map(function(c) { return c.html; }).join("");
  }

  _renderPluginLiveData(name, p, pluginData, pluginStateData) {
    return this._renderPluginLiveDataCards(name, p, pluginData, pluginStateData);
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

  _renderSection(section, config, isOpen, isCollapsible) {
    if (isOpen === undefined) isOpen = true;
    if (isCollapsible === undefined) isCollapsible = false;
    var self = this;
    var controls = (section.controls && section.controls.length) ? section.controls : [];
    var isWide = !!section.full_width || section.columns === 2;
    if (!isWide) {
      for (var k = 0; k < controls.length; k++) {
        var t = controls[k].type;
        if (t === "theme" || t === "devices" || t === "table") {
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

    if (isCollapsible) {
      html += '<div class="settings-collapsible">';
      if (section.title) {
        var arrow = isOpen ? '&#9660; ' : '&#9654; ';
        html += '<a href="#" class="collapse-toggle settings-section-title">' +
          arrow + this._esc(section.title) + "</a>";
      }
      var contentStyle = isOpen ? '' : ' style="display:none;"';
      html += '<div class="collapse-content"' + contentStyle + '>';
    } else {
      if (section.title) {
        html += '<h2 class="settings-section-title">' + this._esc(section.title) + '</h2>';
      }
    }

    var cardClass = "settings-card";
    if (section.columns === 2) cardClass += " settings-card-cols-2";
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
      items.forEach(function (li, idx) {
        if (idx === 0) {
          html += '<h3 class="settings-section-title">' + self._esc(li) + "</h3>";
        } else {
          html += "<p>" + self._esc(li) + "</p>";
        }
      });
      html += "</div>";
    }

    controls.forEach(function (ctrl) {
      if (qr && ctrl === qr) return;
      html += self._renderControl(ctrl, config);
    });

    html += "</div>";

    if (isCollapsible) {
      html += "</div>";
      html += "</div>";
    }
    html += "</div>";
    return html;
  }

  /* ── Control renderer ───────────────────────────────────────── */

  _renderControl(ctrl, config, pluginStateData) {
    switch (ctrl.type) {
      case "toggle":
        return this._renderToggle(ctrl, config);
      case "text":
        return this._renderText(ctrl, config);
      case "password":
        return this._renderPassword(ctrl, config);
      case "hotkey":
        return this._renderHotkey(ctrl, config);
      case "select":
        return this._renderSelect(ctrl, config, pluginStateData);
      case "slider":
        return this._renderSlider(ctrl, config);
      case "number":
        return this._renderNumber(ctrl, config);
      case "button":
        return this._renderButton(ctrl, config);
      case "buttons":
      case "button_group":
        return this._renderButtons(ctrl, config);
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
    var html = '<div class="settings-control">';
    html += '<div class="settings-toggle-row"';
    if (ctrl.description) html += ' title="' + this._esc(ctrl.description) + '"';
    html += ">";
    html += '<span class="settings-toggle-label">' + this._esc(ctrl.label) + "</span>";
    html += '<div class="settings-toggle ' + on + '" data-key="' + this._esc(ctrl.key) + '">';
    html += '<div class="settings-toggle-thumb"></div>';
    html += "</div>";
    html += "</div>";
    html += this._tip(ctrl);
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
    html += this._tip(ctrl);
    html += "</div>";
    return html;
  }

  /* ── Hotkey input ───────────────────────────────────────────── */

  _renderHotkey(ctrl, config) {
    var val = config[ctrl.key] || ctrl.default || "";
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<div class="pe-hotkey-input-row" style="display:flex; gap:6px; align-items:center;">';
    html += '<input type="text" class="settings-input pe-hotkey-input settings-hotkey-input" data-key="' + this._esc(ctrl.key) + '"';
    html += ' value="' + this._esc(val) + '" placeholder="e.g. ' + this._esc(ctrl.default || "Ctrl+Alt+I") + '" style="flex:1;">';
    html += '<button type="button" class="settings-btn pe-hotkey-capture-btn settings-hotkey-capture-btn" data-hotkey-target="' + this._esc(ctrl.key) + '">Capture</button>';
    html += '</div>';
    html += this._tip(ctrl);
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

  _renderSelect(ctrl, config, pluginStateData) {
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
    if (ctrl.options_key) html += ' data-options-key="' + this._esc(ctrl.options_key) + '"';
    html += ">";
    var options = ctrl.options || [];
    // If options not pre-populated but options_key exists, try to get from pluginStateData
    if (!options.length && ctrl.options_key && pluginStateData) {
      var ps = pluginStateData;
      var liveState = ps.state || {};
      options = liveState[ctrl.options_key] || ps[ctrl.options_key] || liveState.profiles || ps.profiles || [];
    }
    if (options.length) {
      var self = this;
      options.forEach(function (opt) {
        var optVal = typeof opt === "object" ? opt.value : opt;
        var optLabel = typeof opt === "object" ? (opt.label || optVal) : opt;
        var sel = optVal === val ? " selected" : "";
        html += '<option value="' + self._esc(optVal) + '"' + sel + ">";
        html += self._esc(optLabel);
        html += "</option>";
      });
    }
    html += "</select>";
    html += this._tip(ctrl);
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
    html += this._tip(ctrl);
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
    html += this._tip(ctrl);
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

  /* ── Multi-button Row ────────────────────────────────────────── */

  _renderButtons(ctrl) {
    var self = this;
    var buttons = ctrl.buttons || [];
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<div class="settings-buttons-row" style="display:flex;gap:10px;align-items:center;">';
    buttons.forEach(function (btn) {
      html += '<button type="button" class="settings-btn" style="flex:1" data-action="' + self._esc(btn.action || "") + '"';
      if (btn.target) html += ' data-target="' + self._esc(btn.target) + '"';
      html += ">";
      if (btn.icon) html += '<span class="material-icons-outlined">' + self._esc(btn.icon) + "</span> ";
      html += self._esc(btn.label || "Button");
      html += "</button>";
    });
    html += "</div>";
    if (ctrl.description) html += this._tip(ctrl);
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

  /* ── Paired devices list (managed via modal) ────────────────── */

  _renderDevices(ctrl, config) {
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    if (ctrl.description) {
      html += '<div class="settings-hint">' + this._esc(ctrl.description) + "</div>";
    }
    html += '<div class="settings-password-row">';
    html += '<button class="settings-btn settings-devices-manage">';
    html += '<span class="material-icons-outlined">devices_other</span> Manage devices</button>';
    html += "</div>";
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
    html += this._tip(ctrl);
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
    html += this._tip(ctrl);
    html += "</div>";
    return html;
  }

  /* ── Visual Theme Control ───────────────────────────────────── */

  _renderTheme(ctrl, config) {
    var theme = config.theme || { mode: "iris", accent: "#B23AF6", neon: "#48B2E9" };
    var mode = theme.mode || "iris";
    var accent = theme.accent || "#B23AF6";
    var neon = theme.neon || "#48B2E9";

    var html = '<div class="settings-control theme-engine-control">';
    html += '<label class="settings-label" style="font-weight:700; margin-bottom:8px; display:block;">Visual Theme</label>';
    html += this._tip(ctrl);

    html += '<div class="theme-presets-grid">';
    
    // 1. Iris preset
    html += '<div class="theme-preset-card' + (mode === 'iris' ? ' active' : '') + '" data-theme-mode="iris">';
    html += '<div class="theme-preset-swatch" style="background: linear-gradient(135deg, #48B2E9 0%, #B23AF6 100%);"></div>';
    html += '<span class="theme-preset-title">Iris</span>';
    html += '</div>';

    // 2. Monochrome preset
    html += '<div class="theme-preset-card' + (mode === 'monochrome' ? ' active' : '') + '" data-theme-mode="monochrome">';
    html += '<div class="theme-preset-swatch" style="background: linear-gradient(135deg, #FFFFFF 0%, #666666 100%);"></div>';
    html += '<span class="theme-preset-title">Monochrome</span>';
    html += '</div>';

    // 3. Custom preset
    html += '<div class="theme-preset-card' + (mode === 'custom' ? ' active' : '') + '" data-theme-mode="custom">';
    html += '<div class="theme-preset-swatch" style="background: linear-gradient(135deg, ' + this._esc(neon) + ' 0%, ' + this._esc(accent) + ' 100%);" id="theme-custom-swatch"></div>';
    html += '<span class="theme-preset-title">Custom</span>';
    html += '</div>';

    html += '</div>';

    // Custom Color Pickers
    html += '<div class="theme-custom-pickers" id="theme-custom-pickers"' + (mode === 'custom' ? '' : ' style="display:none;"') + '>';
    html += '<div class="theme-color-input-row">';
    
    html += '<div class="theme-color-field">';
    html += '<label class="settings-label" style="font-size:12px; margin-bottom:4px;">Color 1: Primary Neon</label>';
    html += '<div class="theme-color-picker-wrap">';
    html += '<input type="color" class="theme-color-native" id="theme-neon-color" value="' + this._esc(neon) + '">';
    html += '<input type="text" class="settings-input theme-color-hex" id="theme-neon-hex" value="' + this._esc(neon) + '" maxlength="7">';
    html += '</div>';
    html += '</div>';

    html += '<div class="theme-color-field">';
    html += '<label class="settings-label" style="font-size:12px; margin-bottom:4px;">Color 2: Neon Accent</label>';
    html += '<div class="theme-color-picker-wrap">';
    html += '<input type="color" class="theme-color-native" id="theme-accent-color" value="' + this._esc(accent) + '">';
    html += '<input type="text" class="settings-input theme-color-hex" id="theme-accent-hex" value="' + this._esc(accent) + '" maxlength="7">';
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

    // Ambient Lighting Environment Card
    var lightingCfg = config.ambient_lighting || { enabled: true, sync_theme: true, follow_daylight: true };
    var lightingEnabled = lightingCfg.enabled !== false;
    var followDaylight = lightingCfg.follow_daylight !== false;

    html += '<div class="theme-preview-box" id="ambient-lighting-box" style="margin-top:16px;">';
    html += '<div class="theme-preview-header" style="display:flex;align-items:center;justify-content:space-between;">';
    html += '<span class="theme-preview-title" style="display:flex;align-items:center;gap:6px;"><span class="material-icons-outlined" style="font-size:18px;color:var(--neon-text);">lightbulb</span> Ambient Lighting & Environment</span>';
    html += '<div id="ambient-provider-badges" style="display:flex;gap:6px;"></div>';
    html += '</div>';

    html += '<div id="ambient-lighting-content" style="padding-top:8px;">';
    html += '<div class="settings-toggle-row" style="margin-bottom:8px;">';
    html += '<span class="settings-toggle-label">Enable Lighting Sync</span>';
    html += '<div class="settings-toggle' + (lightingEnabled ? ' on' : '') + '" id="ambient-enabled-tog"><div class="settings-toggle-thumb"></div></div>';
    html += '</div>';
    html += '<span class="settings-hint" style="margin-top:-4px;margin-bottom:10px;display:block;">Master switch for automatic profile lighting and ambient synchronization.</span>';

    html += '<div class="settings-toggle-row" style="margin-bottom:8px;">';
    html += '<span class="settings-toggle-label">Observe Daylight Cycle</span>';
    html += '<div class="settings-toggle' + (followDaylight ? ' on' : '') + '" id="ambient-daylight-tog"><div class="settings-toggle-thumb"></div></div>';
    html += '</div>';
    html += '<span class="settings-hint" style="margin-top:-4px;margin-bottom:12px;display:block;">During daylight hours (07:30–19:30), ceiling and room lights turn OFF while OpenRGB PC lights remain illuminated in theme colour.</span>';

    // OpenRGB startup behaviour
    var startupMode = lightingCfg.startup_mode || (lightingCfg.sync_theme !== false ? 'theme' : 'off');
    var startupProfile = lightingCfg.startup_profile || '';
    html += '<div class="settings-field" style="margin-top:4px;">';
    html += '<label class="settings-label">PC LED Startup Behaviour</label>';
    html += '<span class="settings-hint" style="margin-top:-2px;margin-bottom:8px;display:block;">Applied once when Iris starts, then left alone. Lighting never auto-switches when you change apps.</span>';
    html += '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px;">';
    var modes = [['theme','Highest-luminance theme colour'],['profile','A specific OpenRGB profile'],['off','Nothing']];
    for (var mi=0; mi<modes.length; mi++) {
      var m = modes[mi][0], ml = modes[mi][1];
      html += '<div class="ambient-mode' + (startupMode===m?' active':'') + '" data-mode="' + m + '" style="flex:1;min-width:130px;cursor:pointer;border:1px solid var(--border);border-radius:8px;padding:8px 10px;text-align:center;font-size:11px;background:var(--bg-control, #1A1C20);' + (startupMode===m?'border-color:var(--neon-text);':'') + '">' + this._esc(ml) + '</div>';
    }
    html += '</div>';
    html += '<div class="ambient-profile-row" id="ambient-profile-row" style="display:' + (startupMode==='profile'?'flex':'none') + ';align-items:center;gap:8px;margin-bottom:4px;">';
    html += '<input type="text" class="settings-input" id="ambient-startup-profile" list="ambient-profile-list" placeholder="Profile name (e.g. Red)" value="' + this._esc(startupProfile) + '" style="flex:1;min-width:0;">';
    html += '<datalist id="ambient-profile-list"></datalist>';
    html += '<span class="settings-hint" style="flex-shrink:0;">Load this OpenRGB profile at startup.</span>';
    html += '</div>';
    html += '</div>';

    // Per-app lighting
    var perApp = lightingCfg.per_app || [];
    html += '<div class="settings-field" style="margin-top:10px;">';
    html += '<label class="settings-label">Lighting While an App is Running</label>';
    html += '<span class="settings-hint" style="margin-top:-2px;margin-bottom:8px;display:block;">Load a profile while a game/app process is running, and revert to the startup behaviour when it exits (not focus-based).</span>';
    html += '<div id="ambient-perapp-list" style="display:flex;flex-direction:column;gap:6px;margin-bottom:6px;">';
    if (perApp.length === 0) {
      html += '<span class="settings-hint" id="ambient-perapp-empty" style="color:var(--fg-dim);">No per-app lighting configured.</span>';
    }
    for (var pi=0; pi<perApp.length; pi++) {
      var pa = perApp[pi] || {};
      html += this._renderPerAppRow(pa, pi);
    }
    html += '</div>';
    html += '<button type="button" class="settings-btn" id="ambient-perapp-add" style="width:100%;padding:6px 10px;">+ Add App</button>';
    html += '</div>';

    html += '</div>';
    html += '</div>';

    // Apply Button
    html += '<div style="display:flex; justify-content:flex-end; gap:8px; margin-top:12px;">';
    html += '<button type="button" class="settings-btn primary" id="theme-apply-btn" style="min-width:140px; padding:10px 20px;">';
    html += '<span class="material-icons-outlined" style="font-size:18px;">palette</span> Apply Theme & Lighting';
    html += '</button>';
    html += '</div>';

    html += '</div>';
    return html;
  }

  _renderPerAppRow(pa, idx) {
    var html = '<div class="ambient-perapp-row" data-idx="' + idx + '" style="display:flex;align-items:center;gap:8px;">';
    html += '<input type="text" class="settings-input ambient-perapp-exe" placeholder="exe name, e.g. EliteDangerous64.exe" value="' + this._esc(pa.exe || '') + '" style="flex:1.2;min-width:0;">';
    html += '<input type="text" class="settings-input ambient-perapp-profile" list="ambient-profile-list" placeholder="profile name" value="' + this._esc(pa.profile || '') + '" style="flex:1;min-width:0;">';
    html += '<button type="button" class="settings-btn ambient-perapp-del" style="flex-shrink:0;padding:4px 8px;color:var(--danger,#ff6b6b);">✕</button>';
    html += '</div>';
    return html;
  }

  _renderMediaPlayerPicker(ctrl, config) {
    var val = config[ctrl.key] || "";
    var html = '<div class="settings-control media-player-picker-wrap" data-key="' + this._esc(ctrl.key) + '">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }

    html += '<div class="media-player-row" style="display:flex;align-items:center;gap:8px;">';
    html += '<div class="media-player-icon-preview" id="media-player-icon-preview" style="width:36px;height:36px;border-radius:6px;background:var(--bg-control, #1A1C20);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden;"><span class="material-icons-outlined" style="font-size:20px;color:var(--fg-dim);">music_note</span></div>';
    html += '<select class="settings-select media-player-select" id="media-player-select" style="flex:1;min-width:0;">';
    html += '<option value="">Scanning installed players...</option>';
    if (val) {
      html += '<option value="' + this._esc(val) + '" selected>' + this._esc(val.split(/[\\/]/).pop() || val) + '</option>';
    }
    html += '</select>';
    html += '<button type="button" class="settings-btn media-player-browse-btn" data-target="' + this._esc(ctrl.key) + '" style="white-space:nowrap;flex-shrink:0;">Browse</button>';
    html += '</div>';

    if (ctrl.description) {
      html += this._tip(ctrl);
    }
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

    // Resolve MDI icons in the grid tiles
    if (typeof applyMdiIcons === "function") {
      applyMdiIcons(container);
    }

    // Build the buttons payload from buttons_def preserving all author properties
    function getButtonsPayload() {
      return (p.buttons_def || []).map(function(b) {
        var bid = b.id || b.button_id;
        return {
          type: (b.widget_type === "display" || b.type === "SENSOR") ? "TOGGLE" : (b.type || "TOGGLE"),
          name: b.name || bid,
          icon: b.icon || "toggle-switch",
          icon_off: b.icon_off || "",
          color: b.color || (name === "elite_dangerous" ? "#ffb703" : ""),
          colors: b.colors || { on: "#00ff88", off: "#444444" },
          labels: b.labels || { on: "ON", off: "OFF" },
          plugin: name,
          button_id: bid,
          widget_type: b.widget_type || "status_toggle",
          state_key: b.state_key || bid,
          hotkey: b.hotkey || b.default_hotkey || "",
          show_name: b.show_name !== false,
          show_icon: b.show_icon !== false,
          show_state: b.show_state !== false,
          use_app_icon: false,
          show_album_art: false
        };
      });
    }

    // Export full preset
    var exportAllBtn = container.querySelector(".btn-export-all");
    if (exportAllBtn) {
      exportAllBtn.addEventListener("click", async function() {
        var profileId = (targetSelect && targetSelect.value && targetSelect.value !== "__default__") ? targetSelect.value : "__new__";
        var btns = getButtonsPayload();
        exportAllBtn.disabled = true;
        var origHtml = exportAllBtn.innerHTML;
        exportAllBtn.innerHTML = '<span class="material-icons-outlined" style="font-size:16px;vertical-align:middle;margin-right:4px">hourglass_empty</span>Exporting...';
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
            exportAllBtn.innerHTML = '<span class="material-icons-outlined" style="font-size:16px;vertical-align:middle;margin-right:4px">check</span>Exported to ' + self._esc(data.target_profile || "Profile") + '!';
            if (typeof fetchPanel === "function") fetchPanel();
            if (typeof fetchConfig === "function") fetchConfig();
            setTimeout(function() { exportAllBtn.disabled = false; exportAllBtn.innerHTML = origHtml; }, 2000);
          } else {
            alert("Export failed: " + (data ? data.error : "Unknown error"));
            exportAllBtn.disabled = false;
            exportAllBtn.innerHTML = origHtml;
          }
        } catch (err) {
          alert("Export failed: " + err);
          exportAllBtn.disabled = false;
          exportAllBtn.innerHTML = origHtml;
        }
      });
    }
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

      case "hotkey":
        var hotkeyInput = container.querySelector(".settings-hotkey-input[data-key='" + self._cssEsc(ctrl.key) + "']");
        var capBtn = container.querySelector(".settings-hotkey-capture-btn[data-hotkey-target='" + self._cssEsc(ctrl.key) + "']");
        if (hotkeyInput) {
          var debounceHk = 300;
          var timerHk = null;
          var capturing = false;

          var CODE_MAP = {
            "Digit1":"1","Digit2":"2","Digit3":"3","Digit4":"4","Digit5":"5",
            "Digit6":"6","Digit7":"7","Digit8":"8","Digit9":"9","Digit0":"0",
            "KeyA":"A","KeyB":"B","KeyC":"C","KeyD":"D","KeyE":"E","KeyF":"F",
            "KeyG":"G","KeyH":"H","KeyI":"I","KeyJ":"J","KeyK":"K","KeyL":"L",
            "KeyM":"M","KeyN":"N","KeyO":"O","KeyP":"P","KeyQ":"Q","KeyR":"R",
            "KeyS":"S","KeyT":"T","KeyU":"U","KeyV":"V","KeyW":"W","KeyX":"X",
            "KeyY":"Y","KeyZ":"Z",
            "F1":"F1","F2":"F2","F3":"F3","F4":"F4","F5":"F5","F6":"F6",
            "F7":"F7","F8":"F8","F9":"F9","F10":"F10","F11":"F11","F12":"F12",
            "F13":"F13","F14":"F14","F15":"F15","F16":"F16","F17":"F17","F18":"F18",
            "F19":"F19","F20":"F20","F21":"F21","F22":"F22","F23":"F23","F24":"F24",
            "Space":"Space","Enter":"Enter","Backspace":"Backspace","Tab":"Tab","Escape":"Esc",
            "Delete":"Delete","Insert":"Insert","Home":"Home","End":"End",
            "PageUp":"PageUp","PageDown":"PageDown",
            "ArrowUp":"Up","ArrowDown":"Down","ArrowLeft":"Left","ArrowRight":"Right"
          };

          function setCapture(on) {
            capturing = on;
            if (capBtn) {
              capBtn.textContent = on ? "Recording..." : "Capture";
              capBtn.classList.toggle("pe-hotkey-capture-active", on);
            }
            hotkeyInput.readOnly = on;
            if (on) hotkeyInput.focus();
          }

          if (capBtn) {
            capBtn.addEventListener("click", function() { setCapture(!capturing); });
          }

          hotkeyInput.addEventListener("keydown", function(e) {
            if (!capturing) return;
            if (e.key === "Escape") { setCapture(false); e.preventDefault(); return; }
            if (e.key === "Backspace" || e.key === "Delete") {
              hotkeyInput.value = "";
              config[ctrl.key] = "";
              saveCallback({ [ctrl.key]: "" });
              e.preventDefault();
              return;
            }
            var mod = [];
            if (e.ctrlKey) mod.push("Ctrl");
            if (e.altKey) mod.push("Alt");
            if (e.shiftKey) mod.push("Shift");
            var token = CODE_MAP[e.code];
            if (!token) return;
            var val = mod.length ? mod.join("+") + "+" + token : token;
            hotkeyInput.value = val;
            config[ctrl.key] = val;
            saveCallback({ [ctrl.key]: val });
            setCapture(false);
            e.preventDefault();
          });

          hotkeyInput.addEventListener("input", function() {
            clearTimeout(timerHk);
            var val = this.value.trim();
            timerHk = setTimeout(function() {
              config[ctrl.key] = val;
              saveCallback({ [ctrl.key]: val });
            }, debounceHk);
          });
          hotkeyInput.addEventListener("blur", function() { if (capturing) setCapture(false); });
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
      case "buttons":
      case "button_group":
        var btnList = ctrl.buttons || [ctrl];
        btnList.forEach(function (b) {
          var buttons = container.querySelectorAll(
            ".settings-btn[data-action='" + b.action + "']");
          buttons.forEach(function (el) {
            if (el._bound) return;
            el._bound = true;
            el.addEventListener("click", function () {
              if (b.action === "navigate" || b.action === "open_page") {
                var targetPage = b.target || "library";
                if (typeof window.navigateToPage === "function") {
                  window.navigateToPage(targetPage);
                } else {
                  var navBtn = document.querySelector(".nav-item[data-page='" + targetPage + "']");
                  if (navBtn) navBtn.click();
                }
                return;
              }
              if (b.action === "copy_token") {
                apiFetch(self._apiBase + "/api/config")
                  .then(function (res) { return res.ok ? res.json() : {}; })
                  .then(function (data) {
                    var token = data.http_token || "";
                    if (token) {
                      apiFetch(self._apiBase + "/api/clipboard", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ text: token })
                      }).catch(function () {
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                          navigator.clipboard.writeText(token).catch(function () {});
                        }
                      });
                    }
                  })
                  .catch(function () {});
                var old = el.textContent;
                el.textContent = "Copied!";
                setTimeout(function () { el.textContent = old; }, 1200);
              }
              if (b.action === "open_plugins_folder") {
                var old = el.textContent;
                apiFetch(self._apiBase + "/api/plugins/open_folder", { method: "POST" })
                  .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
                  .then(function () {
                    el.textContent = "Opened!";
                    setTimeout(function () { el.textContent = old; }, 1500);
                  })
                  .catch(function () {
                    el.textContent = "Error";
                    setTimeout(function () { el.textContent = old; }, 1500);
                  });
              }
            });
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
        var manageBtn = container.querySelector(".settings-devices-manage");
        if (!manageBtn) break;
        manageBtn.addEventListener("click", function () {
          self._openDevicesModal(ctrl);
        });
        break;
    }
  }

  /* ── Paired devices modal (review + revoke) ─────────────────── */

  _openDevicesModal(ctrl) {
    var self = this;
    var html =
      '<div class="panel-modal-backdrop" id="devices-modal">' +
        '<div class="panel-modal">' +
          '<div class="panel-modal-header">' +
            '<h3>Paired devices</h3>' +
            '<div class="panel-modal-subtitle">Devices that have entered the panel password.</div>' +
          '</div>' +
          '<div class="settings-devices" data-devices>' +
            '<div class="settings-devices-empty">Loading…</div>' +
          '</div>' +
          '<div class="panel-modal-actions">' +
            '<button type="button" class="settings-btn" id="devices-close">Close</button>' +
          '</div>' +
        '</div>' +
      '</div>';
    var wrap = document.createElement("div");
    wrap.innerHTML = html;
    document.body.appendChild(wrap);

    var devBox = wrap.querySelector("[data-devices]");
    var closeBtn = wrap.querySelector("#devices-close");

    function close() {
      if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    }

    function renderDeviceRows(devices) {
      if (!devices || !devices.length) {
        devBox.innerHTML =
          '<div class="settings-devices-empty">No devices have paired yet.</div>';
        return;
      }
      var rows = "";
      devices.forEach(function (d) {
        rows += '<div class="settings-device-row" data-device-id="' + self._esc(d.id) + '">';
        rows += '<div class="settings-device-meta">';
        rows += '<span class="settings-device-name">' + self._esc(d.name) + "</span>";
        if (d.ua) {
          rows += '<span class="settings-device-ua">' + self._esc(d.ua) + "</span>";
        }
        if (d.last_seen) {
          try {
            rows += '<span class="settings-device-seen">Last seen ' +
              new Date(d.last_seen * 1000).toLocaleString() + "</span>";
          } catch (_) {}
        }
        rows += "</div>";
        rows += '<button class="settings-btn settings-btn-danger device-revoke" data-dev="' +
          self._esc(d.id) + '">Revoke</button>';
        rows += "</div>";
      });
      devBox.innerHTML = rows;
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
    if (closeBtn) closeBtn.addEventListener("click", close);
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) close();
    });
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

    var selectEl = wrap.querySelector(".media-player-select");
    var iconPreview = wrap.querySelector("#media-player-icon-preview");
    var browseBtn = wrap.querySelector(".media-player-browse-btn");
    var currentPath = config[ctrl.key] || "";

    function updateIcon(path) {
      if (!iconPreview) return;
      if (!path) {
        iconPreview.innerHTML = '<span class="material-icons-outlined" style="font-size:20px;color:var(--fg-dim);">music_note</span>';
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
      img.style.width = "100%";
      img.style.height = "100%";
      img.style.objectFit = "contain";
      img.onload = function () {
        iconPreview.innerHTML = "";
        iconPreview.appendChild(img);
      };
      img.onerror = function () {
        iconPreview.innerHTML = '<span class="material-icons-outlined" style="font-size:20px;color:var(--fg-dim);">play_circle</span>';
      };
    }

    function setPath(p, save) {
      currentPath = p || "";
      config[ctrl.key] = currentPath;
      if (selectEl) {
        var exists = false;
        for (var i = 0; i < selectEl.options.length; i++) {
          if (selectEl.options[i].value && currentPath && selectEl.options[i].value.toLowerCase() === currentPath.toLowerCase()) {
            selectEl.selectedIndex = i;
            exists = true;
            break;
          }
        }
        if (!exists && currentPath) {
          var opt = document.createElement("option");
          opt.value = currentPath;
          opt.text = "Custom: " + (currentPath.split(/[\\/]/).pop() || currentPath);
          opt.selected = true;
          selectEl.appendChild(opt);
        } else if (!currentPath) {
          selectEl.selectedIndex = 0;
        }
      }
      updateIcon(currentPath);
      if (save && saveCallback) {
        saveCallback({ [ctrl.key]: currentPath });
      }
    }

    updateIcon(currentPath);

    // Fetch detected players to populate dropdown
    apiFetch((self._apiBase || "") + "/api/media/players")
      .then(function (res) { return res.ok ? res.json() : { players: [] }; })
      .then(function (data) {
        if (!selectEl) return;
        var players = data.players || [];
        var html = '<option value="">(None / Disabled)</option>';
        var foundSelected = false;
        players.forEach(function (p) {
          var isSel = (currentPath && p.path.toLowerCase() === currentPath.toLowerCase());
          if (isSel) foundSelected = true;
          html += '<option value="' + self._esc(p.path) + '"' + (isSel ? ' selected' : '') + '>' + self._esc(p.name) + '</option>';
        });
        if (currentPath && !foundSelected) {
          html += '<option value="' + self._esc(currentPath) + '" selected>Custom: ' + self._esc(currentPath.split(/[\\/]/).pop() || currentPath) + '</option>';
        }
        selectEl.innerHTML = html;
        updateIcon(selectEl.value || currentPath);
      })
      .catch(function () {
        if (selectEl && !selectEl.options.length) {
          selectEl.innerHTML = '<option value="">(None / Disabled)</option>';
        }
      });

    if (selectEl) {
      selectEl.addEventListener("change", function () {
        setPath(selectEl.value, true);
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
      var link = "";
      if (r.url) {
        link = ' <span class="plugin-req-link material-icons-outlined" data-url="' +
          self._esc(r.url) + '" title="Open ' + self._esc(r.name) + ' website">open_in_new</span>';
      }
      return '<div class="plugin-req-row">' +
        '<span class="material-icons-outlined" style="color:' + color + ";font-size:18px\">" + icon + "</span>" +
        '<span class="plugin-req-name">' + self._esc(r.name) + "</span>" +
        '<span class="plugin-req-desc">' + self._esc(r.description) + "</span>" + link +
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
    var theme = config.theme || { mode: "iris", accent: "#B23AF6", neon: "#48B2E9" };
    var currentMode = theme.mode || "iris";
    var currentAccent = theme.accent || "#B23AF6";
    var currentNeon = theme.neon || "#48B2E9";

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
        customSwatch.style.background = "linear-gradient(135deg, " + currentNeon + " 0%, " + currentAccent + " 100%)";
      }
      var prevGrad = container.querySelector("#theme-preview-grad");
      if (prevGrad) {
        var stops = prevGrad.querySelectorAll("stop");
        if (stops.length >= 2) {
          var c1 = currentMode === "iris" ? "#48B2E9" : (currentMode === "monochrome" ? "#FFFFFF" : currentNeon);
          var c2 = currentMode === "iris" ? "#B23AF6" : (currentMode === "monochrome" ? "#666666" : currentAccent);
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

    // Ambient Lighting Toggles & Badges
    var ambientBadges = container.querySelector("#ambient-provider-badges");
    var ambientContent = container.querySelector("#ambient-lighting-content");
    var enabledTog = container.querySelector("#ambient-enabled-tog");
    var dayTog = container.querySelector("#ambient-daylight-tog");

    var lightingConfig = config.ambient_lighting || { enabled: true, sync_theme: true, follow_daylight: true };

    if (enabledTog) {
      enabledTog.addEventListener("click", function () {
        var on = this.classList.toggle("on");
        lightingConfig.enabled = on;
        config.ambient_lighting = lightingConfig;
        saveCallback({ ambient_lighting: lightingConfig });
      });
    }

    if (dayTog) {
      dayTog.addEventListener("click", function () {
        var on = this.classList.toggle("on");
        lightingConfig.follow_daylight = on;
        config.ambient_lighting = lightingConfig;
        saveCallback({ ambient_lighting: lightingConfig });
      });
    }

    // Startup behaviour mode selector
    var modeEls = container.querySelectorAll(".ambient-mode");
    var profileRow = container.querySelector("#ambient-profile-row");
    var profileInput = container.querySelector("#ambient-startup-profile");
    function syncModeUI(mode) {
      lightingConfig.startup_mode = mode;
      var prVisible = mode === "profile";
      if (profileRow) profileRow.style.display = prVisible ? "flex" : "none";
      Array.prototype.forEach.call(modeEls, function (el) {
        var active = el.getAttribute("data-mode") === mode;
        el.classList.toggle("active", active);
        el.style.borderColor = active ? "var(--neon-text)" : "";
      });
    }
    Array.prototype.forEach.call(modeEls, function (el) {
      el.addEventListener("click", function () {
        var mode = this.getAttribute("data-mode");
        syncModeUI(mode);
        config.ambient_lighting = lightingConfig;
        saveCallback({ ambient_lighting: lightingConfig });
      });
    });
    if (profileInput) {
      profileInput.addEventListener("input", function () {
        lightingConfig.startup_profile = this.value;
        config.ambient_lighting = lightingConfig;
        if (self._saveTimers["ambient-startup-profile"]) clearTimeout(self._saveTimers["ambient-startup-profile"]);
        self._saveTimers["ambient-startup-profile"] = setTimeout(function () {
          saveCallback({ ambient_lighting: lightingConfig });
        }, 350);
      });
    }

    // Per-app lighting rows
    var perAppList = container.querySelector("#ambient-perapp-list");
    function savePerApp() {
      var rows = perAppList ? perAppList.querySelectorAll(".ambient-perapp-row") : [];
      var arr = [];
      Array.prototype.forEach.call(rows, function (row) {
        var exe = row.querySelector(".ambient-perapp-exe").value.trim();
        var profile = row.querySelector(".ambient-perapp-profile").value.trim();
        if (exe || profile) arr.push({ exe: exe, profile: profile, plugin: "openrgb", enabled: true });
      });
      lightingConfig.per_app = arr;
      config.ambient_lighting = lightingConfig;
      saveCallback({ ambient_lighting: lightingConfig });
    }
    if (perAppList) {
      perAppList.addEventListener("input", function () {
        if (self._saveTimers["ambient-perapp"]) clearTimeout(self._saveTimers["ambient-perapp"]);
        self._saveTimers["ambient-perapp"] = setTimeout(savePerApp, 350);
      });
      perAppList.addEventListener("click", function (ev) {
        var btn = ev.target.closest(".ambient-perapp-del");
        if (!btn) return;
        var row = btn.closest(".ambient-perapp-row");
        if (row) row.remove();
        savePerApp();
        var rows = container.querySelectorAll(".ambient-perapp-row");
        if (rows.length === 0) {
          var empty = container.querySelector("#ambient-perapp-empty");
          if (!empty) {
            var span = document.createElement("span");
            span.className = "settings-hint";
            span.id = "ambient-perapp-empty";
            span.style.color = "var(--fg-dim)";
            span.textContent = "No per-app lighting configured.";
            perAppList.appendChild(span);
          }
        }
      });
    }
    var addBtn = container.querySelector("#ambient-perapp-add");
    if (addBtn) {
      addBtn.addEventListener("click", function () {
        var empty = container.querySelector("#ambient-perapp-empty");
        if (empty) empty.remove();
        if (perAppList) perAppList.insertAdjacentHTML("beforeend", self._renderPerAppRow({}, -1));
        if (self._saveTimers["ambient-perapp"]) clearTimeout(self._saveTimers["ambient-perapp"]);
        self._saveTimers["ambient-perapp"] = setTimeout(savePerApp, 100);
      });
    }

    // Dynamic Progressive Disclosure: query /api/lighting/status
    apiFetch((self._apiBase || "") + "/api/lighting/status")
      .then(function (res) { return res.ok ? res.json() : { providers: [] }; })
      .then(function (data) {
        var providers = data.providers || [];
        var connected = providers.filter(function (p) { return p.connected; });

        if (ambientBadges) {
          if (connected.length > 0) {
            ambientBadges.innerHTML = connected.map(function (p) {
              return '<span class="auto-badge auto-badge-trigger" style="background:rgba(46,204,113,0.15);color:var(--neon-grn);border:1px solid rgba(46,204,113,0.3);font-size:10px;">● ' + self._esc(p.name) + '</span>';
            }).join("");
          } else if (providers.length > 0) {
            ambientBadges.innerHTML = '<span class="auto-badge" style="background:rgba(255,200,0,0.1);color:#ffcc00;font-size:10px;">Waiting for connection</span>';
          } else {
            ambientBadges.innerHTML = '<span class="auto-badge" style="font-size:10px;">No lighting plugins</span>';
          }
        }

        if (ambientContent && providers.length === 0) {
          ambientContent.innerHTML = '<div style="padding:8px 0;font-size:12px;color:var(--fg-dim);">' +
            'No lighting plugins installed. Install <strong>OpenRGB</strong> for PC LEDs or <strong>Home Assistant</strong> for smart ceiling/room lights in <a href="#" onclick="if(window.navigateToPage)window.navigateToPage(\'plugins\');return false;" style="color:var(--neon-text);text-decoration:underline;">Plugins</a>.' +
            '</div>';
        }

        // Fill OpenRGB profile datalist for the startup-profile + per-app inputs
        var profileList = container.querySelector("#ambient-profile-list");
        if (profileList) {
          var profSet = {};
          providers.forEach(function (p) {
            if (p.presets) p.presets.forEach(function (pr) {
              var id = pr.id || pr.name;
              if (id && id !== "__theme__") profSet[id] = true;
            });
          });
          profileList.innerHTML = Object.keys(profSet).map(function (k) {
            return '<option value="' + self._esc(k) + '"></option>';
          }).join("");
        }
      })
      .catch(function () {});

    var applyBtn = container.querySelector("#theme-apply-btn");
    if (applyBtn) {
      applyBtn.addEventListener("click", function () {
        var themeObj = {
          mode: currentMode,
          accent: currentAccent,
          neon: currentNeon
        };
        config.theme = themeObj;
        config.ambient_lighting = lightingConfig;
        if (typeof window.applyTheme === "function") {
          window.applyTheme(themeObj);
        }
        var saveTimer = self._saveTimers["theme"];
        if (saveTimer) clearTimeout(saveTimer);
        saveCallback({ theme: themeObj, ambient_lighting: lightingConfig });
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

  _tip(ctrl) {
    if (ctrl && ctrl.description) {
      return '<div class="settings-hint">' + this._esc(ctrl.description) + "</div>";
    }
    return "";
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

  if (link.classList.contains("settings-section-title")) {
    var container = link.closest(".settings-content") || document.querySelector(".settings-content");
    if (container && isHidden) {
      // Collapse all other section titles in the same settings container
      var allToggles = container.querySelectorAll(".collapse-toggle.settings-section-title");
      allToggles.forEach(function (otherLink) {
        if (otherLink !== link) {
          var otherContent = otherLink.nextElementSibling;
          if (otherContent && otherContent.style.display !== "none") {
            otherContent.style.display = "none";
            otherLink.innerHTML = "&#9654;" + otherLink.innerHTML.slice(1);
          }
        }
      });
    }
  }

  content.style.display = isHidden ? "block" : "none";
  link.innerHTML = (isHidden ? "&#9660;" : "&#9654;") + link.innerHTML.slice(1);

  if (isHidden && link.classList.contains("settings-section-title")) {
    var sectionEl = link.closest(".settings-section") || link;
    setTimeout(function () {
      sectionEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 40);
  }

  return false;
}

/* Delegated click handling (CSP: no inline onclick handlers). */
document.addEventListener("click", function (e) {
  var t = e.target;
  var reqLink = t && t.closest ? t.closest(".plugin-req-link") : null;
  if (reqLink) {
    e.preventDefault();
    e.stopPropagation();
    var url = (reqLink.getAttribute("data-url") || "").trim();
    if (url) {
      var base = typeof API_BASE !== "undefined" ? API_BASE : "";
      apiFetch(base + "/api/open_url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url }),
      }).catch(function () {});
    }
    return;
  }
  var link = t && t.closest ? t.closest(".collapse-toggle") : null;
  if (link) {
    e.preventDefault();
    toggleCollapsible(link);
  }
});
