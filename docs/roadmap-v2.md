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
`0.3.0-dev.12` 新增多人邀请和隔离，分析与截图默认切换至 Sonnet 5；需要合并并部署后才在云端生效。

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
- **Phase 5：对话式助手。** 围绕自己的内容与观察提问，引用有来源的数据，按需调用已有分析。可在需求明确时提前；届时再实现所需存储，新库不提前创建空的聊天表。
- **目标选择与布局。** 在不同成功目标间切换；咨询、成交、收入等商业指标在目标需要时加入。

暂不扩展按用户收费、自动抓平台数据、评论/私信全量采集、重视频处理和商业运营看板。当前受邀用户统一由管理员承担 AI 费用，先让手机采集与复盘形成稳定习惯。

## English

The current goal is sustainable content directions, viewing growth and follower growth. Future goal selection should change metrics, comparisons and recommendations, with audience fit and commercial outcomes available when relevant.

Phase 0's data model and migrations are complete. Phase 1 is live: VPS provisioning, HTTPS, server restart recovery and offsite backup restoration have been verified. The creator confirmed real iPhone upload and screenshot recognition on September 17, 2026. Confirmation-field completeness, quality, speed and cost remain under observation; automatic offsite backups remain unconfigured. The current plan is to continue the web app with an iPhone home-screen entry, without scheduling native packages or store distribution. Basic mobile capture moved forward from Phase 2.

Version 0.3.0-dev.12 adds invite-only accounts, per-user data isolation, administrator-funded AI usage and Sonnet 5 defaults. These changes need merging and deployment before taking effect on the live service.

Phase 2 prioritizes grouped screenshots, identity and observation tracking, missing-value semantics, retention/source/audience data, comparable baselines and follow-up content experiments. Account statistics and notes still need deliberate integration into analyses. Video-to-profile extraction remains future work.

Phases 3/4 cover Xiaohongshu, Bilibili and cross-platform comparison, ordered by actual demand. Phase 5 adds conversation grounded in the creator's data. Goal selection can be scheduled as usage clarifies its requirements. Multi-user billing, automated platform scraping and extensive commercial dashboards remain outside this pilot.
