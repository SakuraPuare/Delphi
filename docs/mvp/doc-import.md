# 功能：文档目录导入

## 功能描述

用户提供本地文档目录的绝对路径，系统执行以下操作：

1. 递归扫描目录，按支持格式过滤文件
2. 根据文件格式选择对应解析器，提取纯文本内容
3. 按规则将文本切分为 [Chunk](../concepts/data/chunking.md)
4. 提取文件级和块级元数据
5. 调用 [Embedding](../concepts/core/embedding.md) 模型生成向量
6. 将 Chunk 及其向量存入[向量数据库](../concepts/core/vector-database.md)（Qdrant）

---

## 详细需求列表

### P0（必须实现）

1. 支持 Markdown（`.md`、`.mdx`）文件解析，按标题层级切分
2. 支持纯文本（`.txt`）文件解析，按段落切分
3. 每个 Chunk 携带元数据：`source_path`、`file_type`、`title`（所属标题路径）、`page`（PDF 专用）
4. 生成 Embedding 并写入 Qdrant collection
5. API 返回导入任务 ID，支持轮询任务状态

### P1（应该实现）

6. 支持 HTML（`.html`、`.htm`）文件，转换为 Markdown 后按标题切分
7. 支持 PDF（`.pdf`）文件，提取文本后按页或段落切分
8. 导入完成后返回统计信息：文件数、Chunk 数、跳过文件数、耗时
9. 同一目录重复导入时，先清除旧数据再重新导入（全量刷新）
10. 自动跳过隐藏文件（`.`开头）和系统文件（`Thumbs.db`、`.DS_Store`）

### P2（可以实现）

11. 支持通过 glob 模式指定包含/排除规则（如 `--include="**/*.md"`）
12. 提取文档 Front Matter（YAML/TOML）作为额外元数据
13. 导入进度通过 SSE 实时推送

---

## 输入/输出规格

### 请求

```http
POST /import/docs
Content-Type: application/json

{
  "path": "/absolute/path/to/docs",
  "include_patterns": ["**/*.md", "**/*.pdf"],  // 可选，默认全部支持格式
  "exclude_patterns": ["**/drafts/**"]           // 可选
}
```

### 响应（任务创建）

```json
{
  "task_id": "uuid-v4",
  "status": "pending",
  "created_at": "2026-03-27T00:00:00Z"
}
```

### 任务状态查询

```http
GET /import/tasks/{task_id}
```

```json
{
  "task_id": "uuid-v4",
  "status": "completed",
  "stats": {
    "total_files": 45,
    "processed_files": 43,
    "skipped_files": 2,
    "total_chunks": 890,
    "elapsed_seconds": 12.5
  },
  "error": null
}
```

---

## 各格式处理方式

| 格式 | 解析库 | 切分策略 |
|------|--------|---------|
| Markdown | 内置解析 | 按标题层级切分（见下节） |
| TXT | 内置 | 按空行分段，超长段落滑动窗口 |
| HTML | `trafilatura` | 提取正文后按段落切分 |
| PDF | `PyMuPDF` | 按页提取，超长页滑动窗口 |

---

## Markdown 标题层级切分规则

切分目标：每个 Chunk 对应一个语义完整的章节，保留标题路径作为上下文。

### 规则详述

1. 解析文档，构建标题树（H1 → H2 → H3 …）
2. 以 **H2** 为默认切分粒度：每个 H2 节（含其下所有 H3+ 内容）为一个 Chunk
3. 若文档无 H2，以 **H1** 为切分粒度
4. 若单个 H2 节超过 `max_tokens`（默认 512 tokens），按 H3 进一步拆分
5. 若 H3 节仍超长，使用滑动窗口（`chunk_size=512, overlap=64`）
6. 每个 Chunk 的 `title` 元数据记录完整标题路径，如 `"安装指南 > 环境要求 > Linux"`
7. Front Matter 内容附加到第一个 Chunk，不单独成块

### 示例

```markdown
# 安装指南          ← H1，不切分
## 环境要求         ← Chunk 1 开始
### Linux           ← 若 Chunk 1 超长，拆为子 Chunk
### Windows
## 快速开始         ← Chunk 2 开始
```

---

## HTML 正文提取策略

使用 `trafilatura` 库提取 HTML 正文：

- 自动识别并提取页面主体内容，过滤导航栏、页眉、页脚、广告等噪声
- 输出纯文本，按段落切分
- 保留超链接文本

---

## PDF 文本提取策略

使用 `PyMuPDF`（fitz）提取文本：

1. 按页提取，每页作为独立文本块
2. 检测并合并跨页的段落（通过行尾连字符或段落缩进判断）
3. 过滤页眉页脚（检测重复出现在固定位置的文本行）
4. 若单页文本超过 `max_tokens`，使用滑动窗口切分
5. 元数据记录 `page_number`（从 1 开始）

> 注意：扫描版 PDF（无文本层）在 MVP 阶段不支持，返回错误提示。

---

## 元数据提取规则

每个 Chunk 存储以下元数据：

```json
{
  "source_path": "/docs/guide/install.md",
  "file_type": "markdown",
  "title": "安装指南 > 环境要求",
  "page_number": null,
  "file_mtime": "2026-03-27T00:00:00Z",
  "chunk_index": 2,
  "total_chunks_in_file": 8,
  "front_matter": {
    "author": "team",
    "tags": ["install", "guide"]
  }
}
```

---

## 错误处理策略

| 错误场景 | 处理方式 |
|---------|---------|
| 目录不存在 | 立即返回 400 错误 |
| 单个文件解析失败 | 跳过该文件，记录到 `skipped_files` |
| PDF 无文本层（扫描版） | 跳过，在统计中标注原因 |
| Embedding 服务不可用 | 任务暂停，返回 503 |
| Qdrant 写入失败 | 重试 3 次，仍失败则任务置为 `failed` |
| 目录文件总大小超过 2GB | 拒绝导入，返回 413 |

---

## 相关概念

- [Chunking（文本切分）](../concepts/data/chunking.md) — 切分策略详解
- [Embedding（向量嵌入）](../concepts/core/embedding.md) — 向量生成原理
- [向量数据库](../concepts/core/vector-database.md) — Qdrant 存储与检索
- [Tokenization（分词）](../concepts/data/tokenization.md) — Token 计数与长度控制
