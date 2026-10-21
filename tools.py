"""
AstrBot 元宝搜索插件 v1.0.0 - 参数归一化工具

功能描述：
- 对元宝搜索接口的 mode、cnt、site、industry、freshness 参数做取值校验与归一化
- 非法取值统一回退到安全默认值，避免请求被服务端拒绝

作者: 往昔的涟漪
版本: 1.0.0
日期: 2026-10-21
"""

from __future__ import annotations



MODE_VALUES = {0, 1, 2}
INDUSTRY_VALUES = {"gov", "news", "acad", "finance"}
CNT_VALUES = {10, 20, 30, 40, 50}
FRESHNESS_VALUES = {
    "d1", "d3", "d7", "d15", "d30",
    "m1", "m3", "m6", "m12",
    "y1", "y2", "y3", "y5",
}


def _clamp_cnt(value: object, default: int = 10) -> int:
    """归一化结果条数参数

    Args:
        value: 原始传入值。
        default: 非法值时的回退默认值。

    Returns:
        10/20/30/40/50 之一，或 default。
    """
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number if number in CNT_VALUES else default


def _normalize_mode(value: object) -> int | None:
    """归一化返回结果类型参数

    Args:
        value: 原始传入值。

    Returns:
        0/1/2 之一，非法值返回 None 表示不传该参数。
    """
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number in MODE_VALUES else None


def _normalize_industry(value: object) -> str:
    """归一化垂直领域参数

    Args:
        value: 原始传入值。

    Returns:
        gov/news/acad/finance 之一，非法值返回空字符串。
    """
    text = str(value or "").strip().lower()
    return text if text in INDUSTRY_VALUES else ""


def _normalize_freshness(value: object) -> str:
    """归一化时效范围参数

    Args:
        value: 原始传入值，形如 d7、m3、y2 或 yyyy-mm-dd 区间。

    Returns:
        合法时效字符串，非法值返回空字符串。
    """
    text = str(value or "").strip().lower()
    if text in FRESHNESS_VALUES:
        return text
    # 也接受 dN / mN / yN 形态
    if len(text) >= 2 and text[0] in {"d", "m", "y"} and text[1:].isdigit():
        limits = {"d": 30, "m": 12, "y": 5}
        count = int(text[1:])
        if 1 <= count <= limits[text[0]]:
            return text
    return ""


def _normalize_site(value: object) -> str:
    """归一化站点过滤参数

    Args:
        value: 原始传入值，可为单个域名或 exclude:域名1|域名2。

    Returns:
        合法的站点字符串，非法值返回空字符串。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower().startswith("exclude:"):
        domains = [d.strip() for d in text[len("exclude:"):].split("|") if d.strip()]
        if not domains or len(domains) > 5:
            return ""
        return "exclude:" + "|".join(domains)
    # 指定网址搜索：每次仅支持一个域名
    if "|" in text or " " in text:
        return ""
    return text
