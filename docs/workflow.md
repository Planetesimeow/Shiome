# Branches, releases and version codes / 分支、发布与版本号

> Adopted 2026-09-02, starting with Phase 1. Phase 0 shipped before this existed and was
> merged straight from a feature branch into `main`. The change that introduced these
> rules also went to `main` directly — it records the version `main` already was, so it
> could not wait behind a phase. Everything from Phase 1's first feature onward follows
> what is written below.
>
> 2026-09-02 起用，从 Phase 1 开始。Phase 0 是在这套规矩之前做的，直接从 feature 分支合进了 `main`。
> 引入这套规矩的那次改动本身也是直接进 `main` 的 —— 它记录的是 `main` 当时**已经**是的版本号，
> 不能压在一个阶段后面等。从 Phase 1 的第一个功能开始，一律照下面写的走。

---

## English

### Branches

```
main                        always releasable; every commit here is a shipped version
 └── release/phase-N-name   one long-lived branch per phase from the roadmap
      └── feature/...       one per change, branched from the release branch
```

- **A release branch per phase.** Phases come from [`roadmap-v2.md`](roadmap-v2.md) —
  `release/phase-1-hosting`, `release/phase-2-capture`, and so on. It is created from
  `main` when the phase starts and deleted after it merges back.
- **Feature branches come off the release branch, not `main`.** They target the release
  branch in their PR. This keeps a phase's half-finished parts out of `main` while still
  letting them integrate with each other.
- **`main` only ever receives a release branch**, as one PR at the end of the phase.
- **Delete a feature branch once merged.** Both local and remote. A branch list should
  describe work in progress, not work that happened.
- **Exception — a fix that cannot wait for the phase**: branch `hotfix/...` from `main`,
  PR into `main`, then merge `main` back down into the open release branch so it does not
  regress.

### Version codes

A version is stated on **every** PR, in the PR title and in `app/__init__.py`.

| | Version | Example |
|---|---|---|
| Phase | one minor version | Phase 0 → `0.2.0`, Phase 1 → `0.3.0` |
| Feature PR into a release branch | pre-release counter on the phase's version | `0.3.0-dev.1`, `0.3.0-dev.2` |
| Release branch into `main` | the phase version, suffix dropped, then tagged | `0.3.0` → tag `v0.3.0` |

Semantic versioning, with the pre-1.0 caveat that breaking changes bump the **minor**
rather than the major — which is what a phase is, so the two line up naturally.

Every PR therefore does three things:

1. Bump `__version__` in [`app/__init__.py`](../app/__init__.py).
2. Add the matching heading to [`CHANGELOG.md`](../CHANGELOG.md), in both languages.
3. Put the version in the PR title: `Add mobile capture page (0.3.0-dev.2)`.

`tests/test_version.py` fails if the constant and the newest changelog heading disagree,
so the two cannot drift apart quietly.

Tags are `v` followed directly by the version — `v0.1.0`, `v0.2.0`, `v0.3.0`. Only `main`
is tagged. (The repository's first tag was written `v.0.1.0`, with a dot; both existing
tags were renamed to the standard form on 2026-09-02, pointing at the same commits.)

### Why this shape

The previous workflow put every feature branch straight onto `main`, which was fine while
a change was one self-contained commit. It stops being fine when a phase is five changes
that only make sense together: hosting is not done until auth, deployment, backups and
the budget cap all exist, and merging any one of them into `main` alone would leave the
project in a state nobody wants to run.

A release branch gives a phase somewhere to be half-finished. `main` stays a branch you
can deploy from at any commit.

The version code exists so that a bug report can name what it was running. Anything
published — a deployed instance, an exported report, a screenshot in an issue — should be
traceable back to a commit, and `GET /api/version` answers that at runtime.

---

## 中文

### 分支

```
main                        永远可发布；这里的每个提交都是一个已发布版本
 └── release/phase-N-name   路线图里的一个大阶段对应一条长期分支
      └── feature/...       一个改动一条，从 release 分支切出来
```

- **一个阶段一条 release 分支。** 阶段来自 [`roadmap-v2.md`](roadmap-v2.md) ——
  `release/phase-1-hosting`、`release/phase-2-capture`，以此类推。阶段开始时从 `main` 切出来，
  合回去之后删掉。
- **feature 分支从 release 分支切，不从 `main` 切**，PR 也提给 release 分支。
  这样一个阶段里没做完的部分不会进 `main`，但它们之间可以先集成。
- **`main` 只接收 release 分支**，一个阶段结束时一个 PR。
- **合并完就删掉 feature 分支**，本地和远端都删。分支列表应该反映「正在做什么」，
  而不是「做过什么」。
- **例外 —— 等不到阶段结束的修复**：从 `main` 切 `hotfix/...`，PR 进 `main`，
  然后把 `main` 合回正在开的 release 分支，避免退化。

### 版本号

**每个** PR 都要有版本号，写在 PR 标题里，也写在 `app/__init__.py` 里。

| | 版本号 | 例子 |
|---|---|---|
| 一个阶段 | 一个小版本 | Phase 0 → `0.2.0`，Phase 1 → `0.3.0` |
| feature PR 合进 release 分支 | 该阶段版本的预发布计数 | `0.3.0-dev.1`、`0.3.0-dev.2` |
| release 分支合进 `main` | 去掉后缀的阶段版本，然后打 tag | `0.3.0` → tag `v0.3.0` |

遵循语义化版本，但有一个 1.0 之前的约定：破坏性变更升**小版本**而不是大版本 ——
而一个阶段恰好就是这个量级，所以两者天然对齐。

于是每个 PR 都要做三件事：

1. 改 [`app/__init__.py`](../app/__init__.py) 里的 `__version__`。
2. 在 [`CHANGELOG.md`](../CHANGELOG.md) 里加上对应的版本标题（中英文都要）。
3. 把版本号写进 PR 标题：`Add mobile capture page (0.3.0-dev.2)`。

`tests/test_version.py` 会在常量和最新的 changelog 标题不一致时报错，
所以这两处不会悄悄跑偏。

tag 是 `v` 直接跟版本号 —— `v0.1.0`、`v0.2.0`、`v0.3.0`。只给 `main` 打 tag。
（仓库最早的一个 tag 写成了带点的 `v.0.1.0`；2026-09-02 把已有的两个 tag 都改成了标准写法，
指向的提交不变。）

### 为什么改成这样

之前每条 feature 分支都直接进 `main`。一个改动是一个自洽的提交时，这没问题。
但一个阶段是五个只有凑在一起才成立的改动时就不行了：上云这件事，要等鉴权、部署、异地备份、
预算上限都有了才算完成，单独把其中一个合进 `main`，只会让项目停在一个没人想跑的状态。

release 分支给一个阶段提供了「可以做到一半」的地方，而 `main` 保持在任何一个提交上都能部署。

版本号存在的意义，是让一份 bug 报告能说清楚「我跑的是哪一版」。任何流出去的东西 ——
部署的实例、导出的报告、issue 里的一张截图 —— 都应该能追回到一个提交，
`GET /api/version` 在运行时回答这个问题。
