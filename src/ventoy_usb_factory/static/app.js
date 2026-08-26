const state = {
  devices: [],
  isos: [],
  jobs: [],
  selectedDevices: new Set(),
  selectedIsos: new Set(),
  initialIsoSelectionApplied: false,
  jobEventStreams: new Map(),
};

const els = {
  devices: document.querySelector("[data-devices]"),
  isos: document.querySelector("[data-isos]"),
  jobs: document.querySelector("[data-jobs]"),
  confirmations: document.querySelector("[data-confirmations]"),
  start: document.querySelector("[data-start]"),
  error: document.querySelector("[data-error]"),
  summary: document.querySelector("[data-summary]"),
  refresh: document.querySelector("[data-refresh]"),
};

function formatBytes(value) {
  if (!value) return "unknown size";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function text(value, fallback = "unknown") {
  return value || fallback;
}

function buildElement(tagName, className, content) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  if (content !== undefined) element.textContent = content;
  return element;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }
  return body;
}

async function refreshAll() {
  clearError();
  try {
    const [devices, isos, jobs] = await Promise.all([
      fetchJson("/api/devices"),
      fetchJson("/api/isos"),
      fetchJson("/api/jobs"),
    ]);
    state.devices = devices;
    state.isos = isos;
    state.jobs = jobs;
    applyInitialIsoSelection(isos);
    watchRunningJobs(jobs);
    render();
  } catch (error) {
    showError(error.message);
  }
}

async function refreshJob(jobId) {
  const job = await fetchJson(`/api/jobs/${jobId}`);
  const index = state.jobs.findIndex((entry) => entry.id === job.id);
  if (index === -1) state.jobs.unshift(job);
  else state.jobs[index] = job;
  renderJobs();
  if (job.status !== "pending" && job.status !== "running") closeJobEventStream(job.id);
}

function watchRunningJobs(jobs) {
  for (const job of jobs) {
    if (job.status === "pending" || job.status === "running") watchJobEvents(job);
  }
}

function watchJobEvents(job) {
  if (!window.EventSource || state.jobEventStreams.has(job.id)) return;

  const stream = new EventSource(`/api/jobs/${job.id}/events`);
  state.jobEventStreams.set(job.id, stream);
  stream.addEventListener("message", async () => {
    try {
      await refreshJob(job.id);
    } catch (error) {
      showError(error.message);
    }
  });
  stream.addEventListener("error", () => closeJobEventStream(job.id));
}

function closeJobEventStream(jobId) {
  const stream = state.jobEventStreams.get(jobId);
  if (!stream) return;
  stream.close();
  state.jobEventStreams.delete(jobId);
}

function applyInitialIsoSelection(isos) {
  if (state.initialIsoSelectionApplied) return;
  for (const iso of isos) {
    if (iso.status === "ready") state.selectedIsos.add(iso.key);
  }
  state.initialIsoSelectionApplied = true;
}

function render() {
  renderDevices();
  renderIsos();
  renderConfirmations();
  renderJobs();
  updateStartState();
  els.summary.textContent = `${state.devices.length} devices scanned, ${state.selectedDevices.size} selected`;
}

function renderDevices() {
  els.devices.replaceChildren();
  if (state.devices.length === 0) {
    els.devices.append(emptyCard("No USB drives detected."));
    return;
  }

  for (const device of state.devices) {
    const eligible = device.safety === "eligible";
    const card = buildElement("article", `card device-card ${eligible ? "eligible" : "blocked"}`);
    const label = buildElement("label", "select-row");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.disabled = !eligible;
    checkbox.checked = state.selectedDevices.has(device.path);
    const path = buildElement("span", "mono", device.path);
    const details = document.createElement("dl");

    label.append(checkbox, path);
    details.append(
      definition("Model", text([device.vendor, device.model].filter(Boolean).join(" "))),
      definition("Size", formatBytes(device.size_bytes)),
      definition("Safety", device.safety_reason),
    );
    card.append(label, details);

    checkbox.addEventListener("change", (event) => {
      if (event.target.checked) state.selectedDevices.add(device.path);
      else state.selectedDevices.delete(device.path);
      renderConfirmations();
      updateStartState();
    });
    els.devices.append(card);
  }
}

