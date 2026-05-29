const state = {
  runs: null,
  runOffset: 0,
  trackOffset: 0,
  segmentOffset: 0,
  selectedRunId: null,
  selectedTrackId: null,
  demoMode: new URLSearchParams(window.location.search).get("demo") === "1",
  activeRequestId: 0,
  lastSuccessfulRefresh: null,
  lastRefreshError: null,
};

const REFRESH_INTERVAL_MS = 25000;
const STALE_AFTER_MS = 60000;

const stageCopy = {
  metadata: { label: "Metadata", short: "Run summary" },
  validation: { label: "Validation", short: "Kiểm tra đầu vào" },
  features: { label: "Features", short: "RMS + silence" },
  artifacts: { label: "Artifacts", short: "Media + manifest" },
  review: { label: "Review", short: "Màn hình demo" },
};

const stageValueLabels = {
  ready: "Sẵn sàng",
  degraded: "Cần chú ý",
  failed: "Lỗi",
  empty: "Chưa có",
  unknown: "Chưa rõ",
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
  demoModeToggle: document.getElementById("demo-mode-toggle"),
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
  elements.readyLabel.textContent = error ? "Lỗi" : ready ? "Sẵn sàng" : "Đang tải";
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
    elements.freshnessLabel.textContent = state.lastRefreshError ? "Lỗi tải dữ liệu" : "Đang tải";
    return;
  }

  const ageMs = Date.now() - state.lastSuccessfulRefresh.getTime();
  const ageSeconds = Math.max(0, Math.round(ageMs / 1000));
  if (state.lastRefreshError) {
    elements.body.dataset.refreshState = "error";
    elements.freshnessLabel.textContent = `Lỗi, giữ dữ liệu ${ageSeconds}s trước`;
    return;
  }
  if (ageMs > STALE_AFTER_MS) {
    elements.body.dataset.refreshState = "stale";
    elements.freshnessLabel.textContent = `Dữ liệu cũ ${ageSeconds}s`;
    return;
  }
  elements.body.dataset.refreshState = "fresh";
  elements.freshnessLabel.textContent = `Mới ${ageSeconds}s`;
}

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function readUrlState() {
  const params = new URLSearchParams(window.location.search);
  const trackId = params.get("track_id");
  const parsedTrackId = trackId === null ? null : Number(trackId);
  return {
    runId: params.get("run_id"),
    trackId: Number.isFinite(parsedTrackId) ? parsedTrackId : null,
  };
}

function firstRunId(payload) {
  return payload && Array.isArray(payload.items) && payload.items.length > 0
    ? payload.items[0].run_id
    : null;
}

function firstTrackId(payload) {
  return payload && Array.isArray(payload.items) && payload.items.length > 0
    ? Number(payload.items[0].track_id)
    : null;
}

function startViewRequest() {
  state.activeRequestId += 1;
  return state.activeRequestId;
}

function isCurrentRequest(requestId) {
  return requestId === state.activeRequestId;
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
  const query = params.toString();
  history.replaceState(null, "", query ? `${window.location.pathname}?${query}` : window.location.pathname);
}

function renderModeControls() {
  elements.demoModeToggle.textContent = state.demoMode ? "Tắt demo / Tất cả run" : "Demo playlist";
  elements.demoModeToggle.setAttribute("aria-pressed", String(state.demoMode));
}

function renderEmpty(target, title = "Chưa có dữ liệu", copy = "Màn hình này chỉ đọc dữ liệu đã được persist.") {
  const template = document.getElementById("empty-state-template");
  target.innerHTML = "";
  const fragment = template.content.cloneNode(true);
  fragment.querySelector("h3").textContent = title;
  fragment.querySelector("p").textContent = copy;
  target.append(fragment);
}

function renderInlineError(target, message) {
  renderEmpty(target, "Không tải được dữ liệu", message);
}

function renderRunLoadError(runId, error) {
  elements.runSummaryPanel.classList.remove("hidden");
  elements.detailGrid.classList.add("hidden");
  elements.trackDetailPanel.classList.add("hidden");
  elements.runtimeProofPanel.classList.add("hidden");
  renderInlineError(elements.runSummaryGrid, `Không tải được run ${runId}: ${error.message}`);
  setReviewReady(false, error.message);
  setRefreshError(error);
}

