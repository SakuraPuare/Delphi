# 开发语言选型讨论

在开始写代码之前，有必要认真讨论一个问题：Delphi 应该用什么语言写？

这不是一个有唯一正确答案的问题。不同的语言有不同的权衡，而"最好的语言"取决于项目的具体约束。本文尝试诚实地分析各个候选方案，而不是为某个结论找理由。

---

## 候选语言

### Python

**优势**

- AI/ML 生态系统无可匹敌。LlamaIndex、LangChain、sentence-transformers、faster-whisper、Tree-sitter Python binding——几乎所有 RAG 相关的工具都是 Python 优先的。
- vLLM 本身是 Python 项目，其 Python 客户端 SDK 最成熟，文档最完整。
- Qdrant 的 Python 客户端功能最全，更新最及时。
- 开发速度快，原型验证快。从想法到可运行代码的路径最短。
- 学生和研究者群体最熟悉的语言，降低协作门槛。
- Python 3.13 开始实验性支持无 GIL 模式（`--disable-gil`），长期来看并发限制会逐步改善。

**劣势**

- GIL 限制真正的多线程并发。asyncio 缓解了 I/O 密集场景，但 CPU 密集任务（如大量文件的 AST 解析）仍然是单线程的。
- 内存占用相对较高，尤其是启动时加载大量依赖。
- 类型系统是事后补丁（type hints），mypy/pyright 的覆盖率依赖开发者自律。
- 部署打包不干净：虚拟环境、依赖冲突、Python 版本管理是长期痛点。
- 解释型语言，CPU 密集任务比编译型语言慢 10-60 倍（基准测试数据）。

---

### Go

**优势**

- 编译型语言，单二进制部署，Docker 镜像可以做到极小。
- 原生 goroutine 并发模型，适合 I/O 密集的 API 服务，高并发下内存占用远低于 Python。
- 标准库完善，工具链统一（`go build`、`go test`、`go fmt` 开箱即用）。
- 编译时类型检查，比 Python 的 type hints 更可靠。

**劣势**

- AI/ML 生态几乎为零。没有 LlamaIndex、LangChain 的 Go 等价物，也没有成熟的 embedding 库。
- Tree-sitter 有 Go binding，但维护活跃度和文档质量远不如 Python binding。
- 所有 AI 相关功能都需要通过 HTTP/gRPC 调用 Python 服务，引入额外的网络跳转和序列化开销，同时大幅增加系统复杂度。
- 泛型支持较晚加入（1.18），生态中泛型代码风格尚未统一。

---

### Rust

**优势**

- 极致性能，零成本抽象，内存安全无需 GC。
- Tree-sitter 本身就是用 Rust/C 写的，Rust binding 是一等公民。
- Qdrant 本身是 Rust 写的，理论上可以直接嵌入而非通过 HTTP 调用。
- 编译时捕获大量错误，长期维护成本低。

**劣势**

- 开发速度慢，学习曲线陡峭。借用检查器对新手不友好，原型验证周期长。
- AI/ML 生态不成熟。`candle`（Hugging Face 的 Rust ML 框架）仍在早期阶段，与 Python 生态差距巨大。
- 同样需要通过 HTTP 调用 Python 服务来使用 vLLM、embedding 模型等。
- 对于毕设/研究项目，Rust 的工程复杂度可能超过项目本身的价值。

---

### TypeScript / Node.js

**优势**

- 前后端统一语言，如果有 Web 前端可以共享类型定义。
- LlamaIndex.TS 存在，是 Python 版本的移植，但功能子集。
- 异步 I/O 性能好，事件循环模型适合高并发 API。

**劣势**

- AI 生态远不如 Python。LlamaIndex.TS 的功能覆盖率、更新频率、社区活跃度都落后于 Python 版本。
- Tree-sitter 有 Node.js binding，但文档和示例不如 Python 丰富。
- 计算密集任务性能差，且 JavaScript 的动态类型历史包袱重（TypeScript 只是编译时检查）。
- 对于后端 RAG 系统，TypeScript 的优势（前后端统一）基本用不上。

---

### 混合方案

一种常见的架构是：Python 做核心 RAG 逻辑和数据处理，Go 或 Rust 做 API 网关层。

**潜在优势**：各取所长——Python 负责 AI 相关的重逻辑，Go/Rust 负责高并发的请求路由和认证。

**实际问题**：

- 两套语言意味着两套工具链、两套测试框架、两套部署流程。
- 服务间通信引入额外延迟和序列化成本（虽然通常可以忽略）。
- 对于小团队或个人项目，运维复杂度的增加往往得不偿失。
- 真正需要这种架构的场景是：API 层成为性能瓶颈，且流量规模大到值得这样拆分。

