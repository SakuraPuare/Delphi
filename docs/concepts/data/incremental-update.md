# 增量更新机制

知识库的内容会随着代码和文档的变化而变化。每次变更都重新索引全部内容代价极高，增量更新机制让系统只处理真正发生变化的部分。

## 问题：全量重索引的代价

假设一个代码仓库有 10,000 个文件，每次有人提交代码，如果重新索引所有文件：

```
10,000 文件 × 平均 5 个块/文件 = 50,000 个块
50,000 个块 × 嵌入计算时间 ≈ 数分钟到数十分钟
```

而实际上，一次提交可能只修改了 3 个文件。全量重索引浪费了 99.97% 的计算资源，还会造成长时间的索引延迟。

## 基于内容哈希的变更检测

增量更新的核心是**内容哈希**。对每个文件计算 SHA-256 哈希值，并将其存储在元数据中：

```python
import hashlib

def compute_file_hash(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

# 存储在索引记录中
{
  "file_path": "src/models/attention.py",
  "content_hash": "a3f8c2d1e4b7...",
  "indexed_at": "2024-01-15T10:30:00Z"
}
```

每次扫描时，将当前文件的哈希与存储的哈希对比，只有哈希不同的文件才需要重新处理。

## 三种变更情况

### 新增文件

当前文件系统中存在，但索引中没有记录：

```
操作：
  1. 读取文件内容
  2. 分块（Chunking）
  3. 计算嵌入向量
  4. 写入向量数据库
  5. 记录文件哈希
```

### 修改文件

文件存在于索引中，但哈希值不同：

```
操作：
  1. 删除该文件的所有旧块（按 file_path 过滤删除）
  2. 读取新文件内容
  3. 重新分块、嵌入
  4. 写入新块
  5. 更新文件哈希记录
```

注意必须先删除旧块，否则会出现同一文件的新旧内容混存的情况。

### 删除文件

索引中有记录，但文件系统中已不存在：

```
操作：
  1. 按 file_path 删除向量数据库中的所有相关块
  2. 删除哈希记录
```

## 处理文件重命名

文件重命名是一个特殊情况：内容没变，但路径变了。如果只看路径，会误判为"删除旧文件 + 新增新文件"，导致不必要的重新嵌入。

基于哈希的去重可以优化这个场景：

```
扫描结果：
  已删除：src/utils/helper.py（哈希 abc123）
  新增：  src/utils/helpers.py（哈希 abc123）

检测到哈希相同 → 判断为重命名
操作：
  只更新元数据中的 file_path
  不重新计算嵌入（向量内容不变）
```

这将重命名操作的成本从 O(块数量) 降低到 O(1)。

## 批处理与并行化

当变更文件较多时，批处理和并行化可以显著提升吞吐量：

```python
async def process_changed_files(changed_files: list[str]):
    # 分批处理，避免内存溢出
    batch_size = 32
    for i in range(0, len(changed_files), batch_size):
        batch = changed_files[i:i + batch_size]
        # 并行嵌入计算
        embeddings = await asyncio.gather(*[
            embed_file(f) for f in batch
        ])
        # 批量写入向量数据库
        await vector_db.upsert_batch(embeddings)
```

嵌入计算通常是瓶颈，并行化可以充分利用 GPU 或多核 CPU。

## 一致性保证

增量更新过程中需要避免中间状态被查询到：

**问题**：删除旧块和写入新块之间有时间窗口，此时查询可能返回空结果。

**解决方案**：先写入新块，再删除旧块。利用元数据中的版本号区分新旧块：

```python
# 写入新块时标记新版本
new_chunks = create_chunks(file, version=new_hash)
await vector_db.upsert(new_chunks)

# 删除旧版本的块
await vector_db.delete(
    filter={"file_path": file_path, "version": {"$ne": new_hash}}
)
```

这样在任何时刻，查询都能返回有效结果，只是在短暂的过渡期内可能同时存在新旧两个版本的块。

## Delphi 的增量更新实现

Delphi 维护一个本地的哈希索引表，记录每个已索引文件的路径和内容哈希：

```
索引触发时机：
  - 用户手动触发
  - 监听文件系统变更事件（inotify/FSEvents）
  - 定时扫描（可配置间隔）

处理流程：
  扫描目标目录
    → 对比哈希，分类为新增/修改/删除
    → 并行处理变更文件
    → 批量更新 Qdrant
    → 更新本地哈希记录
```

对于大型代码仓库，首次全量索引后，后续的增量更新通常在秒级完成，保持知识库与代码库的实时同步。

## 延伸阅读

- [代码分块策略](./chunking.md) — 文件如何被切分为块
- [向量嵌入 (Embedding)](../core/embedding.md) — 块如何被转换为向量
- [元数据与知识图谱](./metadata.md) — 哈希等元数据的存储方式
