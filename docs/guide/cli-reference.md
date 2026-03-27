# CLI 命令参考

Delphi 提供统一的命令行工具 `delphi`，覆盖服务管理、数据导入、智能问答、模型管理等全部功能。

## 全局选项

所有子命令均支持以下全局选项：

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--api-url` | `http://localhost:8888` | API 服务地址 |
| `--verbose` / `-v` | 关闭 | 开启详细日志输出 |

```bash
# 示例：连接远程服务并开启详细日志
delphi --api-url http://192.168.1.100:8888 -v status
```

---

## 服务管理

### serve — 启动 API 服务

通过 uvicorn 启动 Delphi API 服务。

**用法**

```bash
delphi serve [--host HOST] [--port PORT] [--reload]
```

**参数说明**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `0.0.0.0` | 监听地址 |
| `--port` | `8888` | 监听端口 |
| `--reload` | 关闭 | 开启热重载（开发模式） |

**示例**

```bash
$ delphi serve --port 9000 --reload
INFO:     Uvicorn running on http://0.0.0.0:9000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345]
```

### status — 查看服务状态

检查各依赖服务的健康状态。

**用法**

```bash
delphi status
```

**示例**

```bash
$ delphi status
Service          Status
───────────────────────
vLLM             ✔ healthy
Qdrant           ✔ healthy
Embedding (BGE)  ✔ healthy
```

---

## 数据导入

### import git — 导入 Git 仓库

克隆并导入远程或本地 Git 仓库，自动进行代码切分与向量化。导入过程显示进度条并轮询任务状态。

**用法**

```bash
delphi import git URL_OR_PATH --project NAME [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `URL_OR_PATH` | 是 | — | Git 仓库 URL 或本地路径 |
| `--project` | 是 | — | 目标项目名称 |
| `--branch` | 否 | `main` | 指定分支 |
| `--include` | 否 | — | 包含的文件 glob 模式（可多次指定） |
| `--exclude` | 否 | — | 排除的文件 glob 模式（可多次指定） |
| `--depth` | 否 | `1` | Git 克隆深度 |

**示例**

```bash
$ delphi import git https://github.com/ApolloAuto/apollo.git \
    --project apollo --branch master \
    --include "*.py" --include "*.cpp" \
    --exclude "third_party/*" --depth 1
