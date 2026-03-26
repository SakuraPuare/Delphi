# 功能：CLI 命令行工具

## 功能描述

`delphi` 是 Delphi 项目的命令行工具，提供数据导入、知识库查询和项目管理能力。所有操作均通过调用 API Server 完成，CLI 本身不直接操作数据库或模型。

实现技术：Python + [Typer](https://typer.tiangolo.com/)，支持彩色输出和进度条。

## 安装

```bash
pip install delphi-cli
# 或从源码安装
pip install -e ./cli
```

## 全局选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--api-url` | API Server 地址 | `http://localhost:8888` |
| `--api-key` | API Key | 读取 `config.yaml` |
| `--config` | 配置文件路径 | `~/.delphi/config.yaml` |
| `--verbose / -v` | 输出详细日志 | `false` |

---

## 命令详情

### `delphi init`

初始化本地配置文件。

```bash
delphi init [--api-url URL] [--api-key KEY]
```

交互式引导用户填写 API Server 地址和 API Key，生成 `~/.delphi/config.yaml`。

**输出示例：**
```
✓ 配置已写入 ~/.delphi/config.yaml
✓ 连接测试通过 (http://localhost:8888)
```

**退出码：** `0` 成功，`1` 连接失败

---

### `delphi import git`

从 Git 仓库导入代码或文档。

```bash
delphi import git <url-or-path> [OPTIONS]

Options:
  --project TEXT     目标项目名称（不存在则自动创建）
  --branch TEXT      指定分支，默认 main
  --include TEXT     文件过滤 glob，可多次指定（如 "**/*.py"）
  --exclude TEXT     排除文件 glob，可多次指定
  --depth INT        clone 深度，默认 1（浅克隆）
```

**示例：**
```bash
delphi import git https://github.com/org/repo --project myproject --include "**/*.md"
delphi import git ./local-repo --project myproject
```

**输出示例：**
```
克隆仓库... ████████████████ 100%
解析文件: 142 个文件
导入进度 ████████████░░░░  78% | 111/142 | 预计剩余 12s
✓ 导入完成：142 个文件，1,893 个文本块
```

---

### `delphi import docs`

从本地目录导入文档。

```bash
delphi import docs <path> [OPTIONS]

Options:
  --project TEXT     目标项目名称
  --recursive / -r   递归扫描子目录（默认开启）
  --type TEXT        文件类型过滤，如 md,txt,pdf（默认全部支持类型）
```

**示例：**
```bash
delphi import docs ./docs --project wiki --type md,txt
```

**支持格式：** `.md`, `.txt`, `.pdf`, `.rst`, `.html`

---

### `delphi query`

在命令行中直接提问。

```bash
delphi query <question> [OPTIONS]

Options:
  --project TEXT     指定查询的项目（默认查询所有项目）
  --top-k INT        召回文档数量，默认 5
  --stream / --no-stream  流式输出，默认开启
  --show-sources     显示引用来源
```

**示例：**
```bash
delphi query "如何配置 vLLM 的并发数？" --project myproject --show-sources
```

**输出示例：**
```
vLLM 的并发数通过 --max-num-seqs 参数控制...

来源：
  [1] docs/deployment/vllm.md (相关度 0.92)
  [2] README.md (相关度 0.87)
```

---

### `delphi status`

查看系统各服务的运行状态。

```bash
delphi status
```

**输出示例：**
```
服务状态
  API Server    ✓ 运行中  (http://localhost:8888)
  vLLM          ✓ 运行中  模型: Qwen2.5-7B-Instruct
  Qdrant        ✓ 运行中  集合数: 3
  Embedding     ✓ 运行中  模型: BAAI/bge-m3

项目统计
  项目数: 2
  总文档块数: 4,821
```

---

### `delphi projects`

项目管理子命令组。

```bash
# 列出所有项目
delphi projects list

# 创建项目
delphi projects create <name> [--description TEXT]

# 删除项目（含所有向量数据）
delphi projects delete <name> [--yes]
```

**`list` 输出示例：**
```
名称          文档块数    创建时间
myproject     1,893      2024-01-15 10:23
wiki          2,928      2024-01-16 09:11
```

---

## 配置文件格式

`~/.delphi/config.yaml`：

```yaml
api_url: http://localhost:8888
api_key: ""          # 留空表示不使用认证
default_project: ""  # 留空表示查询所有项目
```

## 错误处理与退出码

| 退出码 | 含义 |
|--------|------|
| `0` | 成功 |
| `1` | 通用错误（参数错误、文件不存在等） |
| `2` | 网络错误（无法连接 API Server） |
| `3` | 认证失败（API Key 无效） |

错误信息统一输出到 `stderr`，正常输出到 `stdout`，便于脚本捕获。
