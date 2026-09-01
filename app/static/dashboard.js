const state = { posts: [], selectedId: null, activeTab: "enhancement" };
const PORTFOLIO_LEVEL_TYPES = ["content_ideas", "creator_profile"]; // 不依赖单条视频的分析类型

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ---------- 视频列表 ----------

async function loadVideos() {
  state.posts = await api("/api/posts");
  const list = document.getElementById("video-list");
  list.innerHTML = "";
  for (const v of state.posts) {
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
      </div>
      <button class="row-delete" title="删除这条视频及其快照/分析" onclick="deleteVideo(event, ${v.id}, this)">✕</button>`;
    list.appendChild(li);
  }
  document.getElementById("status-line").textContent = `${state.posts.length} 条作品`;
  document.getElementById("video-count").textContent = state.posts.length || "";
  updateHeroStats();
}

// ---------- 账号总览 hero ----------

function updateHeroStats() {
  document.getElementById("hs-count").textContent = state.posts.length || "0";
  document.getElementById("hs-latest").textContent = state.posts[0]?.publish_date ?? "--";
}

async function loadHeroBaseline() {
  try {
    const b = await api("/api/baseline");
    document.getElementById("hs-completion").textContent =
      b.avg_completion_rate != null ? (b.avg_completion_rate * 100).toFixed(1) + "%" : "--";
  } catch (e) { /* 数据库还没数据时保持 -- */ }
}

function showOverview() {
  state.selectedId = null;
  document.getElementById("detail-view").style.display = "none";
  document.getElementById("hero").style.display = "";
  loadVideos();
}

async function deleteVideo(event, id, btn) {
  event.stopPropagation(); // 别触发行点击选中
  const video = state.posts.find((v) => v.id === id);
  if (!confirm(`删除「${video?.title ?? id}」？\n它的快照和分析结果会一起删除，不可恢复。`)) return;
  btn.disabled = true;
  try {
    await api(`/api/posts/${id}`, { method: "DELETE" });
    document.getElementById("status-line").textContent = "已删除";
    if (state.selectedId === id) showOverview();
    else await loadVideos();
    await loadTrendChart();
    await loadHeroBaseline();
  } catch (err) {
    btn.disabled = false;
    document.getElementById("status-line").textContent = "删除失败: " + err.message;
  }
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
  document.getElementById("hero").style.display = "none";
  document.getElementById("detail-view").style.display = "block";
  loadVideos();
  loadMetricsPanel(id);
  loadDiffusionChart(id);
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
    : `post_id=${state.selectedId}&analysis_type=${type}`;
  const cached = await api(`/api/analyze/results?${query}`);

  if (cached.length > 0) {
    const row = cached[0];
    renderResult(type, row.result_json, {
      model: row.model_used,
      created: row.created_at,
      inputTokens: row.input_tokens,
      outputTokens: row.output_tokens,
    });
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
      result = await api(`/api/analyze/account/${type}`, { method: "POST" });
    } else {
      result = await api(`/api/analyze/posts/${state.selectedId}/${type}`, { method: "POST" });
    }
    renderResult(type, result);
  } catch (e) {
    container.innerHTML = `<div class="empty-state">分析失败：${escapeHtml(e.message)}</div>`;
  }
}

function renderResult(type, data, rowMeta) {
  const container = document.getElementById("result-container");
  if (data._api_error) {
    container.innerHTML = `
      <div class="result-card">
        <h3>API 调用失败${data.retryable ? "（可重试）" : ""}</h3>
        <p>${escapeHtml(data._api_error)}</p>
        <button class="primary" onclick="runAnalysis('${type}')">重试</button>
      </div>`;
    return;
  }
  if (data._parse_error) {
    container.innerHTML = `<div class="result-card"><h3>解析失败</h3><p>${escapeHtml(data.raw_text)}</p>
      <button class="primary" onclick="runAnalysis('${type}')">重试</button></div>`;
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
    const warn = /限流|断崖|冻结/.test(data.curve_shape || "") ? " warn" : "";
    html += `<h3>扩散曲线形状 <span class="confidence">置信度 ${escapeHtml(data.shape_confidence)}</span></h3>`;
    html += `<p><span class="badge${warn}">${escapeHtml(data.curve_shape)}</span></p>`;
    html += kvRow("扩散阶段", data.diffusion_stage);
    html += kvRow("卡点信号", data.bottleneck_signal ?? "没有明显卡点");
    html += kvRow("限流vs衰减", data.throttle_vs_decay);
    html += renderList("推动继续扩散的改动", data.unlock_actions);
    if (data.caveat) html += `<div class="caveat">${escapeHtml(data.caveat)}</div>`;
  } else if (type === "creator_profile") {
    html += renderList("当前内容方向分布", data.content_direction_breakdown);
    html += renderList("钩子模式", data.hook_patterns);
    if (data.text_and_music_style) html += `<h3>文字 / 配乐风格</h3><p>${escapeHtml(data.text_and_music_style)}</p>`;
    if (data.matrix_assessment) html += `<h3>矩阵结构评估</h3><p>${escapeHtml(data.matrix_assessment)}</p>`;
    html += renderList("矩阵调整建议", data.matrix_recommendation);
  }

  const m = data._meta || {};
  const model = rowMeta?.model || m.model;
  const created = rowMeta?.created ? rowMeta.created.slice(0, 16).replace("T", " ") : "刚刚";
  const inTok = rowMeta?.inputTokens ?? m.input_tokens;
  const outTok = rowMeta?.outputTokens ?? m.output_tokens;
  if (model) {
    const tok = inTok != null ? ` · ${formatNum(inTok)}+${formatNum(outTok)} tokens` : "";
    html += `<div class="caveat">分析于 ${escapeHtml(created)} · ${escapeHtml(model)}${tok} · 数据快照截至分析时刻</div>`;
  }

  html += `</div>`;
  container.innerHTML = html;
}

function renderList(title, items) {
  if (!items || items.length === 0) return "";
  return `<h3>${title}</h3><ul>${items.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`;
}

function kvRow(k, v) {
  if (v == null || v === "") return "";
  return `<div class="kv-row"><div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(v)}</div></div>`;
}

// ---------- 选中视频：指标面板（vs 基线）----------

function rate(a, b) { return b ? a / b : null; }
function pct(x) { return x == null ? "--" : (x * 100).toFixed(1) + "%"; }

async function loadMetricsPanel(id) {
  const panel = document.getElementById("metrics-panel");
  try {
    const [video, baseline] = await Promise.all([api(`/api/posts/${id}`), api(`/api/baseline`)]);
    const saveRate = rate(video.saves, video.plays);
    const v2f = rate(video.new_followers, video.profile_visits);
    const highIntent = (video.high_intent_comments || 0) + (video.high_intent_dms || 0);
    const metrics = [
      ["完播率", pct(video.completion_rate), video.completion_rate, baseline.avg_completion_rate],
      ["收藏率", pct(saveRate), saveRate, baseline.avg_save_rate],
      ["访问→关注", pct(v2f), v2f, baseline.avg_visit_to_follow_rate],
      ["高意向信号", formatNum(highIntent), highIntent, baseline.avg_high_intent_signals],
    ];
    panel.innerHTML = `<div class="metrics-grid">${metrics.map(metricCell).join("")}</div>`;
  } catch (e) {
    panel.innerHTML = "";
  }
}

function metricCell([label, valueStr, val, base]) {
  let delta = "";
  if (val != null && base) {
    const d = (val - base) / base;
    const cls = d > 0.02 ? "up" : d < -0.02 ? "down" : "flat";
    const sign = d >= 0 ? "+" : "";
    delta = `<div class="delta ${cls}">${sign}${(d * 100).toFixed(0)}% vs 基线</div>`;
  }
  return `<div class="metric"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(valueStr)}</div>${delta}</div>`;
}

// ---------- 选中视频：扩散曲线（快照）----------

let diffusionChartInstance = null;

async function loadDiffusionChart(id) {
  const wrap = document.getElementById("diffusion-wrap");
  const snapshots = await api(`/api/posts/${id}/snapshots`);
  if (!snapshots || snapshots.length === 0) {
    wrap.style.display = "none";
    if (diffusionChartInstance) { diffusionChartInstance.destroy(); diffusionChartInstance = null; }
    return;
  }
  wrap.style.display = "block";
  const labels = snapshots.map((s) => (s.checked_at || "").slice(0, 16).replace("T", " "));
  const plays = snapshots.map((s) => s.plays);
  const interaction = snapshots.map((s) =>
    s.plays ? +(((s.likes || 0) + (s.comments || 0) + (s.shares || 0) + (s.saves || 0)) / s.plays * 100).toFixed(2) : null
  );
  if (diffusionChartInstance) diffusionChartInstance.destroy();
  diffusionChartInstance = new Chart(document.getElementById("diffusion-chart"), {
    data: {
      labels,
      datasets: [
        { type: "bar", label: "播放量", data: plays, yAxisID: "y", order: 2, backgroundColor: "rgba(185,164,126,0.55)" },
        { type: "line", label: "互动率 %", data: interaction, yAxisID: "y1", order: 1, tension: 0.3,
          borderColor: "#EAE6DC", borderWidth: 1.5, pointRadius: 3, pointBackgroundColor: "#B9A47E" },
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
      plugins: { legend: { labels: { color: "#8C877C", font: { family: "ui-monospace", size: 11 } } } },
    },
  });
}

// ---------- 内容画像 ----------

async function loadContentProfileForm(id) {
  // 内容画像住在 creative 上，不在 post 上：同一条内容发多个平台时只有一份，
  // 改哪条 post 的画像，改的都是同一个 creative。
  const post = await api(`/api/posts/${id}`);
  const c = post.creative || {};
  document.getElementById("pf-content_summary").value = c.content_summary || "";
  document.getElementById("pf-on_screen_text").value = c.on_screen_text || "";
  document.getElementById("pf-music").value = c.music || "";
  document.getElementById("pf-hook_description").value = c.hook_description || "";
  document.getElementById("pf-content_pillar").value = c.content_pillar || "";
  const hint = document.getElementById("creative-hint");
  if (hint) {
    hint.textContent = post.creative_id
      ? `内容画像 #${post.creative_id}（这条内容在其他平台的发布共用同一份）`
      : "还没有内容画像，保存后会为这条内容建立一份";
  }
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
  await api(`/api/posts/${state.selectedId}/content-profile`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  document.getElementById("status-line").textContent = "内容画像已保存";
}

