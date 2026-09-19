# 路线图 / Roadmap

更新于 2026-09-18。保留原文件名以兼容已有链接；本文只维护当前状态和后续工作。v1 到 v2 的建模过程见[开发日志 001](devlog/001-2026-09-02-creator-data-model.md)。

## 当前目标

先找到稳定、可持续制作的内容方向，提升观看和涨粉。优先回答：哪些系列值得继续，哪里影响观看或关注，下一条改什么，以及怎样复查是否有效。

完整工具以后应允许创作者选择目标：内容探索、观看增长、粉丝增长、精准触达、商业转化或自定义目标。选择结果应影响指标排序、同类比较、分析和建议；不是只换首页一句文案。当前 `goal_note` 可记录目标，完整选择器尚未实现。

## Phase 0：数据基础 — 已完成

账号、创作物、平台发布与快照分离；人设存为账号数据；基线按账号隔离；重复作品合并；旧数据库迁移与测试。已有迁移与历史表保留。当前多平台数据结构不等于各平台完整支持。

## Phase 1：上线与手机试运行 — 已上线，持续观察

已完成代码：

- 邀请制登录账号、首次管理员设置、共享密钥、按用户独立数据文件和会话撤销；生产凭据检查和 HTTPS 配置。
- 手机总览、作品与截图入口；截图确认、内容画像与快照编辑。
- SQLite 持久化、运行期间每日备份、登录下载、向新文件恢复。
- API 用量记录、月度预算、小服务器配置与部署说明。
- Python、两类浏览器及容器部署自动验证。

上线验收（2026-09-17）：

- VPS、HTTPS 和模型密钥已配置，服务器年付金额与续费金额已确认。
- 创作者已在 iPhone 确认上传与真实截图识别正常；确认入库后的字段完整性继续随实际使用复核。
- 整机重启后服务自动恢复、默认账号记录保留；数据库已下载到电脑并完成恢复演练。

预算方向为约 20 元人民币/月，包括少量 AI 调用。当前服务器为 21.99 美元/年，应用的 AI 月度
预算配置为 0.75 美元（按已记录费用检查，并非供应商账单硬上限）。持续自动异地备份尚未配置。
继续观察识别质量、速度与真实费用，再决定是否调整模型或额度。原 Phase 2 的基础手机入口已提前完成。
当前继续完善网页版，iPhone 可添加到主屏幕；原生安装包与商店上架暂不安排。
`0.3.0-dev.12` 的多人邀请、用户隔离和 Sonnet 5 默认配置已合入本阶段 release 并部署到云端。
本阶段以 `0.3.0` 收口，发布 PR #19 已合入 `main`；按创作者要求保留 `release/phase-1-hosting`。

## Phase 2：可信数据处理与内容复盘 — 目标 `1.0.1`

创作者已从 `main` 建立 `release/phase-2-dataprocessing`。本规划 PR 按创作者要求使用 `1.0.1`，
每项改动单独开分支和 PR。完整口径、截图范式与验收要求见 [Phase 2 数据处理方案](phase-2-data-plan.md)。

依次推进：

1. 指标字典与观察记录：账号日数据、账号周期数据、单作品累计快照分别存储，保留出处、时间、精度和缺失原因。
2. 标准导入：先支持现有两种官方 XLSX，再提供同一口径的版本化 CSV 模板；代码解析、预览确认、重复检测和批次撤销。
3. 截图补录：同作品同观察分组，补齐完播、来源和涨粉数据；OCR 与规则生成草稿，冲突人工复核。
4. 代码统计：确定性计算增量、比率、样本覆盖和可比基线；记录选数与公式，缺失分母不猜测。
5. AI 反馈与内容实验：仅使用确认后的事实，解释趋势、生成内容建议并注明依据；实验按同口径复查。
6. 外部数据验证：核验同类/同 tag API 的实际字段、覆盖、费用及多人服务许可，再决定是否接入。

当前仍是单张截图识别和确认，旧 CSV 已移除；上述新导入、分组及统计方案尚未实现。
曲线暂存可见趋势描述，账号统计和笔记仍需按分析需求接入。视频/图文素材生成内容画像草稿留待后续。

## 后续功能

- **Phase 3 / 4：更多平台。** 小红书、B站的专属采集、口径、界面与分析，以及同一创作物跨平台比较。实际优先级按使用需求和数据决定，不预设某平台更适合增长或转化。
- **Phase 5：对话式助手。** 围绕自己的内容与观察提问，引用有来源的数据，按需调用已有分析。可在需求明确时提前；届时再实现所需存储，新库不提前创建空的聊天表。
- **目标选择与布局。** 在不同成功目标间切换；咨询、成交、收入等商业指标在目标需要时加入。

暂不扩展按用户收费、平台全量抓取、评论/私信全量采集、重视频处理和商业运营看板。
平台 API 先验证可用性，不作为本阶段内部数据处理的前置条件。当前受邀用户统一由管理员承担 AI 费用。

## English

The current goal is sustainable content directions, viewing growth and follower growth. Future goal selection should change metrics, comparisons and recommendations, with audience fit and commercial outcomes available when relevant.

Phase 0's data model and migrations are complete. Phase 1 is live: VPS provisioning, HTTPS, server restart recovery and offsite backup restoration have been verified. The creator confirmed real iPhone upload and screenshot recognition on September 17, 2026. Confirmation-field completeness, quality, speed and cost remain under observation; automatic offsite backups remain unconfigured. The current plan is to continue the web app with an iPhone home-screen entry, without scheduling native packages or store distribution. Basic mobile capture moved forward from Phase 2.

Version 0.3.0-dev.12's invite-only accounts, per-user data isolation, administrator-funded AI usage and Sonnet 5 defaults have been merged into the phase release and deployed. Phase 1's 0.3.0 release PR #19 has merged into `main`; its release branch is retained at the creator's request.

The creator opened `release/phase-2-dataprocessing` from `main`. Phase 2 targets `1.0.1`, with this planning PR explicitly versioned `1.0.1` at the creator’s request. Follow the [data-processing plan](phase-2-data-plan.md): metric semantics and provenance first, then standard XLSX/CSV imports, grouped screenshot observations, deterministic statistics, AI feedback and content experiments. External APIs require a separate feasibility check. These are planned features; the current app still handles individual screenshots and has no CSV import. Account statistics and notes need deliberate integration into analyses; video-to-profile extraction remains future work.

Phases 3/4 cover Xiaohongshu, Bilibili and cross-platform comparison, ordered by actual demand. Phase 5 adds conversation grounded in the creator's data. Goal selection can be scheduled as usage clarifies its requirements. Multi-user billing, automated platform scraping and extensive commercial dashboards remain outside this pilot.
