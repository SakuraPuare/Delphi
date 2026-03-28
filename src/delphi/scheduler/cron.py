"""简单的 cron 表达式解析器，支持分钟、小时、日、月、星期五个字段。

支持的语法：
  - 数字: 5
  - 通配符: *
  - 步长: */6
  - 范围: 1-5
  - 列表: 1,3,5
  - 组合: 1-5/2
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from loguru import logger

_FIELD_RANGES: list[tuple[int, int]] = [
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day of month
    (1, 12),  # month
    (0, 6),  # day of week (0=Mon … 6=Sun)
]

_FIELD_NAMES: list[str] = ["minute", "hour", "day", "month", "weekday"]


@dataclass(frozen=True, slots=True)
class CronExpr:
    """解析后的 cron 表达式，每个字段存储为允许值的 frozenset。"""

    minute: frozenset[int]
    hour: frozenset[int]
    day: frozenset[int]
    month: frozenset[int]
    weekday: frozenset[int]


def _parse_field(token: str, lo: int, hi: int) -> frozenset[int]:
    """将单个 cron 字段解析为允许值集合。"""
    values: set[int] = set()
    for part in token.split(","):
        m = re.fullmatch(r"(\*|\d+-\d+)(?:/(\d+))?", part.strip())
        if not m:
            # 纯数字
            v = int(part.strip())
            if lo <= v <= hi:
                values.add(v)
            continue

        base, step_str = m.group(1), m.group(2)
        step = int(step_str) if step_str else 1

        if base == "*":
            start, end = lo, hi
        else:
            start_s, end_s = base.split("-")
            start, end = int(start_s), int(end_s)

        values.update(range(start, end + 1, step))

    return frozenset(v for v in values if lo <= v <= hi)


def parse_cron(expr: str) -> CronExpr:
    """解析标准五字段 cron 表达式。

    Parameters
    ----------
    expr:
        格式 ``"minute hour day month weekday"``，例如 ``"0 */6 * * *"``。

    Returns
    -------
    CronExpr
        解析后的结构体。

    Raises
    ------
    ValueError
        表达式格式不合法时抛出。
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        logger.error("cron 表达式格式错误: 需要 5 个字段, 实际 {} 个, expr={!r}", len(parts), expr)
        raise ValueError(f"cron 表达式需要 5 个字段，实际得到 {len(parts)}: {expr!r}")

    fields: dict[str, frozenset[int]] = {}
    for _i, (token, (lo, hi), name) in enumerate(zip(parts, _FIELD_RANGES, _FIELD_NAMES, strict=True)):
        parsed = _parse_field(token, lo, hi)
        if not parsed:
            logger.error("cron 字段解析为空: field={}, token={!r}, expr={!r}", name, token, expr)
            raise ValueError(f"cron 字段 {name!r} 解析结果为空: {token!r}")
        fields[name] = parsed

    result = CronExpr(**fields)
    logger.debug(
        "cron 表达式解析成功: expr={!r}, minute={}, hour={}, day={}, month={}, weekday={}",
        expr,
        result.minute,
        result.hour,
        result.day,
        result.month,
        result.weekday,
    )
    return result


def next_run(cron: CronExpr, now: datetime) -> datetime:
    """计算从 *now* 之后的下一次执行时间。

    采用逐分钟向前推进的方式，最多搜索 366 天。
    """
    # 从下一分钟开始，秒和微秒归零
    candidate = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    max_dt = now + timedelta(days=366)
    logger.debug("计算下次执行时间: now={}, 搜索截止={}", now, max_dt)

    while candidate <= max_dt:
        if (
            candidate.month in cron.month
            and candidate.day in cron.day
            and candidate.weekday() in cron.weekday  # Python weekday(): 0=Mon
            and candidate.hour in cron.hour
            and candidate.minute in cron.minute
        ):
            logger.debug("下次执行时间确定: {}", candidate)
            return candidate

        # 快速跳过：如果月份不匹配，跳到下个月
        if candidate.month not in cron.month:
            if candidate.month == 12:
                candidate = candidate.replace(year=candidate.year + 1, month=1, day=1, hour=0, minute=0)
            else:
                candidate = candidate.replace(month=candidate.month + 1, day=1, hour=0, minute=0)
            continue

        # 如果日不匹配，跳到下一天
        if candidate.day not in cron.day or candidate.weekday() not in cron.weekday:
            candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
            continue

        # 如果小时不匹配，跳到下一小时
        if candidate.hour not in cron.hour:
            candidate = (candidate + timedelta(hours=1)).replace(minute=0)
            continue

        # 分钟不匹配，跳到下一分钟
        candidate += timedelta(minutes=1)

    logger.error("在 366 天内未找到匹配的执行时间: cron={}", cron)
    raise RuntimeError(f"在 366 天内未找到匹配的执行时间: {cron}")