// ---------- 快照 ----------

async function loadSnapshots(id) {
  const snapshots = await api(`/api/posts/${id}/snapshots`);
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
    shares: Number(document.getElementById("sn-shares").value) || 0,
    saves: Number(document.getElementById("sn-saves").value) || 0,
    profile_visits: Number(document.getElementById("sn-profile_visits").value) || 0,
    new_followers: Number(document.getElementById("sn-new_followers").value) || 0,
    completion_rate: document.getElementById("sn-completion").value
      ? Number(document.getElementById("sn-completion").value) / 100
      : null,
  };
  await api(`/api/posts/${state.selectedId}/snapshots`, {
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
    const result = await api("/api/posts/import", { method: "POST", body: formData });
    let msg = `新增 ${result.inserted} 条，更新 ${result.updated} 条`;
    if (result.errors?.length) {
      msg += `，${result.errors.length} 行有问题`;
      console.warn("导入问题行：", result.errors);
      alert("部分行未完整导入：\n" + result.errors.map((e) => `第${e.line}行：${e.error}`).join("\n"));
    }
    document.getElementById("status-line").textContent = msg;
    await loadVideos();
    await loadTrendChart();
    await loadHeroBaseline();
  } catch (err) {
    document.getElementById("status-line").textContent = "导入失败: " + err.message;
  }
});