function renderTrackLoadError(trackId, error) {
  elements.trackDetailPanel.classList.remove("hidden");
  elements.trackHead.innerHTML = "";
  elements.trackDetailSource.innerHTML = "";
  elements.segmentPager.innerHTML = "";
  renderInlineError(elements.segmentTable, `Không tải được track ${trackId}: ${error.message}`);
  setReviewReady(false, error.message);
  setRefreshError(error);
}

function renderPipeline(pipelineStages) {
  const items = pipelineStages && Array.isArray(pipelineStages.items) ? pipelineStages.items : [];
  if (items.length === 0) {
    elements.pipelineCard.innerHTML = `
      <div class="pipeline-placeholder">
        Chưa có stage contract trong payload run detail.
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
  renderModeControls();
  elements.runList.innerHTML = "";
  elements.runCount.textContent = `${payload.total} run${payload.total === 1 ? "" : "s"}`;
  elements.modeBanner.textContent = state.demoMode
    ? `Đang lọc demo playlist: ${payload.mode.pinned_run_ids.join(", ")}`
    : "Đang hiển thị các run mới nhất.";

  if (payload.items.length === 0) {
    renderEmpty(
      elements.runList,
      "Chưa có run",
      "Hãy chạy demo evidence path để tạo deterministic runs trước khi trình bày."
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
      const requestId = startViewRequest();
      state.selectedRunId = runItem.run_id;
      state.selectedTrackId = null;
      state.trackOffset = 0;
      state.segmentOffset = 0;
      updateUrl();
      loadRun(runItem.run_id, { requestId }).catch((error) => {
        if (!isCurrentRequest(requestId)) {
          return;
        }
        renderRunLoadError(runItem.run_id, error);
      });
      renderRuns(state.runs);
    });
    elements.runList.append(button);
  });

  buildPager(elements.runPager, payload, (nextOffset) => {
    const requestId = startViewRequest();
    state.runOffset = nextOffset;
    loadRuns({ requestId }).catch((error) => {
      if (!isCurrentRequest(requestId)) {
        return;
      }
      setReviewReady(false, error.message);
      setRefreshError(error);
      renderInlineError(elements.runList, `Không tải được danh sách run: ${error.message}`);
    });
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
    ["Trạng thái", run.state.label, run.state.reason, "status"],
    ["Tracks", formatNumber(run.tracks_total, 0), "Số track quan sát trong run.", "tracks"],
    ["Persisted segments", formatNumber(run.segments_persisted, 0), "Feature rows đã ghi vào TimescaleDB.", "segments"],
    ["Silent ratio", formatRatio(run.silent_ratio), "Tỷ lệ segment silent trong run.", "silent"],
    ["Average RMS", formatNumber(run.avg_rms, 3), "Năng lượng âm thanh trung bình từ features.", "rms"],
    ["Avg processing", run.avg_processing_ms === null ? "-" : `${formatNumber(run.avg_processing_ms, 2)} ms`, "Thời gian xử lý trung bình mỗi segment.", "latency"],
    ["Validation failures", formatNumber(run.validation_failures, 0), "Track bị reject ở bước metadata validation.", "validation"],
    ["Error rate", formatRatio(run.error_rate), "Tỷ lệ lỗi ở mức run.", "errors"],
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
      "Chưa có validation outcome",
      "Run này chưa có outcome validation quan sát được từ review API."
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
        <p>${manifest.exists ? "Đã có trên shared storage." : "Chưa quan sát được trên shared storage."}</p>
        <div>${badgeLabel(manifest.provenance.path)} ${badgeLabel(manifest.provenance.exists)}</div>
      </article>
      <article class="proof-card">
        <h3>Processing State</h3>
        <p class="mono">${escapeHtml(processingState.path)}</p>
        <p>${processingState.exists ? "Có file metrics phục vụ restart/replay." : "Chưa có processing state file cho run này."}</p>
        ${processingState.state ? `
          <p>Segments: <strong>${processingState.state.segment_count}</strong></p>
          <p>Silent ratio: <strong>${formatRatio(processingState.state.silent_ratio)}</strong></p>
        ` : ""}
        ${processingState.read_error ? `<p class="summary-copy">Read error: ${escapeHtml(processingState.read_error)}</p>` : ""}
        <div>${badgeLabel(processingState.provenance.path)} ${badgeLabel(processingState.provenance.exists)}</div>
      </article>
      <article class="proof-card">
        <h3>Checkpoints</h3>
        <p>${checkpoints.length} checkpoint row cho run này.</p>
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
      "Chưa có track",
      "Run này có thể bị dừng ở validation hoặc chưa có track được persist."
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
          <th>Trạng thái</th>
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
      const requestId = startViewRequest();
      state.selectedTrackId = Number(button.dataset.trackId);
      state.segmentOffset = 0;
      updateUrl();
      loadTrack(state.selectedRunId, state.selectedTrackId, { requestId }).catch((error) => {
        if (!isCurrentRequest(requestId)) {
          return;
        }
        renderTrackLoadError(state.selectedTrackId, error);
      });
      renderTracks(payload);
    });
  });

  buildPager(elements.trackPager, payload, (nextOffset) => {
    const requestId = startViewRequest();
    state.trackOffset = nextOffset;
    loadTracks(state.selectedRunId, { requestId }).catch((error) => {
      if (!isCurrentRequest(requestId)) {
        return;
      }
      setReviewReady(false, error.message);
      setRefreshError(error);
      renderInlineError(elements.trackTable, `Không tải được tracks: ${error.message}`);
    });
  });
}

function renderTrackDetail(payload) {
  const track = payload.track;
  elements.trackDetailPanel.classList.remove("hidden");
  elements.trackDetailSource.innerHTML = `${badgeLabel(track.provenance.source)} ${badgeLabel(track.track_state.provenance.source)}`;
  elements.trackHead.innerHTML = `
    <div class="track-head-block track-result-card">
      <h3>Kết quả track</h3>
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
      "Chưa có segment",
      "Track này không có persisted segment; thường gặp ở validation failure hoặc partial evidence."
    );
    elements.segmentPager.innerHTML = "";
    return;
  }

  elements.segmentTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Segment</th>
          <th>Kết quả</th>
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
              <div class="media-error" hidden>Không tải được audio artifact cho segment này.</div>
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
    const requestId = startViewRequest();
    state.segmentOffset = nextOffset;
    loadTrack(state.selectedRunId, state.selectedTrackId, { requestId }).catch((error) => {
      if (!isCurrentRequest(requestId)) {
        return;
      }
      renderTrackLoadError(state.selectedTrackId, error);
    });
  });
}

