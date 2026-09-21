#!/usr/bin/env node
// One-off, parser-verified rebuild of HTML/deck.js from HTML/script.js.
//
// The prior manual line-range extraction corrupted scope boundaries: a
// function's closing brace was dropped, and a later "fix" closed it ~2850
// lines later, silently nesting nearly the whole panel implementation inside
// updateViewportMode()'s local scope. `node --check` cannot catch this kind
// of bug because it only validates that the *file* is brace-balanced overall,
// not that each top-level declaration closes where intended.
//
// This script parses script.js with acorn (a real JS parser, not a hand
// rolled brace/regex scanner) and extracts each required top-level
// declaration by its exact AST node [start, end) offsets - which is immune
// to string/regex/template/comment ambiguity entirely, since acorn already
// resolved it during parsing.
"use strict";
const fs = require("fs");
const path = require("path");
const acorn = require("acorn");

const ROOT = path.join(__dirname, "..");
const srcPath = path.join(ROOT, "HTML", "script.js");
const src = fs.readFileSync(srcPath, "utf8");

const ast = acorn.parse(src, { ecmaVersion: 2022, sourceType: "script", locations: true });

// The whole file is `(function () { ...body... })();` - an ExpressionStatement
// wrapping a CallExpression whose callee is the FunctionExpression. Find that
// function's body (a BlockStatement) and index its direct statements by name.
function findOuterIifeBody(programNode) {
  for (const stmt of programNode.body) {
    if (stmt.type !== "ExpressionStatement") continue;
    let expr = stmt.expression;
    if (expr.type === "UnaryExpression") expr = expr.argument; // e.g. !function(){}()
    if (expr.type !== "CallExpression") continue;
    const callee = expr.callee;
    if (callee.type === "FunctionExpression" && callee.body && callee.body.type === "BlockStatement") {
      return callee.body;
    }
  }
  throw new Error("could not locate outer IIFE body in script.js");
}

const iifeBody = findOuterIifeBody(ast);
const topStatements = iifeBody.body; // array of top-level statements, in order

function lineOf(offset) { return src.slice(0, offset).split("\n").length; }

function findTopLevel(name, minLine) {
  for (const stmt of topStatements) {
    if (minLine && lineOf(stmt.start) < minLine) continue;
    if (stmt.type === "FunctionDeclaration" && stmt.id && stmt.id.name === name) return stmt;
    if (stmt.type === "VariableDeclaration") {
      for (const decl of stmt.declarations) {
        if (decl.id && decl.id.type === "Identifier" && decl.id.name === name) return stmt;
      }
    }
  }
  return null;
}

function extractTopLevel(name) {
  const node = findTopLevel(name);
  if (!node) throw new Error("top-level declaration not found: " + name);
  const text = src.slice(node.start, node.end);
  console.error(`[ok] ${name} => lines ${lineOf(node.start)}-${lineOf(node.end)} (${node.type})`);
  return { name, node, text };
}

const wantedNames = [
  "updateViewportMode",
  "MDI_CACHE_VERSION",
  "_MDI_BUILTIN",
  "mdiCache",
  "mdiFetched",
  "isLightColor",
  "resolveProgressFillColor",
  "mdiChar",
  "applyMdiIcons",
  "preloadBoardIcons",
  "mdiPreload",
  "defaultCoreSlots",
  "CORE_ACTION_DEFS",
  "isComponentEnabled",
];

const results = wantedNames.map(extractTopLevel);

// window.mdiChar = mdiChar; is emitted immediately after the mdiChar function
// in the original file; it's an assignment, not a name-keyed declaration.
const mdiCharAssignNode = (() => {
  for (const stmt of topStatements) {
    if (stmt.type === "ExpressionStatement") {
      const e = stmt.expression;
      if (e.type === "AssignmentExpression" && e.left.type === "MemberExpression" &&
          e.left.object.type === "Identifier" && e.left.object.name === "window" &&
          e.left.property.type === "Identifier" && e.left.property.name === "mdiChar") {
        return stmt;
      }
    }
  }
  throw new Error("window.mdiChar assignment not found");
})();
results.push({ name: "window.mdiChar assign", node: mdiCharAssignNode, text: src.slice(mdiCharAssignNode.start, mdiCharAssignNode.end) });
console.error(`[ok] window.mdiChar assign => lines ${lineOf(mdiCharAssignNode.start)}-${lineOf(mdiCharAssignNode.end)}`);

