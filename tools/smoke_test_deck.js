// One-off smoke test: load deck.html + deck.js into a real jsdom DOM, stub
// network/timers, and assert that init runs without throwing (this is the
// exact bug class that the earlier line-slicing regression caused — a
// misplaced closing brace nested the whole panel implementation inside
// updateViewportMode(), which passed `node --check` but threw ReferenceError
// at runtime). Static analysis (syntax + scope + reference checks) is not
// sufficient by itself; this actually executes the script.
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(ROOT, "HTML", "deck.html"), "utf8");
const deckJs = fs.readFileSync(path.join(ROOT, "HTML", "deck.js"), "utf8");

const errors = [];

const dom = new JSDOM(html, {
  url: "http://10.0.0.10:15505/",
  runScripts: "outside-only",
  pretendToBeVisual: true,
  resources: undefined,
});
const { window } = dom;

// Stub browser APIs jsdom doesn't implement / that must not hit the network.
window.fetch = function () {
  return Promise.resolve({
    status: 200,
    ok: true,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(""),
  });
};
window.WebSocket = function () {
  this.close = function () {};
  this.send = function () {};
};
window.navigator.serviceWorker = { register: () => Promise.resolve() };
window.localStorage = window.localStorage || { getItem: () => null, setItem: () => {}, removeItem: () => {} };
window.matchMedia = window.matchMedia || function () { return { matches: false, addListener() {}, removeListener() {} }; };
window.requestAnimationFrame = window.requestAnimationFrame || function (cb) { return setTimeout(cb, 0); };
window.onerror = function (msg, url, line, col, error) {
  errors.push({ msg, line, col, stack: error && error.stack });
  return false;
};
window.addEventListener("error", (e) => {
  errors.push({ msg: e.message, stack: e.error && e.error.stack });
});

try {
  // theme.js is a separate <script src> the real page loads; irrelevant to
  // deck.js execution, so we just skip it and directly run deck.js in-context.
  window.eval(deckJs);
} catch (err) {
  errors.push({ msg: "synchronous throw during deck.js eval", stack: err.stack });
}

// Let any queued microtasks/timers (loadPanel().then, setInterval, connectWs
// retry, etc.) run for a tick before asserting.
setTimeout(() => {
  const panelView = window.document.getElementById("panel-view");
  if (!panelView) {
    console.error("[FAIL] #panel-view element missing from DOM");
    process.exit(1);
  }
  if (errors.length) {
    console.error("[FAIL] deck.js threw " + errors.length + " error(s) during load/init:");
    for (const e of errors) console.error("  - " + e.msg + (e.stack ? "\n    " + e.stack.split("\n").slice(0, 3).join("\n    ") : ""));
    process.exit(1);
  }
  const requiredSelectors = [
    ".pv-screen", ".pv-scroll", ".pv-box", ".pv-track",
    ".pv-gauges", ".pv-frame", ".pv-util", ".pv-core", ".pv-sliders", "#pv-notif",
  ];
  const missing = requiredSelectors.filter((sel) => !panelView.querySelector(sel));
  if (missing.length) {
    console.error("[FAIL] expected panel DOM structure missing: " + missing.join(", "));
    console.error("panel-view innerHTML snippet: " + panelView.innerHTML.slice(0, 400));
    process.exit(1);
  }
  console.error("[ok] deck.js loaded and initialized with zero uncaught errors");
  console.error("[ok] #panel-view present in DOM with expected structure (" + requiredSelectors.join(", ") + ")");
  console.error("SMOKE TEST PASSED");
  process.exit(0);
}, 250);