// ---------- 截图上传 → 提取草稿 → 确认入库 ----------

const visionDrafts = {}; // cardId -> 提取结果原文
let visionSeq = 0;

// 视频字段：[key, 标签, 类型] 类型 pct 的展示为百分数，保存时 /100
const V_FIELDS = [
  ["title", "标题", "text"], ["publish_datetime", "发布时间", "text"],
  ["plays", "播放", "int"], ["likes", "点赞", "int"],
  ["comments", "评论", "int"], ["shares", "分享", "int"],
  ["saves", "收藏", "int"], ["danmaku_count", "弹幕", "int"],
  ["completion_rate", "完播率%", "pct"], ["bounce_2s_rate", "2s跳出%", "pct"],
  ["avg_watch_time", "均播时长s", "num"], ["cover_ctr", "封面点击%", "pct"],
  ["new_followers", "涨粉", "int"], ["unfollows", "取关", "int"],
  ["fan_conversion_rate", "粉转化%", "pct"],
];
const A_FIELDS = [
  ["period", "统计口径", "text"], ["plays", "播放", "int"],
  ["profile_visits", "主页访问", "int"], ["likes", "点赞", "int"],
  ["comments", "评论", "int"], ["shares", "分享", "int"],
  ["net_followers", "净增粉", "int"], ["unfollows", "取关", "int"],
  ["completion_rate", "完播率%", "pct"], ["search_views", "作品搜索", "int"],
  ["cover_ctr", "封面点击%", "pct"], ["danmaku", "弹幕", "int"],
];

