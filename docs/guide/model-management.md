# 模型管理

## 概述

Delphi 提供完整的模型生命周期管理能力，支持注册、切换、注销模型，并可管理 LoRA 适配器。所有模型元信息保存在本地注册表 `~/.delphi/models/registry.json` 中，同时可查询 vLLM 推理引擎当前加载的模型。

核心组件 `ModelManager` 位于 `src/delphi/models/manager.py`，提供以下能力：

- 注册 / 注销模型（支持 HuggingFace ID 和本地路径）
- 在运行时切换活跃模型
- 管理 LoRA 适配器及其基础模型关联
- 查询 vLLM 当前已加载的模型

用户可通过 CLI 命令或 REST API 两种方式操作。

## 模型注册

### 注册基础模型

通过 CLI 注册一个 HuggingFace 模型：

```bash
delphi models register qwen2.5-coder-14b \
  --path Qwen/Qwen2.5-Coder-14B-Instruct \
  --desc "Qwen2.5 Coder 14B 指令微调版"
```

注册本地路径的模型：

```bash
delphi models register my-local-model \
  --path /data/models/custom-model \
  --desc "本地自定义模型"
```

### 注册参数说明

| 参数 | 缩写 | 必填 | 说明 |
|------|------|------|------|
| `NAME` | - | 是 | 模型名称（位置参数） |
| `--path` | `-p` | 是 | HuggingFace ID 或本地模型路径 |
| `--type` | `-t` | 否 | 模型类型：`base`（默认）或 `lora` |
| `--base` | `-b` | 否 | LoRA 基础模型（仅 `lora` 类型需要） |
| `--desc` | `-d` | 否 | 模型描述 |

注册时如果模型名称已存在，API 会返回 `409 Conflict`。

### 查看已注册模型

```bash
delphi models list
```

输出示例：

```
                    模型列表
┌──────────────────────┬─────────────────────────────────────┬──────┬────────────┬──────┐
│ 名称                 │ 路径                                │ 类型 │ 基础模型   │ 活跃 │
├──────────────────────┼─────────────────────────────────────┼──────┼────────────┼──────┤
│ qwen2.5-coder-14b    │ Qwen/Qwen2.5-Coder-14B-Instruct    │ base │            │  ✓   │
│ my-lora              │ /data/adapters/domain-lora          │ lora │ qwen2.5-…  │      │
└──────────────────────┴─────────────────────────────────────┴──────┴────────────┴──────┘
```

列表会同时包含注册表中的模型和 vLLM 引擎中已加载但未注册的模型。

## 模型切换

使用 `activate` 命令在运行时切换活跃模型：

```bash
delphi models activate qwen2.5-coder-14b
```

切换时系统会：

1. 在注册表中查找目标模型
2. 将 `settings.llm_model` 更新为该模型的 `model_path`
3. 将所有其他模型标记为非活跃，目标模型标记为活跃
4. 持久化注册表状态

同一时间只能有一个模型处于活跃状态。切换操作立即生效，后续的推理请求将使用新模型。

## LoRA 适配器管理

Delphi 原生支持 LoRA 适配器的注册与管理。注册 LoRA 模型时需要指定 `--type lora` 并通过 `--base` 关联基础模型。

### 注册 LoRA 适配器

```bash
delphi models register domain-lora \
  --path /data/adapters/my-domain-lora \
  --type lora \
  --base Qwen/Qwen2.5-Coder-14B-Instruct \
  --desc "领域知识 LoRA 适配器"
```

### 切换到 LoRA 模型

```bash
delphi models activate domain-lora
```

激活 LoRA 模型后，系统会将 `model_path`（即适配器路径）设置为当前推理模型。vLLM 引擎需要预先配置好对应的基础模型和 LoRA 加载支持。

### 注销模型

```bash
delphi models remove domain-lora
```

系统会要求确认，使用 `--yes` / `-y` 跳过确认提示：

```bash
delphi models remove domain-lora --yes
```

## CLI 命令参考

所有模型管理命令均在 `delphi models` 子命令组下：

| 命令 | 说明 | 示例 |
|------|------|------|
| `delphi models list` | 列出所有已注册模型及 vLLM 加载模型 | `delphi models list` |
| `delphi models register` | 注册新模型 | `delphi models register my-model --path Qwen/Qwen2.5-7B` |
| `delphi models activate` | 激活/切换模型 | `delphi models activate my-model` |
| `delphi models remove` | 注销模型 | `delphi models remove my-model --yes` |

全局选项：

- `--api-url`：指定 API Server 地址（默认 `http://localhost:8888`）
- `--verbose` / `-v`：输出详细日志

## API 接口

模型管理提供以下 REST API，路由前缀为 `/models`。

### GET /models

列出所有已注册模型，同时合并 vLLM 引擎中已加载但未注册的模型。

**响应示例：**

```json
[
  {
    "name": "qwen2.5-coder-14b",
    "model_path": "Qwen/Qwen2.5-Coder-14B-Instruct",
    "model_type": "base",
    "base_model": "",
    "description": "Qwen2.5 Coder 14B 指令微调版",
    "active": true
  }
]
```

### POST /models/register

注册新模型。如果模型名称已存在，返回 `409`。

**请求体：**

```json
{
  "name": "my-model",
  "model_path": "Qwen/Qwen2.5-Coder-7B-Instruct",
  "model_type": "base",
  "base_model": "",
  "description": "模型描述"
}
```

**响应：** `201 Created`，返回 `ModelInfoResponse`。

### DELETE /models/{name}

注销指定模型。模型不存在时返回 `404`。

**响应：** `204 No Content`。

### POST /models/activate

激活/切换模型。模型不存在时返回 `404`。

**请求体：**

```json
{
  "name": "qwen2.5-coder-14b"
}
```

**响应：** 返回激活后的模型信息 `ModelInfoResponse`。

## 注册表存储格式

模型注册表以 JSON 数组形式存储在 `~/.delphi/models/registry.json`，系统启动时自动加载，每次变更后立即持久化。

```json
[
  {
    "name": "qwen2.5-coder-14b",
    "model_path": "Qwen/Qwen2.5-Coder-14B-Instruct",
    "model_type": "base",
    "base_model": "",
    "description": "Qwen2.5 Coder 14B 指令微调版",
    "active": true
  },
  {
    "name": "domain-lora",
    "model_path": "/data/adapters/my-domain-lora",
    "model_type": "lora",
    "base_model": "Qwen/Qwen2.5-Coder-14B-Instruct",
    "description": "领域知识 LoRA 适配器",
    "active": false
  }
]
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 用户自定义的模型名称，作为唯一标识 |
| `model_path` | `str` | HuggingFace 模型 ID 或本地文件路径 |
| `model_type` | `str` | `"base"` 或 `"lora"` |
| `base_model` | `str` | LoRA 适配器对应的基础模型（仅 `lora` 类型使用） |
| `description` | `str` | 模型描述信息 |
| `active` | `bool` | 是否为当前活跃模型 |

目录 `~/.delphi/models/` 在首次使用时自动创建。
