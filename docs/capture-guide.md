# 截图采集指南 / Screenshot capture

当前目标：找到稳定内容方向，提升观看和涨粉。以下根据 2026-09-11 提供的 21 张真实生产截图整理。先保留能解释内容表现的数据，采集不要求每小时打卡。

## 现在怎么上传

手机打开已部署的 HTTPS 应用，在底部「截图」从相册选择；电脑使用「上传创作者中心截图」。PNG/JPG 等图片每张最多 10 MB，可多选。

每张独立识别、独立确认。重点复核标题、发布时间、作品时长、万/亿单位、百分数、观察时间和统计周期。确认后才写入数据库；私密作品按当前产品规则跳过，不能据此认定其历史数据没有价值。

详情草稿中的观察时间默认是**上传时的手机本地时间**。旧截图必须改成实际观察时间；上传时间不能冒充截图时间。切换页面或登录过期重登可保留当前截图草稿，刷新页面或关闭浏览器仍会丢失未保存草稿。

## 建议截哪些

这是起步采集节奏，按实际复盘价值调整，不是平台算法规定的时间窗。

| 时机 | 页面 | 重点 |
|---|---|---|
| 发布约 24 小时 | 单作品总览 | 标题、发布时间、状态、播放/赞评转藏、完播、2 秒跳出 |
| 发布约 24 小时 | 流量分析 → 内容吸引力 | 平均时长、5 秒完播、平均播放占比、带轴和图例的留存图 |
| 发布约 72 小时 | 再截单作品总览 | 同口径累计值；重要曲线被截断时补图 |
| 发布约 72 小时 | 流量来源 / 搜索词 | 来源标签、占比与关键词 |
| 发布约 72 小时 | 观众数据 | 吸粉量/率、脱粉量/率、不感兴趣，保留指标定义 |
| 每周 | 作品列表 + 近 7 日账号总览 | 覆盖本周作品；账号作品指标和粉丝指标分别截完整 |

明显继续增长或需要复盘的作品，约第 7 天补总览和来源。观众画像细分优先留给表现突出、低于预期或试新方向的作品。评论全文、城市/设备等长列表、收入和电商页面暂不要求日常采集；商业目标启用后再补。

## 当前能用到什么

总览、列表和部分账号指标可以进入确认表单。详情确认会保存快照；曲线可保留可见形状描述。**多张截图自动组成一条观察、无标题续图绑定作品、来源/留存/观众细分的完整字段尚未实现。** 这些补充图先保留原件，不能因成功上传就认为所有信息都已入库或参与分析。

同一作品先截带身份的首页，续图留一段重叠区域，文件可用 `作品简称_观察日期_页面.png` 命名。不把无标题续图编成新作品，不把多张互补图的累计值相加。重复候选只在人工核对后合并。

## 避免口径误读

- 保留标签、单位、统计周期、坐标轴、图例；不要只裁数字或把长页缩得无法读字。
- 累计播放和某小时新增播放分开；趋势图的一次提示框读数不能当作全作品累计值。
- 近 7 日与近 30 日不能拼成同一记录；局部图窗也不代表完整周期。
- 发布时间、页面截止时间、截图时间分开核对；来源不清的时间保持待确认。
- 缺失不是零，净增粉不是新增关注；作品指标与账号汇总分开。
- 只有「日期 + 播放量」的账号导出 CSV 不能从作品导入入口使用。作品 CSV 示例见 [`sample_import.csv`](../tests/fixtures/sample_import.csv)。

后续实现顺序见[路线图](roadmap-v2.md)。

## English

Use the phone capture tab or desktop screenshot button, review each extracted draft, then save. Images are limited to 10 MB each. Observation time initially uses the phone's current local time; correct it for older screenshots. Unsaved drafts survive view switching and reauthentication, but not a page reload or browser closure.

Start with post overview and retention at roughly 24 hours, then overview, sources/search terms and follower outcomes at roughly 72 hours. Add weekly post-list and seven-day account summaries; detailed audience breakdowns are selective. These are collection suggestions, not platform timing rules.

Grouped screenshots, identity binding for continuation pages, and complete source/retention/audience fields remain pending. Keep supplementary originals. Preserve labels, units, axes and periods; never mix cumulative with hourly values, account totals with post data, or net followers with new followers. CSV import expects one identified post per row.
