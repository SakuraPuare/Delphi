"""导出微调数据为不同格式"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


async def export_jsonl(qa_pairs: AsyncIterator[dict], output_path: Path) -> int:
    """导出为 JSONL 格式（每行一个 JSON 对象），返回导出数量"""
    logger.info("开始导出 JSONL 格式: path={}", output_path)
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        async for pair in qa_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
            count += 1
    logger.info("JSONL 导出完成: path={}, 导出数量={}", output_path, count)
    return count


async def export_alpaca(qa_pairs: AsyncIterator[dict], output_path: Path) -> int:
    """导出为 Alpaca 格式 {"instruction": ..., "input": "", "output": ...}"""
    logger.info("开始导出 Alpaca 格式: path={}", output_path)
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        async for pair in qa_pairs:
            record = {
                "instruction": pair["question"],
                "input": "",
                "output": pair["answer"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    logger.info("Alpaca 导出完成: path={}, 导出数量={}", output_path, count)
    return count


async def export_sharegpt(qa_pairs: AsyncIterator[dict], output_path: Path) -> int:
    """导出为 ShareGPT 格式 {"conversations": [{"from": "human", ...}, {"from": "gpt", ...}]}"""
    logger.info("开始导出 ShareGPT 格式: path={}", output_path)
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        async for pair in qa_pairs:
            record = {
                "conversations": [
                    {"from": "human", "value": pair["question"]},
                    {"from": "gpt", "value": pair["answer"]},
                ],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    logger.info("ShareGPT 导出完成: path={}, 导出数量={}", output_path, count)
    return count