document.getElementById("shot-input").addEventListener("change", async (e) => {
  const files = [...e.target.files];
  e.target.value = "";
  if (!files.length) return;
  const panel = document.getElementById("vision-panel");
  panel.style.display = "block";
  for (const f of files) {
    const cardId = `vd-${++visionSeq}`;
    const holder = document.createElement("div");
    holder.className = "result-card draft-card";
    holder.id = cardId;
    holder.innerHTML = `<div class="card-tag">截图提取中 · ${escapeHtml(f.name)}</div><div class="empty-state">调用 Claude vision 识别中...</div>`;
    panel.prepend(holder);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const draft = await api("/api/vision/extract", { method: "POST", body: fd });
      renderVisionDraft(cardId, f.name, draft);
    } catch (err) {
      holder.innerHTML = `<div class="card-tag">${escapeHtml(f.name)}</div><p>提取失败：${escapeHtml(err.message)}</p>`;
    }
  }
});

function fieldInput(cardId, scope, idx, key, label, type, value) {
  let v = value;
  if (type === "pct" && v != null) v = +(v * 100).toFixed(2);
  const shown = v == null ? "" : v;
  return `<label>${escapeHtml(label)}<input id="${cardId}-${scope}${idx}-${key}"
    type="${type === "text" ? "text" : "number"}" step="any" value="${escapeHtml(shown)}"></label>`;
}

function readField(cardId, scope, idx, key, type) {
  const el = document.getElementById(`${cardId}-${scope}${idx}-${key}`);
  if (!el || el.value === "") return null;
  if (type === "text") return el.value;
  const n = Number(el.value);
  if (Number.isNaN(n)) return null;
  return type === "pct" ? n / 100 : type === "int" ? Math.round(n) : n;
}

const PAGE_TYPE_LABELS = {
  video_detail: "单视频详情页", video_list: "作品列表",
  account_overview: "账号数据总览", account_diagnosis: "账号诊断", unknown: "未识别页面",
};

function renderVisionDraft(cardId, fname, draft) {
  const holder = document.getElementById(cardId);
  if (draft._api_error) {
    holder.innerHTML = `<div class="card-tag">${escapeHtml(fname)}</div>
      <p>API 调用失败${draft.retryable ? "（可重试）" : ""}：${escapeHtml(draft._api_error)}</p>`;
    return;
  }
  visionDrafts[cardId] = draft;
  let html = `<div class="card-tag">${escapeHtml(fname)} ·
    <span class="badge">${escapeHtml(PAGE_TYPE_LABELS[draft.page_type] || draft.page_type)}</span></div>`;

  (draft.videos || []).forEach((v, i) => {
    if (v.status === "私密") {
      html += `<div class="draft-video private"><span class="badge warn">私密 · 已跳过</span>
        <span class="muted-title">${escapeHtml(v.title || "(无标题)")}</span></div>`;
      return;
    }
    html += `<div class="draft-video"><div class="vision-grid">`;
    V_FIELDS.forEach(([key, label, type]) => { html += fieldInput(cardId, "v", i, key, label, type, v[key]); });
    html += `</div></div>`;
  });

  if (draft.account) {
    html += `<h3>账号级数据</h3><div class="vision-grid">`;
    A_FIELDS.forEach(([key, label, type]) => { html += fieldInput(cardId, "a", 0, key, label, type, draft.account[key]); });
    html += `</div>`;
    if (draft.account.peer_percentiles)
      html += `<div class="caveat">同行对比：${escapeHtml(JSON.stringify(draft.account.peer_percentiles))}</div>`;
  }

  const co = draft.curve_observation;
  if (co && co.visible) {
    html += `<h3>趋势图观察 <span class="badge">${escapeHtml(co.pattern_guess || "无法判断")}</span></h3>
      <p>${escapeHtml(co.shape_description || "")}<span class="confidence">${escapeHtml(co.granularity || "")}</span></p>`;
  }
  if (draft.page_type === "video_detail") {
    const now = new Date().toISOString().slice(0, 16);
    html += `<div class="vision-grid"><label>观察时间（快照 checked_at）
      <input id="${cardId}-checked_at" type="datetime-local" value="${now}"></label></div>`;
  }
  if (draft.notes) html += `<div class="caveat">⚠ 需复核：${escapeHtml(draft.notes)}</div>`;

  const m = draft._meta || {};
  html += `<div class="draft-actions">
    <button class="primary" onclick="saveVisionDraft('${cardId}')">确认入库</button>
    <button class="btn-ghost" onclick="discardVisionDraft('${cardId}')">丢弃</button>
    <span class="confidence">${m.input_tokens != null ? `${formatNum(m.input_tokens)}+${formatNum(m.output_tokens)} tokens` : ""}</span>
  </div>`;
  holder.innerHTML = html;
}

