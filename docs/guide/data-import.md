# 数据导入

Delphi 提供统一的数据导入接口，支持多种数据源。所有数据经过解析、切分、Embedding 后存入向量数据库。

## 导入流程

```
用户数据 ──→ 数据导入模块 ──→ 解析 & 切分 ──→ Embedding ──→ 向量数据库
  │                              │
  ├─ Git 仓库（代码）            ├─ Tree-sitter AST 切分
  ├─ 文档目录（MD/HTML/PDF）     ├─ 按标题层级切分
  ├─ 音视频文件                  ├─ Faster-Whisper 转录 → 文本切分
  └─ 自定义文本                  └─ 通用文本切分
```

## 代码仓库导入

### 支持的语言

通过 Tree-sitter grammar 扩展，默认支持：

- C / C++
- Python
- Java
- Go
- Rust
- JavaScript / TypeScript
- Protobuf
- 更多语言可通过安装对应的 Tree-sitter grammar 扩展

### 切分策略

代码不按行数暴力切分，而是基于 AST（抽象语法树）按语法结构切分：

- **函数/方法**：每个函数体作为一个 Chunk
- **类/结构体**：类定义（含成员）作为一个 Chunk，过长时按方法拆分
- **顶层声明**：全局变量、常量、类型定义等
- **导入/头文件**：import 和 include 语句聚合为上下文元数据

每个 Chunk 附带元数据：

| 字段 | 说明 | 示例 |
|------|------|------|
| `file_path` | 文件路径 | `modules/planning/planner/lattice/lattice_planner.cc` |
| `language` | 编程语言 | `cpp` |
| `namespace` | 命名空间/包名 | `apollo::planning` |
| `class_name` | 所属类 | `LatticePlanner` |
| `symbol` | 函数/方法签名 | `Status Plan(...)` |
| `imports` | 依赖的头文件/模块 | `["planning_base.h", "lattice_trajectory.h"]` |

### 构建系统文件

BUILD / .bzl / CMakeLists.txt 等构建文件也会被索引：

- Tree-sitter 支持 Starlark（Bazel）和 CMake 语法
- 提取 `deps` 字段中的依赖关系作为元数据
- 项目自有的 CLI 工具文档作为文档类数据导入

## 文档导入

| 格式 | 处理方式 | 切分策略 |
|------|---------|---------|
| Markdown | 直接解析 | 按标题层级切分，保留层级路径作为元数据 |
| HTML | 转 Markdown 后处理 | 同上 |
| PDF | 文本提取 | 按段落/页面 |
| 纯文本 | 直接处理 | 按段落或固定窗口 |

文档 Chunk 元数据：

| 字段 | 说明 |
|------|------|
| `source` | 来源文件路径或 URL |
| `title` | 文档标题 |
| `heading_path` | 标题层级路径，如 `指南 > 安装 > Docker 部署` |
| `doc_type` | 文档类型（tutorial / api / changelog 等） |

## 音视频导入

使用 Faster-Whisper large-v3（INT8 量化）进行离线转录：

- 自动检测语言（中文/英文）
- 输出带毫秒级时间戳的文本
- 按时间窗口切分（默认 30 秒一段，按语句边界对齐）
- 元数据包含：源文件名、时间区间、检测到的语言

## 增量更新

基于文件内容 hash 检测变更：

- 新增文件：解析并入库
- 修改文件：删除旧 Chunk，重新解析入库
- 删除文件：清除对应 Chunk

无需全量重建，适合持续跟踪活跃仓库。
