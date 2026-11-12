"use strict";

let current = null;
let isBusy = false;
let animationTimer = null;
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
  const totalmersion = status === "active" && mode === "totalmersion";
  const suspended = status === "suspended";
  const visited = new Set(data.audit
    .filter((event) => event.event_type === "presence_mode.changed")
    .map((event) => event.data?.to_mode));
  const visitedBridge = bridge || totalmersion || visited.has("bridge");
  const visitedTotalMersion = totalmersion || visited.has("totalmersion");
  setText("session-status", titleCase(status));
  setText("presence-mode", titleCase(mode));
  // Suspended is a Session status, not a fourth Presence Mode.
  setText("mode-value", suspended ? "None (session suspended)" : titleCase(mode || "standby"));
  const stage = autonomous ? 0 : bridge ? 1 : totalmersion ? 2 : -1;
  document.querySelectorAll(".step").forEach((el, index) => {
    const completed = stage >= 0 ? index < stage :
      suspended && index < (visitedTotalMersion ? 3 : visitedBridge ? 2 : 0);
    el.classList.toggle("is-done", completed);
    el.classList.toggle("is-current", index === stage);
  });
  for (const [id, active, done] of [
    ["autonomous", autonomous, bridge || totalmersion || suspended],
    ["bridge", bridge, totalmersion || (suspended && visitedBridge)],
    ["totalmersion", totalmersion, suspended && visitedTotalMersion],
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
    totalmersion: bridge,
    disconnect: bridge || totalmersion,
    ai_speak: autonomous || bridge,
    ai_wave: autonomous,
    owner_speak: totalmersion,
    owner_wave: bridge || totalmersion,
    stale_ai_wave: bridge || totalmersion || suspended,
    stale_ai_speak: totalmersion || (suspended && visitedTotalMersion),
    stale_owner_wave: suspended,
    reset: true,
  };
  for (const button of actions) button.disabled = isBusy || !permitted[button.dataset.action];
  byId("run-full-scenario").disabled = isBusy;

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
  else if (totalmersion) setText("scene-line", "TotalMersion: Owner holds conversation and gesture. Speech is visual only.");
  else if (bridge) setText("scene-line", "Bridge: Owner holds gesture; AI continues conversation.");
  else if (autonomous) setText("scene-line", "Autonomous: AI holds conversation and gesture control.");
  else setText("scene-line", "Ready to start a simulated session.");
  renderLog(data);
}

function clearRobotAction() {
  if (animationTimer !== null) window.clearTimeout(animationTimer);
  animationTimer = null;
  byId("robot").classList.remove("is-waving", "is-talking");
  byId("robot-action-label").classList.remove("is-visible");
}

function animateAccepted(check) {
  // Visual feedback is only triggered by an accepted Edge check. No robot is driven.
  if (!check || !check.accepted) return;
  const robot = byId("robot");
  const label = byId("robot-action-label");
  if (animationTimer !== null) window.clearTimeout(animationTimer);
  robot.classList.remove("is-waving", "is-talking");
  // Restart the CSS animation for consecutive accepted commands of the same kind.
  void robot.offsetWidth;
  const waving = check.kind === "wave";
  robot.classList.add(waving ? "is-waving" : "is-talking");
  label.textContent = waving ?
    (check.controller === "human-owner" ? "OWNER GESTURE · SIMULATED" : "AI GESTURE · SIMULATED") :
    (check.controller === "human-owner" ? "OWNER SPEECH · SIMULATED" : "AI SPEECH · SIMULATED");
  label.classList.add("is-visible");
  animationTimer = window.setTimeout(() => {
    robot.classList.remove("is-waving", "is-talking");
    label.classList.remove("is-visible");
    animationTimer = null;
  }, 2600);
}

async function loadState() {
  const response = await fetch("/api/state", {cache: "no-store"});
  if (!response.ok) throw Error("Cannot read runtime state");
  render(await response.json());
}

