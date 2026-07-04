"""飞书消息投递器。

主通道: 飞书开放平台直连 API (已配置凭证)
兜底: 本地归档（永不丢数据）
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass

import httpx

from news_briefing.collector.models import Briefing

logger = logging.getLogger(__name__)

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

# 飞书凭证从 OpenClaw 共享配置或环境变量读取
# 禁止硬编码 — 所有密钥通过运行时注入


def _load_feishu_credentials() -> tuple[str, str, str]:
    """从 OpenClaw 配置或环境变量加载飞书凭证。

    优先级: 环境变量 > OpenClaw 配置文件

    Returns:
        (app_id, app_secret, receiver_open_id) 三元组。
    """
    import json
    from pathlib import Path

    # 1. 尝试环境变量
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    receiver_id = os.environ.get("FEISHU_RECEIVER_ID", "")

    if app_id and app_secret and receiver_id:
        return app_id, app_secret, receiver_id

    # 2. 从 OpenClaw 配置文件读取
    openclaw_config = Path.home() / ".openclaw" / "openclaw.json"
    try:
        if openclaw_config.exists():
            with open(openclaw_config) as f:
                cfg = json.load(f)

            # 读取飞书通道配置
            channels = cfg.get("channels", {})
            feishu_cfg = channels.get("feishu", {})
            if not app_id:
                app_id = feishu_cfg.get("appId", "")
            if not app_secret:
                app_secret = feishu_cfg.get("appSecret", "")

            # 读取接收者 ID（allowFrom 列表第一个）
            if not receiver_id:
                allow_from = feishu_cfg.get("allowFrom", [])
                if allow_from:
                    receiver_id = allow_from[0]
    except Exception:
        pass

    # 3. 从 credentials 文件读取
    if not receiver_id:
        cred_file = Path.home() / ".openclaw" / "credentials" / "feishu-default-allowFrom.json"
        try:
            if cred_file.exists():
                with open(cred_file) as f:
                    cred = json.load(f)
                    allow_list = cred.get("allowFrom", [])
                    if allow_list:
                        receiver_id = allow_list[0]
        except Exception:
            pass

    return app_id, app_secret, receiver_id


@dataclass
class DeliveryResult:
    """投递结果。"""
    success: bool
    channel: str
    error: str | None = None
    message_id: str | None = None


async def _get_tenant_token(
    app_id: str | None = None,
    app_secret: str | None = None,
    timeout: float = 10.0,
) -> str | None:
    """获取飞书 tenant_access_token。

    Returns:
        Token 字符串，失败返回 None。
    """
    if not app_id or not app_secret:
        app_id, app_secret, _ = _load_feishu_credentials()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("tenant_access_token")
            if token:
                logger.debug("飞书 tenant_access_token 获取成功")
                return token
            logger.error(f"飞书 token 响应异常: {data}")
            return None
    except Exception as e:
        logger.error(f"获取飞书 token 失败: {e}")
        return None


async def _send_card_to_user(
    card_json: dict,
    receiver_id: str | None = None,
    timeout: float = 10.0,
) -> DeliveryResult:
    """发送飞书卡片消息给指定用户。

    Args:
        card_json: 飞书卡片消息 JSON。
        receiver_id: 接收者 open_id。
        timeout: 超时时间。

    Returns:
        DeliveryResult。
    """
    if not receiver_id:
        _, _, receiver_id = _load_feishu_credentials()
    token = await _get_tenant_token()
    if not token:
        return DeliveryResult(
            success=False, channel="feishu_direct",
            error="无法获取 tenant_access_token",
        )

    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "receive_id": receiver_id,
            "msg_type": "interactive",
            "content": json.dumps(card_json, ensure_ascii=False),
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{FEISHU_API_BASE}/im/v1/messages",
                params={"receive_id_type": "open_id"},
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") == 0:
                msg_id = data.get("data", {}).get("message_id", "")
                logger.info(f"飞书卡片投递成功: {msg_id}")
                return DeliveryResult(
                    success=True, channel="feishu_direct", message_id=msg_id,
                )
            error = f"飞书API错误: code={data.get('code')}, msg={data.get('msg')}"
            logger.error(error)
            return DeliveryResult(
                success=False, channel="feishu_direct", error=error,
            )

    except Exception as e:
        logger.error(f"飞书投递异常: {e}")
        return DeliveryResult(
            success=False, channel="feishu_direct", error=str(e)[:200],
        )


async def _send_text_to_user(
    text: str,
    receiver_id: str | None = None,
    timeout: float = 10.0,
) -> DeliveryResult:
    if not receiver_id:
        _, _, receiver_id = _load_feishu_credentials()
    """发送飞书文本消息（用于降级/通知）。

    Args:
        text: 文本内容。
        receiver_id: 接收者 open_id。
        timeout: 超时时间。

    Returns:
        DeliveryResult。
    """
    if not receiver_id:
        _, _, receiver_id = _load_feishu_credentials()
    token = await _get_tenant_token()
    if not token:
        return DeliveryResult(
            success=False, channel="feishu_direct",
            error="无法获取 tenant_access_token",
        )

    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "receive_id": receiver_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{FEISHU_API_BASE}/im/v1/messages",
                params={"receive_id_type": "open_id"},
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") == 0:
                msg_id = data.get("data", {}).get("message_id", "")
                logger.info(f"飞书文本投递成功: {msg_id}")
                return DeliveryResult(
                    success=True, channel="feishu_direct", message_id=msg_id,
                )
            error = f"飞书API错误: code={data.get('code')}, msg={data.get('msg')}"
            logger.error(error)
            return DeliveryResult(
                success=False, channel="feishu_direct", error=error,
            )

    except Exception as e:
        logger.error(f"飞书文本投递异常: {e}")
        return DeliveryResult(
            success=False, channel="feishu_direct", error=str(e)[:200],
        )


async def deliver(
    briefing: Briefing,
    max_retries: int = 3,
    backoff_seconds: list[int] | None = None,
) -> DeliveryResult:
    """投递简报到飞书（含重试逻辑）。

    优先发送卡片消息，失败时降级为文本消息。

    Args:
        briefing: 简报对象。
        max_retries: 最大重试次数。
        backoff_seconds: 退避等待时间（秒）。

    Returns:
        DeliveryResult。
    """
    if backoff_seconds is None:
        backoff_seconds = [5, 15, 30]

    # 飞书卡片 JSON
    card_json = (
        json.loads(briefing.feishu_card_json)
        if briefing.feishu_card_json
        else None
    )

    # 尝试发送卡片消息（含重试）
    if card_json:
        for attempt in range(max_retries):
            result = await _send_card_to_user(card_json)
            if result.success:
                return result

            if attempt < max_retries - 1:
                wait = backoff_seconds[attempt] if attempt < len(backoff_seconds) else 30
                logger.info(f"投递失败，{wait}s 后重试 ({attempt + 1}/{max_retries})")
                await asyncio.sleep(wait)

        logger.warning(f"飞书卡片投递失败，已重试 {max_retries} 次")

    # 降级: 发送文本摘要
    summary = (
        f"📰 {briefing.title}\n"
        f"精选 {briefing.total_selected} 条新闻\n"
        f"采集: {briefing.total_raw} → 去重后: {briefing.total_after_dedup}\n\n"
    )
    for section in briefing.sections:
        if section.items:
            summary += f"{section.label} ({len(section.items)}条)\n"
    summary += "\n⚠️ 卡片渲染失败，以上为文本摘要。完整内容已归档。"

    text_result = await _send_text_to_user(summary)
    if text_result.success:
        return text_result

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
        error="All delivery channels failed",
    )
