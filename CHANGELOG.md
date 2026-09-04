# Changelog / 更新记录

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

本项目所有重要变更都记录在此。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## English

### [Unreleased]

_Phase 1 · hosting — nothing merged yet._

### [0.2.1] — 2026-09-02

**Changed**
- Git tags normalised to the standard `v0.2.0` form. The repository's first tag was
  written `v.0.1.0`, with a dot after the `v`, and the convention had been documented to
  match it. Both existing tags were renamed in place — same commits, and `v0.2.0` keeps
  its original annotation and date. Changelog compare links and `docs/workflow.md` now
  describe the standard form.

### [0.2.0] — 2026-09-02

**Breaking**
- The `videos` table and every `/api/videos*` route are gone. A creative (what you made)
  and a post (that creative published to one platform) are now separate: `accounts` /
  `creatives` / `posts` / `post_snapshots`. Routes are `/api/posts*`, plus new
  `/api/accounts`, `/api/creatives`, `/api/creator-notes`, and
  `/api/analyze/posts/{id}/{type}` + `/api/analyze/account/{type}`. No compatibility
  aliases — the only client was this repo's own frontend. Reasoning: `docs/roadmap-v2.md`.
- Account persona moved out of `prompts.py` source onto `accounts.persona`. An account
  with no persona now says so in the prompt instead of borrowing another account's.
- The default database file is `app/data/shiome.db`. An existing `douyin.db` is copied
  (not moved) on first launch; the v1 file is left untouched.

**Fixed**
- `compute_baseline` averaged across platforms, which would have made every "vs baseline"
  delta meaningless as soon as a second platform existed. Now scoped per account.
- The trend-forecast prompt hard-coded Douyin's "24 hours decides it" in shared code;
  moved into the per-platform mechanism context, where it is true.
- `content_ideas` and `creator_profile` received no platform at all.
- Post identity matched on exact `(title, publish_date)`, so a truncated list-page title
  and a full detail-page title created two rows. Now: platform post id first, then fuzzy
  title within the same account and publish date.
- `creator_profile` audited posts rather than creatives, which would have counted one
  video once per platform and inflated the content-matrix proportions.
- The exported HTML report called itself self-contained while loading Chart.js from a CDN.
  The library is now embedded, so a downloaded report still renders offline.

**Added**
- Duplicate detection (`GET /api/posts/duplicate-candidates`) and confirmed merge
  (`POST /api/posts/merge`), with a dashboard banner. Detection is automatic; merging is
  not — it needs a click, like every other number that drives a decision.
- Non-destructive v1 to v2 migration: tagged backup first, old tables renamed to
  `_v1_*` rather than dropped, and only byte-identical rows collapsed automatically.
- `creator_notes`, `conversations` and `messages` tables, `app/analysis/context.py` and
  `app/analysis/registry.py` — the sockets for the Phase 5 conversational assistant. The
  context and registry modules are used by the analyses today, not stubs.
- `platform_data` JSON column on posts and snapshots for fields only one platform has.
- MIT license, `docs/roadmap-v2.md`, and a public devlog at `docs/devlog/`.
- pytest suite (62 tests) replacing the manual smoke script, plus GitHub Actions CI.
  Analysis tests are double-gated so CI can never spend money.

#### Earlier in this cycle

**Added**
- Vision ingest: upload creator-center screenshots (phone or PC — layout-agnostic) →
  Claude vision extracts a draft → confirm/edit in the dashboard → saved through the
  same upsert path as CSV. 私密 (private) videos are flagged and refused server-side.
- Per-video detail-page fields the exports never had: 完播率, 2s跳出率, 弹幕, 封面点击率,
  涨粉/取关, 粉丝转化 — new nullable columns on `videos`/`video_snapshots`.
- New `account_metrics` table for account-level pages (主页访问, 净增粉/取关, 账号完播率,
  作品搜索, 同行百分位) + `GET /api/account-metrics`.
- Detail-page hourly trend chart is read *qualitatively* (shape description + pattern
  guess) and stored as `curve_note` on vision snapshots; 扩散诊断 uses it as corroborating
  eyewitness alongside numeric snapshots.
- Capture protocol guide: `docs/capture-guide.md` (per-video +24h/+3d; weekly list +
  account shots; no folder sorting needed).
- Delete button on each video row (removes its snapshots and analyses too, with confirm).
- Pluggable vision provider: `VISION_PROVIDER`/`VISION_MODEL` env decouple screenshot
  extraction from the analysis model — Anthropic (default now `claude-sonnet-4-6`,
  upgraded from Haiku) or Gemini (`gemini-3.5-flash` via `GEMINI_API_KEY`).
