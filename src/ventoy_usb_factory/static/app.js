const state = {
  devices: [],
  isos: [],
  jobs: [],
  selectedDevices: new Set(),
  selectedIsos: new Set(),
  confirmations: {},
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
    for (const iso of isos) {
      if (iso.status === "ready") state.selectedIsos.add(iso.key);
    }
    render();
  } catch (error) {
    showError(error.message);
  }
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
  els.devices.innerHTML = "";
  if (state.devices.length === 0) {
    els.devices.append(emptyCard("No USB drives detected."));
    return;
  }

  for (const device of state.devices) {
    const eligible = device.safety === "eligible";
    const card = document.createElement("article");
    card.className = `card device-card ${eligible ? "eligible" : "blocked"}`;
    card.innerHTML = `
      <label class="select-row">
        <input type="checkbox" ${eligible ? "" : "disabled"} ${state.selectedDevices.has(device.path) ? "checked" : ""}>
        <span class="mono">${device.path}</span>
      </label>
      <dl>
        <div><dt>Model</dt><dd>${text([device.vendor, device.model].filter(Boolean).join(" "))}</dd></div>
        <div><dt>Size</dt><dd>${formatBytes(device.size_bytes)}</dd></div>
        <div><dt>Safety</dt><dd>${device.safety_reason}</dd></div>
      </dl>
    `;
    card.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) state.selectedDevices.add(device.path);
      else state.selectedDevices.delete(device.path);
      renderConfirmations();
      updateStartState();
    });
    els.devices.append(card);
  }
}

function renderIsos() {
  els.isos.innerHTML = "";
  for (const iso of state.isos) {
    const ready = iso.status === "ready";
    const row = document.createElement("label");
    row.className = `row-card ${ready ? "ready" : "blocked"}`;
    row.innerHTML = `
      <input type="checkbox" ${ready ? "" : "disabled"} ${state.selectedIsos.has(iso.key) ? "checked" : ""}>
      <span><strong>${iso.name}</strong><small>${iso.message}</small></span>
      <code>${iso.status}</code>
    `;
    row.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) state.selectedIsos.add(iso.key);
      else state.selectedIsos.delete(iso.key);
      updateStartState();
    });
    els.isos.append(row);
  }
}

function renderConfirmations() {
  els.confirmations.innerHTML = "";
  for (const path of state.selectedDevices) {
    const expected = `ERASE ${path}`;
    const row = document.createElement("label");
    row.className = "confirm-row";
    row.innerHTML = `
      <span>Required for <code>${path}</code></span>
      <strong class="mono">${expected}</strong>
      <input type="text" autocomplete="off" spellcheck="false" value="${state.confirmations[path] || ""}">
    `;
    row.querySelector("input").addEventListener("input", (event) => {
      state.confirmations[path] = event.target.value;
      updateStartState();
    });
    els.confirmations.append(row);
  }
  if (state.selectedDevices.size === 0) {
    els.confirmations.append(emptyCard("Select an eligible USB drive to reveal its confirmation string."));
  }
}

function renderJobs() {
  els.jobs.innerHTML = "";
  if (state.jobs.length === 0) {
    els.jobs.append(emptyCard("No preparation jobs yet."));
    return;
  }

  for (const job of state.jobs) {
    const card = document.createElement("article");
    card.className = "card job-card";
    const drives = job.drives.map((drive) => `
      <li><code>${drive.device.path}</code> ${drive.status} / ${drive.stage}${drive.error ? `: ${drive.error}` : ""}</li>
    `).join("");
    card.innerHTML = `
      <div class="job-head"><strong>${job.id}</strong><code>${job.status}</code></div>
      <ul>${drives}</ul>
    `;
    els.jobs.append(card);
  }
}

function updateStartState() {
  const devices = [...state.selectedDevices];
  const allConfirmed = devices.length > 0 && devices.every((path) => state.confirmations[path] === `ERASE ${path}`);
  els.start.disabled = !(allConfirmed && state.selectedIsos.size > 0);
}

function emptyCard(message) {
  const card = document.createElement("p");
  card.className = "empty";
  card.textContent = message;
  return card;
}

function showError(message) {
  els.error.textContent = message;
}

function clearError() {
  els.error.textContent = "";
}

async function startJob() {
  clearError();
  try {
    await fetchJson("/api/jobs", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        device_paths: [...state.selectedDevices],
        iso_keys: [...state.selectedIsos],
        confirmations: state.confirmations,
      }),
    });
    state.selectedDevices.clear();
    state.confirmations = {};
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
