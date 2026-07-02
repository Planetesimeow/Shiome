const state = { videos: [], selectedId: null, activeTab: "enhancement" };
const PORTFOLIO_LEVEL_TYPES = ["content_ideas", "creator_profile"]; // 不依赖单条视频的分析类型

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ---------- 视频列表 ----------

async function loadVideos() {
  state.videos = await api("/api/videos");
  const list = document.getElementById("video-list");
  list.innerHTML = "";
  for (const v of state.videos) {
    const li = document.createElement("li");
    li.className = "video-row" + (v.id === state.selectedId ? " selected" : "");
    li.onclick = () => selectVideo(v.id);
    const completion = v.completion_rate != null ? (v.completion_rate * 100).toFixed(1) + "%" : "--";
    li.innerHTML = `
      <div class="title">${escapeHtml(v.title)}</div>
      <div class="meta">
        <span>${v.publish_date}</span>
        <span>播放 ${formatNum(v.plays)}</span>
        <span>完播 ${completion}</span>
        ${v.is_anomaly_period ? '<span class="anomaly">● 异常期</span>' : ""}
      </div>`;
    list.appendChild(li);
  }
  document.getElementById("status-line").textContent = `${state.videos.length} 条视频`;
}

function formatNum(n) {
  if (n == null) return "--";
  if (n >= 10000) return (n / 10000).toFixed(1) + "w";
  return n.toString();
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

// ---------- 趋势图 ----------

let chartInstance = null;

async function loadTrendChart() {
  const data = await api("/api/trend-data");
  const ctx = document.getElementById("trend-chart");
  const labels = data.map((d) => d.publish_date);
  const plays = data.map((d) => d.plays);
  const completion = data.map((d) => (d.completion_rate != null ? d.completion_rate * 100 : null));
  const anomalyFlags = data.map((d) => !!d.is_anomaly_period);

  if (chartInstance) chartInstance.destroy();
  chartInstance = new Chart(ctx, {
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "播放量",
          data: plays,
          backgroundColor: (c) => (anomalyFlags[c.dataIndex] ? "rgba(156,74,60,0.35)" : "rgba(185,164,126,0.55)"),
          yAxisID: "y",
          order: 2,
        },
        {
          type: "line",
          label: "完播率 %",
          data: completion,
          borderColor: "#EAE6DC",
          borderWidth: 1.5,
          pointRadius: (c) => (anomalyFlags[c.dataIndex] ? 5 : 2),
          pointBackgroundColor: (c) => (anomalyFlags[c.dataIndex] ? "#9C4A3C" : "#EAE6DC"),
          pointStyle: (c) => (anomalyFlags[c.dataIndex] ? "triangle" : "circle"),
          yAxisID: "y1",
          order: 1,
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { position: "left", ticks: { color: "#8C877C", font: { family: "ui-monospace" } }, grid: { color: "#2C2924" } },
        y1: { position: "right", ticks: { color: "#8C877C", font: { family: "ui-monospace" } }, grid: { display: false } },
        x: { ticks: { color: "#8C877C", font: { family: "ui-monospace", size: 10 } }, grid: { display: false } },
      },
      plugins: {
        legend: { labels: { color: "#8C877C", font: { family: "ui-monospace", size: 11 } } },
      },
    },
  });
}

// ---------- 选中视频 / 分析 ----------

function selectVideo(id) {
  state.selectedId = id;
  document.getElementById("detail-empty").style.display = "none";
  document.getElementById("detail-view").style.display = "block";
  loadVideos();
  loadContentProfileForm(id);
  loadSnapshots(id);
  loadResultForActiveTab();
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    state.activeTab = tab.dataset.type;
    loadResultForActiveTab();
  };
});

async function loadResultForActiveTab() {
  const type = state.activeTab;
  const container = document.getElementById("result-container");
  container.innerHTML = `<div class="empty-state">加载中...</div>`;

  const query = PORTFOLIO_LEVEL_TYPES.includes(type)
    ? `analysis_type=${type}`
    : `video_id=${state.selectedId}&analysis_type=${type}`;
  const cached = await api(`/api/analyze/results?${query}`);

  if (cached.length > 0) {
    renderResult(type, cached[0].result_json);
  } else {
    container.innerHTML = `
      <div class="empty-state">
        还没有分析结果<br><br>
        <button class="primary" onclick="runAnalysis('${type}')">运行分析</button>
      </div>`;
  }
}

async function runAnalysis(type) {
  const container = document.getElementById("result-container");
  container.innerHTML = `<div class="empty-state">调用 Claude 分析中...</div>`;
  try {
    let result;
    if (PORTFOLIO_LEVEL_TYPES.includes(type)) {
      result = await api(`/api/analyze/${type}`, { method: "POST" });
    } else {
      result = await api(`/api/analyze/${state.selectedId}/${type}`, { method: "POST" });
    }
    renderResult(type, result);
  } catch (e) {
    container.innerHTML = `<div class="empty-state">分析失败：${escapeHtml(e.message)}</div>`;
  }
}

