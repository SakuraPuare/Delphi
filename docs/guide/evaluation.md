# RAG 评估

RAG 系统的效果取决于两个环节：检索是否找到了正确的内容，生成是否基于这些内容给出了准确的回答。任何一个环节出问题，最终回答质量都会下降。

Delphi 内置了完整的评估框架，覆盖检索和生成两个维度，支持自动生成评估数据集、一键运行评估、量化输出结果，帮助你持续优化知识库的问答效果。

## 评估指标

### 检索指标

| 指标 | 含义 | 计算方式 |
|------|------|---------|
| Recall（召回率） | 相关文档被检索到的比例 | 检索命中的相关文档数 / 总相关文档数 |
| Precision（精确率） | 检索结果中相关文档的比例 | 检索命中的相关文档数 / 总检索结果数 |
| MRR（Mean Reciprocal Rank） | 第一个相关结果的排名质量 | 1 / 第一个相关结果的排名位置 |

- Recall 高说明系统没有遗漏重要内容
- Precision 高说明检索结果噪音少
- MRR 高说明最相关的内容排在前面

### 生成指标

| 指标 | 含义 | 判定方式 |
|------|------|---------|
| Faithfulness（忠实度） | 回答是否忠于检索到的上下文 | LLM 判断回答内容是否都能在上下文中找到依据 |
| Relevance（相关性） | 回答是否切题 | LLM 判断回答是否直接回应了用户问题 |

两个生成指标均为二值评分（1.0 或 0.0），最终取所有样本的平均值。

## 评估数据集格式

评估数据集为 JSON 文件，格式如下：

```json
{
  "project_id": "my-project",
  "items": [
    {
      "question": "如何配置 Nginx 反向代理？",
      "ground_truth_answer": "在 nginx.conf 中添加 proxy_pass 指令...",
      "relevant_chunk_ids": [
        "docs/nginx.md:10-25",
        "docs/nginx.md:30-45"
      ]
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `project_id` | string | 是 | 项目 ID，对应已导入的知识库 |
| `items[].question` | string | 是 | 评估问题 |
| `items[].ground_truth_answer` | string | 是 | 标准答案，用于参考 |
| `items[].relevant_chunk_ids` | string[] | 否 | 相关文档块 ID，格式为 `file_path:start_line-end_line` |

::: tip
`relevant_chunk_ids` 为空时，检索指标（Recall / Precision / MRR）会返回 0，但生成指标仍然正常计算。
:::

## 自动生成评估数据集

手动编写评估数据集费时费力。Delphi 支持从已有知识库中自动生成：

```bash
delphi eval generate --project my-project --num 50 --output eval_dataset.json
```

参数说明：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--project` | （必填） | 项目 ID |
| `--num` | 50 | 生成的问答对数量 |
| `--output` | `eval_dataset.json` | 输出文件路径 |

生成过程：

1. 从向量库中随机采样文档块（采样量为目标数量的 1.5 倍，以应对部分生成失败）
2. 对每个文档块，用 LLM 生成一个自然的问答对
3. 自动关联 `relevant_chunk_ids`，将生成结果写入 JSON 文件

::: warning
自动生成的数据集质量取决于知识库内容和 LLM 能力。建议生成后人工抽检，剔除质量不佳的条目。
:::

## 运行评估

```bash
# 基本用法
delphi eval run eval_dataset.json

# 指定项目 ID（覆盖数据集中的 project_id）
delphi eval run eval_dataset.json --project my-project

# 将结果保存到文件
delphi eval run eval_dataset.json --output eval_result.json
```

评估过程会对每条数据依次执行：检索 -> 生成 -> 指标计算，最终输出汇总表格：

```
┌────────────────────────────────────────┐
│     评估结果 (50 条, 128.35s)          │
├──────────────┬─────────────────────────┤
│ 指标         │ 值                      │
├──────────────┼─────────────────────────┤
│ Recall       │ 0.7200                  │
│ Precision    │ 0.3600                  │
│ MRR          │ 0.6800                  │
│ Faithfulness │ 0.8400                  │
│ Relevance    │ 0.9200                  │
└──────────────┴─────────────────────────┘
```

## 结果解读与优化建议

### 检索指标偏低

| 现象 | 可能原因 | 优化方向 |
|------|---------|---------|
| Recall 低 | 相关内容未被检索到 | 增大 `chunk_top_k`；优化分块策略，避免关键信息被截断 |
| Precision 低 | 检索结果中噪音多 | 启用 Reranker 重排序；减小 `chunk_top_k` |
| MRR 低 | 相关内容排名靠后 | 启用 Reranker；优化 Embedding 模型 |

### 生成指标偏低

| 现象 | 可能原因 | 优化方向 |
|------|---------|---------|
| Faithfulness 低 | 模型产生幻觉 | 优化 Prompt 模板，强调"仅基于上下文回答"；考虑微调模型 |
| Relevance 低 | 回答偏离问题 | 检查检索质量是否影响了生成；优化 Prompt 引导模型聚焦问题 |

::: tip
通常建议先优化检索指标，再优化生成指标。检索质量是生成质量的基础。
:::

## 完整使用流程

```bash
# 1. 确保项目已导入知识库
delphi ingest --project my-project --repo /path/to/repo

# 2. 自动生成评估数据集
delphi eval generate --project my-project --num 50 --output eval_dataset.json

# 3. （可选）人工审核并修正 eval_dataset.json

# 4. 运行评估
delphi eval run eval_dataset.json --output eval_result.json

# 5. 查看结果，根据指标调整配置

# 6. 调整后重新评估，对比改进效果
delphi eval run eval_dataset.json --output eval_result_v2.json
```

典型的迭代优化循环：

```
评估 → 分析指标 → 调整配置/模型 → 重新评估 → 对比结果
```

通过持续评估，你可以量化每次调整带来的效果变化，避免凭感觉调参。