async function loadRuns({ background = false, requestId = startViewRequest() } = {}) {
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
  if (!isCurrentRequest(requestId)) {
    return;
  }

  const { runId: urlRunId } = readUrlState();
  const urlRunRequested = Boolean(urlRunId && !state.selectedRunId);
  state.selectedRunId = state.selectedRunId || urlRunId || firstRunId(payload);
  if (!state.selectedRunId) {
    state.selectedRunId = null;
    state.selectedTrackId = null;
  }
  renderRuns(payload);
  if (state.selectedRunId) {
    updateUrl();
    try {
      await loadRun(state.selectedRunId, { requestId });
    } catch (error) {
      if (!isCurrentRequest(requestId)) {
        return;
      }
      if (urlRunRequested) {
        const fallbackRunId = firstRunId(payload);
        state.selectedRunId = fallbackRunId;
        state.selectedTrackId = null;
        state.trackOffset = 0;
        state.segmentOffset = 0;
        updateUrl();
        renderRuns(payload);
        if (fallbackRunId) {
          try {
            await loadRun(fallbackRunId, { requestId });
            return;
          } catch (fallbackError) {
            if (!isCurrentRequest(requestId)) {
              return;
            }
            renderRunLoadError(fallbackRunId, fallbackError);
            return;
          }
        }
        setReviewReady(true);
        setRefreshSuccess();
        return;
      }
      renderRunLoadError(state.selectedRunId, error);
    }
    return;
  }
  setReviewReady(true);
  setRefreshSuccess();
}