async function applyAction(action) {
  const response = await fetch("/api/action", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Demo-Token": current.csrf_token},
    body: JSON.stringify({action}),
  });
  const value = await response.json();
  if (!response.ok) throw Error(value.error || "Action rejected");
  if (action === "reset" || action === "disconnect") clearRobotAction();
  if (["ai_speak", "ai_wave", "owner_speak", "owner_wave", "stale_ai_wave", "stale_ai_speak", "stale_owner_wave"].includes(action)) {
    animateAccepted(value.last_command);
  }
  render(value);
  return value;
}

async function runAction(action) {
  if (isBusy || !current) return;
  isBusy = true;
  render(current);
  try {
    await applyAction(action);
  } catch (error) {
    showToast("Demo action failed: " + error.message);
    try { await loadState(); } catch { /* error already visible */ }
  } finally {
    isBusy = false;
    if (current) render(current);
  }
}

// These are the same HTTP actions as manual clicks, never a mocked replay.
const fullScenarioSteps = [
  {action: "reset", label: "Fresh local Core + Edge", status: "ready", delay: 350},
  {action: "start", label: "Autonomous: AI holds both domains", mode: "autonomous", delay: 900},
  {action: "ai_wave", label: "AI wave accepted by Edge", accepted: true, delay: 2700},
  {action: "join", label: "Bridge: Owner takes gesture", mode: "bridge", delay: 1100},
  {action: "owner_wave", label: "Owner wave accepted by Edge", accepted: true, delay: 2700},
  {action: "totalmersion", label: "TotalMersion: Owner takes both domains", mode: "totalmersion", delay: 1150},
  {action: "owner_speak", label: "Owner speech accepted (visual only)", accepted: true, delay: 2700},
  {action: "stale_ai_speak", label: "Old AI conversation Lease denied", accepted: false, reason: "stale_generation", delay: 1500},
  {action: "disconnect", label: "Simulated disconnect: Session suspended", status: "suspended", delay: 1300},
  {action: "stale_owner_wave", label: "Disconnected Owner Lease denied", accepted: false, reason: "revoked", delay: 0},
];

function verifyScenarioStep(step, state) {
  if (step.mode && state.session.presence_mode !== step.mode) {
    throw Error(step.action + " did not enter " + step.mode);
  }
  if (step.status && state.session.session_status !== step.status) {
    throw Error(step.action + " did not reach " + step.status);
  }
  if (step.accepted !== undefined) {
    if (!state.last_command || state.last_command.accepted !== step.accepted ||
        (step.reason && state.last_command.reason !== step.reason)) {
      throw Error(step.action + " produced an unexpected Edge decision");
    }
  }
}

async function runFullScenario() {
  if (isBusy || !current) return;
  isBusy = true;
  render(current); // Disable manual actions throughout the guided flow.
  const progress = byId("scenario-progress");
  try {
    for (const [index, step] of fullScenarioSteps.entries()) {
      progress.textContent = "Step " + (index + 1) + "/" + fullScenarioSteps.length + ": " + step.label;
      const state = await applyAction(step.action);
      verifyScenarioStep(step, state);
      if (step.delay) await new Promise((resolve) => setTimeout(resolve, step.delay));
    }
    progress.textContent = "Complete: 3 modes, accepted commands, revoked Leases, Session suspended.";
  } catch (error) {
    progress.textContent = "Scenario stopped: " + error.message + ". Use Run Full Scenario to restart.";
    showToast("Guided scenario stopped: " + error.message);
    try { await loadState(); } catch { /* error already visible */ }
  } finally {
    isBusy = false;
    if (current) render(current);
  }
}

for (const button of actions) button.addEventListener("click", () => runAction(button.dataset.action));
byId("run-full-scenario").addEventListener("click", runFullScenario);
loadState().catch((error) => showToast(error.message));
window.setInterval(() => {
  if (!isBusy) loadState().catch(() => showToast("Could not refresh local runtime state"));
}, 3000);