Cloning repository...
Importing ━━━━━━━━━━━━━━━━━━━━ 100%  2847/2847 files
Task completed: 2847 chunks indexed.
```

### import docs — 导入文档

导入本地文档目录，支持 Markdown、纯文本、PDF、HTML 格式。

**用法**

```bash
delphi import docs PATH --project NAME [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `PATH` | 是 | — | 文档目录路径 |
| `--project` | 是 | — | 目标项目名称 |
| `--recursive` | 否 | 关闭 | 递归扫描子目录 |
| `--type` | 否 | `md,txt,pdf,html` | 文件类型过滤（逗号分隔） |

**示例**

```bash
$ delphi import docs /data/wiki --project internal-wiki --recursive --type md,pdf
Scanning /data/wiki ...
Importing ━━━━━━━━━━━━━━━━━━━━ 100%  136/136 files
Task completed: 136 documents indexed.
```

### import media — 导入音视频

导入音视频文件，使用 Whisper 模型进行语音转录后索引。

**用法**

```bash
delphi import media PATH --project NAME [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `PATH` | 是 | — | 音视频文件或目录路径 |
| `--project` | 是 | — | 目标项目名称 |
| `--recursive` | 否 | 关闭 | 递归扫描子目录 |
| `--whisper-model` | 否 | `large-v3` | Whisper 模型版本 |

**示例**

```bash
$ delphi import media /data/recordings --project meetings --recursive
Transcribing ━━━━━━━━━━━━━━━━━━━━ 100%  12/12 files
Importing ━━━━━━━━━━━━━━━━━━━━ 100%  12/12 transcripts
Task completed: 12 media files indexed.
```

### import batch — 批量导入仓库

从 JSON 配置批量导入多个 Git 仓库。

**用法**

```bash
delphi import batch REPOS_JSON [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `REPOS_JSON` | 是 | — | 仓库列表 JSON 文件路径 |
| `--depth` | 否 | `1` | Git 克隆深度 |
| `--include` | 否 | — | 包含的文件 glob 模式（可多次指定） |
| `--exclude` | 否 | — | 排除的文件 glob 模式（可多次指定） |

`REPOS_JSON` 文件格式：

```json
[
  {"url": "https://github.com/org/repo-a.git", "branch": "main", "project_name": "repo-a"},
  {"url": "https://github.com/org/repo-b.git", "branch": "develop", "project_name": "repo-b"}
]
```

**示例**

```bash
$ delphi import batch repos.json --depth 1 --include "*.py"
[1/2] Importing repo-a ...
Importing ━━━━━━━━━━━━━━━━━━━━ 100%  1024/1024 files
[2/2] Importing repo-b ...
Importing ━━━━━━━━━━━━━━━━━━━━ 100%  768/768 files
Batch import completed: 2 repositories indexed.
```

---

## 智能问答

### query — RAG 问答

基于检索增强生成（RAG）对知识库进行问答。支持流式输出、多轮会话和来源展示。

**用法**

```bash
delphi query QUESTION --project NAME [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `QUESTION` | 是 | — | 问题文本 |
| `--project` | 是 | — | 目标项目名称 |
| `--top-k` | 否 | `5` | 检索返回的文档片段数量 |
| `--stream` / `--no-stream` | 否 | `--stream` | 是否流式输出 |
| `--show-sources` | 否 | 关闭 | 显示引用来源 |
| `--session` | 否 | — | 会话 ID（用于多轮对话） |
| `--no-graph-rag` | 否 | 关闭 | 禁用 Graph RAG 增强 |

**示例**

```bash
$ delphi query "Apollo 的感知模块如何处理激光雷达点云？" \
    --project apollo --top-k 10 --show-sources
Apollo 的感知模块通过 PointPillars 算法对激光雷达点云进行体素化处理……

Sources:
  [1] modules/perception/lidar/lib/pointpillars/pointpillars.cc:42-87
  [2] modules/perception/lidar/README.md:15-30
```

```bash
# 多轮对话
$ delphi query "详细解释一下 PointPillars 的实现" \
    --project apollo --session sess_abc123
```

### agent — 智能体问答

多步推理智能体，可自主规划检索策略并迭代查询。

**用法**

```bash
delphi agent QUESTION --project NAME [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `QUESTION` | 是 | — | 问题文本 |
| `--project` | 是 | — | 目标项目名称 |
| `--max-steps` | 否 | `5` | 最大推理步数 |
| `--stream` / `--no-stream` | 否 | `--stream` | 是否流式输出 |
| `--session` | 否 | — | 会话 ID（用于多轮对话） |

**示例**

```bash
$ delphi agent "对比 Apollo 和 Autoware 的定位模块架构差异" \
    --project apollo --max-steps 8
[Step 1] 检索 Apollo 定位模块结构...
[Step 2] 检索 Autoware 定位模块结构...
[Step 3] 对比分析...

Apollo 采用多传感器融合的 EKF 定位方案，而 Autoware 则以 NDT 匹配为核心……
```

---

## 项目管理

### projects list — 列出项目

列出所有已创建的项目。

**用法**

```bash
delphi projects list
```

**示例**

```bash
$ delphi projects list
Name            Documents   Created
──────────────────────────────────────
apollo          2847        2025-12-01
internal-wiki   136         2025-12-03
meetings        12          2025-12-05
```

### projects create — 创建项目

创建一个新的空项目。

**用法**

```bash
delphi projects create NAME [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `NAME` | 是 | — | 项目名称 |
| `--description` | 否 | — | 项目描述 |

**示例**

```bash
$ delphi projects create my-project --description "内部微服务代码库"
Project 'my-project' created.
```

### projects delete — 删除项目

删除项目及其所有索引数据。

**用法**

```bash
delphi projects delete NAME [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `NAME` | 是 | — | 项目名称 |
| `--yes` | 否 | 关闭 | 跳过确认提示 |

**示例**

```bash
$ delphi projects delete my-project
Are you sure you want to delete 'my-project'? [y/N]: y
Project 'my-project' deleted.

# 跳过确认
$ delphi projects delete my-project --yes
Project 'my-project' deleted.
```

---

## 模型管理

### models list — 列出模型

列出所有已注册的模型。

**用法**

```bash
delphi models list
```

**示例**

```bash
$ delphi models list
Name                      Type    Active   Path
────────────────────────────────────────────────────────
Qwen2.5-Coder-32B        base    ✔        /models/qwen2.5-coder-32b
my-finetuned-lora         lora    ✘        /models/my-lora-adapter
```

### models register — 注册模型

注册一个新的本地模型。

**用法**

```bash
delphi models register --name NAME --path PATH [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--name` | 是 | — | 模型名称 |
| `--path` | 是 | — | 模型权重路径 |
| `--type` | 否 | `base` | 模型类型：`base` 或 `lora` |
| `--base-model` | 否 | — | LoRA 适配器的基座模型名称（`--type lora` 时必填） |
| `--description` | 否 | — | 模型描述 |

**示例**

```bash
# 注册基座模型
$ delphi models register --name Qwen2.5-7B --path /models/qwen2.5-7b --type base
Model 'Qwen2.5-7B' registered.

# 注册 LoRA 适配器
$ delphi models register --name my-lora \
    --path /models/my-lora-adapter \
    --type lora --base-model Qwen2.5-Coder-32B \
    --description "基于内部代码库微调的适配器"
Model 'my-lora' registered.
```

### models remove — 移除模型

从注册列表中移除模型。

**用法**

```bash
delphi models remove --name NAME
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--name` | 是 | — | 模型名称 |

**示例**

```bash
$ delphi models remove --name my-lora
Model 'my-lora' removed.
```

### models activate — 激活模型

切换当前使用的推理模型。

**用法**

```bash
delphi models activate --name NAME
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--name` | 是 | — | 模型名称 |

**示例**

```bash
$ delphi models activate --name Qwen2.5-7B
Model 'Qwen2.5-7B' activated. vLLM will reload on next request.
```

### models vllm — 查看 vLLM 状态

查看当前 vLLM 推理引擎的运行状态。

**用法**

```bash
delphi models vllm
```

**示例**

```bash
$ delphi models vllm
vLLM Engine Status
──────────────────
Active Model:   Qwen2.5-Coder-32B
GPU Memory:     28.3 / 80.0 GB
Pending Reqs:   0
Uptime:         3d 12h 05m
```

---

## 微调数据生成

### finetune generate — 生成微调数据集

基于已索引的知识库自动生成问答对，用于模型微调。

**用法**

```bash
delphi finetune generate --project NAME [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--project` | 是 | — | 目标项目名称 |
| `--num` | 否 | `100` | 生成的问答对数量 |
| `--questions-per-chunk` | 否 | `2` | 每个文档片段生成的问题数 |
| `--format` | 否 | `jsonl` | 输出格式：`jsonl`、`alpaca`、`sharegpt` |
| `--output` | 否 | — | 输出文件路径 |

**示例**

```bash
$ delphi finetune generate --project apollo --num 200 \
    --questions-per-chunk 3 --format sharegpt \
    --output /data/finetune/apollo_qa.json
Generating QA pairs ━━━━━━━━━━━━━━━━━━━━ 100%  200/200
Saved 200 QA pairs to /data/finetune/apollo_qa.json
```

---

## 代码图谱

### graph build — 构建代码图谱

基于 AST 解析构建代码符号关系图谱。

**用法**

```bash
delphi graph build --project NAME --path DIR [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--project` | 是 | — | 目标项目名称 |
| `--path` | 是 | — | 代码目录路径 |
| `--include` | 否 | — | 包含的文件 glob 模式（可多次指定） |
| `--exclude` | 否 | — | 排除的文件 glob 模式（可多次指定） |

**示例**

```bash
$ delphi graph build --project apollo \
    --path /repos/apollo \
    --include "*.py" --include "*.cpp" \
    --exclude "test_*"
Building code graph ━━━━━━━━━━━━━━━━━━━━ 100%
Graph built: 4521 symbols, 12847 edges.
```

### graph show — 查看图谱概览

显示项目代码图谱的统计信息。

**用法**

```bash
delphi graph show --project NAME
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--project` | 是 | — | 目标项目名称 |

**示例**

```bash
$ delphi graph show --project apollo
Code Graph: apollo
──────────────────
Symbols:    4521
Edges:      12847
Files:      326
Languages:  Python, C++
```

### graph symbol — 查询符号

查询指定符号的定义、引用和依赖关系。

**用法**

```bash
delphi graph symbol --project NAME --name SYMBOL_NAME
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--project` | 是 | — | 目标项目名称 |
| `--name` | 是 | — | 符号名称（函数名、类名等） |

**示例**

```bash
$ delphi graph symbol --project apollo --name PointPillars
Symbol: PointPillars (class)
File:   modules/perception/lidar/lib/pointpillars/pointpillars.h:28
──────────────────────────────────────
Methods:
  - forward()          line 45
  - preprocess()       line 62
References (7):
  - pointpillars.cc:15
  - pointpillars_test.cc:22
  - lidar_detection.cc:88
  ...
```

### graph file — 查询文件符号

查询指定文件中包含的所有符号及其关系。

**用法**

```bash
delphi graph file --project NAME --file FILE_PATH
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--project` | 是 | — | 目标项目名称 |
| `--file` | 是 | — | 文件路径 |

**示例**

```bash
$ delphi graph file --project apollo \
    --file modules/perception/lidar/lib/pointpillars/pointpillars.cc
File: pointpillars.cc
──────────────────────
Symbols (12):
  class  PointPillars           line 15
  func   PointPillars::forward  line 45
  func   PointPillars::preprocess  line 62
  ...
Imports: 4 files
Imported by: 3 files
```

---

## 评估

### eval generate — 生成评估数据集

从知识库自动生成评估问答数据集。

**用法**

```bash
delphi eval generate --project NAME [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--project` | 是 | — | 目标项目名称 |
| `--num` | 否 | `50` | 生成的评估样本数量 |
| `--output` | 否 | — | 输出文件路径 |

**示例**

```bash
$ delphi eval generate --project apollo --num 100 \
    --output /data/eval/apollo_eval.json
Generating eval dataset ━━━━━━━━━━━━━━━━━━━━ 100%  100/100
Saved 100 samples to /data/eval/apollo_eval.json
```

### eval run — 运行评估

对指定数据集运行 RAG 评估，输出各项指标。

**用法**

```bash
delphi eval run DATASET_PATH [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DATASET_PATH` | 是 | — | 评估数据集文件路径 |
| `--project` | 否 | — | 目标项目名称 |
| `--output` | 否 | — | 评估报告输出路径 |

**示例**

```bash
$ delphi eval run /data/eval/apollo_eval.json \
    --project apollo --output /data/eval/report.json
Running evaluation ━━━━━━━━━━━━━━━━━━━━ 100%  100/100

Evaluation Results
──────────────────
Faithfulness:   0.87
Relevancy:      0.91
Correctness:    0.83
Saved report to /data/eval/report.json
```

---

## 定时任务

### schedule add — 添加定时同步

为项目添加定时同步任务，按 cron 表达式周期性拉取仓库更新并重新索引。

**用法**

```bash
delphi schedule add --project NAME --repo URL [选项]
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--project` | 是 | — | 目标项目名称 |
| `--repo` | 是 | — | Git 仓库 URL |
| `--cron` | 否 | `"0 */6 * * *"` | cron 表达式（默认每 6 小时） |
| `--branch` | 否 | `main` | 同步分支 |

**示例**

```bash
$ delphi schedule add --project apollo \
    --repo https://github.com/ApolloAuto/apollo.git \
    --cron "0 2 * * *" --branch master
Schedule added: apollo (daily at 02:00, branch: master)
```

### schedule list — 列出定时任务

列出所有已配置的定时同步任务。

**用法**

```bash
delphi schedule list
```

**示例**

```bash
$ delphi schedule list
Project         Cron            Branch    Next Run
──────────────────────────────────────────────────────
apollo          0 2 * * *       master    2026-03-29 02:00
internal-wiki   0 */6 * * *     main      2026-03-28 18:00
```

### schedule remove — 移除定时任务

移除指定项目的定时同步任务。

**用法**

```bash
delphi schedule remove --project NAME
```

**参数说明**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--project` | 是 | — | 目标项目名称 |

**示例**

```bash
$ delphi schedule remove --project apollo
Schedule removed: apollo
```