对于 Delphi 这个规模的项目，混合方案的工程成本很可能超过其带来的收益。

---

## 关键维度对比

| 维度 | Python | Go | Rust | TypeScript |
|------|--------|-----|------|------------|
| AI/ML 生态匹配度 | ★★★★★ | ★☆☆☆☆ | ★★☆☆☆ | ★★★☆☆ |
| 开发效率 | ★★★★★ | ★★★☆☆ | ★★☆☆☆ | ★★★★☆ |
| 运行性能（CPU） | ★★☆☆☆ | ★★★★☆ | ★★★★★ | ★★★☆☆ |
| 部署便利性 | ★★★☆☆ | ★★★★★ | ★★★★★ | ★★★☆☆ |
| 团队熟悉度（学生/研究者） | ★★★★★ | ★★★☆☆ | ★★☆☆☆ | ★★★★☆ |
| 社区支持（RAG 方向） | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ |
| 长期维护 | ★★★☆☆ | ★★★★☆ | ★★★★★ | ★★★☆☆ |

---

## Delphi 的具体约束分析

在抽象讨论之外，需要结合 Delphi 的实际情况来判断。

**核心计算不在 API 层**

Delphi 的重计算——Embedding 生成和 LLM 推理——都在独立的外部服务中（vLLM、BGE-M3）。API 层本身做的事情是：接收请求、调用向量数据库、拼接 prompt、转发给 LLM、返回结果。这些操作都是 I/O 密集的，Python 的 asyncio 完全够用。

**Tree-sitter 解析是批处理任务**

代码仓库的 AST 解析虽然 CPU 密集，但它是数据导入阶段的离线批处理，不需要实时响应。即使 Python 比 Go 慢 10 倍，把一个仓库解析时间从 10 秒变成 100 秒，对用户体验的影响是可以接受的。

**真正的性能瓶颈在 GPU**

在线查询的延迟分布大致是：

- Qdrant 向量检索：~10ms
- Embedding 生成（BGE-M3）：~100ms
- LLM 生成（vLLM）：~1000-5000ms（取决于输出长度）
- Python API 层开销：~5ms

LLM 推理占据了 90% 以上的延迟。把 API 层从 Python 换成 Go，理论上能节省 5ms，但总延迟仍然是秒级。这个优化在当前阶段没有实际意义。

**项目定位决定优先级**

Delphi 是毕设/研究项目，核心目标是验证 RAG 效果、快速迭代实验。开发效率和生态支持的优先级高于运行时性能。

---

## 什么情况下应该考虑其他语言？

诚实地说，以下场景下重新评估是合理的：

- **Go**：如果 Delphi 演变为需要支持大量并发用户的生产服务，且 API 层成为可测量的瓶颈，可以考虑用 Go 重写 API 网关层（保留 Python 做 RAG 逻辑）。
- **Rust**：如果代码解析性能成为真实痛点（比如需要实时解析超大型 monorepo），可以考虑用 Rust 写一个独立的解析服务。
- **TypeScript**：如果项目重心转向 Web 应用，且团队更熟悉 TypeScript，LlamaIndex.TS 的功能子集可能已经够用。

---

## 结论与建议

综合以上分析，**Python 是 Delphi 当前阶段最合理的选择**，但这个结论的成立依赖于几个前提：项目规模有限、团队熟悉 Python、核心计算在外部服务、开发效率优先于运行性能。

如果这些前提发生变化，结论也应该重新评估。

### 推荐技术栈

如果选择 Python，以下是具体的技术选型建议：

**Web 框架**：FastAPI

FastAPI 基于 asyncio，原生支持异步，自动生成 OpenAPI 文档，类型注解驱动。Flask 太轻量（缺少异步支持），Django 太重（ORM、模板引擎对 RAG API 没用）。

**异步运行时**：asyncio + uvicorn（或 uvicorn + gunicorn 多进程）

**类型检查**：pyright（比 mypy 更快，VS Code 集成更好）

**包管理**：uv

uv 是目前最快的 Python 包管理器（Rust 实现），替代 pip + virtualenv + pip-tools 的组合。poetry 也是好选择，但 uv 的速度优势明显。

**项目结构**：src layout

```
delphi/
├── src/
│   └── delphi/
│       ├── api/
│       ├── core/
│       ├── ingestion/
│       └── retrieval/
├── tests/
├── pyproject.toml
└── uv.lock
```

**代码质量**：ruff（lint + format，替代 flake8 + black + isort）+ pre-commit

**测试**：pytest + pytest-asyncio

---

语言选型没有银弹。Python 在这里的优势不是因为它"最好"，而是因为它在 Delphi 的具体约束下，综合成本最低、收益最高。