- Standalone dark-theme HTML account report (`GET /api/report`, `?download=1`), rendered
  from cached analyses only — no new API cost.
- Dashboard: hero landing with logo/stats/actions, per-video metrics vs baseline,
  diffusion-curve chart from snapshots, logo/favicon branding.
- Data-driven API smoke test (`tests/`) with JSON + CSV fixtures.
- Daily SQLite backup on first launch of the day (`app/data/backups/`, keeps 10) —
  protects hand-entered snapshots/profiles from cloud-sync corruption.
- Per-analysis cost visibility: token usage + duration stored and shown on result cards.

**Changed**
- Replaced the Douyin "traffic-pool tier" model with diffusion-curve analysis
  (pool_diagnosis → curve shape / diffusion stage / throttle-vs-decay); added the
  platform seam (`platform` column, per-platform mechanism contexts, 小红书/B站 stubs).
- CSV import now upserts (no duplicate rows on re-import) and reports per-row errors;
  parser tolerates `1.2万`, `21秒`, `0:21`, comma-grouped numbers.
- Analysis outputs are now schema-enforced via tool-forced JSON (structurally
  eliminates parse failures); API errors return a friendly retryable envelope
  instead of a 500.
- Baseline now averages the most recent 20 non-anomaly videos instead of all history.
- Upgraded `anthropic` SDK 0.39 → 0.116 (removes the httpx pin).

### [0.1.0] — 2026-07-02

Initial public release of the runnable skeleton.

**Added**
- FastAPI backend with SQLite storage and a vanilla HTML/JS + Chart.js dashboard.
- Five independent analysis modules: enhancement direction, content ideas, trend
  forecast, pool diagnosis, and creator profile.
- CSV ingestion with fuzzy header matching (`COLUMN_ALIASES`).
- Anomaly-period handling that excludes flagged videos from baselines.
- Platform-mechanism reference framework in `prompts.py`.
- Project docs: `README.md`, design notes in `MEMO.md`, this `CHANGELOG.md`,
  `.gitignore`, and `.env.example`.

---

## 中文

### [未发布]

_Phase 1 · 上云 —— 还没有合入的改动。_

### [0.2.1] — 2026-09-02

**变更**
- git tag 统一成标准写法 `v0.2.0`。仓库最早那个 tag 写成了 `v.0.1.0`（`v` 后面带一个点），
  之前的约定是照着它写的。现在把已有的两个 tag 都改了名 —— 指向的提交不变，
  `v0.2.0` 保留原来的注释和日期。CHANGELOG 的对比链接和 `docs/workflow.md` 一并改成标准写法。

### [0.2.0] — 2026-09-02

**破坏性变更**
- `videos` 表和所有 `/api/videos*` 路由都没有了。creative（你做的东西）和 post（那个创作物
  发到某个平台上）现在是分开的：`accounts` / `creatives` / `posts` / `post_snapshots`。
  路由改为 `/api/posts*`，并新增 `/api/accounts`、`/api/creatives`、`/api/creator-notes`，
  以及 `/api/analyze/posts/{id}/{type}` 和 `/api/analyze/account/{type}`。
  没有保留兼容别名——唯一的调用方就是本仓库自己的前端。理由见 `docs/roadmap-v2.md`。
- 账号人设从 `prompts.py` 源码搬到 `accounts.persona`。没填人设的账号会在 prompt 里如实说明，
  而不是沿用别的账号的人设。
- 默认数据库文件改为 `app/data/shiome.db`。已有的 `douyin.db` 会在首次启动时被**复制**
  （不是移动）过去，v1 文件原地保留。

**修复**
- `compute_baseline` 跨平台求平均——一旦有第二个平台，dashboard 上每个「对基线 Δ」都会失去意义。
  现在按账号隔离。
- 流量预估的 prompt 把抖音的「24小时定生死」写死在共享代码里；移到按平台的机制上下文中，
  在那里它才成立。
- `content_ideas` 和 `creator_profile` 完全不接收平台参数。
- 作品身份按 `(标题, 发布日期)` 精确匹配，于是列表页的截断标题和详情页的完整标题会建出两行。
  现在：优先用平台侧作品 ID，其次在同账号同发布日期内做标题模糊匹配。
- `creator_profile` 审计的是 post 而不是 creative——同一条内容发几个平台就会被数几遍，
  内容矩阵占比会被平台数量放大成假象。
- 导出的 HTML 报告自称「自包含」，却从 CDN 加载 Chart.js。现在库是内嵌的，
  下载下来断网也能看到图。