async function loadRun(runId, { requestId = startViewRequest() } = {}) {
  const payload = await fetchJSON(`/api/runs/${encodeURIComponent(runId)}`);
  if (!isCurrentRequest(requestId)) {
    return;
  }
  renderRunSummary(payload);
  await loadTracks(runId, { requestId });
}

async function loadTracks(runId, { requestId = startViewRequest() } = {}) {
  const payload = await fetchJSON(`/api/runs/${encodeURIComponent(runId)}/tracks?limit=8&offset=${state.trackOffset}`);
  if (!isCurrentRequest(requestId)) {
    return;
  }

  const { trackId: urlTrackId } = readUrlState();
  const urlTrackRequested = urlTrackId !== null && state.selectedTrackId === null;
  state.selectedTrackId = state.selectedTrackId ?? urlTrackId ?? firstTrackId(payload);
  if (state.selectedTrackId === null) {
    state.selectedTrackId = null;
  }
  renderTracks(payload);
  if (state.selectedTrackId !== null) {
    updateUrl();
    try {
      await loadTrack(runId, state.selectedTrackId, { requestId });
    } catch (error) {
      if (!isCurrentRequest(requestId)) {
        return;
      }
      if (urlTrackRequested) {
        const fallbackTrackId = firstTrackId(payload);
        if (fallbackTrackId !== null && fallbackTrackId !== state.selectedTrackId) {
          state.selectedTrackId = fallbackTrackId;
          state.segmentOffset = 0;
          updateUrl();
          renderTracks(payload);
          try {
            await loadTrack(runId, fallbackTrackId, { requestId });
            return;
          } catch (fallbackError) {
            if (!isCurrentRequest(requestId)) {
              return;
            }
            renderTrackLoadError(fallbackTrackId, fallbackError);
            return;
          }
        }
      }
      renderTrackLoadError(state.selectedTrackId, error);
    }
    return;
  }
  setReviewReady(true);
  setRefreshSuccess();
}

async function loadTrack(runId, trackId, { requestId = startViewRequest() } = {}) {
  const payload = await fetchJSON(
    `/api/runs/${encodeURIComponent(runId)}/tracks/${trackId}?segments_limit=8&segments_offset=${state.segmentOffset}`
  );
  if (!isCurrentRequest(requestId)) {
    return;
  }
  renderTrackDetail(payload);
  setReviewReady(true);
  setRefreshSuccess();
}

async function refreshActiveView() {
  const requestId = startViewRequest();
  try {
    await loadRuns({ background: true, requestId });
  } catch (error) {
    if (!isCurrentRequest(requestId)) {
      return;
    }
    setRefreshError(error);
    if (!state.runs) {
      throw error;
    }
  }
}

async function boot() {
  setReviewReady(false);
  renderModeControls();
  elements.demoModeToggle.addEventListener("click", () => {
    const requestId = startViewRequest();
    state.demoMode = !state.demoMode;
    state.selectedRunId = null;
    state.selectedTrackId = null;
    state.runOffset = 0;
    state.trackOffset = 0;
    state.segmentOffset = 0;
    updateUrl();
    renderModeControls();
    loadRuns({ requestId }).catch((error) => {
      if (!isCurrentRequest(requestId)) {
        return;
      }
      setReviewReady(false, error.message);
      setRefreshError(error);
      renderInlineError(elements.runList, `Không tải được danh sách run: ${error.message}`);
    });
  });
  try {
    await loadRuns({ requestId: startViewRequest() });
    window.setInterval(refreshActiveView, REFRESH_INTERVAL_MS);
    window.setInterval(updateFreshnessLabel, 5000);
  } catch (error) {
    elements.heroTitle.textContent = "Review API chưa sẵn sàng";
    elements.heroCopy.textContent = error.message;
    renderEmpty(
      elements.runList,
      "Không tải được runs",
      "Kiểm tra demo stack hoặc chạy evidence path trước khi trình bày."
    );
    renderPipeline(null);
    setRefreshError(error);
    setReviewReady(false, error.message);
  }
}

boot();
