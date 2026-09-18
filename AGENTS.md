# Shiome working agreement

## Branches — creator instruction, 2026-09-11

- Before starting any new feature, independent fix, cleanup or documentation change,
  create a new branch. Small changes are not an exception.
- Create it from the immediately preceding work branch and target that preceding branch
  in its PR. Keep a stack: `feature/a <- feature/b <- feature/c` (arrows are PR targets).
- The first feature in a phase starts from and targets its `release/phase-*` branch.
  If the preceding work has already merged, continue from its updated integration branch.
- Keep each branch and PR limited to one cohesive change. Review corrections to that
  same change may stay on its branch; start a fresh branch before unrelated work.
- Do not append a new feature to an existing feature branch, rewrite earlier PRs to
  absorb it, or force-push old branches just to rearrange the stack.
- Merge the stack from the bottom up. After a parent merges, update the child's base
  and check its diff before proceeding. Do not delete a branch still targeted by a child PR.
- Follow the version/changelog rules in [docs/workflow.md](docs/workflow.md), including
  a new prerelease number for each PR. The branch-rule change itself follows this workflow.

## Validation and local data

- Run checks appropriate to the change. Normal tests must not invoke paid AI services.
- Preserve real screenshots, local databases and migration compatibility. Generated files
  belong in ignored temporary directories and should be cleaned up after use.
- Local Docker Desktop has produced startup errors in this session. Use the repository's
  container CI for deployment checks; do not restart Docker Desktop without a new request.

## 创作者约定

每个新功能、独立修复、清理或文档变更，无论大小，都先从前一个工作分支新建分支，
PR 指向前一个分支。一个分支只承载一件完整的事，同一件事的审查修正可以继续提交。
前一个分支已经合并时，从更新后的承接分支继续。按依赖顺序合并，调整子 PR 后再删除父分支。
这些约定自本次起执行，已有 PR 不做历史重写。
