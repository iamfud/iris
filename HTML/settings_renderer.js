/* Settings Renderer — unified layout engine for all settings pages.
 *
 * Reads page definitions from settings_pages.json and renders controls
 * with identical styling, spacing, and behaviour. No plugin-specific CSS.
 */

"use strict";

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
      const res = await fetch(this._apiBase + "/api/settings/pages");
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

    if (page.sections && page.sections.length > 0) {
      html += '<section class="settings-content">';
      page.sections.forEach(function (section) {
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

  renderPluginPage(name, pluginCfg, pluginData, pluginStateData) {
    var p = pluginCfg || {};
    var icon = p.icon || "extension";
    var color = this._statusColor(p.status_code);
    var statusLabel = p.status_label || "Unknown";
    var message = p.message || "";
    var ptype = p.type || "service";
    var requirements = p.requirements || [];
    var settings = p.settings || [];

    var html = '<section class="settings-content plugin-settings-content">';
    html += '<div class="plugin-edit-card">';

    /* Status section */
    html += '<div class="plugin-edit-section">';
    html += '<span class="plugin-edit-label">STATUS</span>';
    html += this._detailRow("Type", ptype.charAt(0).toUpperCase() + ptype.slice(1));
    html += this._detailRow("Status", statusLabel, color);
    if (message) {
      html += '<div class="plugin-message">' + this._esc(message) + "</div>";
    }
    if (requirements.length) {
      html += this._renderRequirements(requirements);
    }
    html += "</div>";

    /* Plugin-defined settings sections from plugin.json */
    if (settings.length > 0) {
      var self = this;
      settings.forEach(function (section) {
        if (!section.controls || !section.controls.length) return;
        html += '<div class="plugin-edit-section">';
        if (section.title) {
          html += '<span class="plugin-edit-label">' + self._esc(section.title.toUpperCase()) + '</span>';
        }
        section.controls.forEach(function (ctrl) {
          /* For plugin controls, read values from plugin config (p) not feature config */
          var pluginValues = {};
          pluginValues[ctrl.key] = p[ctrl.key];
          if (ctrl.key === "enabled") pluginValues[ctrl.key] = p.enabled !== false;
          html += self._renderControl(ctrl, pluginValues);
        });
        html += "</div>";
      });
    } else {
      /* Fallback: generic enabled toggle when plugin has no settings defined */
      html += '<div class="plugin-edit-section">';
      html += '<span class="plugin-edit-label">CONFIGURATION</span>';
      html += this._renderControl({
        type: "toggle",
        key: "_plugin_enabled_" + name,
        label: "Enabled",
      }, { _plugin_enabled: p.enabled !== false });
      if (ptype === "app") {
        html += this._renderControl({
          type: "folder_picker",
          key: "_plugin_exe_" + name,
          label: "Target executable",
        }, { _plugin_exe: p.exe_path || p.exe_default || "" });
      }
      html += "</div>";
    }

    /* Data section */
    html += '<div class="plugin-edit-section plugin-data-container">';
    html += '<span class="plugin-edit-label">DATA</span>';
    html += this._renderPluginData(name, pluginData, pluginStateData);
    html += "</div>";

    html += "</div>";
    html += "</section>";

    return html;
  }

  /* ── Section renderer ───────────────────────────────────────── */

  _renderSection(section, config) {
    var self = this;
    var html = '<div class="settings-section">';
    if (section.title) {
      html += '<h2 class="settings-section-title">' + this._esc(section.title) + "</h2>";
    }
    html += '<div class="settings-card">';
    if (section.controls) {
      section.controls.forEach(function (ctrl) {
        html += self._renderControl(ctrl, config);
      });
    }
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
      case "folder_picker":
        return this._renderFolderPicker(ctrl, config);
      case "file_picker":
        return this._renderFilePicker(ctrl, config);
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

  /* ── Password input ─────────────────────────────────────────── */

  _renderPassword(ctrl, config) {
    var val = config[ctrl.key] || "";
    var html = '<div class="settings-control">';
    if (ctrl.label) {
      html += '<label class="settings-label">' + this._esc(ctrl.label) + "</label>";
    }
    html += '<div class="settings-password-wrap">';
    html += '<input type="password" class="settings-input settings-password-input" data-key="' + this._esc(ctrl.key) + '"';
    html += ' value="' + this._esc(val) + '"';
    if (ctrl.placeholder) html += ' placeholder="' + this._esc(ctrl.placeholder) + '"';
    html += ">";
    html += '<button class="settings-password-toggle" data-key="' + this._esc(ctrl.key) + '">';
    html += '<span class="material-icons-outlined">visibility_off</span>';
    html += "</button>";
    html += "</div>";
    html += "</div>";
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
    html += '<input type="range" class="settings-slider" data-key="' + this._esc(ctrl.key) + '"';
    html += ' min="' + (ctrl.min !== undefined ? ctrl.min : 0) + '"';
    html += ' max="' + (ctrl.max !== undefined ? ctrl.max : 100) + '"';
    if (ctrl.step !== undefined) html += ' step="' + ctrl.step + '"';
    html += ' value="' + this._esc(String(val)) + '"';
    html += ">";
    html += "</div>";
    return html;
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

  /* ── Folder picker ──────────────────────────────────────────── */

  _renderFolderPicker(ctrl, config) {
    var val = config[ctrl.key] || "";
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

  /* ── Bind events for a rendered page ────────────────────────── */

  bindBuiltInPage(container, pageId, config, saveCallback) {
    var self = this;
    var page = this.getPage(pageId);
    if (!page || !page.sections) return;

    page.sections.forEach(function (section) {
      if (!section.controls) return;
      section.controls.forEach(function (ctrl) {
        self._bindControl(container, ctrl, config, saveCallback);
      });
    });
  }

  bindPluginPage(container, name, pluginCfg, savePluginCallback) {
    var self = this;
    var p = pluginCfg || {};
    var settings = p.settings || [];

    if (settings.length > 0) {
      /* Bind plugin-defined controls */
      settings.forEach(function (section) {
        if (!section.controls) return;
        section.controls.forEach(function (ctrl) {
          self._bindPluginControl(container, ctrl, name, p, savePluginCallback);
        });
      });
    } else {
      /* Fallback: generic enabled toggle */
      var toggle = container.querySelector(".settings-toggle[data-key='_plugin_enabled_" + name + "']");
      if (toggle) {
        toggle.addEventListener("click", function () {
          var on = this.classList.toggle("on");
          savePluginCallback(name, "enabled", on);
        });
      }
      /* Exe path (app type only) */
      if ((p.type || "service") === "app") {
        var input = container.querySelector(".settings-input[data-key='_plugin_exe_" + name + "']");
        if (input) {
          var exeTimer = null;
          input.addEventListener("input", function () {
            clearTimeout(exeTimer);
            exeTimer = setTimeout(function () {
              savePluginCallback(name, "exe_path", input.value.trim());
            }, 400);
          });
        }
        var browseBtn = container.querySelector(".settings-picker-btn[data-target='_plugin_exe_" + name + "']");
        if (browseBtn) {
          browseBtn.addEventListener("click", function () {
            self._browseExe(name, input, savePluginCallback);
          });
        }
      }
    }
  }

  /* ── Plugin data display ────────────────────────────────────── */

  _renderPluginData(name, liveData, pluginStateData) {
    var ps = pluginStateData || {};
    var liveState = ps.state || {};
    var liveStatus = ps.status || {};
    var liveLayout = ps.layout;
    var hasLiveData = Object.keys(liveState).length > 0 || Object.keys(liveStatus).length > 0;
    var s = hasLiveData ? liveState : (liveData && liveData.state ? liveData.state : {});
    var st = hasLiveData ? liveStatus : (liveData && liveData.status ? liveData.status : {});
    var layout = liveLayout || (liveData && liveData.layout);
    var hasAnyData = Object.keys(s).length > 0 || Object.keys(st).length > 0;

    if (!hasAnyData) {
      return '<div class="plugin-data-unavailable">No data available yet</div>';
    }

    if (layout) {
      var self = this;
      return layout.map(function (g) {
        var rows = g.fields.map(function (f) {
          var src = f.source === "status" ? st : s;
          var val = src[f.key];
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

    var stateRows = Object.entries(s).map(function (e) {
      return [e[0].replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); }), e[1]];
    });
    var statusRows = Object.entries(st).map(function (e) {
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
        var toggles = container.querySelectorAll(".settings-toggle[data-key='" + ctrl.key + "']");
        toggles.forEach(function (el) {
          el.addEventListener("click", function () {
            var on = this.classList.toggle("on");
            config[ctrl.key] = on;
            saveCallback({ [ctrl.key]: on });
          });
        });
        break;

      case "text":
        var textInput = container.querySelector(".settings-input[data-key='" + ctrl.key + "']");
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
        var pwInput = container.querySelector(".settings-password-input[data-key='" + ctrl.key + "']");
        var pwToggle = container.querySelector(".settings-password-toggle[data-key='" + ctrl.key + "']");
        if (pwInput) {
          var pwTimer = null;
          pwInput.addEventListener("input", function () {
            clearTimeout(pwTimer);
            var val = this.value;
            pwTimer = setTimeout(function () {
              config[ctrl.key] = val;
              saveCallback({ [ctrl.key]: val });
            }, 400);
          });
        }
        if (pwToggle) {
          pwToggle.addEventListener("click", function (e) {
            e.preventDefault();
            var inp = container.querySelector(".settings-password-input[data-key='" + ctrl.key + "']");
            if (inp) {
              var isPw = inp.type === "password";
              inp.type = isPw ? "text" : "password";
              pwToggle.querySelector(".material-icons-outlined").textContent = isPw ? "visibility" : "visibility_off";
            }
          });
        }
        break;

      case "select":
        var selectEl = container.querySelector(".settings-select[data-key='" + ctrl.key + "']");
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
        var sliderEl = container.querySelector(".settings-slider[data-key='" + ctrl.key + ""]');
        if (sliderEl) {
          var unit = ctrl.unit || "";
          sliderEl.addEventListener("input", function () {
            var val = this.value;
            var display = container.querySelector("[data-display-for='" + ctrl.key + "']");
            if (display) display.textContent = val + unit;
            clearTimeout(self._saveTimers[ctrl.key]);
            self._saveTimers[ctrl.key] = setTimeout(function () {
              config[ctrl.key] = parseFloat(val);
              saveCallback({ [ctrl.key]: parseFloat(val) });
            }, 200);
          });
        }
        break;

      case "number":
        var numInput = container.querySelector(".settings-number-input[data-key='" + ctrl.key + "']");
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
        var pickerInput = container.querySelector(".settings-input[data-key='" + ctrl.key + "']");
        var pickerBtn = container.querySelector(".settings-picker-btn[data-target='" + ctrl.key + "']");
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
            if (window.pywebview && window.pywebview.api && window.pywebview.api.browse_exe) {
              window.pywebview.api.browse_exe().then(function (path) {
                if (path && pickerInput) {
                  pickerInput.value = path;
                  config[ctrl.key] = path;
                  saveCallback({ [ctrl.key]: path });
                }
              }).catch(function () {});
            }
          });
        }
        break;
    }
  }

  /* ── Bind a single plugin control ───────────────────────────── */

  _bindPluginControl(container, ctrl, pluginName, pluginConfig, savePluginCallback) {
    var self = this;

    switch (ctrl.type) {
      case "toggle":
        var toggles = container.querySelectorAll(".settings-toggle[data-key='" + ctrl.key + "']");
        toggles.forEach(function (el) {
          el.addEventListener("click", function () {
            var on = this.classList.toggle("on");
            pluginConfig[ctrl.key] = on;
            savePluginCallback(pluginName, ctrl.key, on);
          });
        });
        break;

      case "text":
        var textInput = container.querySelector(".settings-input[data-key='" + ctrl.key + "']");
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
        var pwInput = container.querySelector(".settings-password-input[data-key='" + ctrl.key + "']");
        var pwToggle = container.querySelector(".settings-password-toggle[data-key='" + ctrl.key + "']");
        if (pwInput) {
          var pwTimer = null;
          pwInput.addEventListener("input", function () {
            clearTimeout(pwTimer);
            var val = this.value;
            pwTimer = setTimeout(function () {
              pluginConfig[ctrl.key] = val;
              savePluginCallback(pluginName, ctrl.key, val);
            }, 400);
          });
        }
        if (pwToggle) {
          pwToggle.addEventListener("click", function (e) {
            e.preventDefault();
            var inp = container.querySelector(".settings-password-input[data-key='" + ctrl.key + "']");
            if (inp) {
              var isPw = inp.type === "password";
              inp.type = isPw ? "text" : "password";
              pwToggle.querySelector(".material-icons-outlined").textContent = isPw ? "visibility" : "visibility_off";
            }
          });
        }
        break;

      case "select":
        var selectEl = container.querySelector(".settings-select[data-key='" + ctrl.key + "']");
        if (selectEl) {
          selectEl.addEventListener("change", function () {
            var val = this.value;
            pluginConfig[ctrl.key] = val;
            savePluginCallback(pluginName, ctrl.key, val);
          });
        }
        break;

      case "slider":
        var sliderEl = container.querySelector(".settings-slider[data-key='" + ctrl.key + "']");
        if (sliderEl) {
          var unit = ctrl.unit || "";
          sliderEl.addEventListener("input", function () {
            var val = this.value;
            var display = container.querySelector("[data-display-for='" + ctrl.key + "']");
            if (display) display.textContent = val + unit;
            clearTimeout(self._saveTimers[ctrl.key]);
            self._saveTimers[ctrl.key] = setTimeout(function () {
              pluginConfig[ctrl.key] = parseFloat(val);
              savePluginCallback(pluginName, ctrl.key, parseFloat(val));
            }, 200);
          });
        }
        break;

      case "number":
        var numInput = container.querySelector(".settings-number-input[data-key='" + ctrl.key + "']");
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
        var pickerInput = container.querySelector(".settings-input[data-key='" + ctrl.key + "']");
        var pickerBtn = container.querySelector(".settings-picker-btn[data-target='" + ctrl.key + "']");
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

  _esc(s) {
    if (!s) return "";
    var d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }
}
