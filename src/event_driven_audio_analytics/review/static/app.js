const state = {
  runs: null,
  runOffset: 0,
  trackOffset: 0,
  segmentOffset: 0,
  selectedRunId: null,
  selectedTrackId: null,
  demoMode: new URLSearchParams(window.location.search).get("demo") === "1",
  lastSuccessfulRefresh: null,
  lastRefreshError: null,
};

const REFRESH_INTERVAL_MS = 25000;
const STALE_AFTER_MS = 60000;

const stageCopy = {
  metadata: { label: "Metadata", short: "Run summary" },
  validation: { label: "Validation", short: "Kiem tra dau vao" },
  features: { label: "Features", short: "RMS + silence" },
  artifacts: { label: "Artifacts", short: "Media + manifest" },
  review: { label: "Review", short: "Man hinh demo" },
};

const stageValueLabels = {
  ready: "San sang",
  degraded: "Can chu y",
  failed: "Loi",
  empty: "Chua co",
  unknown: "Chua ro",
};

const elements = {
  body: document.body,
  modeBanner: document.getElementById("mode-banner"),
  readyLabel: document.getElementById("ready-label"),
  freshnessLabel: document.getElementById("freshness-label"),
  pipelineCard: document.getElementById("pipeline-card"),
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
    return "-";
  }
  return Number(value).toFixed(digits);
}

