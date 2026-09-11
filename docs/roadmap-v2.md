# 路线图 / Roadmap

更新于 2026-09-11。保留原文件名以兼容已有链接；本文只维护当前状态和后续工作。v1 到 v2 的建模过程见[开发日志 001](devlog/001-2026-09-02-creator-data-model.md)。

## 当前目标

先找到稳定、可持续制作的内容方向，提升观看和涨粉。优先回答：哪些系列值得继续，哪里影响观看或关注，下一条改什么，以及怎样复查是否有效。

完整工具以后应允许创作者选择目标：内容探索、观看增长、粉丝增长、精准触达、商业转化或自定义目标。选择结果应影响指标排序、同类比较、分析和建议；不是只换首页一句文案。当前 `goal_note` 可记录目标，完整选择器尚未实现。

## Phase 0：数据基础 — 已完成

账号、创作物、平台发布与快照分离；人设存为账号数据；基线按账号隔离；重复作品合并；旧数据库迁移与测试。已有迁移与历史表保留。当前多平台数据结构不等于各平台完整支持。

## Phase 1：上线与手机试运行 — 进行中

已完成代码：

- 单用户口令登录、会话、生产凭据检查和 HTTPS 配置。
- 手机总览、作品与截图入口；截图确认、内容画像与快照编辑。
- SQLite 持久化、运行期间每日备份、登录下载、向新文件恢复。
- API 用量记录、月度预算、小服务器配置与部署说明。
- Python、两类浏览器及容器部署自动验证。

剩余验收：

- 确认服务器实际售价、续费和日本访问情况；配置服务器、域名与密钥。
- 使用公网 HTTPS 地址在真实手机完成登录 → 识别 → 确认 → 查看。
- 重启后数据仍在；下载到另一台设备并完成恢复演练。
- 观察少量真实调用的识别质量、速度和费用，再决定是否调整模型或额度。

预算方向为约 20 元人民币/月，包括少量 AI 调用；当前只有费用方案，未购买服务器，也未产生可用的公网实例。自动异地备份尚未配置。原 Phase 2 的基础手机入口已提前完成。

## Phase 2：可信采集与内容复盘

按生产截图暴露的问题推进：

1. 同作品截图组：首图绑定身份，续图补数据，同一观察合并，重复上传幂等；冲突集中复核。
2. 数据保真：区分未观察、不适用与真实 0；保存发布时间精度、截图时间、页面截止时间和统计周期。
3. 补充观看、来源和观众信息：5 秒完播、平均播放占比、留存摘要、推荐/搜索来源、搜索词、吸粉/脱粉/不感兴趣。数据字段须带作用范围与出处。
4. 更可比的基线：作品形态、时长、发布后年龄分组，展示有效样本量，防止新旧累计量直接比较。
5. 少量内容实验：给系列与开头等加标签，记录本次改动和要验证的指标，后续同口径复查。
6. 按各分析所需接入账号统计、笔记、来源与受众数据；保存选数依据。未使用的数据不假装已参与判断。
7. 视频或图文素材生成内容画像草稿，仍需人工确认。

当前每张截图独立确认，曲线仅作为可见趋势描述。这里列的是待开发功能，采集建议不等于已经能完整识别和使用所有页面。

## 后续功能

- **Phase 3 / 4：更多平台。** 小红书、B站的专属采集、口径、界面与分析，以及同一创作物跨平台比较。实际优先级按使用需求和数据决定，不预设某平台更适合增长或转化。
- **Phase 5：对话式助手。** 围绕自己的内容与观察提问，引用有来源的数据，按需调用已有分析。可在需求明确时提前；数据库预留表不代表聊天已实现。
- **目标选择与布局。** 在不同成功目标间切换；咨询、成交、收入等商业指标在目标需要时加入。

暂不扩展多用户计费、自动抓平台数据、评论/私信全量采集、重视频处理和商业运营看板。先让单人手机采集与复盘形成稳定习惯。

## English

The current goal is sustainable content directions, viewing growth and follower growth. Future goal selection should change metrics, comparisons and recommendations, with audience fit and commercial outcomes available when relevant.

Phase 0's data model and migrations are complete. Phase 1 has authentication, HTTPS/container configuration, phone workflows, persistent storage, backup/restore and API cost tracking. Provisioning, actual phone access, offsite recovery and real-use cost/quality checks remain pending. Basic mobile capture moved forward from Phase 2.

Phase 2 prioritizes grouped screenshots, identity and observation tracking, missing-value semantics, retention/source/audience data, comparable baselines and follow-up content experiments. Account statistics and notes still need deliberate integration into analyses. Video-to-profile extraction remains future work.

Phases 3/4 cover Xiaohongshu, Bilibili and cross-platform comparison, ordered by actual demand. Phase 5 adds conversation grounded in the creator's data. Goal selection can be scheduled as usage clarifies its requirements. Multi-user billing, automated platform scraping and extensive commercial dashboards remain outside this pilot.