function definition(term, description) {
  const wrapper = document.createElement("div");
  wrapper.append(buildElement("dt", null, term), buildElement("dd", null, description));
  return wrapper;
}

function renderIsos() {
  els.isos.replaceChildren();
  for (const iso of state.isos) {
    const ready = iso.status === "ready";
    const row = buildElement("label", `row-card ${ready ? "ready" : "blocked"}`);
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.disabled = !ready;
    checkbox.checked = state.selectedIsos.has(iso.key);
    const body = document.createElement("span");
    const name = buildElement("strong", null, iso.name);
    const message = buildElement("small", null, iso.message);
    const status = buildElement("code", null, iso.status);

    body.append(name, message);
    row.append(checkbox, body, status);
    checkbox.addEventListener("change", (event) => {
      if (event.target.checked) state.selectedIsos.add(iso.key);
      else state.selectedIsos.delete(iso.key);
      updateStartState();
    });
    els.isos.append(row);
  }
}

function renderConfirmations() {
  els.confirmations.replaceChildren();
  for (const path of state.selectedDevices) {
    const message = buildElement("p", "confirm-row");
    const pathLabel = buildElement("code", null, path);
    message.append("A popup confirmation will be required for ", pathLabel);
    els.confirmations.append(message);
  }
  if (state.selectedDevices.size === 0) {
    els.confirmations.append(emptyCard("Select an eligible USB drive to enable popup confirmation."));
  }
}

function renderJobs() {
  els.jobs.replaceChildren();
  if (state.jobs.length === 0) {
    els.jobs.append(emptyCard("No preparation jobs yet."));
    return;
  }

  for (const job of state.jobs) {
    const card = buildElement("article", "card job-card");
    const head = buildElement("div", "job-head");
    const id = buildElement("strong", null, job.id);
    const status = buildElement("code", null, job.status);
    const drives = document.createElement("ul");

    head.append(id, status);
    for (const drive of job.drives) {
      const item = document.createElement("li");
      const devicePath = buildElement("code", null, drive.device.path);
      item.append(devicePath, ` ${drive.status} / ${drive.stage}`);
      if (drive.error) item.append(`: ${drive.error}`);
      drives.append(item);
    }
    card.append(head, drives);
    els.jobs.append(card);
  }
}

function updateStartState() {
  const devices = [...state.selectedDevices];
  els.start.disabled = !(devices.length > 0 && state.selectedIsos.size > 0);
}

function popupConfirmations(devices) {
  const confirmations = {};
  for (const path of devices) {
    const device = state.devices.find((entry) => entry.path === path);
    const details = [
      `Device: ${path}`,
      `Model: ${text([device?.vendor, device?.model].filter(Boolean).join(" "))}`,
      `Size: ${formatBytes(device?.size_bytes)}`,
      "Installing Ventoy will erase this USB drive.",
    ].join("\n");
    if (!window.confirm(details)) return null;
    confirmations[path] = "CONFIRMED";
  }
  return confirmations;
}

function emptyCard(message) {
  return buildElement("p", "empty", message);
}

function showError(message) {
  els.error.textContent = message;
}

function clearError() {
  els.error.textContent = "";
}

async function startJob() {
  clearError();
  const devices = [...state.selectedDevices];
  const confirmations = popupConfirmations(devices);
  if (confirmations === null) return;
  try {
    const job = await fetchJson("/api/jobs", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        device_paths: devices,
        iso_keys: [...state.selectedIsos],
        confirmations,
      }),
    });
    watchJobEvents(job);
    state.selectedDevices.clear();
    await refreshAll();
  } catch (error) {
    showError(error.message);
  }
}

els.start.addEventListener("click", startJob);
els.refresh.addEventListener("click", refreshAll);
setInterval(async () => {
  try {
    state.jobs = await fetchJson("/api/jobs");
    renderJobs();
  } catch (error) {
    showError(error.message);
  }
}, 2500);
refreshAll();