// ---- Panel-view implementation: extract each required top-level function
// individually by name (not by a fixed line range), so one function's body
// can never swallow another's.
const panelVarNames = [
  "boxScrollLeft",
  "lastNotifKey",
  "pendingNotifSlide",
  "notifDismissTimer",
  "notifOpen",
  "notifReturnPage",
  "lastAppMixerSig",
  "GAUGE_CIRCUMFERENCE",
  "_lastGaugeVals",
];
const panelFnNames = [
  "slotSig",
  "ensurePanelOverlay",
  "openPanelView",
  "panelViewConfig",
  "panelProfileCurrent",
  "currentBoard",
  "panelViewSignature",
  "getPanelLayoutSpec",
  "layoutPanelBox",
  "rememberBoxScroll",
  "restoreBoxScroll",
  "getCurBoxPage",
  "getMaxBoxPage",
  "renderPanelView",
  "boardPagesHtml",
  "utilTilesHtml",
  "formatTileTitle",
  "parseProgressPercentage",
  "coreTilesHtml",
  "panelTileHtml",
  "gaugeNum",
  "panelGauge",
  "linkifyText",
  "notifKey",
  "notifHtml",
  "notifCardEl",
  "openNotifDrawer",
  "closeNotifDrawer",
  "normalizeNotifTheme",
  "triggerNotificationSlide",
  "setupNotifDrawerGestures",
  "fetchPanelLive",
  "wirePanelView",
  "wireSliderInputs",
  "panelSliderHtml",
  "appMixerHtml",
  "updatePanelView",
  "updateGauge",
  "runSlotAction",
  "paintPanelRanges",
];
const panelBlocks = [];
const missingPanelFns = [];
for (const name of panelVarNames) {
  const node = findTopLevel(name);
  if (!node) { missingPanelFns.push(name); continue; }
  panelBlocks.push({ name, node, text: src.slice(node.start, node.end) });
  console.error(`[ok] ${name} => lines ${lineOf(node.start)}-${lineOf(node.end)}`);
}
for (const name of panelFnNames) {
  // panelSliderHtml exists twice: an admin design-preview version (disabled
  // input, "prev-slider" class) earlier in the file, and the real interactive
  // live-panel version later. Always take the LAST (live-panel) definition.
  const minLine = name === "panelSliderHtml" ? 10000 : undefined;
  const node = findTopLevel(name, minLine);
  if (!node) { missingPanelFns.push(name); continue; }
  panelBlocks.push({ name, node, text: src.slice(node.start, node.end) });
  console.error(`[ok] ${name} => lines ${lineOf(node.start)}-${lineOf(node.end)}`);
}
if (missingPanelFns.length) {
  console.error("[info] not found at top level (may be nested/inline, skipped): " + missingPanelFns.join(", "));
}
panelBlocks.sort((a, b) => a.node.start - b.node.start); // preserve original file order

// ---- Screensaver: extract the REAL mobile-safe implementation (wake lock,
// OLED anti-burn-in drift, locale-aware clock formatting) rather than a
// hand-written approximation, so behavior matches the original exactly.
const screensaverFnNames = [
  "getScreensaverTimeoutMs",
  "ssEl",
  "updateScreensaverClock",
  "driftScreensaverLock",
  "resetScreensaverTimer",
  "showScreensaver",
  "hideScreensaver",
  "screensaverWakeOnEvent",
  "ssArmForPanelView",
  "ssDisarmForPanelView",
];
const screensaverVarNames = ["SS_DRIFT_INTERVAL_MS", "SS_CLOCK_INTERVAL_MS", "ssIdleTimer", "ssDriftTimer", "ssClockTimer", "ssActive"];
const screensaverBlocks = [];
for (const name of screensaverVarNames) {
  const node = findTopLevel(name);
  if (!node) throw new Error("screensaver var not found: " + name);
  screensaverBlocks.push({ name, node, text: src.slice(node.start, node.end) });
}
for (const name of screensaverFnNames) {
  const node = findTopLevel(name);
  if (!node) throw new Error("screensaver fn not found: " + name);
  screensaverBlocks.push({ name, node, text: src.slice(node.start, node.end) });
}
screensaverBlocks.sort((a, b) => a.node.start - b.node.start);
console.error(`[ok] extracted ${screensaverBlocks.length} real screensaver block(s)`);