function renderResult(type, data) {
  const container = document.getElementById("result-container");
  if (data._parse_error) {
    container.innerHTML = `<div class="result-card"><h3>解析失败</h3><p>${escapeHtml(data.raw_text)}</p></div>`;
    return;
  }

  let html = `<div class="result-card">`;
  html += `<button class="primary" style="float:right" onclick="runAnalysis('${type}')">重新分析</button>`;

  if (type === "enhancement") {
    html += renderList("数据诊断", data.diagnosis);
    html += renderList("具体改动建议", data.concrete_edits);
    html += renderList("值得保留的地方", data.what_worked);
  } else if (type === "trend_forecast") {
    html += `<h3>阶段判断</h3><p>${escapeHtml(data.stage_assessment)}</p>`;
    html += `<h3>可能走向 <span class="confidence">置信度: ${escapeHtml(data.confidence)}</span></h3><p>${escapeHtml(data.likely_trajectory)}</p>`;
    html += `<p style="color:var(--text-muted);font-size:12px">${escapeHtml(data.confidence_reason)}</p>`;
    html += renderList("接下来该盯的指标", data.watch_metrics);
    html += `<div class="caveat">${escapeHtml(data.caveat)}</div>`;
  } else if (type === "content_ideas") {
    html += renderList("跑通的内容模式", data.high_performing_patterns);
    if (data.new_content_ideas) {
      html += `<h3>新选题方向</h3><ul>`;
      for (const idea of data.new_content_ideas) {
        html += `<li><strong>${escapeHtml(idea.angle)}</strong> — ${escapeHtml(idea.why)}`;
        if (idea.risk_note) html += `<br><span style="color:var(--danger);font-size:12px">⚠ ${escapeHtml(idea.risk_note)}</span>`;
        html += `</li>`;
      }
      html += `</ul>`;
    }
    html += renderList("可以减少投入的类型", data.patterns_to_retire);
  } else if (type === "pool_diagnosis") {
    html += `<h3>当前流量池 <span class="confidence">置信度: ${escapeHtml(data.tier_confidence)}</span></h3><p>${escapeHtml(data.current_tier)}</p>`;
    html += `<h3>卡点指标</h3><p>${escapeHtml(data.blocking_metric ?? "没有明显卡点")}</p>`;
    if (data.current_vs_target) html += `<p style="color:var(--text-muted);font-size:12px">${escapeHtml(data.current_vs_target)}</p>`;
    html += renderList("解锁下一级的具体改动", data.unlock_actions);
    html += `<div class="caveat">${escapeHtml(data.caveat)}</div>`;
  } else if (type === "creator_profile") {
    html += renderList("当前内容方向分布", data.content_direction_breakdown);
    html += renderList("钩子模式", data.hook_patterns);
    if (data.text_and_music_style) html += `<h3>文字 / 配乐风格</h3><p>${escapeHtml(data.text_and_music_style)}</p>`;
    if (data.matrix_assessment) html += `<h3>矩阵结构评估</h3><p>${escapeHtml(data.matrix_assessment)}</p>`;
    html += renderList("矩阵调整建议", data.matrix_recommendation);
  }

  html += `</div>`;
  container.innerHTML = html;
}

function renderList(title, items) {
  if (!items || items.length === 0) return "";
  return `<h3>${title}</h3><ul>${items.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`;
}

// ---------- 内容画像 ----------

async function loadContentProfileForm(id) {
  const video = await api(`/api/videos/${id}`);
  document.getElementById("pf-content_summary").value = video.content_summary || "";
  document.getElementById("pf-on_screen_text").value = video.on_screen_text || "";
  document.getElementById("pf-music").value = video.music || "";
  document.getElementById("pf-hook_description").value = video.hook_description || "";
  document.getElementById("pf-content_pillar").value = video.content_pillar || "";
}

async function saveContentProfile() {
  if (!state.selectedId) return;
  // 注意：这里故意不把空字符串转成 null——表单一直显示的是数据库里的当前值，
  // 所以"清空了再保存"就应该真的清空，而不是被后端的 COALESCE 当成"没传"而保留旧值。
  const payload = {
    content_summary: document.getElementById("pf-content_summary").value,
    on_screen_text: document.getElementById("pf-on_screen_text").value,
    music: document.getElementById("pf-music").value,
    hook_description: document.getElementById("pf-hook_description").value,
    content_pillar: document.getElementById("pf-content_pillar").value,
  };
  await api(`/api/videos/${state.selectedId}/content-profile`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  document.getElementById("status-line").textContent = "内容画像已保存";
}

// ---------- 快照 ----------

async function loadSnapshots(id) {
  const snapshots = await api(`/api/videos/${id}/snapshots`);
  const list = document.getElementById("snapshot-list");
  if (snapshots.length === 0) {
    list.innerHTML = `<li>还没有快照记录</li>`;
    return;
  }
  list.innerHTML = snapshots
    .map((s) => `<li>${s.checked_at.slice(0, 16).replace("T", " ")} — 播放 ${formatNum(s.plays)} / 赞 ${formatNum(s.likes)} / 评论 ${formatNum(s.comments)}</li>`)
    .join("");
}

async function addSnapshot() {
  if (!state.selectedId) return;
  const payload = {
    plays: Number(document.getElementById("sn-plays").value) || 0,
    likes: Number(document.getElementById("sn-likes").value) || 0,
    comments: Number(document.getElementById("sn-comments").value) || 0,
    saves: Number(document.getElementById("sn-saves").value) || 0,
    completion_rate: document.getElementById("sn-completion").value
      ? Number(document.getElementById("sn-completion").value) / 100
      : null,
  };
  await api(`/api/videos/${state.selectedId}/snapshots`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await loadSnapshots(state.selectedId);
  document.getElementById("status-line").textContent = "快照已记录";
}

// ---------- CSV 导入 ----------

document.getElementById("csv-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  document.getElementById("status-line").textContent = "导入中...";
  try {
    const result = await api("/api/videos/import", { method: "POST", body: formData });
    document.getElementById("status-line").textContent = `导入了 ${result.inserted} 条`;
    await loadVideos();
    await loadTrendChart();
  } catch (err) {
    document.getElementById("status-line").textContent = "导入失败: " + err.message;
  }
});

// ---------- 初始化 ----------

loadVideos();
loadTrendChart();
