"""飞书消息投递器。

主通道: OpenClaw Gateway (127.0.0.1:18790)
备用通道: 飞书开放平台直连 API
兜底: 本地归档（永不丢数据）
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from news_briefing.collector.models import Briefing

logger = logging.getLogger(__name__)

# OpenClaw Gateway 地址
DEFAULT_GATEWAY_URL = "http://127.0.0.1:18790"

# 飞书开放平台 API
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


@dataclass
class DeliveryResult:
    """投递结果。"""
    success: bool
    channel: str  # openclaw | feishu_direct | archive_only
    error: Optional[str] = None
    message_id: Optional[str] = None


async def _send_via_openclaw(
    card_json: dict,
    gateway_url: str = DEFAULT_GATEWAY_URL,
    timeout: float = 10.0,
) -> DeliveryResult:
    """通过 OpenClaw Gateway 发送飞书卡片消息。

    Args:
        card_json: 飞书卡片 JSON。
        gateway_url: Gateway 地址。
        timeout: 超时时间。

    Returns:
        DeliveryResult。
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # OpenClaw Gateway 的消息发送端点
            response = await client.post(
                f"{gateway_url}/api/messages/send",
                json={
                    "type": "feishu_card",
                    "content": card_json,
                },
            )
            response.raise_for_status()
            data = response.json()

            logger.info("飞书投递成功 (OpenClaw Gateway)")
            return DeliveryResult(
                success=True,
                channel="openclaw",
                message_id=data.get("message_id"),
            )

    except httpx.TimeoutException:
        logger.warning("OpenClaw Gateway 超时")
        return DeliveryResult(
            success=False, channel="openclaw", error="Timeout",
        )
    except httpx.ConnectError:
        logger.warning("OpenClaw Gateway 不可达")
        return DeliveryResult(
            success=False, channel="openclaw", error="Connection refused",
        )
    except Exception as e:
        logger.error(f"OpenClaw Gateway 投递异常: {e}")
        return DeliveryResult(
            success=False, channel="openclaw", error=str(e)[:200],
        )


async def _send_via_feishu_direct(
    card_json: dict,
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
    timeout: float = 10.0,
) -> DeliveryResult:
    """直连飞书开放平台发送卡片消息（备用通道）。

    Args:
        card_json: 飞书卡片 JSON。
        app_id: 飞书应用 ID。
        app_secret: 飞书应用 Secret。
        timeout: 超时时间。

    Returns:
        DeliveryResult。
    """
    import os

    if app_id is None:
        app_id = os.environ.get("FEISHU_APP_ID", "")
    if app_secret is None:
        app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        return DeliveryResult(
            success=False, channel="feishu_direct",
            error="Feishu credentials not configured",
        )

    try:
        # 获取 tenant_access_token
        async with httpx.AsyncClient(timeout=timeout) as client:
            token_resp = await client.post(
                f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            token = token_data.get("tenant_access_token")

            if not token:
                return DeliveryResult(
                    success=False, channel="feishu_direct",
                    error="Failed to get tenant_access_token",
                )

            # 发送消息（此处需要具体的 open_id/chat_id，占位实现）
            # 实际实现需要从用户配置中获取接收者 ID
            logger.info("飞书直连投递: 获取 token 成功，消息发送逻辑待实现")
            return DeliveryResult(
                success=False, channel="feishu_direct",
                error="Direct feishu send not fully implemented",
            )

    except Exception as e:
        logger.error(f"飞书直连投递异常: {e}")
        return DeliveryResult(
            success=False, channel="feishu_direct", error=str(e)[:200],
        )


async def deliver(
    briefing: Briefing,
    gateway_url: str = DEFAULT_GATEWAY_URL,
    max_retries: int = 3,
    backoff_seconds: list[int] = [60, 120, 240],
) -> DeliveryResult:
    """投递简报（含重试逻辑）。

    投递顺序: OpenClaw Gateway → 飞书直连 → 本地归档
    每次失败后指数退避重试。

    Args:
        briefing: 简报对象。
        gateway_url: OpenClaw Gateway 地址。
        max_retries: 最大重试次数。
        backoff_seconds: 退避等待时间（秒）。

    Returns:
        DeliveryResult。
    """
    # 确保有飞书卡片 JSON
    card_json = (
        json.loads(briefing.feishu_card_json)
        if briefing.feishu_card_json
        else {"header": {"title": {"tag": "plain_text", "content": briefing.title}}}
    )

    result: Optional[DeliveryResult] = None

    # 尝试 OpenClaw Gateway (含重试)
    for attempt in range(max_retries):
        result = await _send_via_openclaw(card_json, gateway_url)
        if result.success:
            return result

        if attempt < max_retries - 1:
            wait = backoff_seconds[attempt] if attempt < len(backoff_seconds) else 60
            logger.info(f"投递失败，{wait}s 后重试 ({attempt + 1}/{max_retries})")
            await asyncio.sleep(wait)
        else:
            logger.warning(f"OpenClaw Gateway 投递失败，已重试 {max_retries} 次")

    # 备用: 飞书直连
    logger.info("切换到飞书直连备用通道...")
    direct_result = await _send_via_feishu_direct(card_json)
    if direct_result.success:
        return direct_result

    logger.warning(f"飞书直连也失败: {direct_result.error}")

    # 兜底: 本地归档
    from news_briefing.deliverer.archive import save_to_archive
    try:
        path = save_to_archive(briefing)
        logger.info(f"已归档到本地: {path}")
    except Exception as e:
        logger.error(f"归档失败: {e}")

    return DeliveryResult(
        success=False,
        channel="archive_only",
        error=f"All delivery channels failed. OpenClaw: {result.error if result else 'N/A'}",
    )
