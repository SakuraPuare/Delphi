# CI/CD 流水线

## 概述

项目使用 GitHub Actions 实现自动化 CI/CD，覆盖以下环节：

- **持续集成**：代码质量检查、单元测试、前端构建验证
- **Docker 构建**：多架构镜像构建并推送至 GHCR
- **自动发布**：基于 git tag 触发 changelog 生成和 GitHub Release 创建

## CI 工作流（ci.yml）

每次推送到 `main` 分支或提交 Pull Request 时自动触发。

### 并发控制

同一分支/PR 的多次推送只保留最新一次运行，旧的运行会被自动取消：

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

### Python Job

使用 uv 管理依赖，Python 3.12 环境：

| 步骤 | 命令 | 说明 |
|------|------|------|
| Ruff lint | `uv run ruff check src/` | 代码规范检查（E/W/F/I/UP/B/SIM/TCH 规则） |
| Ruff format | `uv run ruff format --check src/` | 代码格式检查 |
| Pytest | `uv run pytest -v --cov=delphi --cov-report=xml` | 单元测试 + 覆盖率报告 |

覆盖率报告会作为 artifact 上传，即使测试失败也会保留（`if: always()`）。

### Frontend Job

使用 Node.js 20，工作目录为 `web/`：

| 步骤 | 命令 | 说明 |
|------|------|------|
| 安装依赖 | `npm ci` | 基于 lockfile 的确定性安装 |
| 类型检查 | `npx tsc -b --noEmit` | TypeScript 编译检查 |
| 构建 | `npm run build` | 生产构建验证 |

npm 缓存基于 `web/package-lock.json` 自动管理。

## Docker 构建工作流（docker.yml）

推送 `v*` 格式的 tag 时自动触发，也支持手动触发（`workflow_dispatch`）。

### 构建特性

- **多架构支持**：通过 QEMU + Buildx 同时构建 `linux/amd64` 和 `linux/arm64`
- **镜像仓库**：推送至 GitHub Container Registry（`ghcr.io`）
- **Layer 缓存**：使用 GitHub Actions Cache（`type=gha,mode=max`）加速后续构建

### 镜像标签策略

| 标签格式 | 示例 | 说明 |
|----------|------|------|
| `{{version}}` | `0.1.0` | 完整语义化版本 |
| `{{major}}.{{minor}}` | `0.1` | 主版本.次版本 |
| `sha-{{sha}}` | `sha-a7d1e50` | 提交哈希 |

标签和 label 由 `docker/metadata-action` 自动从 git tag 中提取。

## 发布工作流（release.yml）

推送 `v*` 格式的 tag 时自动触发。

### 流程

1. 检出代码（`fetch-depth: 0` 获取完整历史）
2. 使用 [git-cliff](https://git-cliff.org/) 根据 `cliff.toml` 配置生成 changelog
3. 调用 `softprops/action-gh-release` 创建 GitHub Release，body 为生成的 changelog

### Changelog 生成规则

基于 [Conventional Commits](https://www.conventionalcommits.org/) 规范，commit 按类型自动分组：

| Commit 前缀 | 分组 |
|-------------|------|
| `feat` | Features |
| `fix` | Bug Fixes |
| `doc` | Documentation |
| `perf` | Performance |
| `refactor` | Refactoring |
| `style` | Styling |
| `test` | Testing |
| `chore` | Miscellaneous |
| `ci` | CI/CD |
| `build` | Build |

## 发布流程

创建一个符合语义化版本的 tag 即可触发 Docker 构建 + GitHub Release：

```bash
# 打 tag
git tag v0.2.0

# 推送 tag 到远程
git push origin v0.2.0
```

这会同时触发：
- `docker.yml` — 构建并推送多架构 Docker 镜像到 GHCR
- `release.yml` — 生成 changelog 并创建 GitHub Release

## 本地开发者指南

在提交代码前，可以在本地运行与 CI 相同的检查：

### Python 检查

```bash
# 安装开发依赖
uv sync --group dev

# Lint 检查
uv run ruff check src/

# 格式检查（加 --fix 自动修复）
uv run ruff format --check src/

# 运行测试
uv run pytest -v --cov=delphi
```

### 前端检查

```bash
cd web

# 安装依赖
npm ci

# TypeScript 类型检查
npx tsc -b --noEmit

# 构建
npm run build
```

### Pre-commit

项目配置了 `pre-commit`，建议安装 hook 在提交时自动检查：

```bash
uv run pre-commit install
```
