# 代码解析方案对比

本文对比主流代码解析方案在 Delphi 场景下的适用性，重点分析为何 AST 解析优于行分割，以及 Tree-sitter 的选型理由。

## 方案概览对比

| 方案 | 解析精度 | 增量解析 | 多语言支持 | 错误恢复 | 性能 | 部署复杂度 | 生态 |
|------|---------|---------|-----------|---------|------|-----------|------|
| Tree-sitter | 高（AST 级）| 支持 | 100+ 语言 | 优秀 | 极快 | 低 | 活跃 |
| LSP | 极高（语义级）| 支持 | 取决于语言服务器 | 一般 | 慢 | 高 | 成熟 |
| ctags | 中（符号级）| 不支持 | 广泛 | 良好 | 快 | 低 | 老旧 |
| 正则表达式 | 低（模式匹配）| 不支持 | 手动实现 | 差 | 极快 | 极低 | 无 |
| srcML | 中（XML-AST）| 不支持 | 有限（C/C++/Java 等）| 一般 | 中 | 中 | 较小 |
| Semgrep | 高（模式 AST）| 不支持 | 30+ 语言 | 良好 | 中 | 中 | 活跃 |

## 为什么 AST 解析优于行分割

RAG 系统的检索质量高度依赖于 chunk 的语义完整性。行分割（line-based splitting）是最简单的方案，但存在根本性缺陷。

### 具体示例：同一 C++ 文件的两种处理方式

**原始代码片段：**

```cpp
// 计算两点之间的欧氏距离
double euclidean_distance(Point a, Point b) {
    double dx = a.x - b.x;
    double dy = a.y - b.y;
    return std::sqrt(dx * dx + dy * dy);
}

class PointCloud {
public:
    void add_point(Point p) { points_.push_back(p); }
    Point nearest(Point query) const {
        // 线性扫描，找最近邻
        return *std::min_element(points_.begin(), points_.end(),
            [&](const Point& a, const Point& b) {
                return euclidean_distance(query, a) <
                       euclidean_distance(query, b);
            });
    }
private:
    std::vector<Point> points_;
};
```

**行分割（每 10 行一个 chunk）的结果：**

- Chunk 1：包含 `euclidean_distance` 函数的完整定义 + `PointCloud` 类声明开头
- Chunk 2：包含 `add_point`、`nearest` 方法的一部分 + lambda 表达式被截断
- Chunk 3：lambda 剩余部分 + `points_` 成员变量

问题显而易见：`nearest` 方法被切断，lambda 跨越两个 chunk，语义完全破碎。当用户搜索"如何找最近邻点"时，没有任何一个 chunk 包含完整的实现逻辑。

**Tree-sitter AST 解析的结果：**

- Chunk 1：`euclidean_distance` 函数（完整，含注释）
- Chunk 2：`PointCloud::add_point` 方法（完整）
- Chunk 3：`PointCloud::nearest` 方法（完整，含 lambda）
- Chunk 4：`PointCloud` 类的私有成员声明

每个 chunk 都是语义完整的代码单元，检索时可以精确匹配用户意图。

## 各方案详细分析

**Tree-sitter**
基于 PEG 语法的增量解析器生成器，为每种语言生成独立的 C 解析库。解析速度极快（毫秒级），支持不完整代码的错误恢复，是 Neovim、GitHub Copilot 等工具的底层解析引擎。Python 绑定（`tree-sitter`）成熟稳定。

**LSP（Language Server Protocol）**
提供完整的语义分析能力（类型推断、跨文件引用等），但需要为每种语言启动独立的语言服务器进程，初始化耗时长，资源占用高。对于 RAG 的 chunk 切分场景，其语义能力过剩，部署成本不合理。

**ctags / Universal Ctags**
仅提取顶层符号（函数名、类名、变量名），无法理解嵌套结构和代码体。适合符号索引，不适合提取完整代码块用于 RAG。

**正则表达式**
对于结构化程度高的语言（如 Python 的 `def`/`class`）可以勉强使用，但无法处理嵌套、多行字符串、宏展开等边缘情况。维护成本高，每种语言需要单独编写规则。

**srcML**
将源代码转换为 XML 格式的 AST，主要面向 C/C++/Java/C#，语言覆盖有限，社区活跃度低，不适合需要广泛语言支持的场景。

**Semgrep**
以代码模式匹配为核心设计目标，擅长安全扫描和代码审计，而非通用代码结构提取。API 不适合用于 RAG chunk 生成。

## 为什么 Delphi 选择 Tree-sitter

1. **语义完整性**：按函数、类、方法边界切分，每个 chunk 都是可独立理解的代码单元
2. **广泛语言支持**：官方维护 Python、JavaScript、TypeScript、Rust、Go、C/C++、Java 等 100+ 语言的语法文件
3. **错误恢复**：即使代码存在语法错误（如开发中的未完成文件），仍能解析出已有的结构
4. **增量解析**：文件修改时只重新解析变更部分，适合监听文件系统变化的实时索引场景
5. **零外部依赖**：纯本地运行，无需启动语言服务器或网络连接，符合 Delphi 离线设计原则
6. **性能**：C 实现的解析核心，Python 绑定开销极小，大型代码库的全量索引在秒级完成