**新增**
- 重复发现（`GET /api/posts/duplicate-candidates`）和确认后合并（`POST /api/posts/merge`），
  dashboard 上有横幅提示。发现是自动的，合并不是——要点一下，
  跟其他任何影响决策的数字一样。
- 不删数据的 v1→v2 迁移：先打带标记的备份，旧表改名为 `_v1_*` 而不是 DROP，
  只自动合并每个字段都完全相同的行。
- `creator_notes`、`conversations`、`messages` 表，以及 `app/analysis/context.py`
  和 `app/analysis/registry.py`——给 Phase 5 对话式助手留的插槽。
  其中 context 和 registry 今天就在被分析模块使用，不是空壳。
- posts 和快照上的 `platform_data` JSON 列，用于只有某一个平台才有的字段。
- MIT 许可证、`docs/roadmap-v2.md`，以及 `docs/devlog/` 公开开发日志。
- pytest 测试套件（62 个）取代手动冒烟脚本，加上 GitHub Actions CI。
  分析类测试有双重保险，CI 不可能花到钱。

#### 本周期更早的改动

**新增**
- 截图采集：上传创作者中心截图（手机/PC 排版均可）→ Claude vision 提取草稿 →
  dashboard 内确认/修改 → 与 CSV 同一条 upsert 路径入库。私密视频自动标记并被
  服务端拒绝入库。
- 导出文件里从来没有的详情页字段：完播率、2s跳出率、弹幕、封面点击率、涨粉/取关、
  粉丝转化——`videos`/`video_snapshots` 新增可空列。
- 新增 `account_metrics` 表承接账号级页面（主页访问、净增粉/取关、账号完播率、
  作品搜索、同行百分位）+ `GET /api/account-metrics`。
- 详情页小时级趋势图做**定性**读取（形状描述+形态初判），作为 `curve_note` 存进
  vision 快照；扩散诊断把它当作数字快照的旁证使用。
- 采集节奏指南：`docs/capture-guide.md`（每条视频 +24h/+3天；每周列表+账号页各一张；
  无需整理文件夹）。
- 视频列表每行的删除按钮（连同快照/分析一起删，带确认）。
- 可插拔提取模型：`VISION_PROVIDER`/`VISION_MODEL` 把截图提取与分析模型解耦——
  Anthropic（默认升级为 `claude-sonnet-4-6`，不再用 Haiku）或 Gemini
  （`gemini-3.5-flash`，配 `GEMINI_API_KEY`）。
- 独立的暗色主题 HTML 账号报告（`GET /api/report`，`?download=1` 下载），只渲染已缓存分析，
  不产生新的 API 费用。
- Dashboard：带 logo/统计/操作入口的 hero 首屏、单视频指标对基线面板、快照扩散曲线图、
  logo/favicon 品牌化。
- 数据驱动的 API 冒烟测试（`tests/`），JSON + CSV 数据插槽。
- 每天首次启动自动备份数据库（`app/data/backups/`，保留 10 份）——保护手动录入的
  快照/内容画像不被云同步损坏。
- 每次分析的成本可见性：token 用量 + 耗时入库并显示在结果卡片上。

**变更**
- 用扩散曲线分析取代抖音"流量池分级"模型（pool_diagnosis → 曲线形状 / 扩散阶段 /
  限流vs衰减判别）；加入平台接缝（`platform` 列、按平台的机制上下文、小红书/B站占位）。
- CSV 导入改为 upsert（重复导入不再产生重复行）并逐行报告错误；解析器容忍
  `1.2万`、`21秒`、`0:21`、千分位逗号。
- 分析输出改为工具强制 JSON（从结构上消灭解析失败）；API 错误返回可重试的友好
  提示而不是 500。
- 基线改为最近 20 条非异常期视频的均值，不再全历史平均。
- `anthropic` SDK 0.39 → 0.116（移除 httpx 版本锁）。

### [0.1.0] — 2026-07-02

可运行骨架的首个公开版本。

**新增**
- FastAPI 后端 + SQLite 存储 + 原生 HTML/JS + Chart.js 的 dashboard。
- 五个独立分析模块：增强方向、内容建议、流量预估、流量池定位、内容创作者画像。
- 带表头模糊匹配的 CSV 导入（`COLUMN_ALIASES`）。
- 异常期处理，计算基线时自动排除被标记的视频。
- `prompts.py` 中的平台机制参考框架。
- 项目文档：`README.md`、设计备忘 `MEMO.md`、本 `CHANGELOG.md`、
  `.gitignore` 和 `.env.example`。

---

[Unreleased]: https://github.com/Planetesimeow/Shiome/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/Planetesimeow/Shiome/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Planetesimeow/Shiome/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Planetesimeow/Shiome/releases/tag/v0.1.0
