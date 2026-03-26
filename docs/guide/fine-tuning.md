# 微调支持

Delphi 本身定位为推理部署平台，不负责训练过程。但提供完整的微调工作流支持，让用户可以用自己的数据优化模型效果。

## 工作流

```
1. 数据生成    从已导入的知识库中自动生成 Q&A 训练数据
       ↓
2. 外部微调    用户在自己的训练环境完成 QLoRA / 全量微调
       ↓
3. 模型导入    将权重放入模型目录，系统自动加载
```

## 微调数据自动生成

Delphi 可以从已有的知识库数据中自动构建微调数据集：

### 代码 Q&A 对

从代码 Chunk 中，用 LLM 自动生成问答对：

```json
{
  "instruction": "解释 LatticePlanner::Plan 方法的实现逻辑",
  "input": "",
  "output": "LatticePlanner::Plan 方法首先通过 ...",
  "source": "modules/planning/planner/lattice/lattice_planner.cc"
}
```

### 文档 Q&A 对

从文档 Chunk 中提取知识问答：

```json
{
  "instruction": "如何使用 aem 工具启动 Apollo 容器？",
  "input": "",
  "output": "使用 aem start 命令可以启动 Apollo 容器 ...",
  "source": "docs/aem.md"
}
```

### 导出格式

支持导出为常见微调格式：
- Alpaca 格式（instruction / input / output）
- ShareGPT 格式（多轮对话）
- 自定义模板

## 微调方案

| 方法 | 显存需求 | 适用场景 |
|------|---------|---------|
| QLoRA | 单卡 24GB 可微调 7B~14B | 领域适配，低成本首选 |
| LoRA | 单卡 48GB 或多卡 | 中等规模微调 |
| 全量微调 | 多卡 A100/H100 | 深度定制，效果最好 |

推荐从 QLoRA 微调 Qwen2.5-Coder-7B/14B 开始，在领域数据上做 SFT（监督微调）。

## 模型导入

微调完成后，将权重放入 Delphi 的模型目录即可：

### LoRA Adapter

```bash
# 将 LoRA adapter 放入指定目录
cp -r /path/to/lora-adapter models/custom-lora/

# 修改配置指定 base model + adapter
# config.yaml
llm:
  model: Qwen/Qwen2.5-Coder-14B-Instruct
  lora_adapter: models/custom-lora/
```

### 合并后的全量权重

```bash
# 将合并后的模型放入目录
cp -r /path/to/merged-model models/custom-model/

# 修改配置
# config.yaml
llm:
  model: models/custom-model/
```

系统会在启动时自动检测并加载模型。