// ---- Notification link click wiring: a single top-level document click
// listener in script.js dispatches `.pv-notif-link` taps to openUrlOnPc().
// Extract it verbatim; it calls the header's inert openUrlOnPc() stub, so
// tapping a link no-ops instead of throwing (LAN clients cannot open URLs on
// the host - see app/server policy).
const notifClickListenerNode = (() => {
  for (const stmt of topStatements) {
    if (stmt.type === "ExpressionStatement" && stmt.expression.type === "CallExpression") {
      const callee = stmt.expression.callee;
      if (callee.type === "MemberExpression" && callee.object.type === "Identifier" &&
          callee.object.name === "document" && callee.property.name === "addEventListener") {
        const args = stmt.expression.arguments;
        if (args[0] && args[0].value === "click" && src.slice(stmt.start, stmt.end).includes("pv-notif-link")) {
          return stmt;
        }
      }
    }
  }
  throw new Error("notification link click listener not found");
})();
console.error(`[ok] notif link click listener => lines ${lineOf(notifClickListenerNode.start)}-${lineOf(notifClickListenerNode.end)}`);

// ---- Screensaver interaction wiring: an anonymous top-level IIFE that wires
// touch/pointer/click activity to reset/wake the screensaver, plus unlock-tap
// handlers on the overlay itself. Located by distinctive content rather than
// name, since it's an anonymous IIFE, not a named declaration.
const ssWiringNode = (() => {
  for (const stmt of topStatements) {
    if (stmt.type === "ExpressionStatement" && stmt.expression.type === "CallExpression") {
      const text = src.slice(stmt.start, stmt.end);
      if (text.includes("iris-screensaver") && text.includes("unlockTap") && text.includes("onActivity")) {
        return stmt;
      }
    }
  }
  throw new Error("screensaver interaction wiring IIFE not found");
})();
console.error(`[ok] screensaver interaction wiring => lines ${lineOf(ssWiringNode.start)}-${lineOf(ssWiringNode.end)}`);



// ---- Assemble deck.js ----
const header = fs.readFileSync(path.join(ROOT, "tools", "deck_header.js.tmpl"), "utf8");
const footer = fs.readFileSync(path.join(ROOT, "tools", "deck_footer.js.tmpl"), "utf8");

const body = results.map((r) => r.text).join("\n\n")
  + "\n\n" + panelBlocks.map((r) => r.text).join("\n\n")
  + "\n\n" + screensaverBlocks.map((r) => r.text).join("\n\n")
  + "\n\n" + src.slice(notifClickListenerNode.start, notifClickListenerNode.end)
  + "\n\n" + src.slice(ssWiringNode.start, ssWiringNode.end);
const assembled = header.trimEnd() + "\n\n" + body + "\n\n" + footer.trimStart();

const outPath = path.join(ROOT, "HTML", "deck.js");
fs.writeFileSync(outPath, assembled, "utf8");
console.error("Wrote " + outPath + " (" + assembled.length + " chars)");

// ---- Self-verification: re-parse the ASSEMBLED file with acorn and assert
// every critical function is declared at true top level inside the outer
// IIFE (not accidentally nested inside another function/block).
const assembledAst = acorn.parse(assembled, { ecmaVersion: 2022, sourceType: "script" });
const assembledIifeBody = findOuterIifeBody(assembledAst);
const assembledTopNames = new Set();
for (const stmt of assembledIifeBody.body) {
  if (stmt.type === "FunctionDeclaration" && stmt.id) assembledTopNames.add(stmt.id.name);
  if (stmt.type === "VariableDeclaration") {
    for (const decl of stmt.declarations) if (decl.id && decl.id.type === "Identifier") assembledTopNames.add(decl.id.name);
  }
}
const mustBeTopLevel = [
  "updateViewportMode", "mdiChar", "applyMdiIcons", "renderPanelView", "boardPagesHtml",
  "panelTileHtml", "wirePanelView", "wireSliderInputs", "updatePanelView", "paintPanelRanges",
  "fetchPanelLive", "loadPanel", "connectWs", "showScreensaver", "hideScreensaver",
  "ssArmForPanelView", "screensaverWakeOnEvent",
];
let failed = false;
for (const name of mustBeTopLevel) {
  if (assembledTopNames.has(name)) {
    console.error(`[ok] ${name} at correct top-level scope`);
  } else {
    console.error(`[FAIL] ${name} missing or not top-level - would be a ReferenceError at call sites`);
    failed = true;
  }
}
if (failed) {
  console.error("SCOPE VERIFICATION FAILED");
  process.exit(1);
}
console.error("SCOPE VERIFICATION PASSED");

