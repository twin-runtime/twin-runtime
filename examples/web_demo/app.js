"use strict";

let current = null;
let isBusy = false;
let lastCheck = null;
let toastTimer = null;
const byId = (id) => document.getElementById(id);
const actions = document.querySelectorAll("[data-action]");

function titleCase(value) {
  if (value === null || value === undefined) return "None";
  return String(value).replaceAll("_", " ").replace(/^./, (s) => s.toUpperCase());
}

function showToast(message) {
  const el = byId("toast");
  el.textContent = message;
  el.classList.add("is-visible");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-visible"), 4000);
}

function setText(id, value) {
  byId(id).textContent = value;
}

function addText(parent, tagName, className, value) {
  const node = document.createElement(tagName);
  node.className = className;
  node.textContent = value;
  parent.appendChild(node);
  return node;
}

function renderLog(data) {
  const audit = byId("audit-events");
  audit.replaceChildren();
  for (const event of data.audit) {
    const row = document.createElement("div");
    row.className = "event";
    addText(row, "span", "event-index", "#" + String(event.session_sequence).padStart(2, "0"));
    const right = document.createElement("div");
    addText(right, "div", "event-name", event.event_type);
    const detail = event.data?.reason || event.data?.mode || event.data?.to_mode || "";
    if (detail) addText(right, "div", "event-data", String(detail));
    row.appendChild(right);
    audit.appendChild(row);
  }
  if (data.audit.length === 0) addText(audit, "p", "muted", "No audit events yet.");
  const checks = byId("command-checks");
  checks.replaceChildren();
  for (const check of data.command_checks.slice(0, 5)) {
    const row = document.createElement("div");
    row.className = "check-entry " + (check.accepted ? "is-good" : "is-bad");
    addText(row, "span", "", check.label);
    addText(row, "b", "", check.accepted ? "ACCEPTED" : "DENIED · " + check.reason);
    checks.appendChild(row);
  }
  if (data.command_checks.length === 0) addText(checks, "p", "muted", "No commands tested yet.");
}

function render(data) {
  current = data;
  const session = data.session;
  const status = session.session_status;
  const mode = session.presence_mode;
  const bridge = status === "active" && mode === "bridge";
  const autonomous = status === "active" && mode === "autonomous";
  const suspended = status === "suspended";
  setText("session-status", titleCase(status));
  setText("presence-mode", titleCase(mode));
  setText("mode-value", suspended ? "Suspended" : titleCase(mode || "standby"));
  const stage = autonomous ? 0 : bridge ? 1 : suspended ? 3 : -1;
  document.querySelectorAll(".step").forEach((el, index) => {
    el.classList.toggle("is-done", stage >= 0 && index < stage);
    el.classList.toggle("is-current", index === stage || (index === 2 && suspended));
  });
  for (const [id, active, done] of [
    ["autonomous", autonomous, bridge || suspended],
    ["bridge", bridge, suspended],
    ["suspended", suspended, false],
  ]) {
    const el = byId("pill-" + id);
    el.classList.toggle("is-active", active);
    el.classList.toggle("is-done", done);
  }

  for (const entry of data.domains) {
    const el = byId("domain-" + entry.name);
    el.className = "controller " + (entry.edge_authorized_now ?
      (entry.controller === "human-owner" ? "is-owner" : "is-ai") : "is-off");
    el.textContent = entry.edge_authorized_now ?
      (entry.controller === "human-owner" ? "Identity Owner" : "AI Agent") : "No authority";
    setText("domain-" + entry.name + "-gen", "Generation " + (entry.generation ?? "-"));
  }

  const permitted = {
    start: status === "ready",
    join: autonomous,
    disconnect: bridge,
    ai_speak: autonomous || bridge,
    ai_wave: autonomous,
    owner_wave: bridge,
    stale_ai_wave: bridge || suspended,
    stale_owner_wave: suspended,
    reset: true,
  };
  for (const button of actions) button.disabled = isBusy || !permitted[button.dataset.action];

  const result = byId("command-result");
  result.classList.toggle("is-accepted", Boolean(data.last_command?.accepted));
  result.classList.toggle("is-denied", Boolean(data.last_command && !data.last_command.accepted));
  if (data.last_command) {
    result.lastElementChild.textContent = data.last_command.label + " → " +
      (data.last_command.accepted ? "accepted" : "rejected (" + data.last_command.reason + ")");
  } else {
    result.lastElementChild.textContent = "Select a scenario step, then send a simulated command.";
  }
  if (suspended) setText("scene-line", "Session suspended. No controller can send new accepted commands.");
  else if (bridge) setText("scene-line", "Bridge: Owner holds gesture; AI continues conversation.");
  else if (autonomous) setText("scene-line", "Autonomous: AI holds conversation and gesture control.");
  else setText("scene-line", "Ready to start a simulated session.");
  renderLog(data);
}

function animateAccepted(check) {
  if (!check || check === lastCheck) return;
  lastCheck = check;
  if (!check.accepted) return;
  const robot = byId("robot");
  robot.classList.remove("is-waving", "is-talking");
  // Force restart only for a new, accepted demo command (never for a rejected command).
  void robot.offsetWidth;
  robot.classList.add(check.kind === "wave" ? "is-waving" : "is-talking");
  window.setTimeout(() => robot.classList.remove("is-waving", "is-talking"), 2400);
}

async function loadState() {
  const response = await fetch("/api/state", {cache: "no-store"});
  if (!response.ok) throw Error("Cannot read runtime state");
  render(await response.json());
}

async function runAction(action) {
  if (isBusy || !current) return;
  isBusy = true;
  actions.forEach((b) => { b.disabled = true; });
  try {
    const response = await fetch("/api/action", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Demo-Token": current.csrf_token},
      body: JSON.stringify({action}),
    });
    const value = await response.json();
    if (!response.ok) throw Error(value.error || "Action rejected");
    if (["ai_speak", "ai_wave", "owner_wave", "stale_ai_wave", "stale_owner_wave"].includes(action)) {
      animateAccepted(value.last_command);
    }
    render(value);
  } catch (error) {
    showToast("Demo action failed: " + error.message);
    try { await loadState(); } catch { /* error already visible */ }
  } finally {
    isBusy = false;
    if (current) render(current);
  }
}

for (const button of actions) button.addEventListener("click", () => runAction(button.dataset.action));
loadState().catch((error) => showToast(error.message));
window.setInterval(() => {
  if (!isBusy) loadState().catch(() => showToast("Could not refresh local runtime state"));
}, 3000);
