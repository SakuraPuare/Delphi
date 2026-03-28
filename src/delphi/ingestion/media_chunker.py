"""音视频转录与切分：基于 Faster-Whisper"""

from __future__ import annotations

from typing import TYPE_CHECKING

from delphi.ingestion.models import Chunk, ChunkMetadata

if TYPE_CHECKING:
    from pathlib import Path

from loguru import logger

MEDIA_EXTENSIONS: set[str] = {".mp3", ".mp4", ".wav", ".m4a", ".flac", ".ogg", ".webm"}

# 延迟加载的 WhisperModel 实例缓存
_model_cache: dict[str, object] = {}


def _get_model(model_size: str = "large-v3", compute_type: str = "int8"):
    """延迟加载 WhisperModel，相同参数复用实例。"""
    key = f"{model_size}:{compute_type}"
    if key not in _model_cache:
        from faster_whisper import WhisperModel

        logger.info("加载 WhisperModel: model_size={}, compute_type={}", model_size, compute_type)
        _model_cache[key] = WhisperModel(model_size, compute_type=compute_type)
        logger.info("WhisperModel 加载完成, key={}", key)
    else:
        logger.debug("复用已缓存的 WhisperModel, key={}", key)
    return _model_cache[key]


def _format_time(seconds: int) -> str:
    """将秒数格式化为 MM:SS 字符串。"""
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def transcribe_and_chunk(
    path: Path,
    model_size: str = "large-v3",
    compute_type: str = "int8",
    window_seconds: int = 30,
    overlap_seconds: int = 5,
) -> list[Chunk]:
    """转录音视频文件并按时间窗口切分为 Chunk 列表。

    Args:
        path: 音视频文件路径
        model_size: Whisper 模型大小
        compute_type: 计算类型（int8 对 CPU 友好）
        window_seconds: 每个 chunk 的时间窗口（秒）
        overlap_seconds: 相邻 chunk 的重叠时间（秒）

    Returns:
        切分后的 Chunk 列表
    """
    ext = path.suffix.lower()
    if ext not in MEDIA_EXTENSIONS:
        logger.warning("不支持的媒体格式: ext={}", ext)
        return []

    # 判断媒体类型
    media_type = "video" if ext in (".mp4", ".webm") else "audio"
    logger.info("开始转录媒体文件, path={}, media_type={}, model={}", path.name, media_type, model_size)

    model = _get_model(model_size, compute_type)
    segments, _info = model.transcribe(str(path))

    # 收集所有 segment 的文本和时间戳
    seg_list: list[dict] = []
    for seg in segments:
        seg_list.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})

    if not seg_list:
        logger.warning("转录结果为空, path={}", path.name)
        return []

    logger.debug("转录 segment 收集完成, path={}, segment数={}", path.name, len(seg_list))

    # 计算总时长
    total_duration = seg_list[-1]["end"]

    # 按时间窗口切分，带重叠
    step = window_seconds - overlap_seconds
    chunks: list[Chunk] = []
    win_start = 0.0

    while win_start < total_duration:
        win_end = win_start + window_seconds

        # 收集落在当前窗口内的 segment 文本
        texts: list[str] = []
        for seg in seg_list:
            # segment 与窗口有交集即纳入
            if seg["end"] > win_start and seg["start"] < win_end:
                texts.append(seg["text"])

        if texts:
            start_sec = int(win_start)
            end_sec = min(int(win_end), int(total_duration))
            chunks.append(
                Chunk(
                    text=" ".join(texts),
                    metadata=ChunkMetadata(
                        file_path=str(path),
                        language=media_type,
                        node_type="transcript",
                        start_line=start_sec,
                        end_line=end_sec,
                        symbol_name=f"{_format_time(start_sec)}-{_format_time(end_sec)}",
                    ),
                )
            )

        win_start += step

    logger.info("转录完成: file={}, 块数={}, 总时长={:.1f}s", path.name, len(chunks), total_duration)
    return chunks
