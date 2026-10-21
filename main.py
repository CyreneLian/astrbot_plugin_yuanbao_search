"""
AstrBot 元宝搜索插件 v1.0.0

功能描述：
- 基于腾讯云元宝搜索（wsa / SearchPro）接口的实时联网检索
- 支持公开网页信源、优质权威垂直信源、混合结果三种模式
- 支持站点定向/排除、垂直领域过滤、时效范围控制
- 摘要支持标准摘要与动态摘要两档，可按需截断控制总量
- 指令：元宝搜索
- 大模型工具：yuanbao_search

作者: 往昔的涟漪
版本: 1.0.0
日期: 2026-10-21
"""

from __future__ import annotations

from typing import AsyncGenerator

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.star.filter.command import GreedyStr

from .client import YuanbaoSearchClient, YuanbaoSearchError
from .tools import (
    _clamp_cnt,
    _normalize_freshness,
    _normalize_industry,
    _normalize_mode,
    _normalize_site,
)



@register(
    "astrbot_plugin_yuanbao_search",
    "往昔的涟漪",
    "为 AstrBot 提供每月 2000次 的免费腾讯生态实时联网检索能力。支持网页信源、优质权威垂直信源、混合结果，并可按站点、垂直领域与时间范围精细过滤，可以让 Bot 在回答中获取实时外部信息。",
    "1.0.0",
    "https://github.com/CyreneLian/astrbot_plugin_yuanbao_search",
)
class YuanbaoSearchPlugin(Star):
    # 供 LLM 工具共享使用的客户端实例
    _shared_client: YuanbaoSearchClient | None = None

    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | dict | None = None,
    ) -> None:
        super().__init__(context)
        self.config = config or {}
        secret_id = str(self.config.get("secret_id", "")).strip()
        secret_key = str(self.config.get("secret_key", "")).strip()
        self.client = YuanbaoSearchClient(
            secret_id=secret_id,
            secret_key=secret_key,
        )
        YuanbaoSearchPlugin._shared_client = self.client
        if secret_id and secret_key:
            logger.info(
                f"元宝搜索插件初始化完成，使用密钥 {self._mask(secret_id)}"
            )
        else:
            logger.warning(
                "元宝搜索插件未配置 SecretId/SecretKey，搜索功能将不可用。"
            )

    @classmethod
    def get_shared_client(cls) -> YuanbaoSearchClient | None:
        return cls._shared_client

    @staticmethod
    def _mask(secret: str) -> str:
        """脱敏显示密钥，避免日志泄露完整凭据。"""
        if not secret or len(secret) < 8:
            return "***"
        return f"{secret[:4]}...{secret[-4:]}"

    async def terminate(self) -> None:
        YuanbaoSearchPlugin._shared_client = None
        logger.info("元宝搜索插件已停止。")

    @filter.llm_tool(name="yuanbao_search")
    async def yuanbao_search(
        self,
        event: AstrMessageEvent,
        query: str,
        mode: int = 0,
        site: str = "",
        cnt: int = 10,
        industry: str = "",
        freshness: str = "",
        full_content: bool = False,
        max_chars: int = 0,
    ) -> str:
        """使用腾讯元宝搜索进行实时联网搜索。适合查询最新事实、新闻、资讯、文档、资料检索和一般网页信息。当用户需要当前资料、网页信息、事实核验、产品信息或资料出处时优先调用本工具。

        Args:
            query(string): 必填。搜索关键词或自然语言问题。
            mode(int, optional): 返回结果类型。0 公开网页信源结果（默认），1 优质权威垂直信源结果，2 混合结果。
            site(string, optional): 指定网址搜索或过滤。指定搜索填单个域名如 zhihu.com；过滤用 exclude:域名1|域名2，最多五个域名。
            cnt(int, optional): 返回结果条数，可填 10、20、30、40、50，默认 10。
            industry(string, optional): 垂直领域搜索，可填 gov 政府、news 新闻、acad 学术、finance 财经。
            freshness(string, optional): 搜索时效范围，可填 d7 最近七天、m3 最近三月、y2 最近两年，或具体日期区间如 2026-08-20,2026-08-30。
            full_content(boolean, optional): 是否返回更详细的正文摘要。默认 false 返回标准摘要约 800 字；设为 true 返回动态摘要约 2000 字，含更完整的细节。摘要不够用时再开启。
            max_chars(int, optional): 单条结果的摘要字数上限，0 表示不限制（默认）。注意接口本身单条摘要上限约 2500 字，本参数只能做截断不能突破接口上限；需要更多内容时请提高 cnt 拿更多结果，或用更精确的关键词重新搜索。
        """
        _ = event
        query = str(query or "").strip()
        if not query:
            return "错误：query 不能为空。"

        client = self.get_shared_client()
        if client is None:
            return "错误：元宝搜索客户端未初始化，请重载插件。"

        try:
            return await client.search(
                query,
                mode=_normalize_mode(mode),
                site=_normalize_site(site),
                cnt=_clamp_cnt(cnt),
                industry=_normalize_industry(industry),
                freshness=_normalize_freshness(freshness),
                full_content=bool(full_content),
                max_chars_per_item=max(0, int(max_chars or 0)),
            )
        except YuanbaoSearchError as exc:
            return f"错误：{exc}"

    @filter.command(
        "元宝搜索",
        alias={"元宝", "yuanbao", "元宝搜"},
        desc="元宝搜索：腾讯生态实时联网搜索。",
    )
    async def search_command(
        self,
        event: AstrMessageEvent,
        query: GreedyStr,
    ) -> AsyncGenerator[MessageEventResult | None, None]:
        """元宝搜索：腾讯生态实时联网搜索。

        Args:
            event: 消息事件上下文。
            query: 搜索关键词，支持以 key=value 形式附加 mode/cnt/industry/freshness/site 参数。

        Yields:
            搜索结果文本或用法说明。
        """
        query = query.strip()
        if not query:
            yield event.plain_result(self._usage_text())
            return

        parts = query.split()
        action = parts[0].lower() if parts else ""

        if action in {"help", "帮助", "用法"}:
            yield event.plain_result(self._usage_text())
            return

        options: dict = {}
        keyword_parts: list[str] = []
        for token in parts[1:]:
            if token.startswith("mode="):
                options["mode"] = _normalize_mode(token[5:])
            elif token.startswith("cnt="):
                options["cnt"] = _clamp_cnt(token[4:])
            elif token.startswith("industry="):
                options["industry"] = _normalize_industry(token[9:])
            elif token.startswith("freshness="):
                options["freshness"] = _normalize_freshness(token[10:])
            elif token.startswith("site="):
                options["site"] = _normalize_site(token[5:])
            else:
                keyword_parts.append(token)

        keyword = " ".join(keyword_parts).strip() or query

        try:
            result = await self.client.search(
                keyword,
                mode=options.get("mode"),
                site=options.get("site", ""),
                cnt=options.get("cnt", 10),
                industry=options.get("industry", ""),
                freshness=options.get("freshness", ""),
            )
        except YuanbaoSearchError as exc:
            yield event.plain_result(f"元宝搜索失败：{exc}")
            return
        yield event.plain_result(result)

    def _usage_text(self) -> str:
        return """🔍 元宝搜索插件帮助
━━━━━━━━━━━━
🌸 核心指令：
• 元宝搜索 <关键词> - 搜索并返回带摘要的结果
• 元宝搜索 帮助 - 查看此菜单

💡 可选参数（跟在关键词后，顺序不限）：
• mode 0/1/2 - 网页信源/权威信源/混合
• cnt 10/20/30/40/50 - 结果条数，默认 10
• industry gov/news/acad/finance
  - 政府/新闻/学术/财经
• freshness d7/m3/y2 - 时效范围
  也可用 2026-08-20,2026-08-30
• site 域名 - 只搜指定站点
  如 site=zhihu.com
• site exclude:域名1|域名2 - 排除站点
  最多 5 个
• full_content true - 更详细摘要（约2500字）
• max_chars 数字 - 单条摘要字数上限，0 不限

📝 示例：
元宝搜索 崩坏星穹铁道 4.6 版本
元宝搜索 今日AI新闻 mode=2 cnt=20
  industry=news freshness=d7
元宝搜索 昔涟 剧情解析 site=zhihu.com
元宝搜索 编程教程 full_content=true

📌 其他别名：/元宝、/元宝搜、/yuanbao
"""
