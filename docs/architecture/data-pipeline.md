# 数据处理流水线

## 总体设计

数据处理流水线负责将原始数据转化为可检索的向量 Chunk。核心设计目标：

- 语法感知：代码按 AST 结构切分，不破坏语义完整性
- 元数据丰富：每个 Chunk 携带足够的上下文信息用于过滤和溯源
- 增量处理：仅处理变更部分，避免全量重建

## 流水线架构

```
                    ┌─────────────┐
                    │  数据源注册   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  格式检测    │
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
   │ 代码解析器   │ │ 文档解析器   │ │ 媒体解析器   │
   │ (Tree-sitter)│ │ (MD/HTML/PDF)│ │ (Whisper)   │
   └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
          │                │                │
          └────────────────┼────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Chunk 标准化 │
                    │  + 元数据附加  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  BGE-M3     │
                    │  Embedding  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Qdrant     │
                    │  写入/更新   │
                    └─────────────┘
```

## 解析器接口

所有解析器实现统一接口：

```python
class BaseParser:
    def can_handle(self, file_path: str) -> bool:
        """判断是否能处理该文件"""
        ...

    def parse(self, file_path: str, content: bytes) -> list[Chunk]:
        """解析文件，返回 Chunk 列表"""
        ...
```

### Chunk 数据结构

```python
@dataclass
class Chunk:
    content: str              # Chunk 文本内容
    metadata: dict            # 元数据（文件路径、语言、函数签名等）
    chunk_type: str           # 类型：code / doc / media_transcript
    source_hash: str          # 源文件内容 hash，用于增量更新
```

## 代码解析器

### Tree-sitter AST 切分

以 C++ 为例，解析流程：

1. Tree-sitter 解析源文件生成 AST
2. 遍历 AST，提取目标节点类型：
   - `function_definition` → 函数级 Chunk
   - `class_specifier` → 类级 Chunk（过长时按方法拆分）
   - `namespace_definition` → 提取命名空间作为元数据
   - `preproc_include` → 聚合为依赖元数据
3. 对每个节点生成 Chunk，附带完整元数据

### 处理边界情况

| 情况 | 处理策略 |
|------|---------|
| 函数体过长（> 2000 tokens） | 按逻辑块（if/for/switch）二次切分 |
| 头文件只有声明 | 整文件作为单个 Chunk |
| 宏定义展开 | 保留原始宏文本，不展开 |
| 模板特化 | 每个特化作为独立 Chunk |
| 构建文件（BUILD/CMake） | 按 target 切分，提取 deps |

## 文档解析器

### Markdown 切分

按标题层级递归切分：

```
# 一级标题          → 作为 heading_path 前缀
## 二级标题         → 切分点
正文内容...         → Chunk 内容
### 三级标题        → 更细粒度切分点
正文内容...         → Chunk 内容
```

每个 Chunk 的 `heading_path` 保留完整层级路径，如 `安装指南 > Docker 部署 > GPU 支持`。

### HTML 处理

HTML → Markdown（使用 markdownify 或 html2text）→ 走 Markdown 切分流程。

### PDF 处理

使用 PyMuPDF 或 pdfplumber 提取文本，按页面/段落切分。

## 媒体解析器

### Faster-Whisper 转录

- 模型：large-v3，INT8 量化
- 自动语言检测
- 输出带时间戳的分段文本
- 按 30 秒窗口切分，在语句边界对齐

## 增量更新机制

```
文件列表 → 计算 hash → 与数据库中已有 hash 对比
                              │
                ┌──────────────┼──────────────┐
                │              │              │
           新增文件        修改文件        删除文件
           解析入库     删旧Chunk+重新入库  清除Chunk
```

使用文件内容的 SHA-256 hash 作为变更检测依据，存储在 Qdrant 的 payload 中。
