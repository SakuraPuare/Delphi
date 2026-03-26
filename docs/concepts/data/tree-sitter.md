# Tree-sitter 与 AST 解析

Tree-sitter 是一个高性能的增量式语法解析库，被 Neovim、GitHub、Zed 等主流工具广泛采用。Delphi 使用 Tree-sitter 对代码文件进行结构化解析，从而实现语义级别的代码切分，而不是简单地按行数或字符数截断。

## 什么是抽象语法树（AST）

源代码本质上是一串字符序列。编译器或解析器的第一步工作，就是将这串字符转换为有层次结构的树形表示——这就是**抽象语法树（Abstract Syntax Tree，AST）**。

"抽象"的含义是：AST 只保留语法结构，丢弃了空白符、注释、括号等对语义无关紧要的细节（具体保留哪些取决于工具）。

以一段简单的 Python 代码为例：

```python
def add(a, b):
    return a + b
```

其对应的 AST 结构大致如下：

```
function_definition
├── name: "add"
├── parameters
│   ├── identifier: "a"
│   └── identifier: "b"
└── body
    └── return_statement
        └── binary_expression
            ├── left: identifier "a"
            ├── operator: "+"
            └── right: identifier "b"
```

每个节点都有明确的类型（`function_definition`、`binary_expression`）和位置信息（行号、列号），这使得程序可以精确地定位和操作代码的任意部分。

## AST 对代码理解的意义

基于 AST 的代码分析比基于文本的分析有本质优势：

| 能力 | 纯文本/正则 | AST |
|------|------------|-----|
| 识别函数边界 | 脆弱，依赖缩进或括号计数 | 精确，直接读取节点范围 |
| 提取函数签名 | 需要复杂正则，易误匹配 | 直接访问 `parameters` 子节点 |
| 处理多行表达式 | 困难 | 天然支持 |
| 语言无关性 | 每种语言需单独规则 | 统一 API，切换语言只需换 grammar |
| 嵌套结构 | 几乎不可能 | 树遍历即可 |

对于代码知识库而言，AST 让我们能够以"函数"、"类"、"方法"为单位切分代码，而不是以"500 个 token"为单位盲目截断。

## Tree-sitter 是什么

Tree-sitter 由 GitHub 工程师 Max Brunsfeld 开发，于 2018 年开源。它的核心特性有三点：

**1. 增量解析（Incremental Parsing）**

当文件内容发生变化时，Tree-sitter 不会重新解析整个文件，而是只重新解析受影响的部分。这使得它在编辑器中实时高亮时延迟极低，也让 Delphi 在文件更新时能高效地重新索引。

**2. 错误恢复（Error Recovery）**

真实世界的代码往往是不完整的（正在编辑中、存在语法错误）。Tree-sitter 在遇到语法错误时不会崩溃，而是尽力解析剩余部分，将错误节点标记为 `ERROR`，保证树的完整性。

**3. 多语言支持**

Tree-sitter 通过独立的 grammar 文件支持每种语言。目前官方和社区维护的 grammar 覆盖了 100+ 种语言，包括 C/C++、Python、JavaScript、TypeScript、Rust、Go、Java 等主流语言。

## Tree-sitter 的工作原理

```
Grammar 定义文件 (grammar.js)
        │
        ▼
  tree-sitter generate
        │
        ▼
  C 语言解析器源码 (parser.c)
        │
        ▼
  编译为动态库 (.so / .dylib)
        │
        ▼
  输入源代码字符串
        │
        ▼
  ts_parser_parse() 调用
        │
        ▼
  TSTree（语法树对象）
        │
        ▼
  通过 TSNode API 遍历节点
```

Grammar 文件使用 JavaScript DSL 描述语言的语法规则，例如：

```javascript
// grammar.js 片段（简化）
function_definition: $ => seq(
  'def',
  field('name', $.identifier),
  field('parameters', $.parameters),
  ':',
  field('body', $.block)
)
```

Tree-sitter 根据这个描述生成一个 GLR 解析器，能够处理大多数编程语言的上下文无关文法。

## Tree-sitter vs 其他代码分析方案

### vs 正则表达式

正则表达式是最常见的"快速方案"，但在代码分析场景下问题很多：

```
# 用正则匹配 Python 函数定义
pattern = r'^def\s+(\w+)\s*\('

# 问题：
# 1. 无法处理装饰器
# 2. 无法确定函数体的结束位置
# 3. 字符串中的 "def" 也会被匹配
# 4. 多行参数列表会失败
```

Tree-sitter 直接给出精确的节点范围，没有这些问题。

### vs LSP（Language Server Protocol）

LSP 提供了更丰富的语义信息（类型推断、跨文件引用、符号解析），但它：

- 需要完整的项目环境（依赖安装、编译配置）
- 启动慢，资源消耗大
- 不适合批量离线处理

Tree-sitter 只需要单个文件，无需任何项目上下文，毫秒级解析，非常适合索引管道。

### 对比总结

```
          速度    准确性    语义深度    环境依赖
正则       ★★★★★   ★★        ★          无
Tree-sitter ★★★★   ★★★★★    ★★★        无
LSP        ★★      ★★★★★    ★★★★★      需要完整项目
```

## 具体示例：解析 C++ 函数

给定以下 C++ 代码：

```cpp
int calculate(int x, int y) {
    if (x > 0) {
        return x + y;
    }
    return y;
}
```

Tree-sitter 解析后的节点树（简化）：

```
translation_unit [0:0 - 7:0]
└── function_definition [0:0 - 6:1]
    ├── type: primitive_type "int"          [0:0 - 0:3]
    ├── declarator: function_declarator     [0:4 - 0:30]
    │   ├── declarator: identifier "calculate"
    │   └── parameters: parameter_list
    │       ├── parameter_declaration
    │       │   ├── type: primitive_type "int"
    │       │   └── declarator: identifier "x"
    │       └── parameter_declaration
    │           ├── type: primitive_type "int"
    │           └── declarator: identifier "y"
    └── body: compound_statement            [0:31 - 6:1]
        ├── if_statement                    [1:4 - 4:5]
        │   ├── condition: ...
        │   └── consequence: ...
        └── return_statement                [5:4 - 5:13]
```

通过这棵树，我们可以精确提取：
- 函数名：`calculate`（`identifier` 节点的文本）
- 参数列表：`(int x, int y)`（`parameter_list` 节点的文本范围）
- 函数体的起止行号：第 0 行到第 6 行
- 函数的完整源码：通过起止字节偏移量切片原始字符串

## Delphi 如何使用 Tree-sitter

Delphi 在索引代码文件时，使用 Tree-sitter 进行**语义级代码切分**：

```
代码文件输入
     │
     ▼
Tree-sitter 解析 → 语法树
     │
     ▼
遍历顶层节点（函数、类、方法）
     │
     ▼
按节点边界切分代码块
     │
     ▼
为每个块附加元数据
  - 节点类型（function / class / method）
  - 函数名 / 类名
  - 起止行号
  - 所属文件路径
  - 语言类型
     │
     ▼
向量化 → 存入向量数据库
```

这种方式确保每个代码块都是语义完整的单元（一个完整的函数或类），而不是在函数中间截断的代码片段。当用户查询"calculate 函数是怎么实现的"时，检索到的 chunk 就是完整的函数体，而不是函数的前半段。

对于超长的函数（超过 token 限制），Delphi 会进一步按内部块结构（`if` 语句、循环体等）递归切分，并在每个子块的元数据中记录其父函数信息，保证上下文可追溯。
