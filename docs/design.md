# 当前设计 / Current design

更新于 2026-09-11。这里描述现有实现；待做事项见[路线图](roadmap-v2.md)，历史取舍见[开发日志](devlog/README.md)。旧版 `MEMO.md` 已合并到本文，可从 Git 历史查询。

## 产品目标

当前先帮助创作者找到能持续制作的内容方向，提升观看和涨粉。详情优先展示播放、完播、新增关注及播放到关注的转化；选题建议寻找可重复的模式，内容画像审计方向的连贯性与探索比例。

账号的 `persona` 和 `goal_note` 是用户数据。分析尊重账号填写的目标，未填写时说明信息不足；不默认所有创作者都以商业转化为目标。目标选择器及不同目标下的完整指标布局留待后续实现。

## 数据与分析

```text
截图 → AI 提取草稿 → 人工确认 → 作品指标 / 时序快照 / 账号统计
作品 CSV → 表头与数据校验 → 作品指标
内容画像手填 → 创作物
作品 + 创作物 + 同账号基线 → 按需分析 → 缓存结果 / HTML 报告
```

- `accounts` 表示平台账号；`creatives` 表示内容本身；`posts` 表示一次平台发布；`post_snapshots` 保留不同观察时刻的数据。导入指标不覆盖手填内容画像。
- 五类分析独立执行，由 `analysis/registry.py` 登记作用范围与入口。`analysis/context.py` 只保留实际使用的作品、创作物和笔记取数函数。
- 账号统计和创作者笔记可以保存、查询，**目前五类分析尚未完整使用这些信息**。未接入的完整助手上下文组装函数已删除，避免形成两套貌似在用的数据入口。
- 基线为同账号最近 20 条非异常期作品的均值；新增播放、涨粉及播放到关注的基线。还没有按作品年龄、形态、时长分组；每个指标的有效样本数也尚未单独展示。
- 截图看不到的数据应留空，累计值、分时新增、净增粉与新增关注必须区分。历史计数列仍有默认 0，需要后续迁移区分“未观察”和“真实零”，不能把现有数据当作已经解决了缺失值问题。
- 曲线只能支持对可见趋势的描述，不能直接证明限流或审核原因。少量样本、时间窗不一致或缺少内容描述时，结论必须说明限制。历史分析保留原文，新提示不会自动重写它们。
- 当前多张截图逐张确认；跨截图分组、身份绑定、冲突复核与重复上传幂等尚未完成。不会从曲线图片自动还原精确逐时数据。

## 部署边界

FastAPI + SQLite + 原生 HTML/CSS/JavaScript。当前为单用户、单实例、单 worker；`owner_id` 及预留对话表不代表已经支持多租户或聊天。保留迁移、备份和既有表结构，以兼容已保存的数据。

公网入口通过 Caddy 提供 HTTPS；生产启动检查口令哈希和会话密钥。数据库放在持久卷，运行期间每天备份，可登录下载并恢复到新文件。异地备份仍需另行配置，详见[部署指南](deployment.md)。

AI 仅按需调用，花销单独记账。预算检查依据已记录金额，最后一笔和并发调用可能超额，无定价调用无法计入；严格账单限制还需要模型服务商端配合。前端复用同一项进行中的分析请求，避免切换标签重复发起调用。

## English

The current goal is sustainable content directions, better viewing and follower growth. Account persona and goal notes remain user data; analyses must respect them and state when context is missing. A goal selector and complete goal-specific layouts are future work.

Screenshots produce editable drafts before saving. CSV imports require one post per row. Accounts, creative descriptions, platform posts and observations remain separate; metric imports cannot overwrite creative descriptions. Five registered analyses use shared data readers and store results. Account statistics and notes are stored, but their integration into analyses is incomplete.

Baselines use the latest 20 normal posts within one account. Matching by post age, format and duration, per-metric sample counts, missing-value migration and grouped screenshot capture remain pending. Curve shape alone cannot establish moderation or distribution causes. Existing analysis records and schema migrations remain readable.

Deployment is one authenticated FastAPI worker with persistent SQLite, Caddy HTTPS and daily local backups. Reserved ownership and conversation fields do not provide multi-user isolation or chat. Offsite recovery and an actual phone session must be verified on the provisioned server. API budget checks use recorded costs and cannot guarantee an exact provider bill.
