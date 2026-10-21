"""
AstrBot 元宝搜索插件 v1.0.0 - 腾讯云 API 客户端

功能描述：
- 实现腾讯云 API 3.0 的 TC3-HMAC-SHA256 请求签名
- 封装元宝搜索 SearchPro 接口的调用与结果格式化
- 纯标准库 + aiohttp 实现，无需安装腾讯云 SDK

作者: 往昔的涟漪
版本: 1.0.0
日期: 2026-10-21
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import aiohttp

from astrbot.api import logger


class YuanbaoSearchError(RuntimeError):
    """Raised when the Yuanbao Search API returns an error or an invalid response."""


class YuanbaoSearchClient:
    """腾讯云元宝搜索（wsa / SearchPro）客户端，使用 TC3-HMAC-SHA256 签名。"""

    endpoint = "wsa.tencentcloudapi.com"
    service = "wsa"
    version = "2025-05-08"
    action = "SearchPro"
    algorithm = "TC3-HMAC-SHA256"

    def __init__(self, secret_id: str = "", secret_key: str = "", timeout: int = 30) -> None:
        self.secret_id = secret_id.strip()
        self.secret_key = secret_key.strip()
        self.timeout = timeout

    # ---------- 签名 ----------
    @staticmethod
    def _hmac_sha256(key: bytes, msg: str) -> hmac.HMAC:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256)

    def _build_authorization(self, body: str, timestamp: int, date: str) -> str:
        """生成 TC3-HMAC-SHA256 Authorization 请求头

        Args:
            body: 请求体 JSON 字符串，参与签名计算。
            timestamp: Unix 时间戳（秒）。
            date: UTC 日期，格式 YYYY-MM-DD。

        Returns:
            完整的 Authorization 头字符串。
        """
        canonical_headers = f"content-type:application/json\nhost:{self.endpoint}\n"
        signed_headers = "content-type;host"
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        canonical_request = (
            f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )
        credential_scope = f"{date}/{self.service}/tc3_request"
        string_to_sign = (
            f"{self.algorithm}\n{timestamp}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        secret_date = self._hmac_sha256(("TC3" + self.secret_key).encode("utf-8"), date)
        secret_service = self._hmac_sha256(secret_date.digest(), self.service)
        secret_signing = self._hmac_sha256(secret_service.digest(), "tc3_request")
        signature = self._hmac_sha256(secret_signing.digest(), string_to_sign).hexdigest()
        return (
            f"{self.algorithm} Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

    # ---------- 请求 ----------
    async def search(
        self,
        query: str,
        *,
        mode: int | None = None,
        site: str = "",
        cnt: int | None = None,
        industry: str = "",
        freshness: str = "",
        deeplinks: bool | None = None,
        full_content: bool = False,
        max_chars_per_item: int = 0,
    ) -> str:
        """调用元宝搜索 SearchPro 接口并返回格式化结果

        Args:
            query: 必填。搜索词或自然语言问题。
            mode: 返回结果类型。0 公开网页信源，1 优质权威垂直信源，2 混合结果。
            site: 指定网址搜索或过滤。指定搜索填单个域名，过滤用 exclude:域名1|域名2。
            cnt: 返回结果条数，可填 10/20/30/40/50。
            industry: 垂直领域，可填 gov、news、acad、finance。
            freshness: 搜索时效范围，如 d7、m3、y2 或日期区间。
            deeplinks: 是否返回附件子链信息，仅旗舰版支持。
            full_content: 为真时优先输出动态摘要（约 2500 字）而非标准摘要（约 800 字）。
            max_chars_per_item: 单条结果的摘要字数上限，0 表示不限制。

        Returns:
            格式化后的搜索结果文本，每条包含标题、链接、摘要与相关度。

        Raises:
            YuanbaoSearchError: 请求失败、返回无效 JSON、API 报错或结果为空时抛出。
        """
        payload: dict[str, Any] = {"Query": query}
        if mode is not None:
            payload["Mode"] = mode
        if site:
            payload["Site"] = site
        if cnt is not None:
            payload["Cnt"] = cnt
        if industry:
            payload["Industry"] = industry
        if freshness:
            payload["Freshness"] = freshness
        if deeplinks is not None:
            payload["Deeplinks"] = deeplinks

        body = json.dumps(payload)
        timestamp = int(time.time())
        date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
        headers = {
            "Authorization": self._build_authorization(body, timestamp, date),
            "Content-Type": "application/json",
            "Host": self.endpoint,
            "X-TC-Action": self.action,
            "X-TC-Version": self.version,
            "X-TC-Timestamp": str(timestamp),
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            try:
                async with session.post(
                    f"https://{self.endpoint}/",
                    data=body.encode("utf-8"),
                    headers=headers,
                ) as response:
                    text = await response.text()
                    if response.status >= 400:
                        logger.error(
                            f"元宝搜索请求失败: HTTP {response.status}, "
                            f"查询={query!r}, 响应={text[:300]}"
                        )
                        raise YuanbaoSearchError(
                            f"元宝搜索 HTTP {response.status}: {text[:500]}"
                        )
            except TimeoutError as exc:
                logger.error(f"元宝搜索请求超时: 查询={query!r}, 超时={self.timeout}s")
                raise YuanbaoSearchError("元宝搜索请求超时。") from exc
            except aiohttp.ClientError as exc:
                logger.error(f"元宝搜索连接失败: 查询={query!r}, 错误={exc}")
                raise YuanbaoSearchError(f"元宝搜索连接失败: {exc}") from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error(f"元宝搜索返回无效 JSON: 查询={query!r}, 响应={text[:300]}")
            raise YuanbaoSearchError(f"元宝搜索返回了无效 JSON: {text[:500]}") from exc

        if "Error" in data:
            error = data["Error"]
            if isinstance(error, dict):
                message = error.get("Message") or json.dumps(error, ensure_ascii=False)
            else:
                message = str(error)
            logger.error(f"元宝搜索 API 返回错误: 查询={query!r}, 错误={message}")
            raise YuanbaoSearchError(f"元宝搜索 API 错误: {message}")

        response = data.get("Response", {})
        pages = response.get("Pages") or []
        if not pages:
            msg = response.get("Msg") or "未找到相关结果"
            raise YuanbaoSearchError(f"元宝搜索未返回结果（{msg}）。")

        return self._format_pages(pages, response, full_content, max_chars_per_item)

    # ---------- 结果格式化 ----------
    @staticmethod
    def _format_pages(
        pages: list[str],
        response: dict[str, Any],
        full_content: bool = False,
        max_chars_per_item: int = 0,
    ) -> str:
        """把接口返回的 Pages 数组格式化为可读文本

        Args:
            pages: 接口返回的 JSON 字符串数组，每项代表一条搜索结果。
            response: 接口的 Response 对象，用于取回版本号等信息。
            full_content: 为真时优先输出动态摘要而非标准摘要。
            max_chars_per_item: 单条结果的摘要字数上限，0 表示不限制。

        Returns:
            拼接好的结果文本，每条结果包含标题、来源、日期、相关度、链接与摘要。
        """
        lines: list[str] = []
        version = response.get("Version")
        if version:
            lines.append(f"【元宝搜索 · {version}版】共 {len(pages)} 条结果")
        else:
            lines.append(f"【元宝搜索】共 {len(pages)} 条结果")

        for index, raw in enumerate(pages, 1):
            try:
                item = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except (json.JSONDecodeError, TypeError):
                lines.append(f"{index}. (结果解析失败)")
                continue

            title = str(item.get("title") or "无标题").strip()
            url = str(item.get("url") or "").strip()
            site = str(item.get("site") or "").strip()
            date = str(item.get("date") or "").strip()
            score = item.get("score")
            passage = str(item.get("passage") or "").strip()
            content = str(item.get("content") or "").strip()
            # full_content 为真时优先输出更详细的动态摘要
            if full_content and content:
                passage = content
            # 单条摘要的字数上限，0 表示不限制
            if max_chars_per_item > 0 and len(passage) > max_chars_per_item:
                passage = passage[:max_chars_per_item] + "…（已截断，可用更精确的关键词或提高 max_chars 获得更多内容）"

            header = f"{index}. {title}"
            if site:
                header += f" — {site}"
            if date:
                header += f" ({date})"
            if score is not None:
                try:
                    header += f" [相关度 {float(score):.2f}]"
                except (TypeError, ValueError):
                    pass
            lines.append(header)
            if url:
                lines.append(f"   链接: {url}")
            if passage:
                lines.append(f"   摘要: {passage}")
        return "\n".join(lines)