// ---- Reference-integrity check: walk the assembled IIFE body and collect
// every identifier that is READ (call, bare reference, member-object) but
// never declared anywhere in scope (function/var/let/const, function params,
// catch clause bindings) and isn't a known browser/JS global. This catches
// "helper function silently omitted from extraction" bugs that a syntax
// check alone cannot detect.
const walk = require("acorn-walk");
const declared = new Set();
const KNOWN_GLOBALS = new Set([
  "window", "document", "navigator", "location", "console", "localStorage",
  "sessionStorage", "fetch", "WebSocket", "Object", "Array", "String", "Number",
  "Boolean", "Date", "RegExp", "Math", "JSON", "Promise", "Set", "Map", "WeakMap",
  "Symbol", "Error", "TypeError", "encodeURIComponent", "decodeURIComponent",
  "parseInt", "parseFloat", "isNaN", "isFinite", "setTimeout", "clearTimeout",
  "setInterval", "clearInterval", "requestAnimationFrame", "cancelAnimationFrame",
  "Infinity", "NaN", "undefined", "globalThis", "self", "top", "performance",
  "CustomEvent", "Event", "MutationObserver", "ResizeObserver", "IntersectionObserver",
  "structuredClone", "queueMicrotask", "matchMedia", "getComputedStyle", "Intl",
]);
function collectDeclared(node) {
  walk.full(node, (n) => {
    if ((n.type === "FunctionDeclaration" || n.type === "FunctionExpression" || n.type === "ArrowFunctionExpression")) {
      if (n.id) declared.add(n.id.name);
      for (const p of n.params) walk.full(p, (pn) => { if (pn.type === "Identifier") declared.add(pn.name); });
    }
    if (n.type === "VariableDeclarator" && n.id.type === "Identifier") declared.add(n.id.name);
    if (n.type === "CatchClause" && n.param && n.param.type === "Identifier") declared.add(n.param.name);
  });
}
collectDeclared(assembledIifeBody);
KNOWN_GLOBALS.forEach((g) => declared.add(g));

const referenced = new Map(); // name -> first offset seen
walk.full(assembledIifeBody, (n, state, ancestors) => {
  if (n.type !== "Identifier") return;
  const parent = ancestors[ancestors.length - 2];
  if (!parent) return;
  // Skip identifiers that are declaration targets or property keys/labels
  // (those aren't "reads" of an outer binding).
  if (parent.type === "VariableDeclarator" && parent.id === n) return;
  if ((parent.type === "FunctionDeclaration" || parent.type === "FunctionExpression" || parent.type === "ArrowFunctionExpression") && (parent.id === n || parent.params.includes(n))) return;
  if (parent.type === "MemberExpression" && parent.property === n && !parent.computed) return;
  if (parent.type === "Property" && parent.key === n && !parent.computed) return;
  if (parent.type === "CatchClause" && parent.param === n) return;
  if (parent.type === "LabeledStatement" || parent.type === "BreakStatement" || parent.type === "ContinueStatement") return;
  if (!referenced.has(n.name)) referenced.set(n.name, n.start);
});

const unresolved = [];
for (const [name, offset] of referenced) {
  if (!declared.has(name)) unresolved.push([name, lineOf(offset)]);
}
if (unresolved.length) {
  console.error("\n[FAIL] Unresolved identifiers referenced in deck.js (likely missing extracted helpers):");
  unresolved.sort((a, b) => a[1] - b[1]).forEach(([name, line]) => console.error(`  ${name} (first used near line ${line})`));
  process.exit(1);
}
console.error("REFERENCE INTEGRITY CHECK PASSED (no unresolved identifiers)");
