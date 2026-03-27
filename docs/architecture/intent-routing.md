# 意图路由

## 概述

Delphi 的意图路由模块（`src/delphi/retrieval/intent.py`）负责在 RAG 检索流程中对用户查询进行意图分类，并根据分类结果选择对应的 System Prompt，引导 LLM 生成与意图匹配的回答。

该模块采用纯规则方式实现，基于正则表达式匹配关键词和代码风格模式，不依赖 LLM 推理，具有零延迟、确定性强的优势。

## 意图分类

系统定义了三种意图类型（`Intent` 枚举）：

| 意图 | 枚举值 | 适用场景 |
|------|--------|----------|
| CODE | `code` | 代码相关问答：函数实现、bug 分析、代码解释 |
| DOC | `doc` | 文档相关问答：概念解释、使用指南 |
| GENERAL | `general` | 通用问答：架构设计、最佳实践 |

### CODE 匹配模式

CODE 意图使用两组正则模式：

**关键词模式**（case-insensitive）：

```python
_CODE_KEYWORD_PATTERNS = [
    r"(函数|方法|接口|变量|参数|返回值|定义|调用|bug|报错|异常|error)",
    r"\b(function|class|method|def|import|return|error|exception|bug|implement)\b",
]
```

**代码风格模式**（case-sensitive）：

```python
_CODE_STYLE_PATTERNS = [
    r"[A-Z][a-z]+[A-Z]",  # CamelCase 标识符
    r"[a-z]+_[a-z]+",      # snake_case 标识符
    r"`[^`]+`",            # 行内代码（反引号包裹）
]
```

代码风格模式用于捕捉用户查询中直接出现的代码标识符，即使没有显式的关键词也能识别为代码意图。

### DOC 匹配模式

```python
_DOC_PATTERNS = [
    r"(文档|说明|指南|教程|概念|原理|介绍|是什么|什么是|如何理解)",
    r"\b(document|guide|tutorial|concept|explain|what is|how to understand)\b",
]
```

## 分类算法

`classify_intent(question)` 的评分机制如下：

```
code_score = CODE 关键词模式命中数 + CODE 代码风格模式命中数
doc_score  = DOC 模式命中数
```

判定规则：

1. `code_score > doc_score` → 返回 `Intent.CODE`
2. `doc_score > code_score` → 返回 `Intent.DOC`
3. 两者相等（含均为 0）→ 返回 `Intent.GENERAL`

注意事项：

- CODE 关键词模式使用 `re.IGNORECASE`，代码风格模式使用默认（区分大小写）
- DOC 模式统一使用 `re.IGNORECASE`
- 每个正则模式最多贡献 1 分（只判断是否命中，不计重复匹配次数）
- CODE 最高可得 5 分（2 个关键词模式 + 3 个风格模式），DOC 最高可得 2 分

### 示例

| 查询 | CODE 得分 | DOC 得分 | 结果 |
|------|-----------|----------|------|
| `get_user_info 函数怎么调用` | 3（关键词×1 + snake_case×1 + 行内无） | 0 | CODE |
| `什么是向量检索的原理` | 0 | 1（"什么是"+"原理"在同一模式中） | DOC |
| `项目怎么部署` | 0 | 0 | GENERAL |
| `UserService 类的文档说明` | 1（CamelCase） | 1（"文档"+"说明"在同一模式中） | GENERAL（平局） |

## 意图专属 Prompt

每种意图对应一套 System Prompt，存储在 `PROMPTS` 字典中，通过 `get_system_prompt(intent)` 获取。

### CODE Prompt

```
你是一个代码分析助手。请根据以下检索到的代码片段回答用户的问题。

规则：
- 只基于提供的代码上下文回答，不要编造信息
- 解释代码逻辑时，引用具体的函数名、类名和行号
- 如果涉及 bug 或错误，分析可能的原因并给出修复建议
- 代码示例使用代码块格式，标注语言和来源文件
- 如果上下文中没有足够信息，明确说明"根据现有代码，无法回答该问题"
```

### DOC Prompt

```
你是一个文档问答助手。请根据以下检索到的文档内容回答用户的问题。

规则：
- 只基于提供的文档上下文回答，不要编造信息
- 用清晰易懂的语言解释概念
- 引用具体的文档章节和来源
- 如果有相关的代码示例，一并展示
- 如果上下文中没有足够信息，明确说明"根据现有文档，无法回答该问题"
```

### GENERAL Prompt

```
你是一个代码与文档问答助手。请根据以下检索到的上下文内容回答用户的问题。

规则：
- 只基于提供的上下文回答，不要编造信息
- 如果上下文中没有足够信息，明确说明"根据现有文档，无法回答该问题"
- 回答时引用具体的文件或章节名称
- 代码示例使用代码块格式
```

三套 Prompt 的共同约束是"只基于检索上下文回答，不编造信息"，差异在于引导 LLM 关注的维度不同：CODE 强调函数名/行号/bug 分析，DOC 强调概念解释/章节引用，GENERAL 则取平衡策略。

## 集成方式

意图路由在 RAG 管线的 Prompt 组装阶段介入。调用链路位于 `src/delphi/retrieval/rag.py`：

```
用户查询
   ↓
向量检索 + Rerank → Top-N Chunk
   ↓
classify_intent(question)  → Intent
   ↓
get_system_prompt(intent)  → System Prompt
   ↓
组装 messages：[system_prompt, ...history, user_content]
   ↓
vLLM 生成 → 流式输出
```

关键代码：

```python
intent = classify_intent(question)
system_prompt = get_system_prompt(intent)

messages = [{"role": "system", "content": system_prompt}]
if history:
    messages.extend(history)
messages.append({"role": "user", "content": user_content})
```

意图分类结果同时通过 OpenTelemetry span 属性 `rag.prompt_build.intent` 记录，便于在可观测性平台中分析意图分布。

## 扩展指南

### 添加新意图

1. 在 `Intent` 枚举中添加新值：

```python
class Intent(StrEnum):
    CODE = "code"
    DOC = "doc"
    API = "api"       # 新增
    GENERAL = "general"
```

2. 定义对应的正则模式列表：

```python
_API_PATTERNS = [
    r"(API|接口文档|端点|endpoint|请求|响应|HTTP|REST)",
    r"\b(GET|POST|PUT|DELETE|PATCH)\b",
]
```

3. 在 `classify_intent()` 中加入新意图的评分逻辑：

```python
api_score = sum(1 for p in _API_PATTERNS if re.search(p, question, re.IGNORECASE))
```

4. 更新判定逻辑，处理多意图间的优先级关系。

5. 在 `PROMPTS` 字典中添加对应的 System Prompt。

### 升级为 LLM 分类

当前规则方案适合关键词边界清晰的场景。如果需要处理更模糊的意图（如隐含意图、多意图混合），可以：

- 将 `classify_intent()` 替换为 LLM 调用，使用 few-shot prompt 进行分类
- 保留规则分类作为 fallback，在 LLM 超时或不可用时降级
- 通过 `rag.prompt_build.intent` span 属性对比两种方案的分类准确率
