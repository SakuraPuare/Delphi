# Whisper 语音识别

## 什么是 OpenAI Whisper

Whisper 是 OpenAI 于 2022 年开源的自动语音识别（ASR）模型。它通过在 68 万小时的多语言音频数据上进行弱监督训练，具备了强大的多语言转录和翻译能力。与传统 ASR 系统不同，Whisper 不依赖特定领域的微调，开箱即用的鲁棒性极强。

Whisper 的核心特点：

- 支持 99 种语言的语音识别
- 支持将非英语语音直接翻译为英文
- 对噪声、口音、专业术语有较强的适应能力
- 完全开源，可本地部署，无需调用外部 API

## 架构：编码器-解码器 Transformer

Whisper 采用标准的 **编码器-解码器（Encoder-Decoder）Transformer** 架构。

```
音频输入
   │
   ▼
┌─────────────────────────────┐
│  音频预处理                  │
│  · 重采样至 16kHz            │
│  · 提取 80 维 Mel 频谱特征   │
│  · 切分为 30 秒窗口          │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  编码器（Encoder）           │
│  · 多层 Transformer 块       │
│  · 输出音频的上下文表示       │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  解码器（Decoder）           │
│  · 自回归生成文本 token       │
│  · 交叉注意力关注编码器输出   │
│  · 输出转录文本 / 翻译结果    │
└─────────────────────────────┘
```

解码器在生成时会首先输出特殊的语言标记（如 `<|zh|>`）和任务标记（如 `<|transcribe|>`），从而控制输出语言和任务类型。

### 模型规格

| 模型名称 | 参数量 | 相对速度 | 英文 WER |
|---------|--------|---------|---------|
| tiny    | 39M    | 32x     | ~5.7%   |
| base    | 74M    | 16x     | ~4.2%   |
| small   | 244M   | 6x      | ~3.0%   |
| medium  | 769M   | 2x      | ~2.2%   |
| large-v3| 1550M  | 1x      | ~1.8%   |

## 支持的语言与能力

Whisper 对中文、英文、日文、西班牙文等主流语言的识别效果尤为出色。对于中文，`large-v3` 模型在普通话上的字错率（CER）可低至 3% 以下。

主要能力：

- **转录（Transcription）**：将音频转为同语言文本
- **翻译（Translation）**：将非英语音频直接翻译为英文文本
- **时间戳对齐**：输出词级或句级时间戳，便于字幕生成
- **语言检测**：自动识别音频语言

## Faster-Whisper：CTranslate2 加速与 INT8 量化

原版 Whisper 使用 PyTorch 实现，推理速度在 CPU 上较慢。[Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) 通过以下技术大幅提升性能：

### CTranslate2 推理引擎

CTranslate2 是一个专为 Transformer 模型优化的 C++ 推理库，相比 PyTorch 具有：

- 更低的内存占用（无需 Python 运行时开销）
- 针对 CPU/GPU 的算子融合优化
- 支持批量推理和流式输出

### INT8 量化

将模型权重从 FP32/FP16 量化为 INT8，在几乎不损失精度的前提下：

- 模型体积缩小约 4 倍
- 推理速度提升 2-4 倍
- 内存占用显著降低

```python
from faster_whisper import WhisperModel

# 使用 INT8 量化加载 large-v3 模型
model = WhisperModel("large-v3", device="cpu", compute_type="int8")

segments, info = model.transcribe("audio.mp3", beam_size=5)
for segment in segments:
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
```

## 速度对比：原版 vs Faster-Whisper

以下为在同一硬件（CPU: Intel i7-12700, GPU: RTX 3080）上转录 1 小时音频的耗时对比：

| 实现方式 | 设备 | 模型 | 耗时 | 实时率 |
|---------|------|------|------|--------|
| openai/whisper | CPU | large-v3 | ~180 min | 0.33x |
| faster-whisper | CPU (INT8) | large-v3 | ~45 min | 1.3x |
| openai/whisper | GPU (FP16) | large-v3 | ~12 min | 5x |
| faster-whisper | GPU (INT8) | large-v3 | ~6 min | 10x |

> 实时率 > 1 表示处理速度快于音频实际时长。

## 典型使用场景

### 会议转录

将录音文件自动转为带时间戳的文字记录，结合说话人分离（Speaker Diarization）可生成"谁说了什么"的完整会议纪要。

### 视频内容索引

对视频文件提取音轨后进行转录，将语音内容纳入全文检索索引，使视频内容可被搜索。

### 播客与课程归档

将音频内容转为文本，便于知识库沉淀和后续检索。

## Delphi 如何使用 Faster-Whisper

在 Delphi 的媒体导入流程中，Faster-Whisper 承担音频/视频文件的语音转文字任务：

```
用户上传音视频文件
        │
        ▼
  提取音频轨道（ffmpeg）
        │
        ▼
  Faster-Whisper 转录
  · 自动检测语言
  · 输出带时间戳的文本段落
        │
        ▼
  文本分块（Chunking）
        │
        ▼
  BGE-M3 向量化 → 存入 Milvus
        │
        ▼
  可被 RAG 检索的知识片段
```

Delphi 默认使用 `large-v3` 模型配合 INT8 量化，在保证中文识别精度的同时，使普通消费级硬件也能完成转录任务。转录结果中的时间戳信息会被保留在元数据中，方便用户在检索结果中定位到原始音视频的具体位置。
