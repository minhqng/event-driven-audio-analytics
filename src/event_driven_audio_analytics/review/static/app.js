const state = {
  runs: null,
  runOffset: 0,
  trackOffset: 0,
  segmentOffset: 0,
  selectedRunId: null,
  selectedTrackId: null,
  demoMode: new URLSearchParams(window.location.search).get("demo") === "1",
};

const elements = {
  body: document.body,
  modeBanner: document.getElementById("mode-banner"),
  runList: document.getElementById("run-list"),
  runCount: document.getElementById("run-count"),
  runPager: document.getElementById("run-pager"),
  heroTitle: document.getElementById("hero-title"),
  heroCopy: document.getElementById("hero-copy"),
  runSummaryPanel: document.getElementById("run-summary-panel"),
  runSummaryGrid: document.getElementById("run-summary-grid"),
  runSummarySource: document.getElementById("run-summary-source"),
  detailGrid: document.getElementById("detail-grid"),
  validationOutcomes: document.getElementById("validation-outcomes"),
  trackTable: document.getElementById("track-table"),
  trackCount: document.getElementById("track-count"),
  trackPager: document.getElementById("track-pager"),
  trackDetailPanel: document.getElementById("track-detail-panel"),
  trackHead: document.getElementById("track-head"),
  trackDetailSource: document.getElementById("track-detail-source"),
  segmentTable: document.getElementById("segment-table"),
  segmentPager: document.getElementById("segment-pager"),
  runtimeProofPanel: document.getElementById("runtime-proof-panel"),
  runtimeProof: document.getElementById("runtime-proof"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function chipClass(value) {
  return `chip chip-${String(value).replace(/[^a-z_]/gi, "_")}`;
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined) {
    return "—";
  }
  return Number(value).toFixed(digits);
}

function formatRatio(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatTime(value) {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString();
}

function badgeLabel(source) {
  if (source === "db") {
    return '<span class="badge badge-db">DB</span>';
  }
  if (source === "fs") {
    return '<span class="badge badge-fs">FS</span>';
  }
  return '<span class="badge badge-derived">Derived</span>';
}

function setReviewReady(ready, error = null) {
  elements.body.dataset.reviewReady = ready ? "true" : "false";
  if (state.selectedRunId) {
    elements.body.dataset.selectedRunId = state.selectedRunId;
  } else {
    delete elements.body.dataset.selectedRunId;
  }
  if (state.selectedTrackId !== null) {
    elements.body.dataset.selectedTrackId = String(state.selectedTrackId);
  } else {
    delete elements.body.dataset.selectedTrackId;
  }
  if (error) {
    elements.body.dataset.reviewError = error;
  } else {
    delete elements.body.dataset.reviewError;
  }
}

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function buildPager(container, payload, onPageChange) {
  container.innerHTML = "";
  if (!payload || payload.total <= payload.limit) {
    return;
  }

  const prev = document.createElement("button");
  prev.textContent = "Previous";
  prev.disabled = payload.offset === 0;
  prev.addEventListener("click", () => onPageChange(Math.max(0, payload.offset - payload.limit)));

  const meta = document.createElement("span");
  meta.className = "panel-meta";
  meta.textContent = `${payload.offset + 1}-${payload.offset + payload.items.length} of ${payload.total}`;

  const next = document.createElement("button");
  next.textContent = "Next";
  next.disabled = !payload.has_more;
  next.addEventListener("click", () => onPageChange(payload.offset + payload.limit));

  container.append(prev, meta, next);
}

function updateUrl() {
  const params = new URLSearchParams();
  if (state.demoMode) {
    params.set("demo", "1");
  }
  if (state.selectedRunId) {
    params.set("run_id", state.selectedRunId);
  }
  if (state.selectedTrackId !== null) {
    params.set("track_id", String(state.selectedTrackId));
  }
  history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

function renderEmpty(target) {
  const template = document.getElementById("empty-state-template");
  target.innerHTML = "";
  target.append(template.content.cloneNode(true));
}

function renderRuns(payload) {
  state.runs = payload;
  elements.runList.innerHTML = "";
  elements.runCount.textContent = `${payload.total} run${payload.total === 1 ? "" : "s"}`;
  elements.modeBanner.textContent = state.demoMode
    ? `Demo mode pinned to deterministic runs: ${payload.mode.pinned_run_ids.join(", ")}`
    : "Showing recent persisted runs.";

  if (payload.items.length === 0) {
    renderEmpty(elements.runList);
    elements.runPager.innerHTML = "";
    return;
  }

  payload.items.forEach((runItem) => {
    const button = document.createElement("button");
    button.className = "run-button";
    button.setAttribute("aria-pressed", String(runItem.run_id === state.selectedRunId));
    button.innerHTML = `
      <div class="run-title">
        <strong>${escapeHtml(runItem.run_id)}</strong>
        <span class="${chipClass(runItem.state.value)}">${escapeHtml(runItem.state.label)}</span>
      </div>
      <div class="run-metrics">
        <span>${runItem.segments_persisted} persisted</span>
        <span>${formatRatio(runItem.silent_ratio)} silent</span>
        <span>${formatNumber(runItem.avg_rms, 2)} RMS</span>
      </div>
      <div class="run-metrics">
        ${badgeLabel(runItem.provenance.source)}
        ${badgeLabel(runItem.state.provenance.source)}
      </div>
    `;
    button.addEventListener("click", () => {
      state.selectedRunId = runItem.run_id;
      state.selectedTrackId = null;
      state.trackOffset = 0;
      state.segmentOffset = 0;
      updateUrl();
      loadRun(runItem.run_id);
      renderRuns(state.runs);
    });
    elements.runList.append(button);
  });

  buildPager(elements.runPager, payload, (nextOffset) => {
    state.runOffset = nextOffset;
    loadRuns();
  });
}

function renderRunSummary(payload) {
  const run = payload.run;
  elements.runSummaryPanel.classList.remove("hidden");
  elements.detailGrid.classList.remove("hidden");
  elements.runtimeProofPanel.classList.remove("hidden");
  elements.heroTitle.textContent = run.run_id;
  elements.heroCopy.textContent = run.state.reason;
  elements.runSummarySource.innerHTML = `${badgeLabel(run.provenance.source)} ${badgeLabel(run.state.provenance.source)}`;

  const cards = [
    ["Status", run.state.label, run.state.reason],
    ["Tracks", formatNumber(run.tracks_total, 0), "Tracks observed in the current run."],
    ["Segments Persisted", formatNumber(run.segments_persisted, 0), "Feature rows persisted into TimescaleDB."],
    ["Silent Ratio", formatRatio(run.silent_ratio), "Replay-stable run total from persisted metrics or features."],
    ["Average RMS", formatNumber(run.avg_rms, 3), "Persisted summary field from audio_features."],
    ["Average Processing", run.avg_processing_ms === null ? "—" : `${formatNumber(run.avg_processing_ms, 2)} ms`, "Average processing latency over persisted segments."],
    ["Validation Failures", formatNumber(run.validation_failures, 0), "Track-level reject outcomes from track_metadata."],
    ["Error Rate", formatRatio(run.error_rate), "Failed-track ratio at run summary level."],
  ];

  elements.runSummaryGrid.innerHTML = cards.map(([title, value, copy]) => `
    <article class="summary-card">
      <h3>${escapeHtml(title)}</h3>
      <div class="summary-value">${escapeHtml(value)}</div>
      <div class="summary-copy">${escapeHtml(copy)}</div>
    </article>
  `).join("");

  const validationItems = payload.validation_outcomes.items;
  if (validationItems.length === 0) {
    renderEmpty(elements.validationOutcomes);
  } else {
    elements.validationOutcomes.innerHTML = `
      <div class="validation-list">
        ${validationItems.map((item) => `
          <div class="summary-card">
            <h3>${escapeHtml(item.validation_status)}</h3>
            <div class="summary-value">${item.track_count}</div>
            <div class="summary-copy">${badgeLabel(item.provenance.source)}</div>
          </div>
        `).join("")}
      </div>
    `;
  }

  renderRuntimeProof(payload.runtime_proof);
}

function renderRuntimeProof(runtimeProof) {
  const checkpoints = runtimeProof.checkpoints.items;
  const processingState = runtimeProof.processing_state;
  const manifest = runtimeProof.manifest;

  elements.runtimeProof.innerHTML = `
    <div class="proof-grid">
      <article class="proof-card">
        <h3>Manifest</h3>
        <p class="mono">${escapeHtml(manifest.path)}</p>
        <p>${manifest.exists ? "Present on shared storage." : "Not present on shared storage."}</p>
        <div>${badgeLabel(manifest.provenance.path)} ${badgeLabel(manifest.provenance.exists)}</div>
      </article>
      <article class="proof-card">
        <h3>Processing State</h3>
        <p class="mono">${escapeHtml(processingState.path)}</p>
        <p>${processingState.exists ? "Replay-stable processing metrics file is present." : "No persisted processing state file for this run."}</p>
        ${processingState.state ? `
          <p>Segments: <strong>${processingState.state.segment_count}</strong></p>
          <p>Silent ratio: <strong>${formatRatio(processingState.state.silent_ratio)}</strong></p>
        ` : ""}
        ${processingState.read_error ? `<p class="summary-copy">Read error: ${escapeHtml(processingState.read_error)}</p>` : ""}
        <div>${badgeLabel(processingState.provenance.path)} ${badgeLabel(processingState.provenance.exists)}</div>
      </article>
      <article class="proof-card">
        <h3>Checkpoints</h3>
        <p>${checkpoints.length} checkpoint row${checkpoints.length === 1 ? "" : "s"} for this run.</p>
        ${checkpoints.length > 0 ? `
          <ul>
            ${checkpoints.map((item) => `<li><span class="mono">${escapeHtml(item.topic_name)}[${item.partition_id}]</span> @ ${item.last_committed_offset}</li>`).join("")}
          </ul>
        ` : "<p>No checkpoint rows found.</p>"}
        <div>${badgeLabel(runtimeProof.checkpoints.provenance.source)}</div>
      </article>
    </div>
  `;
}

function renderTracks(payload) {
  elements.trackCount.textContent = `${payload.total} track${payload.total === 1 ? "" : "s"}`;
  if (payload.items.length === 0) {
    renderEmpty(elements.trackTable);
    elements.trackPager.innerHTML = "";
    elements.trackDetailPanel.classList.add("hidden");
    return;
  }

  elements.trackTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Track</th>
          <th>State</th>
          <th>Validation</th>
          <th>Persisted</th>
          <th>Silent Ratio</th>
          <th>Average RMS</th>
        </tr>
      </thead>
      <tbody>
        ${payload.items.map((item) => `
          <tr>
            <td>
              <button class="table-button" data-track-id="${item.track_id}" aria-pressed="${String(item.track_id === state.selectedTrackId)}">
                <div class="table-primary">
                  <strong>${item.track_id}</strong>
                  ${badgeLabel(item.provenance.source)}
                </div>
                <div class="table-secondary">
                  <span>${escapeHtml(item.genre)}</span>
                  <span>${item.duration_s.toFixed(2)} s</span>
                </div>
              </button>
            </td>
            <td><span class="${chipClass(item.track_state.value)}">${escapeHtml(item.track_state.label)}</span></td>
            <td>${escapeHtml(item.validation_status)}</td>
            <td>${item.segments_persisted}</td>
            <td>${item.silent_ratio === null ? "—" : formatRatio(item.silent_ratio)}</td>
            <td>${item.avg_rms === null ? "—" : formatNumber(item.avg_rms, 3)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  elements.trackTable.querySelectorAll("[data-track-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedTrackId = Number(button.dataset.trackId);
      state.segmentOffset = 0;
      updateUrl();
      loadTrack(state.selectedRunId, state.selectedTrackId);
      renderTracks(payload);
    });
  });

  buildPager(elements.trackPager, payload, (nextOffset) => {
    state.trackOffset = nextOffset;
    loadTracks(state.selectedRunId);
  });
}

function renderTrackDetail(payload) {
  const track = payload.track;
  elements.trackDetailPanel.classList.remove("hidden");
  elements.trackDetailSource.innerHTML = `${badgeLabel(track.provenance.source)} ${badgeLabel(track.track_state.provenance.source)}`;
  elements.trackHead.innerHTML = `
    <div class="track-head-block">
      <h3>Track Result</h3>
      <p><strong>${track.track_id}</strong> • ${escapeHtml(track.genre)}</p>
      <p>${escapeHtml(track.track_state.reason)}</p>
      <div class="run-metrics">
        <span class="${chipClass(track.track_state.value)}">${escapeHtml(track.track_state.label)}</span>
        <span>${escapeHtml(track.validation_status)}</span>
        <span>${track.segments_persisted} persisted segment${track.segments_persisted === 1 ? "" : "s"}</span>
      </div>
    </div>
    <div class="track-head-block">
      <h3>Source Metadata</h3>
      <p>Artist ID: <strong>${track.artist_id}</strong></p>
      <p>Subset: <strong>${escapeHtml(track.subset)}</strong></p>
      <p>Duration: <strong>${formatNumber(track.duration_s, 2)} s</strong></p>
      <p class="mono">${escapeHtml(track.source_audio_uri)}</p>
    </div>
  `;

  if (payload.segments.items.length === 0) {
    renderEmpty(elements.segmentTable);
    elements.segmentPager.innerHTML = "";
    return;
  }

  elements.segmentTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Segment</th>
          <th>Result</th>
          <th>Processing</th>
          <th>Artifact</th>
        </tr>
      </thead>
      <tbody>
        ${payload.segments.items.map((segment) => `
          <tr>
            <td>
              <strong>#${segment.segment_idx}</strong>
              <div class="table-secondary">
                <span>RMS ${formatNumber(segment.rms, 3)}</span>
                <span>${segment.silent_flag ? "Silent" : "Non-silent"}</span>
              </div>
            </td>
            <td>
              <div>${segment.silent_flag ? '<span class="chip chip-metadata_only">Silent</span>' : '<span class="chip chip-persisted">Active</span>'}</div>
              <div class="table-secondary">${badgeLabel(segment.provenance.source)}</div>
            </td>
            <td>
              <div>${formatNumber(segment.processing_ms, 2)} ms</div>
              <div class="table-secondary">${escapeHtml(segment.ts ? formatTime(segment.ts) : "No timestamp")}</div>
            </td>
            <td>
              <div class="artifact-links">
                <a href="${escapeHtml(segment.artifact.media_url)}">Play WAV</a>
                ${badgeLabel(segment.artifact.provenance.uri)}
                ${badgeLabel(segment.artifact.provenance.exists)}
              </div>
              <div class="table-secondary mono">${escapeHtml(segment.artifact.uri)}</div>
              <audio controls preload="none" src="${escapeHtml(segment.artifact.media_url)}"></audio>
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  buildPager(elements.segmentPager, payload.segments, (nextOffset) => {
    state.segmentOffset = nextOffset;
    loadTrack(state.selectedRunId, state.selectedTrackId);
  });
}

async function loadRuns() {
  setReviewReady(false);
  const params = new URLSearchParams({
    limit: "8",
    offset: String(state.runOffset),
  });
  if (state.demoMode) {
    params.set("demo_mode", "true");
  }
  const payload = await fetchJSON(`/api/runs?${params.toString()}`);
  const urlRunId = new URLSearchParams(window.location.search).get("run_id");
  if (urlRunId && payload.items.some((item) => item.run_id === urlRunId)) {
    state.selectedRunId = urlRunId;
  } else if (!state.selectedRunId && payload.items.length > 0) {
    state.selectedRunId = payload.items[0].run_id;
  } else if (state.selectedRunId && !payload.items.some((item) => item.run_id === state.selectedRunId) && payload.items.length > 0) {
    state.selectedRunId = payload.items[0].run_id;
  } else if (payload.items.length === 0) {
    state.selectedRunId = null;
    state.selectedTrackId = null;
  }
  renderRuns(payload);
  if (state.selectedRunId) {
    updateUrl();
    await loadRun(state.selectedRunId);
    return;
  }
  setReviewReady(true);
}

async function loadRun(runId) {
  const payload = await fetchJSON(`/api/runs/${encodeURIComponent(runId)}`);
  renderRunSummary(payload);
  await loadTracks(runId);
}

async function loadTracks(runId) {
  const payload = await fetchJSON(`/api/runs/${encodeURIComponent(runId)}/tracks?limit=8&offset=${state.trackOffset}`);
  const urlTrackId = new URLSearchParams(window.location.search).get("track_id");
  if (urlTrackId && payload.items.some((item) => String(item.track_id) === urlTrackId)) {
    state.selectedTrackId = Number(urlTrackId);
  } else if (!state.selectedTrackId && payload.items.length > 0) {
    state.selectedTrackId = payload.items[0].track_id;
  } else if (state.selectedTrackId && !payload.items.some((item) => item.track_id === state.selectedTrackId) && payload.items.length > 0) {
    state.selectedTrackId = payload.items[0].track_id;
  } else if (payload.items.length === 0) {
    state.selectedTrackId = null;
  }
  renderTracks(payload);
  if (state.selectedTrackId !== null) {
    updateUrl();
    await loadTrack(runId, state.selectedTrackId);
    return;
  }
  setReviewReady(true);
}

async function loadTrack(runId, trackId) {
  const payload = await fetchJSON(
    `/api/runs/${encodeURIComponent(runId)}/tracks/${trackId}?segments_limit=8&segments_offset=${state.segmentOffset}`
  );
  renderTrackDetail(payload);
  setReviewReady(true);
}

async function boot() {
  setReviewReady(false);
  try {
    await loadRuns();
  } catch (error) {
    elements.heroTitle.textContent = "Review surface unavailable";
    elements.heroCopy.textContent = error.message;
    renderEmpty(elements.runList);
    setReviewReady(false, error.message);
  }
}

boot();
