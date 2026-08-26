const jobAutoScroll = new Map();

const state = {
  devices: [],
  isos: [],
  jobs: [],
  status: null,
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
  status: document.querySelector("[data-status]"),
  refresh: document.querySelector("[data-refresh]"),
  concurrency: document.querySelector("[data-concurrency]"),
  concurrencyHint: document.querySelector("[data-concurrency-hint]"),
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

function formatEventTime(value) {
  if (!value) return "--:--:--";
  return new Date(value * 1000).toLocaleTimeString();
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
    const [status, devices, isos, jobs] = await Promise.all([
      fetchJson("/api/status"),
      fetchJson("/api/devices"),
      fetchJson("/api/isos"),
      fetchJson("/api/jobs"),
    ]);
    state.status = status;
    state.devices = devices;
    state.isos = isos;
    state.jobs = jobs;
    applyInitialIsoSelection(isos);
    watchRunningJobs(jobs);
    updateConcurrencyLimit();
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
  renderStatus();
  renderDevices();
  renderIsos();
  renderConfirmations();
  renderJobs();
  updateStartState();
  els.summary.textContent = `${state.devices.length} devices scanned, ${state.selectedDevices.size} selected`;
}

function renderStatus() {
  els.status.replaceChildren();
  if (!state.status) return;
  const message = buildElement("strong", null, state.status.message);
  const details = buildElement(
    "small",
    null,
    `Platform: ${state.status.platform} / root: ${state.status.running_as_root ? "yes" : "no"}`,
  );
  els.status.classList.toggle("danger", !state.status.can_prepare);
  els.status.append(message, details);
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
  updateConcurrencyLimit();
}

function updateConcurrencyLimit() {
  if (!els.concurrency) return;
  const selectedCount = Math.max(1, state.selectedDevices.size);
  els.concurrency.max = String(selectedCount);
  if (Number(els.concurrency.value) > selectedCount) els.concurrency.value = String(selectedCount);
  els.concurrencyHint.textContent =
    state.selectedDevices.size > 1
      ? `Up to ${selectedCount} selected drives can run at the same time.`
      : "Select multiple drives to increase parallel installations.";
}

function buildEventItem(event) {
  const item = document.createElement("li");
  const time = buildElement("time", null, formatEventTime(event.created_at));
  const stage = buildElement("code", null, event.stage);
  const device = buildElement("span", "mono", event.device_path);
  const isCommandOutput = event.message.startsWith("stdout:") || event.message.startsWith("stderr:");
  const message = buildElement("span", isCommandOutput ? "command-line" : null, event.message);
  item.append(time, stage, device, message);
  return item;
}

function buildJobTimeline(job) {
  const list = buildElement("ol", "event-timeline");
  list.dataset.jobId = job.id;
  list.addEventListener("scroll", () => {
    const nearBottom = list.scrollTop + list.clientHeight >= list.scrollHeight - 20;
    jobAutoScroll.set(job.id, nearBottom);
  });
  if ((job.events || []).length === 0) {
    list.append(buildElement("li", "empty", "Waiting for progress events."));
  } else {
    for (const event of job.events) list.append(buildEventItem(event));
  }
  return list;
}

function buildDrivesList(drives) {
  const ul = document.createElement("ul");
  for (const drive of drives) {
    const item = document.createElement("li");
    const devicePath = buildElement("code", null, drive.device.path);
    item.append(devicePath, ` ${drive.status} / ${drive.stage}`);
    if (drive.error) item.append(`: ${drive.error}`);
    ul.append(item);
  }
  return ul;
}

function renderJobs() {
  if (state.jobs.length === 0) {
    els.jobs.replaceChildren(emptyCard("No preparation jobs yet."));
    return;
  }

  const existingCards = new Map();
  for (const child of [...els.jobs.children]) {
    if (child.dataset.jobId) existingCards.set(child.dataset.jobId, child);
    else child.remove();
  }

  const currentJobIds = new Set(state.jobs.map((j) => j.id));
  for (const [id, card] of existingCards) {
    if (!currentJobIds.has(id)) card.remove();
  }

  for (const job of state.jobs) {
    if (existingCards.has(job.id)) {
      const card = existingCards.get(job.id);
      card.querySelector(".job-head code").textContent = job.status;
      card.querySelector("ul").replaceWith(buildDrivesList(job.drives));

      const timeline = card.querySelector(".event-timeline");
      const existingCount = timeline.querySelectorAll("li:not(.empty)").length;
      const newEvents = (job.events || []).slice(existingCount);
      if (newEvents.length > 0) {
        timeline.querySelector(".empty")?.remove();
        for (const event of newEvents) timeline.append(buildEventItem(event));
        if (jobAutoScroll.get(job.id) !== false) {
          requestAnimationFrame(() => { timeline.scrollTop = timeline.scrollHeight; });
        }
      }
    } else {
      const card = buildElement("article", "card job-card");
      card.dataset.jobId = job.id;
      const head = buildElement("div", "job-head");
      head.append(
        buildElement("strong", null, job.id),
        buildElement("small", null, `parallel installs: ${job.max_concurrent_drives || 1}`),
        buildElement("code", null, job.status),
      );
      card.append(head, buildDrivesList(job.drives), buildJobTimeline(job));
      els.jobs.append(card);
      requestAnimationFrame(() => {
        const tl = card.querySelector(".event-timeline");
        if (tl) tl.scrollTop = tl.scrollHeight;
      });
    }
  }
}

function updateStartState() {
  const devices = [...state.selectedDevices];
  els.start.disabled = !(devices.length > 0 && state.selectedIsos.size > 0 && state.status?.can_prepare);
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
        max_concurrent_drives: Number(els.concurrency?.value || 1),
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
els.concurrency?.addEventListener("input", updateConcurrencyLimit);
setInterval(async () => {
  try {
    state.jobs = await fetchJson("/api/jobs");
    renderJobs();
  } catch (error) {
    showError(error.message);
  }
}, 2500);
refreshAll();
