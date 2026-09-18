"""
潮目 Shiome —— 单一版本号来源。

版本规则（见 docs/workflow.md）：
- Phase 2 从 1.0.0 开始；历史 0.x 版本不改写。
- 阶段进行中，每个 PR（含串联 feature 分支的 PR）带一个预发布号：1.0.0-dev.1、1.0.0-dev.2……
- release 合进 main 时去掉后缀，打 tag。

改这里的时候一并更新 CHANGELOG.md 最新的版本标题 —— tests/test_version.py 会盯着这两处一致。
"""
__version__ = "1.0.0-dev.1"
