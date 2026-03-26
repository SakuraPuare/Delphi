# 功能：Git 仓库导入

## 功能描述

用户提供 Git 仓库的远程 URL 或本地路径，系统执行以下操作：

1. Clone 远程仓库（或直接读取本地路径）
2. 遍历仓库文件，按过滤规则筛选目标文件
3. 使用 [Tree-sitter](../concepts/data/tree-sitter.md) 对代码文件进行语法感知解析
4. 将解析结果切分为 [Chunk](../concepts/data/chunking.md)
5. 调用 [Embedding](../concepts/core/embedding.md) 模型生成向量
6. 将 Chunk 及其向量存入[向量数据库](../concepts/core/vector-database.md)（Qdrant）

---

## 详细需求列表

### P0（必须实现）

1. 支持通过 HTTPS URL clone 公开 Git 仓库
2. 支持读取本地绝对路径的 Git 仓库
3. 对每个代码文件使用 Tree-sitter 解析，按函数/类边界切分
4. 对无法用 Tree-sitter 解析的文件，回退到按行数滑动窗口切分
5. 每个 Chunk 携带元数据：`repo_url`、`file_path`、`start_line`、`end_line`、`language`
6. 生成 Embedding 并写入 Qdrant collection
7. API 返回导入任务 ID，支持轮询任务状态

### P1（应该实现）

8. 支持通过 SSH URL clone 私有仓库（需用户提供 SSH key 路径）
9. 支持指定 branch 或 commit hash
10. 导入完成后返回统计信息：文件数、Chunk 数、跳过文件数、耗时
11. 同一仓库重复导入时，先清除旧数据再重新导入（全量刷新）
12. 解析构建文件（`BUILD`、`CMakeLists.txt`）并提取 target 依赖关系作为元数据

### P2（可以实现）

13. 支持 shallow clone（`--depth=1`）以加速大仓库导入
14. 并发处理多个文件（线程池）
15. 导入进度通过 SSE 实时推送

---

## 输入/输出规格

### 请求

```http
POST /api/v1/import/git
Content-Type: application/json

{
  "url": "https://github.com/example/repo.git",  // 与 path 二选一
  "path": "/absolute/local/path",                 // 与 url 二选一
  "branch": "main",                               // 可选，默认 HEAD
  "ssh_key_path": "/home/user/.ssh/id_rsa"        // 可选，私有仓库使用
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
GET /api/v1/tasks/{task_id}
```

```json
{
  "task_id": "uuid-v4",
  "status": "completed",  // pending | running | completed | failed
  "stats": {
    "total_files": 120,
    "processed_files": 118,
    "skipped_files": 2,
    "total_chunks": 3450,
    "elapsed_seconds": 47.2
  },
  "error": null
}
```

---

## 处理流程

```
用户请求
    │
    ▼
[1] 参数校验
    │  URL 格式 / 路径存在性检查
    ▼
[2] Clone / 挂载仓库
    │  git clone --depth=1 <url> /tmp/<task_id>
    │  或直接使用本地路径
    ▼
[3] 文件遍历与过滤
    │  读取 .gitignore 规则
    │  排除 vendor/ node_modules/ third_party/
    │  排除生成文件（*.pb.cc *.pb.h *_generated.* *.min.js）
    │  按支持语言列表过滤扩展名
    ▼
[4] 语言检测 & Tree-sitter 解析
    │  根据扩展名选择 grammar
    │  提取函数/类/方法节点
    │  无法解析时回退到滑动窗口
    ▼
[5] Chunk 生成
    │  每个节点 → 一个 Chunk
    │  超长节点按 max_tokens 截断并重叠
    ▼
[6] Embedding 生成（BGE-M3）
    │  批量调用，batch_size=32
    ▼
[7] 写入 Qdrant
    │  collection: repo_<task_id> 或按 repo URL hash 命名
    ▼
[8] 更新任务状态 → completed
```

---

## 支持的语言与 Tree-sitter Grammar

| 语言 | 文件扩展名 | Grammar 包 |
|------|-----------|------------|
| Python | `.py` | `tree-sitter-python` |
| JavaScript | `.js` `.mjs` `.cjs` | `tree-sitter-javascript` |
| TypeScript | `.ts` `.tsx` | `tree-sitter-typescript` |
| Go | `.go` | `tree-sitter-go` |
| Rust | `.rs` | `tree-sitter-rust` |
| C | `.c` `.h` | `tree-sitter-c` |
| C++ | `.cc` `.cpp` `.cxx` `.hpp` | `tree-sitter-cpp` |
| Java | `.java` | `tree-sitter-java` |
| Ruby | `.rb` | `tree-sitter-ruby` |
| Markdown | `.md` `.mdx` | 按标题切分（不用 Tree-sitter） |

---

## 文件过滤规则

### 自动排除目录

```
vendor/
node_modules/
third_party/
.git/
__pycache__/
.venv/
dist/
build/
out/
target/          # Rust/Java build output
```

### 自动排除文件模式

```
*.pb.cc  *.pb.h          # Protobuf 生成文件
*_generated.*            # 代码生成文件
*.min.js  *.min.css      # 压缩文件
*.lock                   # 锁文件（package-lock.json 等）
*.sum                    # Go checksum
```

### .gitignore 集成

系统读取仓库根目录及各子目录的 `.gitignore`，使用 `pathspec` 库匹配，被忽略的文件不参与索引。

---

## 构建文件处理

`BUILD`（Bazel）和 `CMakeLists.txt` 作为普通文本文件处理，使用滑动窗口切分。元数据中标记 `file_type: "build"`，便于后续检索时区分。

---

## 错误处理策略

| 错误场景 | 处理方式 |
|---------|---------|
| URL 无法访问 / clone 失败 | 任务状态置为 `failed`，返回错误信息 |
| 单个文件解析失败 | 跳过该文件，记录到 `skipped_files`，继续处理 |
| Embedding 服务不可用 | 任务暂停，返回 503，建议重试 |
| Qdrant 写入失败 | 重试 3 次，仍失败则任务置为 `failed` |
| 仓库超过 500MB | 拒绝导入，返回 413 错误 |

---

## 相关概念

- [Tree-sitter](../concepts/data/tree-sitter.md) — 代码语法解析
- [Chunking（文本切分）](../concepts/data/chunking.md) — 切分策略详解
- [Embedding（向量嵌入）](../concepts/core/embedding.md) — 向量生成原理
- [向量数据库](../concepts/core/vector-database.md) — Qdrant 存储与检索