async function saveVisionDraft(cardId) {
  const draft = visionDrafts[cardId];
  if (!draft) return;
  const videos = (draft.videos || []).map((v, i) => {
    if (v.status === "私密") return { status: "私密", title: v.title };
    const out = { status: v.status || "已发布" };
    V_FIELDS.forEach(([key, , type]) => { out[key] = readField(cardId, "v", i, key, type); });
    return out;
  });
  let account = null;
  if (draft.account) {
    account = {};
    A_FIELDS.forEach(([key, , type]) => { account[key] = readField(cardId, "a", 0, key, type); });
    account.peer_percentiles = draft.account.peer_percentiles || null;
  }
  const checkedEl = document.getElementById(`${cardId}-checked_at`);
  const payload = {
    page_type: draft.page_type,
    videos, account,
    curve_observation: draft.curve_observation,
    checked_at: checkedEl?.value ? new Date(checkedEl.value).toISOString() : null,
  };
  try {
    const r = await api("/api/vision/save", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    document.getElementById("status-line").textContent =
      `入库：新增${r.inserted} 更新${r.updated} 快照${r.snapshots}` +
      (r.skipped_private ? ` 跳过私密${r.skipped_private}` : "") + (r.account_saved ? " 账号级✓" : "");
    discardVisionDraft(cardId);
    await loadVideos(); await loadTrendChart(); await loadHeroBaseline();
  } catch (err) {
    document.getElementById("status-line").textContent = "入库失败: " + err.message;
  }
}

function discardVisionDraft(cardId) {
  delete visionDrafts[cardId];
  document.getElementById(cardId)?.remove();
  const panel = document.getElementById("vision-panel");
  if (!panel.children.length) panel.style.display = "none";
}

// ---------- 初始化 ----------

loadVideos();
loadTrendChart();
loadHeroBaseline();
loadDuplicateCandidates();


// ---------- 疑似重复的作品（发现由机器做，合并由人确认）----------
//
// 截图是主要数据源，而同一条作品在列表页（标题被截断）和详情页（完整标题）长得不一样，
// OCR 还会读错字，于是同一条内容容易进两行。这里只列出候选和判断依据 ——
// 真正合并要点一下，跟截图入库要人确认是同一个道理：破坏性操作不自动做。

async function loadDuplicateCandidates() {
  const wrap = document.getElementById("dup-banner");
  if (!wrap) return;
  let groups = [];
  try {
    groups = await api("/api/posts/duplicate-candidates");
  } catch (e) {
    wrap.style.display = "none";
    return;
  }
  if (!groups.length) {
    wrap.style.display = "none";
    wrap.innerHTML = "";
    return;
  }
  wrap.style.display = "block";
  wrap.innerHTML =
    `<div class="dup-head">发现 ${groups.length} 组疑似重复的作品 —— 确认后才会合并</div>` +
    groups.map((g, i) => {
      const rows = g.posts
        .map(
          (p) => `<li><span class="dup-id">#${p.id}</span>
             <span class="dup-title">${escapeHtml(p.title || "(无标题)")}</span>
             <span class="dup-metrics">播放 ${formatNum(p.plays)} · 赞 ${formatNum(p.likes)}
             · 评 ${formatNum(p.comments)} · 完播 ${p.completion_rate != null ? (p.completion_rate * 100).toFixed(1) + "%" : "--"}</span></li>`
        )
        .join("");
      return `<div class="dup-group">
        <div class="dup-reason">${escapeHtml(g.publish_date)} · ${escapeHtml(g.reason)}</div>
        <ul class="dup-list">${rows}</ul>
        <button class="primary" onclick="mergeDuplicates(${i}, [${g.post_ids.join(",")}], this)">
          合并这 ${g.post_ids.length} 条
        </button>
      </div>`;
    })
    .join("");
}

async function mergeDuplicates(idx, postIds, btn) {
  if (!confirm(`把 #${postIds.join("、#")} 合并成一条？\n` +
               `保留字段最全的那条作为底稿，其余的非空数值补进来，快照合并去重。\n` +
               `这一步不可撤销（但数据库每天有备份）。`)) return;
  btn.disabled = true;
  try {
    const r = await api("/api/posts/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ post_ids: postIds }),
    });
    document.getElementById("status-line").textContent =
      `已合并为 #${r.merged_into}（去掉 ${r.removed_posts.length} 条重复、${r.snapshots_deduped} 条重复快照）`;
    await loadVideos();
    await loadTrendChart();
    await loadHeroBaseline();
    await loadDuplicateCandidates();
  } catch (err) {
    btn.disabled = false;
    document.getElementById("status-line").textContent = "合并失败: " + err.message;
  }
}