function formatRatio(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatTime(value) {
  if (!value) {
    return "-";
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
  elements.readyLabel.textContent = error ? "Loi" : ready ? "San sang" : "Dang tai";
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

function setRefreshSuccess() {
  state.lastSuccessfulRefresh = new Date();
  state.lastRefreshError = null;
  updateFreshnessLabel();
}

function setRefreshError(error) {
  state.lastRefreshError = error instanceof Error ? error.message : String(error);
  updateFreshnessLabel();
}

function updateFreshnessLabel() {
  if (!state.lastSuccessfulRefresh) {
    elements.body.dataset.refreshState = state.lastRefreshError ? "error" : "loading";
    elements.freshnessLabel.textContent = state.lastRefreshError ? "Loi tai du lieu" : "Dang tai";
    return;
  }

  const ageMs = Date.now() - state.lastSuccessfulRefresh.getTime();
  const ageSeconds = Math.max(0, Math.round(ageMs / 1000));
  if (state.lastRefreshError) {
    elements.body.dataset.refreshState = "error";
    elements.freshnessLabel.textContent = `Loi, giu du lieu ${ageSeconds}s truoc`;
    return;
  }
  if (ageMs > STALE_AFTER_MS) {
    elements.body.dataset.refreshState = "stale";
    elements.freshnessLabel.textContent = `Du lieu cu ${ageSeconds}s`;
    return;
  }
  elements.body.dataset.refreshState = "fresh";
  elements.freshnessLabel.textContent = `Moi ${ageSeconds}s`;
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
  prev.textContent = "Prev";
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

function renderEmpty(target, title = "Chua co du lieu", copy = "Man hinh nay chi doc du lieu da duoc persist.") {
  const template = document.getElementById("empty-state-template");
  target.innerHTML = "";
  const fragment = template.content.cloneNode(true);
  fragment.querySelector("h3").textContent = title;
  fragment.querySelector("p").textContent = copy;
  target.append(fragment);
}

function renderInlineError(target, message) {
  renderEmpty(target, "Khong tai duoc du lieu", message);
}

function renderPipeline(pipelineStages) {
  const items = pipelineStages && Array.isArray(pipelineStages.items) ? pipelineStages.items : [];
  if (items.length === 0) {
    elements.pipelineCard.innerHTML = `
      <div class="pipeline-placeholder">
        Chua co stage contract trong payload run detail.
      </div>
    `;
    return;
  }

  elements.pipelineCard.innerHTML = items.map((item, index) => {
    const value = String(item.value || "unknown");
    const stageId = String(item.id || `stage-${index + 1}`);
    const copy = stageCopy[stageId] || { label: item.label || stageId, short: "Observable evidence" };
    const reason = String(item.reason || "No reason provided.");
    return `
      <article class="pipeline-node pipeline-node-${escapeHtml(value)}" title="${escapeHtml(reason)}">
        <span>${String(index + 1).padStart(2, "0")}</span>
        <strong>${escapeHtml(copy.label)}</strong>
        <small>${escapeHtml(copy.short)}</small>
        <p>${escapeHtml(reason)}</p>
        <div class="stage-footer">
          <span class="stage-status stage-status-${escapeHtml(value)}">${escapeHtml(stageValueLabels[value] || value)}</span>
          ${badgeLabel(item.provenance?.source)}
        </div>
      </article>
    `;
  }).join("");
}

function renderRuns(payload) {
  state.runs = payload;
  elements.runList.innerHTML = "";
  elements.runCount.textContent = `${payload.total} run${payload.total === 1 ? "" : "s"}`;
  elements.modeBanner.textContent = state.demoMode
    ? `Demo playlist: ${payload.mode.pinned_run_ids.join(", ")}`
    : "Dang hien thi cac run moi nhat.";

  if (payload.items.length === 0) {
    renderEmpty(
      elements.runList,
      "Chua co run",
      "Hay chay demo evidence path de tao deterministic runs truoc khi trinh bay."
    );
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
        <span>${formatNumber(runItem.tracks_total, 0)} track</span>
        <span>${runItem.segments_persisted} segment</span>
        <span>${formatRatio(runItem.silent_ratio)} silent</span>
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
      loadRun(runItem.run_id).catch((error) => {
        setReviewReady(false, error.message);
        setRefreshError(error);
        renderInlineError(elements.runSummaryGrid, `Khong tai duoc run ${runItem.run_id}: ${error.message}`);
      });
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
  renderPipeline(payload.pipeline_stages);
  elements.heroTitle.textContent = run.run_id;
  elements.heroCopy.textContent = `${run.state.reason} ${formatNumber(run.tracks_total, 0)} track, ${formatNumber(run.segments_persisted, 0)} persisted segment, ${formatRatio(run.silent_ratio)} silent.`;
  elements.runSummarySource.innerHTML = `${badgeLabel(run.provenance.source)} ${badgeLabel(run.state.provenance.source)}`;

  const cards = [
    ["Trang thai", run.state.label, run.state.reason, "status"],
    ["Tracks", formatNumber(run.tracks_total, 0), "So track quan sat trong run.", "tracks"],
    ["Persisted segments", formatNumber(run.segments_persisted, 0), "Feature rows da ghi vao TimescaleDB.", "segments"],
    ["Silent ratio", formatRatio(run.silent_ratio), "Ty le segment silent trong run.", "silent"],
    ["Average RMS", formatNumber(run.avg_rms, 3), "Nang luong am thanh trung binh tu features.", "rms"],
    ["Avg processing", run.avg_processing_ms === null ? "-" : `${formatNumber(run.avg_processing_ms, 2)} ms`, "Thoi gian xu ly trung binh moi segment.", "latency"],
    ["Validation failures", formatNumber(run.validation_failures, 0), "Track bi reject o buoc metadata validation.", "validation"],
    ["Error rate", formatRatio(run.error_rate), "Ty le loi o muc run.", "errors"],
  ];

  elements.runSummaryGrid.innerHTML = cards.map(([title, value, copy, tone]) => `
    <article class="summary-card summary-card-${escapeHtml(tone)}">
      <h3>${escapeHtml(title)}</h3>
      <div class="summary-value">${escapeHtml(value)}</div>
      <div class="summary-copy">${escapeHtml(copy)}</div>
    </article>
  `).join("");

  const validationItems = payload.validation_outcomes.items;
  if (validationItems.length === 0) {
    renderEmpty(
      elements.validationOutcomes,
      "Chua co validation outcome",
      "Run nay chua co outcome validation quan sat duoc tu review API."
    );
  } else {
    elements.validationOutcomes.innerHTML = `
      <div class="validation-list">
        ${validationItems.map((item) => `
          <div class="summary-card compact-card">
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
        <p>${manifest.exists ? "Da co tren shared storage." : "Chua quan sat duoc tren shared storage."}</p>
        <div>${badgeLabel(manifest.provenance.path)} ${badgeLabel(manifest.provenance.exists)}</div>
      </article>
      <article class="proof-card">
        <h3>Processing State</h3>
        <p class="mono">${escapeHtml(processingState.path)}</p>
        <p>${processingState.exists ? "Co file metrics phuc vu restart/replay." : "Chua co processing state file cho run nay."}</p>
        ${processingState.state ? `
          <p>Segments: <strong>${processingState.state.segment_count}</strong></p>
          <p>Silent ratio: <strong>${formatRatio(processingState.state.silent_ratio)}</strong></p>
        ` : ""}
        ${processingState.read_error ? `<p class="summary-copy">Read error: ${escapeHtml(processingState.read_error)}</p>` : ""}
        <div>${badgeLabel(processingState.provenance.path)} ${badgeLabel(processingState.provenance.exists)}</div>
      </article>
      <article class="proof-card">
        <h3>Checkpoints</h3>
        <p>${checkpoints.length} checkpoint row cho run nay.</p>
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
    renderEmpty(
      elements.trackTable,
      "Chua co track",
      "Run nay co the bi dung o validation hoac chua co track duoc persist."
    );
    elements.trackPager.innerHTML = "";
    elements.trackDetailPanel.classList.add("hidden");
    return;
  }

  elements.trackTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Track</th>
          <th>Trang thai</th>
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
            <td>${item.silent_ratio === null ? "-" : formatRatio(item.silent_ratio)}</td>
            <td>${item.avg_rms === null ? "-" : formatNumber(item.avg_rms, 3)}</td>
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
    <div class="track-head-block track-result-card">
      <h3>Ket qua track</h3>
      <p><strong>${track.track_id}</strong> / ${escapeHtml(track.genre)}</p>
      <p>${escapeHtml(track.track_state.reason)}</p>
      <div class="run-metrics">
        <span class="${chipClass(track.track_state.value)}">${escapeHtml(track.track_state.label)}</span>
        <span>${escapeHtml(track.validation_status)}</span>
        <span>${track.segments_persisted} persisted segment${track.segments_persisted === 1 ? "" : "s"}</span>
      </div>
    </div>
    <div class="track-head-block">
      <h3>Source metadata</h3>
      <p>Artist ID: <strong>${track.artist_id}</strong></p>
      <p>Subset: <strong>${escapeHtml(track.subset)}</strong></p>
      <p>Duration: <strong>${formatNumber(track.duration_s, 2)} s</strong></p>
      <p class="mono">${escapeHtml(track.source_audio_uri)}</p>
    </div>
  `;

  if (payload.segments.items.length === 0) {
    renderEmpty(
      elements.segmentTable,
      "Chua co segment",
      "Track nay khong co persisted segment; thuong gap o validation failure hoac partial evidence."
    );
    elements.segmentPager.innerHTML = "";
    return;
  }

  elements.segmentTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Segment</th>
          <th>Ket qua</th>
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
                <span>${segment.silent_flag ? "Silent" : "Active"}</span>
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
              <div class="media-error" hidden>Khong tai duoc audio artifact cho segment nay.</div>
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  elements.segmentTable.querySelectorAll("audio").forEach((audio) => {
    audio.addEventListener("error", () => {
      const errorNode = audio.parentElement?.querySelector(".media-error");
      if (errorNode) {
        errorNode.hidden = false;
      }
    });
  });

  buildPager(elements.segmentPager, payload.segments, (nextOffset) => {
    state.segmentOffset = nextOffset;
    loadTrack(state.selectedRunId, state.selectedTrackId);
  });
}

async function loadRuns({ background = false } = {}) {
  if (!background) {
    setReviewReady(false);
  }
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
  setRefreshSuccess();
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
  setRefreshSuccess();
}

async function loadTrack(runId, trackId) {
  const payload = await fetchJSON(
    `/api/runs/${encodeURIComponent(runId)}/tracks/${trackId}?segments_limit=8&segments_offset=${state.segmentOffset}`
  );
  renderTrackDetail(payload);
  setReviewReady(true);
  setRefreshSuccess();
}

async function refreshActiveView() {
  try {
    await loadRuns({ background: true });
  } catch (error) {
    setRefreshError(error);
    if (!state.runs) {
      throw error;
    }
  }
}

async function boot() {
  setReviewReady(false);
  try {
    await loadRuns();
    window.setInterval(refreshActiveView, REFRESH_INTERVAL_MS);
    window.setInterval(updateFreshnessLabel, 5000);
  } catch (error) {
    elements.heroTitle.textContent = "Review API chua san sang";
    elements.heroCopy.textContent = error.message;
    renderEmpty(
      elements.runList,
      "Khong tai duoc runs",
      "Kiem tra demo stack hoac chay evidence path truoc khi trinh bay."
    );
    renderPipeline(null);
    setRefreshError(error);
    setReviewReady(false, error.message);
  }
}

boot();
